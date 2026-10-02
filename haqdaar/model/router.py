"""haqdaar/model/router.py

Model router client for HAQDAAR v2.
Turns caller speech transcripts into facets, stamps, and turn decisions.
Enforces the 2-failure keypad-only circuit, 2.0s timeout, and Span Guard.
Never raises.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from haqdaar.contracts import tunables, vocab
from haqdaar.contracts.types import (
    Answer,
    Clarify,
    Meta,
    Repeat,
    Stamp,
    TurnResult,
    Unclear,
)
from haqdaar.model.client import GroqModelClient
from haqdaar.model.prompts.opener import build_opener_prompt
from haqdaar.model.prompts.system import SYSTEM_PROMPT
from haqdaar.model.prompts.turn import build_turn_prompt
from haqdaar.model.confirm import match_confirm
from haqdaar.model.span_guard import SpanGuard


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
    ) -> None:
        self.corpus = corpus
        self.client = client if client is not None else GroqModelClient(timeout=timeout)
        self._failures: int = 0

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

    def opener(self, transcript: str, lang: str = "en") -> list[Stamp] | Unclear:
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
            {"role": "user", "content": build_opener_prompt(transcript, lang=lang)},
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
        raw_stamps = raw_data.get("stamps", [])

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
    ) -> TurnResult:
        """Classify caller response to a question turn.

        Precedence: META > ANSWER > CLARIFY > REPEAT > UNCLEAR.
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

    def confirm(self, transcript: str, lang: Optional[str] = None) -> Optional[bool]:
        """T09: Model owns language. Classify confirmation utterance as True (accept), False (reject), or None (unclear)."""
        return match_confirm(transcript, lang=lang)

