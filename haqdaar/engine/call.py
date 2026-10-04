"""haqdaar/engine/call.py

Call loop orchestrator for Haqdaar v2 (T11, T14, T16, T17, T18, T24, Architecture §4 & §8).
Coordinates single-caller conversation: Turn 0 -> Consent -> Questions -> Terminal
-> Read-back menu -> Anything else -> Closing farewell.

Hard rules:
- Imports only contracts/, engine/, and data/log.py.
- Imports no audio, no model, no data/pipeline/.
- Zero concurrency primitives: synchronous single-process execution.
- All numbers live in contracts/tunables.py, never inline.
- Output order from Terminals is never reordered.
"""
from __future__ import annotations

import re
import time
from typing import Any, Mapping, Optional

from haqdaar.contracts import tunables, vocab
from haqdaar.contracts.log_schema import (
    STOP_LE_4_SURVIVORS,
    STOP_MAX_QUESTIONS,
    STOP_MAX_TURNS,
    STOP_NO_SPLIT,
    STOP_REASONS,
    STOP_ZERO_SURVIVORS,
    DeliveryRecord,
    LangSwitchRecord,
    TurnLogRecord,
)
from haqdaar.contracts.types import (
    Ask,
    Digit,
    Hangup,
    Noise,
    Question,
    SEVEN_BOXES,
    Silence,
    Speech,
    Stop,
    UNASKED,
    Unclear,
    UNKNOWN,
    Widen,
    WIDENING_ORDER,
)
from haqdaar.data import log_text
from haqdaar.data.log import Log
from haqdaar.engine.door_a import DoorA, unmatched_content
from haqdaar.engine.filter import Filter
from haqdaar.engine.planner import Planner
from haqdaar.engine.terminals import (
    DELIVERY_DIRECT_MATCH,
    DELIVERY_EMPTY,
    DELIVERY_NEAREST,
    DELIVERY_OVERFLOW,
    DELIVERY_WIDENED_MATCH,
    RESULTS_MORE_PROMPT,
    SECTION_MENU,
    SECTION_SOURCE_FRAME,
    Terminals,
    mark_end,
    mark_name,
    scheme_name_chunk,
    scheme_summary_chunk,
)

def _next_lang(curr_lang: str) -> str:
    """Rotate hi -> mr -> en -> hi (D13's `*` cycle). Shared by the question phase
    and the read-back menu so both keypads use the same rotation."""
    offered = tunables.LANGS_OFFERED  # a paused language is skipped
    return offered[(offered.index(curr_lang) + 1) % len(offered)] if curr_lang in offered else offered[0]


LANG_EN = {"hi": "Hindi", "mr": "Marathi", "en": "English"}


def _log_key(log: Log, digit: Any, means: str) -> None:
    """One readable row for a key the engine judged: what the key meant here, in English.
    Log.write never raises; the guard is for the means being made."""
    try:
        log.write({"ev": "key", "key": str(digit), "means": means})
    except Exception:
        pass


def _answer_means(log: Log, corpus: Any, box: str, digit: str) -> str:
    """Meaning of a key on a question box: the value it picks, or off the menu."""
    try:
        if digit == "#":
            return "repeat"
        if digit == "*":
            return "change language"
        if digit == "0":
            return "do not know"
        vals = corpus.values(box)
        n = int(digit) if digit.isdigit() else -1
        if 1 <= n <= len(vals) and n <= tunables.KEYPAD_CARDINALITY_MAX:
            val = vals[n - 1]
            label = log_text.lookup(log.snapshot_id)(f"chip_{box}_{val}", "en") or vocab.LABELS.get(val, {}).get("en") or str(val)
            return f"{box} = {label}"
    except Exception:
        pass
    return "not on the menu"


class _LoggedAudio:
    """The audio the engine talks to, with a readable log row for what is said and what cuts in.

    Every attribute passes straight through, get and set, so hasattr() answers as it does on the
    real audio and the caller hears exactly the same. Only say, say_text, next_input and
    select_language are watched: after the real call returns, one `said` or `cut` row is written.
    A failure in the row is dropped; it must never reach the call.
    """

    def __init__(self, audio: Any, log: Log, corpus: Any) -> None:
        object.__setattr__(self, "_real", audio)
        object.__setattr__(self, "_log", log)
        object.__setattr__(self, "_corpus", corpus)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._real, name, value)

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._real, name)  # raises AttributeError exactly when the real audio would
        if name == "say":
            return lambda sequence, *a, **k: self._said(attr(sequence, *a, **k), tuple(sequence))
        if name == "say_text":
            return lambda text, *a, **k: self._said_text(attr(text, *a, **k), text)
        if name in ("next_input", "select_language"):
            return lambda *a, **k: self._cut(attr(*a, **k))
        return attr

    def _said(self, result: Any, tokens: tuple[str, ...]) -> Any:
        try:
            spoken = [t for t in tokens if not t.startswith(("name:", "end:"))]
            if spoken:
                find = log_text.lookup(self._log.snapshot_id)
                lang = getattr(self._real, "language", "hi")
                self._log.write({
                    "ev": "said", "tokens": spoken,
                    "text": log_text.said_words(spoken, lang, find, self._corpus),
                    "en": log_text.said_words(spoken, "en", find, self._corpus),
                })
        except Exception:
            pass
        return result

    def _said_text(self, result: Any, text: str) -> Any:
        if result is not False:  # False: nothing was said
            try:
                self._log.write({"ev": "said", "tokens": ["answer"], "text": text, "en": ""})
            except Exception:
                pass
        return result

    def _cut(self, inp: Any) -> Any:
        try:
            if isinstance(inp, (Speech, Digit)) and inp.heard_ms >= 0 and inp.cut_clip:
                self._log.write({
                    "ev": "cut", "by": "key" if isinstance(inp, Digit) else "speech",
                    "clip": inp.cut_clip, "heard_ms": inp.heard_ms,
                    "en": log_text.lookup(self._log.snapshot_id)(inp.cut_clip, "en"),
                })
        except Exception:
            pass
        return inp


def _newer_words(audio: Any, old_text: str) -> bool:
    """7.5: True if the caller spoke again while the engine was working on `old_text`.

    The words are then kept by the audio and the next wait gives them, so what was made from
    the older words must be dropped, never said. Costs nothing: it only reads the queued line.
    """
    if not (hasattr(audio, "newer_words") and audio.newer_words()):
        return False
    trace = getattr(audio, "trace", None)
    if trace is not None and hasattr(trace, "input_event"):
        trace.input_event(prompt_n=-1, prompt="", event="speech", value=old_text, took=False, why="newer_words")
    return True


def _door_a_read(audio: Any, log: Log, slug: str, transcript: str, span: str,
                 turn_n: int, candidate_count: int, t0: float) -> None:
    """Door A read-back (T12/ARCH §6): name + summary, exempt from echo-confirm.

    Token pattern mirrors Terminals.direct_match (name mark, name chunk, summary
    chunk, end mark). t_name/t_end are monotonic-clock proxies for the provider
    marks (utterance end → first word of name / last word of summary); the bar
    is judged on t_name. The scheme lives in this LOG record only — never in
    box_vector, whose keys all enter the filter table (T12: the pseudo-box
    never enters the filter table, never gets a mask).
    """
    if hasattr(audio, "on_mark"):
        audio.on_mark(f"door_a_name:{slug}")
    t_name = time.monotonic() - t0
    audio.say((mark_name(slug), scheme_name_chunk(slug), scheme_summary_chunk(slug),
               mark_end(slug)))
    t_end = time.monotonic() - t0
    log.write(TurnLogRecord(
        turn_n=turn_n,
        turn_class="ANSWER",
        box="scheme",
        value=slug,
        transcript=transcript,
        span=span,
        t_name=t_name,
        t_end=t_end,
        candidate_count=candidate_count,
    ))


# The silence ladder ends the call on the second silent wait in a row (Silence.n counts them
# across every wait; any key, word or noise resets it, so one counter serves the whole call).
# Each wait is long (SILENCE_REMIND_S, then the rest up to SILENCE_HANGUP_S), so two is the whole ladder.
SILENCE_HANGUP_RUNG = 2


def _answer_silence(
    audio: Any, log: Log, rung: int, turn_n: int, prompt: tuple[str, ...], *, say_reply: bool = True,
) -> bool:
    """The one answer to silence at every wait (7.3): never a silent default, never dead air.

    True: the caller was told "we are waiting" and the live `prompt` was said again, so wait again.
    False: the ladder is spent; the farewell is said and the caller hangs up and closes the log.
    A silence spends no turn. `prompt` is empty where the loop says its own prompt next.
    `say_reply` is False at turn 0: no language is picked yet, so the "waiting" line would come
    out in Hindi; the trilingual greeting is the re-prompt and the loop plays it again.
    """
    log.write(TurnLogRecord(turn_n=turn_n, turn_class="SILENCE", silence_n=rung))
    if rung >= SILENCE_HANGUP_RUNG:
        audio.say(("closing_farewell",))
        if hasattr(audio, "on_mark"):
            audio.on_mark("closing_farewell")
        return False
    if say_reply:
        audio.say(("waiting_for_reply",) + prompt)
    return True


def _door_a_pick(audio: Any, log: Log, turn_n: int, s1: str, s2: str) -> str | None:
    """Door A 2-candidate keypad turn (T12): name both, press 1/2/3.

    Returns "1"/"2" (picked), "hangup", or None (0/3/anything else declines).
    One turn, no repeats; silence asks again until the ladder ends the call.
    """
    prompt = ("door_a_option_1", scheme_name_chunk(s1),
              "door_a_option_2", scheme_name_chunk(s2),
              "door_a_option_none")
    audio.say(prompt)
    while True:
        pick = audio.next_input(profile="normal")
        if isinstance(pick, Silence):
            if _answer_silence(audio, log, pick.n, turn_n, prompt):
                continue
            return "hangup"
        break
    if isinstance(pick, Hangup):
        return "hangup"
    if isinstance(pick, Digit):
        _log_key(log, pick.digit, {"1": "first scheme", "2": "second scheme"}.get(pick.digit, "none of these"))
    if isinstance(pick, Digit) and pick.digit in ("1", "2"):
        return pick.digit
    return None


class Engine:
    """Stateful orchestrator for a single phone call."""
    current_scheme: str | None = None


    @staticmethod
    def _handle_digit_input(
        audio: Any,
        log: Log,
        corpus: Any,
        box: str,
        digit_inp: Digit,
        box_vector: dict[str, Any],
        box_strikes: dict[str, int],
        turn_n: int,
        question_count: int,
        mode: str,
        is_box_keypad: bool,
    ) -> tuple[int, int, str | None, str]:
        """Process a DTMF digit input for the current question box.

        Returns (turn_n, question_count, stop_reason, action) where action is
        'continue' (to re-ask/loop) or 'break' (to proceed to next question).
        """
        digit = digit_inp.digit
        _log_key(log, digit, _answer_means(log, corpus, box, digit))

        # Control keys
        if digit == "#":
            if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                audio.trace.input_event(
                    prompt_n=getattr(digit_inp, "prompt_n", -1),
                    prompt=box,
                    event="key",
                    value="#",
                    took=True,
                    why="ok",
                )
            # No audio.repeat() here: the question loop says the prompt again on its next pass.
            # Both together said it twice in a row (and after `*`, once in the old language).
            return turn_n, question_count, None, "continue"

        elif digit == "*":
            curr_lang = getattr(audio, "language", "hi")
            new_lang = _next_lang(curr_lang)
            if hasattr(audio, "language"):
                audio.language = new_lang
            log.write(LangSwitchRecord(
                lang=new_lang,
                lang_source="keypad",
                turn_n=turn_n,
            ))
            if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                audio.trace.input_event(
                    prompt_n=getattr(digit_inp, "prompt_n", -1),
                    prompt=box,
                    event="key",
                    value="*",
                    took=True,
                    why="ok",
                )
            # No audio.repeat() here: the question loop says the prompt again on its next pass.
            # Both together said it twice in a row (and after `*`, once in the old language).
            return turn_n, question_count, None, "continue"

        elif digit == "0":
            # D7/F8: 0 always means "don't know", on any box. It is a
            # real answer (UNKNOWN, declined), not a miss: no strike,
            # no repeat.
            turn_n += 1
            box_vector[box] = UNKNOWN
            box_strikes[box] = 0
            question_count += 1
            log.write(TurnLogRecord(
                turn_n=turn_n,
                turn_class="ANSWER",
                box=box,
                value=UNKNOWN,
                unknown_source="declined",
                transcript="0",
                span="0",
            ))
            if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                audio.trace.input_event(
                    prompt_n=getattr(digit_inp, "prompt_n", -1),
                    prompt=box,
                    event="key",
                    value="0",
                    took=True,
                    why="ok",
                )
            stop_reason = None
            if turn_n >= tunables.MAX_TURNS:
                stop_reason = STOP_MAX_TURNS
            elif question_count >= tunables.MAX_QUESTIONS:
                stop_reason = STOP_MAX_QUESTIONS
            return turn_n, question_count, stop_reason, "continue"

        # Keypad answer: 1-9
        turn_n += 1
        vals = corpus.values(box)
        d_int = -1
        try:
            d_int = int(digit)
        except ValueError:
            d_int = -1

        if 1 <= d_int <= len(vals) and d_int <= tunables.KEYPAD_CARDINALITY_MAX:
            val = vals[d_int - 1]
            box_vector[box] = val
            box_strikes[box] = 0
            question_count += 1
            log.write(TurnLogRecord(
                turn_n=turn_n,
                turn_class="ANSWER",
                box=box,
                value=val,
                transcript=str(digit),
                span=str(digit),
            ))
            if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                audio.trace.input_event(
                    prompt_n=getattr(digit_inp, "prompt_n", -1),
                    prompt=box,
                    event="key",
                    value=str(digit),
                    took=True,
                    why="ok",
                )
            stop_reason = None
            if turn_n >= tunables.MAX_TURNS:
                stop_reason = STOP_MAX_TURNS
            elif question_count >= tunables.MAX_QUESTIONS:
                stop_reason = STOP_MAX_QUESTIONS
            return turn_n, question_count, stop_reason, "break"
        else:
            # Out of menu digit (G6: "wrong key" line then repeat)
            box_strikes[box] += 1
            log.write(TurnLogRecord(
                turn_n=turn_n,
                turn_class="UNCLEAR",
                transcript=str(digit),
            ))
            if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                audio.trace.input_event(
                    prompt_n=getattr(digit_inp, "prompt_n", -1),
                    prompt=box,
                    event="key",
                    value=str(digit),
                    took=False,
                    why="not_on_menu",
                )
            if (
                getattr(audio, "keypad_only", False)
                or getattr(getattr(audio, "turn", None), "keypad_only", False)
            ):
                mode = "keypad_only"
                log.write({"mode": "keypad_only"})
                audio.say(("keypad_only_mode",))
            if box_strikes[box] >= tunables.UNCLEAR_TRIES:
                if mode == "keypad_only" or is_box_keypad:
                    box_vector[box] = UNKNOWN
                    question_count += 1
                    log.write(TurnLogRecord(
                        turn_n=turn_n,
                        turn_class="ANSWER",
                        box=box,
                        value=UNKNOWN,
                        unknown_source="keypad_dropped",
                    ))
            else:
                # The loop asks the question again; repeat() here would say this line twice.
                audio.say(("unclear_prompt",))

            stop_reason = None
            if turn_n >= tunables.MAX_TURNS:
                stop_reason = STOP_MAX_TURNS
            elif question_count >= tunables.MAX_QUESTIONS:
                stop_reason = STOP_MAX_QUESTIONS
            return turn_n, question_count, stop_reason, "continue"

    @staticmethod
    def _try_question(
        audio: Any,
        model: Any,
        corpus: Any,
        log: Log,
        qa: dict[str, Any],
        inp: Any,
        mode: str,
        turn_n: int,
        box_vector: Optional[dict[str, Any]] = None,
        scheme_ids: Optional[list[str]] = None,
        asked: Optional[str] = None,
    ) -> bool:
        """7.1: answer a caller's question in text and say it. True only if it was said.

        False means "not handled", and the caller then does exactly what it did
        before this existed. `asked` names a prompt that has no router call of
        its own (anything-else, section menu): the question is then sorted here
        by model.sort. `turn_n` is logged as is: a question never moves the call.
        """
        if not (
            tunables.QA_ENABLED
            and hasattr(model, "answer")
            and hasattr(audio, "say_text")
            and qa["n"] < tunables.QA_MAX_PER_CALL
            and mode != "keypad_only"
            and not getattr(model, "keypad_only", False)
            and not getattr(audio, "keypad_only", False)
            and not getattr(getattr(audio, "turn", None), "keypad_only", False)
        ):
            return False
        text = str(getattr(inp, "text", "") or "").strip()
        if not text:
            return False
        english = bool(getattr(inp, "english", False))
        filler = False
        try:
            if asked is not None:
                if not hasattr(model, "sort") or model.sort(asked, text) not in ("QUESTION", "BOTH"):
                    return False
            lang = "en" if english else getattr(audio, "language", "hi")
            ids = scheme_ids
            door = DoorA.from_corpus(corpus).match(text, lang=lang)
            if door.action == "read":
                ids = [door.scheme_ids[0]]  # a scheme named in the question always wins (E2)
            elif getattr(Engine, "current_scheme", None) is not None:
                ids = [Engine.current_scheme]  # 7.2: answer "this scheme" questions from current-scheme
            elif ids is None:
                bv = box_vector or {}
                survs = Filter.survivors(bv, corpus)
                if len(survs) > tunables.QA_MAX_SCHEMES and not tunables.QA_SEARCH:
                    return False
                ids = [corpus.scheme_id(s) for s in survs if Filter.speakable(s, bv, corpus)]
            if "texts" not in qa:
                from haqdaar.data.scheme_text import SchemeText  # lazy: only a QA call needs it
                qa["texts"] = SchemeText.load(corpus.snapshot_id)
            if scheme_ids is None and len(ids or ()) > tunables.QA_MAX_SCHEMES:
                # 7.3 search: too many left and none named, so pick by word overlap with each card.
                from haqdaar.data.scheme_search import find_schemes
                ids = find_schemes(text, {sid: qa["texts"].card(sid, lang) for sid in ids}, tunables.QA_MAX_SCHEMES)
            if not ids or len(ids) > tunables.QA_MAX_SCHEMES:
                return False
            cards = [qa["texts"].card(sid, lang) for sid in ids]
            kwargs: dict[str, Any] = {"profile": {
                b: v for b, v in (box_vector or {}).items() if v not in (None, UNASKED, UNKNOWN)
            }, "scheme_ids": list(ids)}
            if english:
                kwargs["english"] = True
            if _newer_words(audio, text):
                return True  # 7.5: no filler, no paid call for words that are already old
            audio.say(("one_moment",))  # 7.4: once per question, not per retry; it plays while the model works
            filler = True
            import importlib  # lazy: nothing heavy at the top of this file
            write_fn = getattr(importlib.import_module("haqdaar.model.answer"), "write_question_line", None)
            answer = None
            for attempt in (1, 2):  # only a failed or empty answer is asked again (the model call is paid)
                try:
                    answer = model.answer(text, getattr(audio, "language", "hi"), cards, **kwargs)
                except Exception as e:
                    if write_fn:
                        write_fn(
                            lang=getattr(audio, "language", "hi"),
                            question=text,
                            scheme_ids=list(ids),
                            answer=None,
                            blocked_by=f"exception: {type(e).__name__}",  # class only: the text can hold caller words
                            attempt=attempt,
                        )
                    answer = None
                else:
                    if write_fn and not hasattr(model, "_ask_answer"):
                        write_fn(
                            lang=getattr(audio, "language", "hi"),
                            question=text,
                            scheme_ids=list(ids),
                            answer=answer,
                            blocked_by=None if answer else "model_null",
                            attempt=attempt,
                        )
                    blocked = None if answer else getattr(model, "last_blocked", None)
                    if isinstance(blocked, dict):  # the router kept why it refused; numbers masked like the QUESTION row
                        log.write({
                            "ev": "blocked", "rule": str(blocked.get("rule", "")),
                            "question": re.sub(r"\d{8,}", "\u2026", text),
                            "text": re.sub(r"\d{8,}", "\u2026", str(blocked.get("text", ""))),
                        })
                if answer:
                    break
            if _newer_words(audio, text):
                return True  # 7.5: the answer is for old words; it is never said
            if not answer:
                return False
            if audio.say_text(answer) is False:
                if _newer_words(audio, text):
                    return True  # say_text gave up for the same reason
                if audio.say_text(answer) is False:
                    return False  # speaking is tried twice with the answer in hand, never a second model call
        except Exception:
            return False  # a question must never take the call down
        finally:
            # say_text cuts the filler itself just before the answer plays (no gap). Every other
            # way out cuts it here, so the line that follows is not queued behind it.
            if filler and hasattr(audio, "stop_filler"):
                audio.stop_filler()
        qa["n"] += 1
        log.write(TurnLogRecord(
            turn_n=turn_n,
            turn_class="QUESTION",
            transcript=re.sub(r"\d{8,}", "\u2026", text),  # callers read out Aadhaar and phone numbers
            answer=answer,
        ))
        return True

    @staticmethod
    def _heard_sections(audio: Any, sid: str, sections: list[str]) -> list[str]:
        """The terminal queues every name+summary in one go, so "summary" is seeded
        for all of them. On a real phone it counts only if that clip played to its
        end; a hangup or key press before it must not be logged as heard."""
        if hasattr(audio, "heard") and not audio.heard(scheme_summary_chunk(sid)):
            return [x for x in sections if x != "summary"]
        return sections

    @staticmethod
    def run_call(
        audio: Any,
        model: Any,
        corpus: Any,
        log: Log,
    ) -> None:
        """Run a single call from connect to hangup."""
        audio = _LoggedAudio(audio, log, corpus)
        Engine.current_scheme = None
        if hasattr(audio, "current_scheme"):
            audio.current_scheme = None
        # --- 1. Turn 0: Language Selection ---
        # No language is picked for the caller: silence asks again (the greeting is the
        # prompt, and the audio says it on each pass); a key that is not a language is
        # a miss, and only the third one falls back to Hindi. Words that name no language
        # (7.5) are a miss too: not silence, so they never hang the caller up.
        wrong_keys = 0
        while True:
            if hasattr(audio, "select_language"):
                inp = audio.select_language()
            else:
                audio.say(("greeting_trilingual",))
                inp = audio.next_input(profile="turn0")
            if isinstance(inp, tuple):
                lang, lang_source = inp
                break
            if isinstance(inp, Hangup):
                audio.hangup()
                log.close(reason=STOP_ZERO_SURVIVORS, ladder_rung=0, mode="voice")
                return
            if isinstance(inp, Silence):
                if _answer_silence(audio, log, inp.n, 0, (), say_reply=False):
                    continue
                audio.hangup()
                log.close(reason=STOP_ZERO_SURVIVORS, ladder_rung=0, mode="voice")
                return
            if isinstance(inp, Digit) and inp.digit in tunables.turn0_keys():
                lang, lang_source = tunables.turn0_keys()[inp.digit], "keypad"
                break
            if isinstance(inp, Digit):
                _log_key(log, inp.digit, "not on the menu")
            wrong_keys += 1
            if wrong_keys >= 3:
                lang, lang_source = "hi", "default"
                break

        if lang_source == "keypad":
            pressed = next((k for k, v in tunables.turn0_keys().items() if v == lang), "")
            _log_key(log, pressed, f"language = {LANG_EN.get(lang, lang)}")
        if hasattr(audio, "language"):
            audio.language = lang

        # Turn 0 writes a log line and does NOT count against MAX_TURNS
        log.write(TurnLogRecord(
            turn_n=0,
            turn_class="ANSWER",
            transcript=str(lang),
        ))
        # Log.open runs before turn 0, so its header carries the default
        # lang_source. Record the value the caller actually produced.
        log.write(LangSwitchRecord(
            lang=lang,
            lang_source=lang_source,
            turn_n=0,
        ))

        # --- 2. Consent Notice (off unless CONSENT_LINE is set) ---
        if tunables.CONSENT_LINE:
            audio.say(("consent_notice",))

        # --- 2b. Talk only (7.13): no keys after the language pick. The keys path below is untouched.
        if tunables.TALK_ONLY:
            from haqdaar.engine import talk
            return talk.run(audio, model, corpus, log, lang)

        # --- 3. Mode Initialization ---
        # Keypad-only mode is entered when model is None or keypad-only requested
        if (
            model is None
            or getattr(model, "keypad_only", False)
            or getattr(audio, "keypad_only", False)
            or getattr(getattr(audio, "turn", None), "keypad_only", False)
        ):
            mode = "keypad_only"
            log.write({"mode": "keypad_only"})
            audio.say(("keypad_only_mode",))
        else:
            mode = "voice"

        # Mutable call state
        box_vector: dict[str, Any] = {b: UNASKED for b in SEVEN_BOXES}
        # T18 §3: in keypad-only mode, a closed set that will not fit a keypad menu drops to UNKNOWN
        # up front. This is a cardinality test, never a hard-coded box: on the
        # production corpus `state` has 36 values and drops; on fixtures it has
        # 2 and stays askable.
        if mode == "keypad_only":
            for _b in SEVEN_BOXES:
                _vals = corpus.values(_b)
                if _vals and len(_vals) > tunables.KEYPAD_CARDINALITY_MAX:
                    box_vector[_b] = UNKNOWN
                    log.write(TurnLogRecord(
                        turn_n=0,
                        turn_class="ANSWER",
                        box=_b,
                        value=UNKNOWN,
                        unknown_source="keypad_dropped",
                    ))

        turn_n = 0
        question_count = 0
        silence_ladder = 0
        qa: dict[str, Any] = {"n": 0}  # questions answered this call (7.1)
        # T11 box strikes: counts non-ANSWER turns per box towards keypad drop.
        # Interleaved SILENCE turns do not reset this counter; keeping strikes
        # cumulative per box ensures callers who alternate between silence and
        # unclear speech reliably receive keypad fallback.
        box_strikes: dict[str, int] = {b: 0 for b in SEVEN_BOXES}
        ladder_rung = 0
        stop_reason: Optional[str] = None

        # Door B (T18 §6): "anything else" clears ONLY category and re-enters
        # the questioning loop. Turn and question budgets are call-wide, so a
        # second subject spends what is left, never a fresh allowance.
        door_b_used = False
        # Door A: a read-back satisfies the opener (the caller stated their
        # need by naming a scheme), so the opener is not re-asked. Reset on
        # Door B re-entry, when a new subject re-opens Door A.
        door_a_done = False
        # 7.3 talk-first: the opener is one short line. The nine-choice list plays on
        # key 0, or once the caller has missed twice (silence or words we could not use).
        opener_menu = ""  # why the list is playing: "key_0", "two_misses" or "silence"; "" = short line only
        opener_misses = 0
        while True:
            stop_reason = None
            # Door A (Architecture §6, box 0): `category` is the opener, not a
            # box the Planner may or may not get round to. It is asked first and
            # kept in front of the caller until it is answered or struck out to
            # UNKNOWN. Without this the caller is never asked what they phoned
            # about, and every terminal is computed from facts alone.
            # --- 4. Questioning Loop ---
            while True:
                # Check for budget caps directly from tunables
                if turn_n >= tunables.MAX_TURNS:
                    stop_reason = STOP_MAX_TURNS
                    break
                if question_count >= tunables.MAX_QUESTIONS:
                    stop_reason = STOP_MAX_QUESTIONS
                    break

                opener_vals = corpus.values("category")
                opener_open = (
                    box_vector.get("category") in (None, UNASKED)
                    and bool(opener_vals)
                    and (mode == "voice" or len(opener_vals) <= tunables.KEYPAD_CARDINALITY_MAX)
                    and not door_a_done
                )
                if opener_open:
                    action = Ask("category")
                else:
                    action = Planner.next_action(
                        box_vector,
                        corpus,
                        turn_count=turn_n,
                        question_count=question_count,
                    )

                if isinstance(action, Stop):
                    stop_reason = action.reason
                    break
                elif isinstance(action, Widen):
                    stop_reason = STOP_ZERO_SURVIVORS
                    break

                assert isinstance(action, Ask)
                box = action.box
                if box == "category" and not opener_menu and opener_misses >= tunables.UNCLEAR_TRIES:
                    opener_menu = "two_misses"
                    log.write({"mode": mode, "opener_menu": opener_menu, "opener_misses": opener_misses})

                is_box_keypad = (mode == "keypad_only") or (box_strikes[box] >= tunables.UNCLEAR_TRIES)

                # Verify box cardinality for keypad mode
                vals = corpus.values(box)
                if is_box_keypad and vals and len(vals) > tunables.KEYPAD_CARDINALITY_MAX:
                    box_vector[box] = UNKNOWN
                    log.write(TurnLogRecord(
                        turn_n=turn_n,
                        turn_class="ANSWER",
                        box=box,
                        value=UNKNOWN,
                        unknown_source="keypad_dropped",
                    ))
                    continue

                if is_box_keypad:
                    if box == "category":
                        prompt_id = "opener_prompt"
                    elif box == "state":
                        prompt_id = "state_q_maharashtra"
                    else:
                        prompt_id = f"keypad_{box}"
                    audio.say((prompt_id,))
                    inp = audio.next_input(profile="normal")
                else:
                    if box == "category":
                        prompt_id = "opener_prompt" if opener_menu else "opener_short_prompt"
                    elif box == "state":
                        prompt_id = "state_q_maharashtra"
                    elif box_strikes[box] >= 1:
                        prompt_id = f"rephrase_{box}"
                    else:
                        prompt_id = f"q_{box}"
                    audio.say((prompt_id,))
                    inp = audio.next_input(profile="spoken")

                if isinstance(inp, Silence):
                    rung = inp.n if (hasattr(inp, "n") and inp.n) else (silence_ladder + 1)
                    silence_ladder = rung
                    # The loop says the prompt itself on its next pass, so none is passed here.
                    if _answer_silence(audio, log, rung, turn_n, ()):
                        # A quiet caller at the opener hears the key list once before the goodbye.
                        if box == "category" and not opener_menu:
                            opener_menu = "silence"
                            log.write({"mode": mode, "opener_menu": opener_menu, "opener_misses": opener_misses})
                        continue
                    audio.hangup()
                    survs_s = Filter.survivors(box_vector, corpus)
                    silence_stop = (
                        STOP_ZERO_SURVIVORS if len(survs_s) == 0
                        else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT)
                    )
                    log.close(reason=silence_stop, ladder_rung=ladder_rung, mode=mode)
                    return

                elif isinstance(inp, Noise):
                    # NOISE spends a cap turn
                    turn_n += 1
                    silence_ladder = 0
                    box_strikes[box] += 1
                    log.write(TurnLogRecord(
                        turn_n=turn_n,
                        turn_class="NOISE",
                    ))
                    if mode != "keypad_only" and (
                        getattr(audio, "keypad_only", False)
                        or getattr(getattr(audio, "turn", None), "keypad_only", False)
                        or getattr(model, "keypad_only", False)
                    ):
                        mode = "keypad_only"
                        log.write({"mode": "keypad_only"})
                        audio.say(("keypad_only_mode",))
                        if turn_n >= tunables.MAX_TURNS:
                            stop_reason = STOP_MAX_TURNS
                            break
                        continue
                    if box_strikes[box] >= tunables.UNCLEAR_TRIES:
                        if mode == "keypad_only" or is_box_keypad:
                            box_vector[box] = UNKNOWN
                            question_count += 1
                            log.write(TurnLogRecord(
                                turn_n=turn_n,
                                turn_class="ANSWER",
                                box=box,
                                value=UNKNOWN,
                                unknown_source="keypad_dropped",
                            ))
                    # The loop says the prompt again on its next pass: no audio.repeat() here,
                    # or the caller hears the question twice in a row.
                    if turn_n >= tunables.MAX_TURNS:
                        stop_reason = STOP_MAX_TURNS
                        break
                    continue

                elif isinstance(inp, Hangup):
                    audio.hangup()
                    survs_s = Filter.survivors(box_vector, corpus)
                    h_stop = (
                        STOP_ZERO_SURVIVORS if len(survs_s) == 0
                        else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT)
                    )
                    log.close(reason=h_stop, ladder_rung=ladder_rung, mode=mode)
                    return

                elif isinstance(inp, Digit):
                    silence_ladder = 0
                    if inp.digit == "0" and box == "category" and not is_box_keypad and not opener_menu:
                        # At the short line 0 asks for the list; it is not "don't know" yet.
                        opener_menu = "key_0"
                        _log_key(log, "0", "the key list")
                        log.write({"mode": mode, "opener_menu": opener_menu, "opener_misses": opener_misses})
                        continue
                    turn_n, question_count, stop_reason, act = Engine._handle_digit_input(
                        audio, log, corpus, box, inp, box_vector, box_strikes,
                        turn_n, question_count, mode, is_box_keypad,
                    )
                    if box_strikes[box] == 0:
                        opener_misses = 0  # a valid key clears the unclear count
                    if stop_reason:
                        break
                    continue

                elif isinstance(inp, Speech):
                    silence_ladder = 0
                    transcript = getattr(inp, "text", "") or ""
                    if is_box_keypad or model is None:
                        # A Speech input in keypad-only mode is a caller talking to a
                        # menu. It is not free text to the Engine: it spends a cap turn
                        # and is discarded, exactly like an out-of-menu digit.
                        turn_n += 1
                        box_strikes[box] += 1
                        log.write(TurnLogRecord(
                            turn_n=turn_n,
                            turn_class="UNCLEAR",
                            discarded_transcript=str(transcript),
                        ))
                        if box_strikes[box] >= tunables.UNCLEAR_TRIES:
                            box_vector[box] = UNKNOWN
                            question_count += 1
                            log.write(TurnLogRecord(
                                turn_n=turn_n,
                                turn_class="ANSWER",
                                box=box,
                                value=UNKNOWN,
                                unknown_source="keypad_dropped",
                            ))
                        if turn_n >= tunables.MAX_TURNS:
                            stop_reason = STOP_MAX_TURNS
                            break
                        continue

                    # --- Voice mode: process spoken answer via model ---
                    turn_n += 1
                    curr_lang = getattr(audio, "language", "hi")
                    proposed_val = None
                    proposed_span = ""
                    is_question = False
                    also_question = None

                    if box == "category":
                        # Door A (T12/ARCH §6): exact code match before the model.
                        # Unavailable in keypad-only mode (this is the voice branch).
                        door = DoorA.from_corpus(corpus)
                        door_t0 = time.monotonic()
                        dres = door.match(transcript, lang=curr_lang)
                        door_a_read = False
                        model_failed = False
                        if (
                            dres.action == "read"
                            and unmatched_content(transcript, dres.matched_alias)
                            and Engine._try_question(
                                audio, model, corpus, log, qa, inp, mode, turn_n - 1, box_vector,
                                scheme_ids=[dres.scheme_ids[0]], asked="opener",
                            )
                        ):
                            # 7.3: a question about a named scheme ("how much money is in PM Kisan?")
                            # is answered, not read out. No turn, no strike, the opener again.
                            turn_n -= 1
                            box_strikes[box] = 0
                            opener_misses = 0
                            continue
                        if dres.action == "read":
                            _door_a_read(audio, log, dres.scheme_ids[0], transcript,
                                         dres.matched_alias or transcript, turn_n, 1, door_t0)
                            turn_n += 1  # T10: opener costs 2 turns when it fills anything
                            door_a_done = True
                            door_a_read = True
                            if unmatched_content(transcript, dres.matched_alias):
                                res = model.opener(transcript, lang=curr_lang)
                                if isinstance(res, list):
                                    seeds = [s for s in res if s.box != "scheme"]
                                else:
                                    if not (isinstance(res, Unclear) and getattr(res, "reason", "") in ("unclear", "unrecognized")):
                                        model_failed = True
                                    seeds = []
                            else:
                                seeds = []  # clean naming: zero model calls (T12)
                        elif dres.action == "keypad_pick":
                            s1, s2 = dres.scheme_ids[0], dres.scheme_ids[1]
                            outcome = _door_a_pick(audio, log, turn_n, s1, s2)
                            turn_n += 1
                            question_count += 1  # T12: the pick costs 1 turn against the six
                            if outcome == "hangup":
                                audio.hangup()
                                survs_s = Filter.survivors(box_vector, corpus)
                                h_stop = (
                                    STOP_ZERO_SURVIVORS if len(survs_s) == 0
                                    else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT)
                                )
                                log.close(reason=h_stop, ladder_rung=ladder_rung, mode=mode)
                                return
                            if outcome in ("1", "2"):
                                slug = s1 if outcome == "1" else s2
                                _door_a_read(audio, log, slug, transcript,
                                             dres.matched_alias or transcript, turn_n, 2,
                                             time.monotonic())
                                turn_n += 1
                                door_a_done = True
                                door_a_read = True
                                seeds = []
                            else:
                                # Declined: Door B, one keypad turn, no repeats
                                audio.say(("door_a_downgrade_to_b",))
                                res = model.opener(transcript, lang=curr_lang)
                                seeds = [s for s in res if s.box != "scheme"] if isinstance(res, list) else []
                        else:  # downgrade_to_b
                            downgrade_line_said = False
                            if dres.scheme_ids:
                                audio.say(("door_a_downgrade_to_b",))
                                downgrade_line_said = True
                            # else: 0 matches go to Door B silently (ARCH §6 diagram)
                            # T12 search #2: model selection from the alias closed
                            # set. The code pass found nothing; the model may
                            # still hear a scheme name (mis-hearings live here).
                            res = model.opener(transcript, lang=curr_lang)
                            model_ids: list[str] = []
                            if isinstance(res, list):
                                for s in res:
                                    if (s.box == "scheme" and s.value not in model_ids
                                            and door.has_scheme(s.value)):
                                        model_ids.append(s.value)
                                seeds = [s for s in res if s.box != "scheme"]
                            else:
                                seeds = []
                            if (
                                tunables.QA_ENABLED and not model_ids and not seeds
                                and hasattr(model, "sort") and model.sort("opener", transcript) in ("QUESTION", "BOTH")
                            ):
                                is_question = True  # 7.3: a question at the first prompt; nothing usable was heard
                            if len(model_ids) == 1:
                                span = next(s.span for s in res if s.box == "scheme")
                                _door_a_read(audio, log, model_ids[0], transcript,
                                             span, turn_n, 1, door_t0)
                                turn_n += 1
                                door_a_done = True
                                door_a_read = True
                            elif len(model_ids) == 2:
                                outcome = _door_a_pick(audio, log, turn_n, model_ids[0], model_ids[1])
                                turn_n += 1
                                question_count += 1
                                if outcome == "hangup":
                                    audio.hangup()
                                    survs_s = Filter.survivors(box_vector, corpus)
                                    h_stop = (
                                        STOP_ZERO_SURVIVORS if len(survs_s) == 0
                                        else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT)
                                    )
                                    log.close(reason=h_stop, ladder_rung=ladder_rung, mode=mode)
                                    return
                                if outcome in ("1", "2"):
                                    slug = model_ids[0] if outcome == "1" else model_ids[1]
                                    _door_a_read(audio, log, slug, transcript,
                                                 transcript, turn_n, 2, time.monotonic())
                                    turn_n += 1
                                    door_a_done = True
                                    door_a_read = True
                                elif not downgrade_line_said:
                                    audio.say(("door_a_downgrade_to_b",))
                            elif len(model_ids) >= 3 and not downgrade_line_said:
                                audio.say(("door_a_downgrade_to_b",))
                        # Scheme stamps never become box values (the old res[0]
                        # fallback could stamp a scheme id as the category value).
                        for s in seeds:
                            if s.box == "category":
                                proposed_val = s.value
                                proposed_span = s.span
                                break
                        if not proposed_val and door_a_read and not model_failed:
                            # Named scheme already read and nothing to confirm:
                            # planner asks on. (A failed model pass still falls
                            # through so failure accounting runs.)
                            box_strikes[box] = 0
                            opener_misses = 0
                            continue
                    else:
                        turn_kwargs = {"english": True, "lang": inp.lang} if getattr(inp, "english", False) else {}
                        res = model.turn(transcript, box=box, ask_count=box_strikes[box], **turn_kwargs)
                        is_question = isinstance(res, Question)
                        if getattr(res, "also_question", False):
                            also_question = inp
                        if hasattr(res, "box") and hasattr(res, "value") and res.value:
                            proposed_val = res.value
                            proposed_span = getattr(res, "span", transcript)

                    pending = audio.pending_key() if hasattr(audio, "pending_key") else None
                    if pending is None and _newer_words(audio, transcript):
                        # 7.5: they spoke again while the router worked; the older words are
                        # dropped and the loop waits again, which gives the newest words.
                        turn_n -= 1
                        continue
                    if pending is not None:
                        if isinstance(pending, Hangup):
                            audio.hangup()
                            survs_s = Filter.survivors(box_vector, corpus)
                            h_stop = (
                                STOP_ZERO_SURVIVORS if len(survs_s) == 0
                                else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT)
                            )
                            log.close(reason=h_stop, ladder_rung=ladder_rung, mode=mode)
                            return
                        if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                            audio.trace.input_event(
                                prompt_n=getattr(pending, "prompt_n", -1),
                                prompt=box,
                                event="speech",
                                value=transcript,
                                took=False,
                                why="key_beat_speech",
                            )
                        turn_n -= 1
                        silence_ladder = 0
                        turn_n, question_count, stop_reason, act = Engine._handle_digit_input(
                            audio, log, corpus, box, pending, box_vector, box_strikes,
                            turn_n, question_count, mode, is_box_keypad,
                        )
                        if box_strikes[box] == 0:
                            opener_misses = 0
                        if stop_reason:
                            break
                        continue

                    if not proposed_val:
                        if is_question and Engine._try_question(
                            audio, model, corpus, log, qa, inp, mode, turn_n - 1, box_vector,
                        ):
                            # A question never moves the call: no turn, no strike, same box again.
                            turn_n -= 1
                            box_strikes[box] = 0
                            opener_misses = 0
                            continue
                        # Model did not understand speech -> UNCLEAR
                        box_strikes[box] += 1
                        if box == "category":
                            opener_misses += 1
                        log.write(TurnLogRecord(
                            turn_n=turn_n,
                            turn_class="UNCLEAR",
                            transcript=transcript,
                        ))
                        if (
                            getattr(model, "keypad_only", False)
                            or getattr(audio, "keypad_only", False)
                            or getattr(getattr(audio, "turn", None), "keypad_only", False)
                        ):
                            mode = "keypad_only"
                            log.write({"mode": "keypad_only"})
                            audio.say(("keypad_only_mode",))
                        elif box_strikes[box] < tunables.UNCLEAR_TRIES:
                            audio.say(("unclear_prompt",))
                        if turn_n >= tunables.MAX_TURNS:
                            stop_reason = STOP_MAX_TURNS
                            break
                        continue

                    # Model understood proposed_val!
                    if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                        audio.trace.input_event(
                            prompt_n=getattr(inp, "prompt_n", -1),
                            prompt=box,
                            event="speech",
                            value=transcript,
                            took=True,
                            why="ok",
                        )
                    # Log spoken PROPOSAL turn (non-ANSWER class, confirmed on subsequent turn)
                    log.write(TurnLogRecord(
                        turn_n=turn_n,
                        turn_class="PROPOSAL",
                        box=box,
                        value=proposed_val,
                        transcript=transcript,
                        span=proposed_span,
                    ))

                    if turn_n >= tunables.MAX_TURNS:
                        stop_reason = STOP_MAX_TURNS
                        break

                    # --- Confirmation Turn: Mouth reads back what it heard ---
                    confirm_seq = (
                        "bundle_confirm_intro",
                        f"chip_{box}_{proposed_val}",
                        "confirm_yn_suffix",
                    )
                    audio.say(confirm_seq)

                    # Confirmation loop: bounded against repeat-mashing via confirm_repeats
                    # without consuming cap turns (# and SILENCE do not consume turns per T14/T16)
                    confirm_repeats = 0
                    while True:
                        confirm_inp = audio.next_input(profile="confirm")
                        if isinstance(confirm_inp, Digit):
                            silence_ladder = 0
                            _log_key(log, confirm_inp.digit, {
                                "#": "repeat", "*": "change language", "1": "yes", "2": "no",
                            }.get(confirm_inp.digit, "not on the menu"))
                            if confirm_inp.digit == "#":
                                audio.repeat()
                                confirm_repeats += 1
                                if confirm_repeats >= tunables.CONFIRM_REPEAT_MAX:
                                    turn_n += 1
                                    box_strikes[box] += 1
                                    log.write(TurnLogRecord(
                                        turn_n=turn_n,
                                        turn_class="UNCLEAR",
                                        transcript="#",
                                    ))
                                    if box_strikes[box] < tunables.UNCLEAR_TRIES:
                                        audio.say(("unclear_prompt",))
                                    break
                                continue
                            elif confirm_inp.digit == "*":
                                curr_lang = getattr(audio, "language", "hi")
                                new_lang = _next_lang(curr_lang)
                                if hasattr(audio, "language"):
                                    audio.language = new_lang
                                log.write(LangSwitchRecord(
                                    lang=new_lang,
                                    lang_source="keypad",
                                    turn_n=turn_n,
                                ))
                                audio.say((
                                    "bundle_confirm_intro",
                                    f"chip_{box}_{proposed_val}",
                                    "confirm_yn_suffix",
                                ))
                                confirm_repeats += 1
                                if confirm_repeats >= tunables.CONFIRM_REPEAT_MAX:
                                    turn_n += 1
                                    box_strikes[box] += 1
                                    log.write(TurnLogRecord(
                                        turn_n=turn_n,
                                        turn_class="UNCLEAR",
                                        transcript="*",
                                    ))
                                    if box_strikes[box] < tunables.UNCLEAR_TRIES:
                                        audio.say(("unclear_prompt",))
                                    break
                                continue
                            elif confirm_inp.digit == "1":
                                # CONFIRM ACCEPT: caller confirmed!
                                turn_n += 1
                                box_vector[box] = proposed_val
                                box_strikes[box] = 0
                                opener_misses = 0
                                question_count += 1
                                log.write(TurnLogRecord(
                                    turn_n=turn_n,
                                    turn_class="ANSWER",
                                    box=box,
                                    value=proposed_val,
                                    transcript="1",
                                    span="1",
                                ))
                                break
                            elif confirm_inp.digit == "2":
                                # CONFIRM MISMATCH / RE-ASK: caller rejected!
                                turn_n += 1
                                box_strikes[box] += 1
                                log.write(TurnLogRecord(
                                    turn_n=turn_n,
                                    turn_class="UNCLEAR",
                                    transcript="2",
                                ))
                                if box_strikes[box] < tunables.UNCLEAR_TRIES:
                                    audio.say(("unclear_prompt",))
                                break
                            else:
                                # Out-of-menu digit on confirm
                                turn_n += 1
                                box_strikes[box] += 1
                                log.write(TurnLogRecord(
                                    turn_n=turn_n,
                                    turn_class="UNCLEAR",
                                    transcript=str(confirm_inp.digit),
                                ))
                                if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                                    audio.trace.input_event(
                                        prompt_n=getattr(confirm_inp, "prompt_n", -1),
                                        prompt="confirm",
                                        event="key",
                                        value=str(confirm_inp.digit),
                                        took=False,
                                        why="not_on_menu",
                                    )
                                if (
                                    getattr(model, "keypad_only", False)
                                    or getattr(audio, "keypad_only", False)
                                    or getattr(getattr(audio, "turn", None), "keypad_only", False)
                                ):
                                    mode = "keypad_only"
                                    log.write({"mode": "keypad_only"})
                                    audio.say(("keypad_only_mode",))
                                    break
                                elif box_strikes[box] >= tunables.UNCLEAR_TRIES:
                                    break
                                else:
                                    audio.say(("unclear_prompt",))
                                    audio.say(confirm_seq)
                                    continue

                        elif isinstance(confirm_inp, Silence):
                            rung = confirm_inp.n if (hasattr(confirm_inp, "n") and confirm_inp.n) else (silence_ladder + 1)
                            silence_ladder = rung
                            if not _answer_silence(audio, log, rung, turn_n, confirm_seq):
                                audio.hangup()
                                survs_s = Filter.survivors(box_vector, corpus)
                                silence_stop = (
                                    STOP_ZERO_SURVIVORS if len(survs_s) == 0
                                    else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT)
                                )
                                log.close(reason=silence_stop, ladder_rung=ladder_rung, mode=mode)
                                return
                            confirm_repeats += 1
                            if confirm_repeats >= tunables.CONFIRM_REPEAT_MAX:
                                turn_n += 1
                                box_strikes[box] += 1
                                log.write(TurnLogRecord(
                                    turn_n=turn_n,
                                    turn_class="UNCLEAR",
                                    transcript="silence_limit",
                                ))
                                if box_strikes[box] < tunables.UNCLEAR_TRIES:
                                    audio.say(("unclear_prompt",))
                                break
                            continue

                        elif isinstance(confirm_inp, Noise):
                            turn_n += 1
                            box_strikes[box] += 1
                            log.write(TurnLogRecord(
                                turn_n=turn_n,
                                turn_class="NOISE",
                            ))
                            if mode != "keypad_only" and (
                                getattr(model, "keypad_only", False)
                                or getattr(audio, "keypad_only", False)
                                or getattr(getattr(audio, "turn", None), "keypad_only", False)
                            ):
                                mode = "keypad_only"
                                log.write({"mode": "keypad_only"})
                                audio.say(("keypad_only_mode",))
                            elif box_strikes[box] < tunables.UNCLEAR_TRIES:
                                audio.say(("unclear_prompt",))
                            break

                        elif isinstance(confirm_inp, Speech):
                            silence_ladder = 0
                            spk = str(getattr(confirm_inp, "text", "") or "").strip().lower()
                            if model is not None and hasattr(model, "confirm"):
                                is_confirmed = model.confirm(spk, lang=getattr(audio, "language", None))
                            else:
                                is_confirmed = None

                            if is_confirmed is True:
                                turn_n += 1
                                box_vector[box] = proposed_val
                                box_strikes[box] = 0
                                opener_misses = 0
                                question_count += 1
                                log.write(TurnLogRecord(
                                    turn_n=turn_n,
                                    turn_class="ANSWER",
                                    box=box,
                                    value=proposed_val,
                                    transcript=spk,
                                    span=spk,
                                ))
                                break
                            elif is_confirmed is False:
                                turn_n += 1
                                box_strikes[box] += 1
                                log.write(TurnLogRecord(
                                    turn_n=turn_n,
                                    turn_class="UNCLEAR",
                                    transcript=spk,
                                ))
                                if box_strikes[box] < tunables.UNCLEAR_TRIES:
                                    audio.say(("unclear_prompt",))
                                break
                            else:
                                if Engine._try_question(
                                    audio, model, corpus, log, qa, confirm_inp, mode, turn_n, box_vector, asked="confirm",
                                ):
                                    audio.say(confirm_seq)  # 7.3: answered; the same read-back again, no strike
                                    continue
                                turn_n += 1
                                box_strikes[box] += 1
                                log.write(TurnLogRecord(
                                    turn_n=turn_n,
                                    turn_class="UNCLEAR",
                                    transcript=spk,
                                ))
                                if mode != "keypad_only" and (
                                    getattr(model, "keypad_only", False)
                                    or getattr(audio, "keypad_only", False)
                                    or getattr(getattr(audio, "turn", None), "keypad_only", False)
                                ):
                                    mode = "keypad_only"
                                    log.write({"mode": "keypad_only"})
                                    audio.say(("keypad_only_mode",))
                                elif box_strikes[box] < tunables.UNCLEAR_TRIES:
                                    audio.say(("unclear_prompt",))
                                break

                        elif isinstance(confirm_inp, Hangup):
                            audio.hangup()
                            survs_s = Filter.survivors(box_vector, corpus)
                            h_stop = (
                                STOP_ZERO_SURVIVORS if len(survs_s) == 0
                                else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT)
                            )
                            log.close(reason=h_stop, ladder_rung=ladder_rung, mode=mode)
                            return

                    if also_question is not None and box_vector[box] == proposed_val:
                        # BOTH: the answer was read back and accepted; now the question, once.
                        Engine._try_question(audio, model, corpus, log, qa, also_question, mode, turn_n, box_vector)
                    if stop_reason:
                        break
                    if turn_n >= tunables.MAX_TURNS:
                        stop_reason = STOP_MAX_TURNS
                        break
                    if question_count >= tunables.MAX_QUESTIONS:
                        stop_reason = STOP_MAX_QUESTIONS
                        break


            # --- 5. Terminal Phase ---
            survs = Filter.survivors(box_vector, corpus)
            # No pre_vetted here. The Engine has not run speakable(), so it must
            # not claim it has: Terminals owns the truth lock and it is the only
            # thing standing between an UNKNOWN hard box and a scheme the caller
            # cannot get. classify_shape also runs the widening ladder here and
            # hands back the schemes it resolved.
            shape, candidate_survs, dropped_boxes = Terminals.classify_shape(
                survivors=survs,
                state=box_vector.get("state"),
                box_vector=box_vector,
                corpus=corpus,
            )

            if shape == DELIVERY_WIDENED_MATCH:
                ladder_rung = len(dropped_boxes)
            elif shape == DELIVERY_NEAREST:
                answered_soft = [
                    b for b in WIDENING_ORDER
                    if box_vector.get(b) not in (None, UNASKED, UNKNOWN)
                ]
                ladder_rung = len(answered_soft)
            else:
                ladder_rung = 0

            # Ranked ids for prefetch and D8 paging
            ranked_ids = [
                corpus.scheme_id(s) if hasattr(corpus, "scheme_id") else str(s)
                for s in Terminals.ranked(candidate_survs, corpus)
            ]
            if hasattr(audio, "prefetch"):
                try:
                    audio.prefetch(ranked_ids)
                except Exception:
                    pass

            # Feed back the schemes classify_shape resolved, not the raw survivor
            # list. On a widened or nearest ending `survs` is empty, and passing
            # it here threw the ladder's result away and played a preamble with
            # no names. These are pre_vetted for real: speakable() ran above.
            terminal_seq = Terminals.sequence(
                survivors=candidate_survs,
                state=box_vector.get("state"),
                box_vector=box_vector,
                corpus=corpus,
                dropped_boxes=dropped_boxes,
                shape=shape,
                pre_vetted=True,
            )
            # --- D9: Delivery log ---
            named = [
                t.split(":", 1)[1] for t in terminal_seq if t.startswith("name:")
            ]

            # --- 6. Read-Back Menu ---
            # Results queued one scheme at a time: read the scheme, play its menu,
            # wait, then the next. The engine's current-scheme is always the one
            # the caller hears.
            if SECTION_MENU in terminal_seq:
                first_scheme_idx = next(
                    (i for i, t in enumerate(terminal_seq) if t.startswith("name:")),
                    len(terminal_seq),
                )
                preamble = terminal_seq[:first_scheme_idx]
                if preamble:
                    audio.say(preamble)

                sections_heard: dict[str, list[str]] = {n: ["summary"] for n in named}
                # D8 paging: candidate_survs holds every speakable candidate this
                # terminal resolved, not just the ones named so far (direct match
                # names all of them, so this is empty there; overflow and a >4
                # widened match name only the top OVERFLOW_READ_CAP).
                rest = [sid for sid in ranked_ids if sid not in named]
                qa["model"], qa["mode"] = model, mode
                kept_going = Engine._read_back(audio, named, sections_heard, rest, corpus, log, turn_n, qa)
                cur_lang = getattr(audio, "language", lang)
                for n in named:
                    log.write(DeliveryRecord(
                        slug=n,
                        ending=shape,
                        sections=Engine._heard_sections(audio, n, sections_heard[n]),
                        lang=cur_lang,
                    ))
                if not kept_going:
                    log.close(reason=STOP_ZERO_SURVIVORS if not survs else STOP_LE_4_SURVIVORS,
                              ladder_rung=ladder_rung, mode=mode)
                    return
            else:
                audio.say(terminal_seq)
                if named:
                    # Nearest: "Restraint: summary only, NO section_menu,
                    # auto-advance" (terminals.py nearest()) -- there is no later
                    # touch point for these schemes, so write here.
                    cur_lang = getattr(audio, "language", lang)
                    for n in named:
                        log.write(DeliveryRecord(
                            slug=n,
                            ending=shape,
                            sections=Engine._heard_sections(audio, n, ["summary"]),
                            lang=cur_lang,
                        ))

            # --- 7. Anything Else ---
            ae_strikes = 0
            while True:
                audio.say(("anything_else",))
                if mode == "keypad_only":
                    ae_inp = audio.next_input(profile="normal")
                else:
                    ae_inp = audio.next_input(profile="confirm")
                if isinstance(ae_inp, Hangup):
                    audio.hangup()
                    log.close(reason=STOP_ZERO_SURVIVORS if not survs else STOP_LE_4_SURVIVORS,
                              ladder_rung=ladder_rung, mode=mode)
                    return
                if isinstance(ae_inp, Silence):
                    # The loop says anything_else again on its next pass.
                    if _answer_silence(audio, log, ae_inp.n, turn_n, ()):
                        continue
                    audio.hangup()
                    log.close(reason=STOP_ZERO_SURVIVORS if not survs else STOP_LE_4_SURVIVORS,
                              ladder_rung=ladder_rung, mode=mode)
                    return
                is_yes = False
                if isinstance(ae_inp, Digit):
                    _log_key(log, ae_inp.digit, {
                        "#": "repeat", "*": "change language", "1": "yes", "0": "no", "2": "no",
                    }.get(ae_inp.digit, "not on the menu"))
                    if ae_inp.digit == "#":
                        continue  # the loop says the line again
                    elif ae_inp.digit == "*":
                        curr_lang = getattr(audio, "language", "hi")
                        new_lang = _next_lang(curr_lang)
                        if hasattr(audio, "language"):
                            audio.language = new_lang
                        log.write(LangSwitchRecord(
                            lang=new_lang,
                            lang_source="keypad",
                            turn_n=turn_n,
                        ))
                        continue
                    elif ae_inp.digit == "1":
                        is_yes = True
                        if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                            audio.trace.input_event(
                                prompt_n=getattr(ae_inp, "prompt_n", -1),
                                prompt="anything_else",
                                event="key",
                                value="1",
                                took=True,
                                why="ok",
                            )
                        break
                    elif ae_inp.digit in ("0", "2"):
                        is_yes = False
                        if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                            audio.trace.input_event(
                                prompt_n=getattr(ae_inp, "prompt_n", -1),
                                prompt="anything_else",
                                event="key",
                                value=str(ae_inp.digit),
                                took=True,
                                why="ok",
                            )
                        break
                    else:
                        # Out of menu digit on anything_else (G6: "wrong key" line then repeat)
                        ae_strikes += 1
                        if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                            audio.trace.input_event(
                                prompt_n=getattr(ae_inp, "prompt_n", -1),
                                prompt="anything_else",
                                event="key",
                                value=str(ae_inp.digit),
                                took=False,
                                why="not_on_menu",
                            )
                        if ae_strikes >= tunables.UNCLEAR_TRIES:
                            break  # a stuck key must not loop forever: take it as "no"
                        audio.say(("unclear_prompt",))
                        continue
                elif isinstance(ae_inp, Speech):
                    spk = str(getattr(ae_inp, "text", "") or "").strip().lower()
                    if model is not None and hasattr(model, "confirm"):
                        confirmed = model.confirm(spk, lang=getattr(audio, "language", None))
                    else:
                        confirmed = None
                    if confirmed is None and Engine._try_question(
                        audio, model, corpus, log, qa, ae_inp, mode, turn_n, box_vector, asked="anything_else",
                    ):
                        continue  # the loop asks anything-else again
                    if confirmed is True:
                        is_yes = True
                    break
                else:
                    break
            if (
                is_yes
                and not door_b_used
                and turn_n < tunables.MAX_TURNS
                and question_count < tunables.MAX_QUESTIONS
            ):
                # One Door B per call. A second subject that narrows to nothing
                # new would otherwise re-play the same terminal forever: the
                # round can end without spending a turn, so the caps do not
                # bound it.
                door_b_used = True
                box_vector["category"] = UNASKED
                box_strikes["category"] = 0
                # The next round re-opens Door A: the caller states a new subject.
                door_a_done = False
                opener_menu = ""
                opener_misses = 0
                continue
            break

        # --- 8. Closing ---
        audio.say(("closing_farewell",))
        if hasattr(audio, "on_mark"):
            audio.on_mark("closing_farewell")
        audio.hangup()

        if stop_reason in STOP_REASONS:
            final_stop = stop_reason
        elif len(survs) == 0:
            final_stop = STOP_ZERO_SURVIVORS
        elif len(survs) <= tunables.STOP_SURVIVORS:
            final_stop = STOP_LE_4_SURVIVORS
        else:
            final_stop = STOP_NO_SPLIT
        log.close(
            reason=final_stop,
            ladder_rung=ladder_rung,
            mode=mode,
        )

    # Section keys on `section_menu` (T23 line 28): 1 benefits, 2 how to apply,
    # 3 required documents, 4 who can apply, 9 next scheme.
    SECTION_KEYS: dict[str, str] = {
        "1": "benefit_text",
        "2": "how_to_apply",
        "3": "documents",
        "4": "who_can_apply",
    }

    @staticmethod
    def _read_back(
        audio: Any,
        named: list[str],
        sections_heard: dict[str, list[str]],
        rest: list[str],
        corpus: Any,
        log: Log,
        turn_n: int,
        qa: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Drive the read-back menu one scheme at a time. Returns False if the caller hung up.

        Appends each section actually played to sections_heard[<scheme>] (D9),
        so the caller writes one DeliveryRecord per scheme once this returns.
        `rest` holds the ranked ids of speakable candidates not already named
        (D8 paging, step 1.8): key 9 on the last named scheme pages in the next
        OVERFLOW_READ_CAP of them, extending `named` in place, instead of leaving.
        """
        ix = 0
        just_paged = False
        pending_section: tuple[str, str] | None = None

        while ix < len(named):
            sid = named[ix]
            # 1. Play this scheme + its menu
            block = Terminals.render_scheme_block(sid, corpus=corpus, include_section_menu=True)
            if ix > 0 and not just_paged:
                audio.say(("next_scheme_intro", *block))
            else:
                audio.say(tuple(block))
            just_paged = False

            heard: set[str] = set()
            replays = 0

            # 2. Wait loop for this scheme's menu
            while True:
                # Set current_scheme to the scheme just read before each wait
                Engine.current_scheme = sid
                setattr(audio, "current_scheme", sid)

                rb_inp = audio.next_input(profile="readback")

                if pending_section is not None:
                    p_sid, p_sec = pending_section
                    if not (hasattr(audio, "was_cut") and audio.was_cut(f"scheme:{p_sid}:{p_sec}")):
                        sections_heard[p_sid].append(p_sec)
                    pending_section = None

                if isinstance(rb_inp, Hangup):
                    audio.hangup()
                    Engine.current_scheme = None
                    setattr(audio, "current_scheme", None)
                    return False

                if isinstance(rb_inp, Silence):
                    if (hasattr(audio, "was_cut") and audio.was_cut("")) or bool(getattr(rb_inp, "cut_clip", "")):
                        replays += 1
                        if replays > tunables.READBACK_REPLAY_MAX:
                            replays = 0
                            ix += 1
                            if ix < len(named):
                                break  # Move to next scheme
                            else:
                                audio.say(("no_more_schemes",))
                                Engine.current_scheme = None
                                setattr(audio, "current_scheme", None)
                                return True
                        audio.say(("unclear_prompt", SECTION_MENU))
                        continue
                    # Real silence on the menu: say so, play the menu again, wait again.
                    # The ladder, not the menu, decides when a caller who left is let go.
                    if _answer_silence(audio, log, rb_inp.n, turn_n, (SECTION_MENU,)):
                        continue
                    Engine.current_scheme = None
                    setattr(audio, "current_scheme", None)
                    audio.hangup()
                    return False

                if (
                    qa is not None
                    and isinstance(rb_inp, Speech)
                    and Engine._try_question(
                        audio, qa["model"], corpus, log, qa, rb_inp, qa["mode"], turn_n,
                        scheme_ids=[sid],
                        asked="section_menu",
                    )
                ):
                    audio.say((SECTION_MENU,))  # Question answered; replay section menu
                    continue

                if not isinstance(rb_inp, Digit):
                    replays += 1
                    if replays > tunables.READBACK_REPLAY_MAX:
                        replays = 0
                        ix += 1
                        if ix < len(named):
                            break  # Move to next scheme
                        else:
                            audio.say(("no_more_schemes",))
                            Engine.current_scheme = None
                            setattr(audio, "current_scheme", None)
                            return True
                    audio.say(("unclear_prompt", SECTION_MENU))
                    continue

                key = rb_inp.digit
                if key in Engine.SECTION_KEYS and key not in heard:
                    means = "read " + Engine.SECTION_KEYS[key].replace("_", " ")
                else:
                    means = {"*": "change language", "#": "repeat", "0": "stop reading"}.get(
                        key, "next scheme" if key in Engine.SECTION_KEYS or key == "9" else "not on the menu")
                _log_key(log, key, means)

                if key == "*":
                    new_lang = _next_lang(getattr(audio, "language", "hi"))
                    if hasattr(audio, "language"):
                        audio.language = new_lang
                    log.write(LangSwitchRecord(
                        lang=new_lang,
                        lang_source="keypad",
                        turn_n=turn_n,
                    ))
                    audio.say(tuple(Terminals.render_scheme_block(sid, corpus=corpus, include_section_menu=True)))
                    continue

                if key in Engine.SECTION_KEYS and key not in heard:
                    heard.add(key)
                    replays = 0
                    section = Engine.SECTION_KEYS[key]
                    pending_section = (sid, section)
                    audio.say((
                        SECTION_SOURCE_FRAME,
                        f"scheme:{sid}:{section}",
                        SECTION_MENU,
                    ))
                    continue

                if key in Engine.SECTION_KEYS:
                    key = "9"

                if key == "#":
                    audio.repeat()
                    continue

                if key == "9":
                    replays = 0
                    if ix == len(named) - 1 and rest:
                        page = rest[:tunables.OVERFLOW_READ_CAP]
                        del rest[:tunables.OVERFLOW_READ_CAP]
                        audio.say((RESULTS_MORE_PROMPT,))
                        for psid in page:
                            sections_heard[psid] = ["summary"]
                        named.extend(page)
                        ix += 1
                        just_paged = True
                        break  # Move to first scheme of the new page
                    ix += 1
                    if ix < len(named):
                        break  # Move to next scheme
                    else:
                        audio.say(("no_more_schemes",))
                        Engine.current_scheme = None
                        setattr(audio, "current_scheme", None)
                        return True

                if key == "0":
                    if pending_section is not None:
                        p_sid, p_sec = pending_section
                        if not (hasattr(audio, "was_cut") and audio.was_cut(f"scheme:{p_sid}:{p_sec}")):
                            sections_heard[p_sid].append(p_sec)
                        pending_section = None
                    Engine.current_scheme = None
                    setattr(audio, "current_scheme", None)
                    return True

                # Unmapped digits (5-8):
                replays += 1
                if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                    audio.trace.input_event(
                        prompt_n=getattr(rb_inp, "prompt_n", -1),
                        prompt="readback",
                        event="key",
                        value=str(key),
                        took=False,
                        why="not_on_menu",
                    )
                if replays > tunables.READBACK_REPLAY_MAX:
                    replays = 0
                    ix += 1
                    if ix < len(named):
                        break
                    else:
                        audio.say(("no_more_schemes",))
                        Engine.current_scheme = None
                        setattr(audio, "current_scheme", None)
                        return True
                audio.say(("unclear_prompt", SECTION_MENU))

        if pending_section is not None:
            p_sid, p_sec = pending_section
            if not (hasattr(audio, "was_cut") and audio.was_cut(f"scheme:{p_sid}:{p_sec}")):
                sections_heard[p_sid].append(p_sec)
        Engine.current_scheme = None
        setattr(audio, "current_scheme", None)
        return True


run_call = Engine.run_call
