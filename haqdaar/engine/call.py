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

import time
from typing import Any, Mapping, Optional

from haqdaar.contracts import tunables
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
    SEVEN_BOXES,
    Silence,
    Speech,
    Stop,
    UNASKED,
    UNKNOWN,
    Widen,
    WIDENING_ORDER,
)
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
    return "mr" if curr_lang == "hi" else ("en" if curr_lang == "mr" else "hi")


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


def _door_a_pick(audio: Any, s1: str, s2: str) -> str | None:
    """Door A 2-candidate keypad turn (T12): name both, press 1/2/3.

    Returns "1"/"2" (picked), "hangup", or None (0/3/anything else declines).
    One turn, no repeats.
    """
    audio.say(("door_a_option_1", scheme_name_chunk(s1),
               "door_a_option_2", scheme_name_chunk(s2),
               "door_a_option_none"))
    pick = audio.next_input(profile="normal")
    if isinstance(pick, Hangup):
        return "hangup"
    if isinstance(pick, Digit) and pick.digit in ("1", "2"):
        return pick.digit
    return None


class Engine:
    """Stateful orchestrator for a single phone call."""

    @staticmethod
    def run_call(
        audio: Any,
        model: Any,
        corpus: Any,
        log: Log,
    ) -> None:
        """Run a single call from connect to hangup."""
        # --- 1. Turn 0: Language Selection ---
        if hasattr(audio, "select_language"):
            lang, lang_source = audio.select_language()
        else:
            audio.say(("greeting_trilingual",))
            inp = audio.next_input(profile="turn0")
            if isinstance(inp, Digit):
                if inp.digit == "1":
                    lang, lang_source = "hi", "keypad"
                elif inp.digit == "2":
                    lang, lang_source = "mr", "keypad"
                elif inp.digit == "3":
                    lang, lang_source = "en", "keypad"
                else:
                    lang, lang_source = "hi", "default"
            else:
                lang, lang_source = "hi", "default"

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

        # --- 2. Consent Notice ---
        audio.say(("consent_notice",))

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

                is_box_keypad = (mode == "keypad_only") or (box_strikes[box] >= tunables.BOX_STRIKES_TO_KEYPAD)

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
                        prompt_id = "opener_prompt"
                    elif box == "state":
                        prompt_id = "state_q_maharashtra"
                    elif box_strikes[box] == 1:
                        prompt_id = f"rephrase_{box}"
                    else:
                        prompt_id = f"q_{box}"
                    audio.say((prompt_id,))
                    inp = audio.next_input(profile="spoken")

                if isinstance(inp, Silence):
                    rung = inp.n if (hasattr(inp, "n") and inp.n) else (silence_ladder + 1)
                    silence_ladder = rung
                    # SILENCE leaves turn_n unchanged and logs silence_n
                    log.write(TurnLogRecord(
                        turn_n=turn_n,
                        turn_class="SILENCE",
                        silence_n=rung,
                    ))
                    if rung == 1:
                        audio.repeat()
                        continue
                    elif rung == 2:
                        audio.say(("silence_presence",))
                        continue
                    else:
                        # Rung 3: closing farewell + hangup
                        audio.say(("closing_farewell",))
                        if hasattr(audio, "on_mark"):
                            audio.on_mark("closing_farewell")
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
                    if box_strikes[box] >= tunables.BOX_STRIKES_TO_KEYPAD:
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
                        audio.repeat()
                    if turn_n >= tunables.MAX_TURNS:
                        stop_reason = STOP_MAX_TURNS
                        break
                    continue

                elif isinstance(inp, Hangup):
                    audio.hangup()
                    return

                elif isinstance(inp, Digit):
                    silence_ladder = 0
                    digit = inp.digit

                    # Control keys
                    if digit == "#":
                        audio.repeat()
                        continue
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
                        audio.repeat()
                        continue
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
                        if turn_n >= tunables.MAX_TURNS:
                            stop_reason = STOP_MAX_TURNS
                            break
                        if question_count >= tunables.MAX_QUESTIONS:
                            stop_reason = STOP_MAX_QUESTIONS
                            break
                        continue

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
                    else:
                        # Out of menu digit
                        box_strikes[box] += 1
                        log.write(TurnLogRecord(
                            turn_n=turn_n,
                            turn_class="UNCLEAR",
                            transcript=str(digit),
                        ))
                        if box_strikes[box] >= tunables.BOX_STRIKES_TO_KEYPAD:
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
                            audio.repeat()

                    if turn_n >= tunables.MAX_TURNS:
                        stop_reason = STOP_MAX_TURNS
                        break
                    if question_count >= tunables.MAX_QUESTIONS:
                        stop_reason = STOP_MAX_QUESTIONS
                        break

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
                        if box_strikes[box] >= tunables.BOX_STRIKES_TO_KEYPAD:
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
                            audio.repeat()
                        if turn_n >= tunables.MAX_TURNS:
                            stop_reason = STOP_MAX_TURNS
                            break
                        continue

                    # --- Voice mode: process spoken answer via model ---
                    turn_n += 1
                    curr_lang = getattr(audio, "language", "hi")
                    proposed_val = None
                    proposed_span = ""

                    if box == "category":
                        # Door A (T12/ARCH §6): exact code match before the model.
                        # Unavailable in keypad-only mode (this is the voice branch).
                        door = DoorA.from_corpus(corpus)
                        door_t0 = time.monotonic()
                        dres = door.match(transcript, lang=curr_lang)
                        door_a_read = False
                        model_failed = False
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
                                    model_failed = True
                                    seeds = []
                            else:
                                seeds = []  # clean naming: zero model calls (T12)
                        elif dres.action == "keypad_pick":
                            s1, s2 = dres.scheme_ids[0], dres.scheme_ids[1]
                            outcome = _door_a_pick(audio, s1, s2)
                            turn_n += 1
                            question_count += 1  # T12: the pick costs 1 turn against the six
                            if outcome == "hangup":
                                audio.hangup()
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
                            if len(model_ids) == 1:
                                span = next(s.span for s in res if s.box == "scheme")
                                _door_a_read(audio, log, model_ids[0], transcript,
                                             span, turn_n, 1, door_t0)
                                turn_n += 1
                                door_a_done = True
                                door_a_read = True
                            elif len(model_ids) == 2:
                                outcome = _door_a_pick(audio, model_ids[0], model_ids[1])
                                turn_n += 1
                                question_count += 1
                                if outcome == "hangup":
                                    audio.hangup()
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
                            continue
                    else:
                        res = model.turn(transcript, box=box, ask_count=box_strikes[box])
                        if hasattr(res, "box") and hasattr(res, "value") and res.value:
                            proposed_val = res.value
                            proposed_span = getattr(res, "span", transcript)

                    if not proposed_val:
                        # Model did not understand speech -> UNCLEAR
                        box_strikes[box] += 1
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
                        elif box_strikes[box] < tunables.BOX_STRIKES_TO_KEYPAD:
                            audio.say(("unclear_prompt",))
                        if turn_n >= tunables.MAX_TURNS:
                            stop_reason = STOP_MAX_TURNS
                            break
                        continue

                    # Model understood proposed_val!
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
                                    if box_strikes[box] < tunables.BOX_STRIKES_TO_KEYPAD:
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
                                    if box_strikes[box] < tunables.BOX_STRIKES_TO_KEYPAD:
                                        audio.say(("unclear_prompt",))
                                    break
                                continue
                            elif confirm_inp.digit == "1":
                                # CONFIRM ACCEPT: caller confirmed!
                                turn_n += 1
                                box_vector[box] = proposed_val
                                box_strikes[box] = 0
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
                                if box_strikes[box] < tunables.BOX_STRIKES_TO_KEYPAD:
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
                                if box_strikes[box] < tunables.BOX_STRIKES_TO_KEYPAD:
                                    audio.say(("unclear_prompt",))
                                break

                        elif isinstance(confirm_inp, Silence):
                            rung = confirm_inp.n if (hasattr(confirm_inp, "n") and confirm_inp.n) else (silence_ladder + 1)
                            silence_ladder = rung
                            log.write(TurnLogRecord(
                                turn_n=turn_n,
                                turn_class="SILENCE",
                                silence_n=rung,
                            ))
                            if rung == 1:
                                audio.repeat()
                                confirm_repeats += 1
                                if confirm_repeats >= tunables.CONFIRM_REPEAT_MAX:
                                    turn_n += 1
                                    box_strikes[box] += 1
                                    log.write(TurnLogRecord(
                                        turn_n=turn_n,
                                        turn_class="UNCLEAR",
                                        transcript="silence_limit",
                                    ))
                                    if box_strikes[box] < tunables.BOX_STRIKES_TO_KEYPAD:
                                        audio.say(("unclear_prompt",))
                                    break
                                continue
                            elif rung == 2:
                                audio.say(("silence_presence",))
                                confirm_repeats += 1
                                if confirm_repeats >= tunables.CONFIRM_REPEAT_MAX:
                                    turn_n += 1
                                    box_strikes[box] += 1
                                    log.write(TurnLogRecord(
                                        turn_n=turn_n,
                                        turn_class="UNCLEAR",
                                        transcript="silence_limit",
                                    ))
                                    if box_strikes[box] < tunables.BOX_STRIKES_TO_KEYPAD:
                                        audio.say(("unclear_prompt",))
                                    break
                                continue
                            else:
                                audio.say(("closing_farewell",))
                                if hasattr(audio, "on_mark"):
                                    audio.on_mark("closing_farewell")
                                audio.hangup()
                                survs_s = Filter.survivors(box_vector, corpus)
                                silence_stop = (
                                    STOP_ZERO_SURVIVORS if len(survs_s) == 0
                                    else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT)
                                )
                                log.close(reason=silence_stop, ladder_rung=ladder_rung, mode=mode)
                                return

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
                            elif box_strikes[box] < tunables.BOX_STRIKES_TO_KEYPAD:
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
                                if box_strikes[box] < tunables.BOX_STRIKES_TO_KEYPAD:
                                    audio.say(("unclear_prompt",))
                                break
                            else:
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
                                elif box_strikes[box] < tunables.BOX_STRIKES_TO_KEYPAD:
                                    audio.say(("unclear_prompt",))
                                break

                        elif isinstance(confirm_inp, Hangup):
                            audio.hangup()
                            return

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
            audio.say(terminal_seq)

            # --- D9: Delivery log ---
            # Every named scheme in terminal_seq already had its name+summary
            # spoken by the audio.say() above, regardless of what the caller
            # does next in the read-back menu. So "summary" is seeded for all
            # of them up front; _read_back appends any extra section the
            # caller actually asks for, and the record is written once each,
            # after the caller's interaction with that terminal is fully known
            # (simplest correct point -- one write per scheme, no rewrites).
            named = [
                t.split(":", 1)[1] for t in terminal_seq if t.startswith("name:")
            ]

            # --- 6. Read-Back Menu ---
            # section_menu plays after each named scheme. 1-4 replay a section
            # behind section_source_frame, 9 advances (or pages in more, D8),
            # * switches language and replays, 0 leaves, other keys replay the menu.
            if SECTION_MENU in terminal_seq:
                sections_heard: dict[str, list[str]] = {n: ["summary"] for n in named}
                # D8 paging: candidate_survs holds every speakable candidate this
                # terminal resolved, not just the ones named so far (direct match
                # names all of them, so this is empty there; overflow and a >4
                # widened match name only the top OVERFLOW_READ_CAP).
                rest = [sid for sid in ranked_ids if sid not in named]
                kept_going = Engine._read_back(audio, named, sections_heard, rest, corpus, log, turn_n)
                cur_lang = getattr(audio, "language", lang)
                for n in named:
                    log.write(DeliveryRecord(
                        slug=n,
                        ending=shape,
                        sections=sections_heard[n],
                        lang=cur_lang,
                    ))
                if not kept_going:
                    log.close(reason=STOP_ZERO_SURVIVORS if not survs else STOP_LE_4_SURVIVORS,
                              ladder_rung=ladder_rung, mode=mode)
                    return
            elif named:
                # Nearest: "Restraint: summary only, NO section_menu,
                # auto-advance" (terminals.py nearest()) -- there is no later
                # touch point for these schemes, so write here.
                cur_lang = getattr(audio, "language", lang)
                for n in named:
                    log.write(DeliveryRecord(
                        slug=n,
                        ending=shape,
                        sections=["summary"],
                        lang=cur_lang,
                    ))

            # --- 7. Anything Else ---
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
            is_yes = False
            if isinstance(ae_inp, Digit):
                if ae_inp.digit == "1":
                    is_yes = True
            elif isinstance(ae_inp, Speech):
                spk = str(getattr(ae_inp, "text", "") or "").strip().lower()
                if model is not None and hasattr(model, "confirm"):
                    confirmed = model.confirm(spk, lang=getattr(audio, "language", None))
                else:
                    confirmed = None
                if confirmed is True:
                    is_yes = True
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
    ) -> bool:
        """Drive the read-back menu. Returns False if the caller hung up.

        Appends each section actually played to sections_heard[<scheme>] (D9),
        so the caller writes one DeliveryRecord per scheme once this returns.
        `rest` holds the ranked ids of speakable candidates not already named
        (D8 paging, step 1.8): key 9 on the last named scheme pages in the next
        OVERFLOW_READ_CAP of them, extending `named` in place, instead of leaving.
        """
        ix = 0
        heard: set[str] = set()
        replays = 0
        while ix < len(named):
            rb_inp = audio.next_input(profile="readback")
            if isinstance(rb_inp, Hangup):
                audio.hangup()
                return False
            if isinstance(rb_inp, Silence):
                # No key on the menu is not a dead end: move on to the next scheme.
                ix += 1
                replays = 0
                continue
            if not isinstance(rb_inp, Digit):
                ix += 1
                replays = 0
                continue
            key = rb_inp.digit

            if key == "*":
                # D13's `*` cycle, shared with the question phase (_next_lang):
                # rotate language, log the switch, then replay the current
                # scheme's block in the new language. Does not advance ix.
                new_lang = _next_lang(getattr(audio, "language", "hi"))
                if hasattr(audio, "language"):
                    audio.language = new_lang
                log.write(LangSwitchRecord(
                    lang=new_lang,
                    lang_source="keypad",
                    turn_n=turn_n,
                ))
                sid = named[ix]
                audio.say((
                    mark_name(sid),
                    scheme_name_chunk(sid),
                    scheme_summary_chunk(sid),
                    mark_end(sid),
                    SECTION_MENU,
                ))
                continue

            if key in Engine.SECTION_KEYS and key not in heard:
                # Each section plays at most once per scheme. Without the guard
                # a caller (or a fake) holding one key replays it forever.
                heard.add(key)
                replays = 0
                section = Engine.SECTION_KEYS[key]
                sections_heard[named[ix]].append(section)
                audio.say((
                    SECTION_SOURCE_FRAME,
                    f"scheme:{named[ix]}:{section}",
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
                    # D8 paging: more speakable candidates than were named. Page
                    # in the next OVERFLOW_READ_CAP instead of leaving the menu.
                    page = rest[:tunables.OVERFLOW_READ_CAP]
                    del rest[:tunables.OVERFLOW_READ_CAP]
                    audio.say(Terminals.more_sequence(page, corpus))
                    for sid in page:
                        sections_heard[sid] = ["summary"]
                    named.extend(page)
                    ix += 1
                    heard = set()
                    continue
                ix += 1
                heard = set()
                if ix < len(named):
                    audio.say(("next_scheme_intro",))
                else:
                    audio.say(("no_more_schemes",))
                continue
            if key == "0":
                # 0 = none of these: leave the menu.
                return True
            # Any other digit (5-8): replay the section menu, bounded so a stuck
            # key can never loop forever. After READBACK_REPLAY_MAX replays in a
            # row on the same scheme, treat the next one as 9.
            replays += 1
            if replays > tunables.READBACK_REPLAY_MAX:
                replays = 0
                ix += 1
                heard = set()
                if ix < len(named):
                    audio.say(("next_scheme_intro",))
                else:
                    audio.say(("no_more_schemes",))
                continue
            audio.say((SECTION_MENU,))
        return True


run_call = Engine.run_call
