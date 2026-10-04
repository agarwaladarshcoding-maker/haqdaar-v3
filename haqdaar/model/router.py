"""haqdaar/model/router.py

Model router client for HAQDAAR v2.
Turns caller speech transcripts into facets, stamps, and turn decisions.
Enforces the 2-failure keypad-only circuit, 2.0s timeout, and Span Guard.
Never raises.
"""
from __future__ import annotations

import time
from typing import Any, Optional, Sequence

from haqdaar.contracts import tunables, vocab
from haqdaar.contracts.types import (
    Answer,
    Clarify,
    Meta,
    Question,
    Repeat,
    Stamp,
    TurnResult,
    Unclear,
)
from haqdaar.data import answer_store
from haqdaar.model import answer as qa_answer
from haqdaar.model.client import GroqModelClient
from haqdaar.model.prompts.kinds import KINDS, english_note, sort_system
from haqdaar.model.prompts.opener import build_opener_prompt
from haqdaar.model.prompts.system import SYSTEM_PROMPT
from haqdaar.model.prompts.turn import build_turn_prompt
from haqdaar.model.confirm import match_confirm
from haqdaar.model.span_guard import SpanGuard
from haqdaar.model.translate import AnswerTranslator

# Share of QA_TIMEOUT_S the first answer call may use; the backup model gets what is left.
_ANSWER_FIRST_SHARE = 0.6


class Model:
    """Voice Model router client turning caller speech transcripts into facets.

    - Groq JSON output, temperature 0, 2 s timeout, never raises.
    - Failure accounting: 429 or any failure/timeout counts as a failure;
      2 failures -> keypad-only for the rest of the call.
    - Span guard: values are kept only if their words literally appear in the transcript.
    - One caller at a time, non-blocking socket loop.
    """

    def __init__(
        self,
        corpus: Any = None,
        client: Optional[GroqModelClient] = None,
        timeout: Optional[float] = None,
        translator: Any = None,
    ) -> None:
        self.corpus = corpus
        self.translator = translator
        self.client = client if client is not None else GroqModelClient(timeout=timeout)
        self._failures: int = 0
        self.last_blocked: Optional[dict[str, str]] = None  # the refusal of the last answer(): {"rule", "text"}

    @property
    def failures(self) -> int:
        """Expose current failure counter for Engine inspection."""
        return self._failures

    @property
    def keypad_only(self) -> bool:
        """Trigger keypad-only mode once 2 failures have occurred."""
        return self._failures >= tunables.MODEL_FAILURES_TO_KEYPAD

    def reset_failures(self) -> None:
        """Reset call-level failure counter (e.g. for new call)."""
        self._failures = 0

    def opener(self, transcript: str, lang: str = "en", english: bool = False) -> list[Stamp] | Unclear:
        """Parse opener transcript into demographic Stamps and Door A scheme requests.

        Exact alias match in code runs first if corpus is available.
        Any failure/timeout increments failures and returns Unclear.
        Stamps are filtered through SpanGuard before returning.
        Never raises.
        """
        if not transcript or not transcript.strip():
            return []

        # If call is already degraded to keypad-only, skip network
        if self.keypad_only:
            return Unclear(reason="keypad_only")

        stamps: list[Stamp] = []

        # 1. Exact alias match in code before model (Door A happy path)
        # Note: alias fast-path stamps bypass SpanGuard by design as they match verified corpus aliases directly.
        if self.corpus is not None and hasattr(self.corpus, "alias_lookup"):
            matched_slugs = self.corpus.alias_lookup(transcript, lang)
            for slug in matched_slugs:
                stamps.append(Stamp(box="scheme", value=slug, span=transcript))

        # 2. Call Groq model for demographic facets and additional stamps
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_opener_prompt(transcript, lang=lang, english=english)},
        ]

        try:
            resp = self.client.call(messages, task="model_opener")
        except Exception as e:
            self._failures += 1
            return Unclear(reason=f"client_exception: {e}")

        if not resp.success:
            self._failures += 1
            err_reason = "timeout" if resp.is_timeout else (resp.error or "model_failure")
            return Unclear(reason=err_reason)

        raw_data = resp.data or {}
        cls_name = str(raw_data.get("class", "")).upper().strip()
        raw_stamps = [] if cls_name == "UNCLEAR" else raw_data.get("stamps", [])
        if not raw_stamps and not stamps:
            # UNCLEAR is not a failure (T11): one fixed reason, whatever words the model sent.
            # Alias stamps found in step 1 are kept even when the model adds nothing.
            return Unclear(reason="unclear")

        # Parse raw stamps into typed Stamp objects
        candidate_stamps: list[Stamp] = []
        for item in raw_stamps:
            if not isinstance(item, dict):
                continue
            box = str(item.get("box", "")).strip()
            val = item.get("value")
            span = str(item.get("span", "")).strip()
            if box and val is not None and span:
                candidate_stamps.append(Stamp(box=box, value=val, span=span))

        # 3. Apply SpanGuard and closed-set validation
        allowed_values = None
        if self.corpus is not None and hasattr(self.corpus, "values"):
            try:
                allowed_values = {b: self.corpus.values(b) for b in vocab.KEYPAD_LISTS.keys()}
            except Exception:
                allowed_values = None

        validated = SpanGuard.filter_stamps(
            transcript,
            candidate_stamps,
            allowed_values=allowed_values,
        )

        # Merge alias stamps + model stamps (avoid duplicates)
        existing_boxes = {s.box for s in stamps}
        for s in validated:
            if s.box not in existing_boxes:
                stamps.append(s)
                existing_boxes.add(s.box)

        return stamps

    def turn(
        self,
        transcript: str,
        box: str,
        window: Sequence[str] | None = None,
        ask_count: int = 0,
        english: bool = False,
        lang: str = "",
    ) -> TurnResult:
        """Classify caller response to a question turn.

        Precedence: META > ANSWER > CLARIFY > REPEAT > UNCLEAR.
        With QA_ENABLED the model sorts the words into a kind instead (ANSWER, BOTH, QUESTION,
        REPEAT, OTHER); OTHER, a missing kind and bad JSON are all Unclear.
        Never raises.
        """
        if not transcript or not transcript.strip():
            return Unclear(reason="empty_transcript")

        # If call is already degraded to keypad-only, skip network
        if self.keypad_only:
            return Unclear(reason="keypad_only")

        # Determine valid values for this box
        values: Sequence[str] = ()
        if self.corpus is not None and hasattr(self.corpus, "values"):
            try:
                values = self.corpus.values(box)
            except Exception:
                values = ()
        if not values and box in vocab.KEYPAD_LISTS:
            values = vocab.KEYPAD_LISTS[box]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_turn_prompt(
                    transcript=transcript,
                    box=box,
                    values=values,
                    window=window,
                    ask_count=ask_count,
                    qa=tunables.QA_ENABLED,
                    english=english,
                    lang=lang,
                ),
            },
        ]

        try:
            resp = self.client.call(messages, task="model_turn")
        except Exception as e:
            self._failures += 1
            return Unclear(reason=f"client_exception: {e}")

        if not resp.success:
            self._failures += 1
            err_reason = "timeout" if resp.is_timeout else (resp.error or "model_failure")
            return Unclear(reason=err_reason)

        data = resp.data or {}
        if tunables.QA_ENABLED:
            return self._kind_result(transcript, box, data)
        cls_name = str(data.get("class", "UNCLEAR")).upper().strip()

        # 1. META
        if cls_name == "META":
            cmd = str(data.get("command", "")).strip()
            return Meta(command=cmd)

        # 2. ANSWER
        if cls_name == "ANSWER":
            ans_box = str(data.get("box", box)).strip()
            ans_val = data.get("value")
            ans_span = str(data.get("span", "")).strip()

            if ans_box and ans_val is not None and ans_span:
                candidate = Stamp(box=ans_box, value=ans_val, span=ans_span)
                if SpanGuard.validate_stamp(transcript, candidate):
                    return Answer(box=ans_box, value=ans_val, span=ans_span)

            # Span drop or invalid closed-set value falls back to Unclear
            drop_reason = (
                "span_drop"
                if not SpanGuard.validate_span(transcript, ans_span)
                else "invalid_value"
            )
            return Unclear(reason=drop_reason)

        # 3. CLARIFY
        if cls_name == "CLARIFY":
            return Clarify(box=box)

        # 4. REPEAT
        if cls_name == "REPEAT":
            return Repeat()

        # 5. UNCLEAR (default)
        return Unclear(reason=str(data.get("reason", "unclear")))

    def _kind_result(self, transcript: str, box: str, data: dict) -> TurnResult:
        """Map a kind reply (QA_ENABLED) to a turn result. Values still pass the span guard."""
        kind = str(data.get("kind", "")).upper().strip()
        if kind in ("ANSWER", "BOTH"):
            ans_box = str(data.get("box", box)).strip()
            ans_val = data.get("value")
            ans_span = str(data.get("span", "")).strip()
            if ans_box and ans_val is not None and ans_span:
                candidate = Stamp(box=ans_box, value=ans_val, span=ans_span)
                if SpanGuard.validate_stamp(transcript, candidate):
                    return Answer(box=ans_box, value=ans_val, span=ans_span, also_question=(kind == "BOTH"))
            drop_reason = "span_drop" if not SpanGuard.validate_span(transcript, ans_span) else "invalid_value"
            return Unclear(reason=drop_reason)
        if kind == "QUESTION":
            return Question()
        if kind == "REPEAT":
            return Repeat()
        return Unclear(reason="unclear")

    def sort(self, asked: str, transcript: str, english: bool = False, lang: str = "") -> str:
        """Sort caller words into ANSWER, BOTH, QUESTION, REPEAT or OTHER for the places that have
        no turn call of their own (anything-else, section menu). Any failure gives "OTHER".
        Does not count toward failures: a missed sort just means today's path."""
        if not transcript or not transcript.strip() or self.keypad_only:
            return "OTHER"
        user = (english_note(lang) if english else "") + transcript
        messages = [
            {"role": "system", "content": sort_system(asked)},
            {"role": "user", "content": user},
        ]
        try:
            resp = self.client.call(messages, task="model_sort")
            if not resp.success:
                return "OTHER"
            kind = str((resp.data or {}).get("kind", "")).upper().strip()
        except Exception:
            return "OTHER"
        return kind if kind in KINDS else "OTHER"

    def answer(
        self,
        question: str,
        lang: str,
        cards: str | list[str],
        profile: dict | None = None,
        scheme_ids: list[str] | None = None,
        english: bool = False,
    ) -> str | None:
        """Answer a caller's question from the scheme text in `cards`, or None for "no safe answer".

        `english` says `question` is an English translation; with ENGLISH_PIPE on, `cards` must then
        be the English cards. The text is written in English, checked, and translated to `lang`.
        Never raises. Does not count toward failures. Writes one questions.jsonl line.
        """
        t0 = time.monotonic()
        self.last_blocked = None
        if not isinstance(cards, str):  # the engine hands over one text per scheme
            cards = "\n\n".join(c for c in cards if c)
        question = qa_answer.mask_digits(question or "")
        piped = tunables.ENGLISH_PIPE and english and lang != "en"
        write_lang = "en" if (tunables.ENGLISH_PIPE and english) else lang
        raw: Optional[str] = None
        final: Optional[str] = None
        blocked: Optional[str] = None
        # Saved answers (7.3): the key holds the snapshot id, so a new snapshot never serves an old one.
        snap = getattr(self.corpus, "snapshot_id", None)
        key = answer_store.make_key(snap, lang, scheme_ids, question) if isinstance(snap, str) and scheme_ids else None
        saved = answer_store.get(key) if key else None
        if saved:
            qa_answer.write_question_line(
                lang=lang, question=question, scheme_ids=scheme_ids or [], answer=saved, blocked_by=None,
                seconds=round(time.monotonic() - t0, 2), saved=True,
            )
            return saved
        try:
            raw, blocked = self._ask_answer(question, write_lang, cards, profile)
            if blocked is None:
                raw = qa_answer.shorten(raw)
                blocked = qa_answer.check_answer(raw, write_lang, cards)
            if blocked is None:
                final = raw
                if piped:
                    final, blocked = self._translate_checked(raw, lang)
        except Exception:
            final, blocked = None, "model_null"
        if key and final and blocked is None:
            answer_store.put(key, final)
        if blocked is not None:
            self.last_blocked = {"rule": blocked, "text": raw or ""}
        qa_answer.write_question_line(
            lang=lang,
            question=question,
            scheme_ids=scheme_ids or [],
            answer=final,
            blocked_by=blocked,
            seconds=round(time.monotonic() - t0, 2),
            question_en=question if tunables.ENGLISH_PIPE and english else None,
            answer_en=raw if tunables.ENGLISH_PIPE and english else None,
            raw_answer=raw,
        )
        return final

    def _ask_answer(
        self, question: str, write_lang: str, cards: str, profile: dict | None
    ) -> tuple[Optional[str], Optional[str]]:
        """The model call with one try on the backup model, inside QA_TIMEOUT_S in all.
        Returns (text, None) or (None, blocked_by)."""
        if not cards or not cards.strip() or not question.strip():
            return None, "model_null"
        messages = [
            {"role": "system", "content": qa_answer.build_system(write_lang, cards, profile)},
            {"role": "user", "content": question},
        ]
        total = tunables.QA_TIMEOUT_S
        t0 = time.monotonic()
        timed_out = False
        for model, budget in ((None, total * _ANSWER_FIRST_SHARE), (tunables.QA_BACKUP_MODEL, None)):
            remaining = total - (time.monotonic() - t0)
            if remaining < 0.3:
                break
            kwargs: dict[str, Any] = {"timeout": remaining if budget is None else budget}
            if model:
                kwargs["model"] = model
            try:
                resp = self.client.call(messages, task="qa_answer", **kwargs)
            except Exception:
                continue
            if not resp.success:
                timed_out = timed_out or resp.is_timeout
                continue
            text = (resp.data or {}).get("answer")
            if not isinstance(text, str) or not text.strip() or text.strip() == "NOT_IN_TEXT":
                return None, "model_null"
            return text.strip(), None
        return None, "timeout" if timed_out else "model_error"

    def _translate_checked(self, english_text: str, lang: str) -> tuple[Optional[str], Optional[str]]:
        """English answer -> the caller's language, with the code checks run again on the result."""
        if self.translator is None:
            self.translator = AnswerTranslator()
        out = self.translator.translate(english_text, lang)
        if not out:
            return None, "translate"
        if qa_answer.digits_of(out) != qa_answer.digits_of(english_text):
            return None, "translate"
        if vocab.find_forbidden(out, lang) or vocab.find_verdict(out, lang):
            return None, "translate"
        return out, None

    def confirm(self, transcript: str, lang: Optional[str] = None, english: bool = False) -> Optional[bool]:
        """T09: Model owns language. Classify confirmation utterance as True (accept), False (reject), or None (unclear)."""
        return match_confirm(transcript, lang=lang, english=english)

