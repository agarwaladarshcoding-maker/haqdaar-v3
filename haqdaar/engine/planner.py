"""haqdaar/engine/planner.py

Pure questioning and widening planner for Haqdaar v2.
Implements D3 minimax scoring, speaking-rule exception, widen ladder, and stop conditions.
Follows T10, T11, T15, T18, 04-INTERFACES, and tunables.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Union

from haqdaar.contracts import tunables
from haqdaar.contracts.log_schema import (
    STOP_LE_4_SURVIVORS,
    STOP_MAX_QUESTIONS,
    STOP_MAX_TURNS,
    STOP_NO_SPLIT,
    STOP_ZERO_SURVIVORS,
)
from haqdaar.contracts.types import (
    Ask,
    BoxId,
    HARD_BOXES,
    SEVEN_BOXES,
    Stop,
    UNASKED,
    UNKNOWN,
    ValueCode,
    Widen,
    WIDENING_ORDER,
)
from haqdaar.engine.filter import Filter
from haqdaar.engine.terminals import _filter_speakable

EXPECTED_TURNS_KEYPAD: int = 1
EXPECTED_TURNS_SPOKEN: int = 2

# 1.3a: the fixed easy-first order for breaking minimax ties. The kind of help
# first, then what callers say most readily on a spoken call: their work, age,
# who it is for, where they live, their group, income last.
EASY_FIRST: tuple[BoxId, ...] = (
    "category",
    "occupation",
    "age",
    "gender",
    "state",
    "social_category",
    "income_band",
)


def _is_answered(box: BoxId, val: Optional[ValueCode], corpus: Any) -> bool:
    """Return True if box is answered with a valid in-corpus value."""
    if val is None or val == UNASKED or val == UNKNOWN:
        return False
    vals = corpus.values(box)
    if not vals or val not in vals:
        return False
    return True


def _is_askable(box: BoxId, val: Optional[ValueCode], corpus: Any) -> bool:
    """Check if a box can be asked.

    - Skip answered boxes (in-corpus value).
    - Skip UNKNOWN boxes permanently (UNASKED stays askable, UNKNOWN does not).
    - Out-of-set answers must come back as a re-ask.
    """
    if val == UNKNOWN:
        return False
    if val is None or val == UNASKED:
        return True
    vals = corpus.values(box)
    if not vals or val not in vals:
        return True  # Out-of-set value is treated as unasked / re-askable
    return False


def _expected_turns(box: BoxId, corpus: Any) -> int:
    """Expected turns for answering box: Keypad = 1, Spoken = 2 (T10 D2, T15)."""
    vals = corpus.values(box)
    if vals and len(vals) > tunables.KEYPAD_CARDINALITY_MAX:
        return EXPECTED_TURNS_SPOKEN
    return EXPECTED_TURNS_KEYPAD


def _box_splits_survivors(
    box: BoxId,
    survivors: Sequence[int],
    box_vector: Mapping[BoxId, ValueCode],
    corpus: Any,
) -> bool:
    """Check if asking box can split the survivors.

    Skip any box where every survivor holds the same value (or all are ANY).
    A box splits survivors if there is at least one candidate value where
    some survivors survive and some are eliminated (0 < survivors_count < n).
    """
    n = len(survivors)
    if n <= 1:
        return False
    vals = corpus.values(box)
    if not vals:
        return False
    for v in vals:
        candidate_vector = {**box_vector, box: v}
        cnt = len(Filter.survivors(candidate_vector, corpus))
        if 0 < cnt < n:
            return True
    return False


def _is_scheme_non_any(scheme_ix: int, box: BoxId, corpus: Any) -> bool:
    """Return True if scheme requires specific value(s) for box (is non-ANY)."""
    bit = 1 << scheme_ix
    vals = corpus.values(box)
    if not vals:
        return False
    for v in vals:
        if not bool(corpus.mask(box, v) & bit):
            return True
    return False


def _minimax_score(
    box: BoxId,
    survivors: Sequence[int],
    box_vector: Mapping[BoxId, ValueCode],
    corpus: Any,
) -> float:
    """Minimax elimination divided by expected turns (T10 D2, D3)."""
    n = len(survivors)
    vals = corpus.values(box)
    if not vals:
        return 0.0
    surv_counts = [
        len(Filter.survivors({**box_vector, box: v}, corpus))
        for v in vals
    ]
    max_remaining = max(surv_counts) if surv_counts else n
    elimination = n - max_remaining
    turns = _expected_turns(box, corpus)
    return elimination / turns


def _average_remaining(
    box: BoxId,
    box_vector: Mapping[BoxId, ValueCode],
    corpus: Any,
) -> float:
    """1.3a: the mean schemes left over the box's answers (fewer is better).

    The second step of the tie rule: of two boxes whose worst answer leaves
    the same count, the one that leaves fewer on average asks first.
    """
    vals = corpus.values(box)
    if not vals:
        return 0.0
    counts = [
        len(Filter.survivors({**box_vector, box: v}, corpus))
        for v in vals
    ]
    return sum(counts) / len(counts)


def _pick_best(
    boxes: Sequence[BoxId],
    survivors: Sequence[int],
    box_vector: Mapping[BoxId, ValueCode],
    corpus: Any,
) -> BoxId:
    """1.3a: worst answer leaves the fewest; ties: fewer left on average,
    then the fixed easy-first order. No model, no chance."""
    order = {b: n for n, b in enumerate(EASY_FIRST)}
    best = boxes[0]
    best_key = (0.0, 0.0, 0)
    for b in boxes:
        score = _minimax_score(b, survivors, box_vector, corpus)
        avg = _average_remaining(b, box_vector, corpus)
        key = (score, -avg, -order.get(b, len(order)))
        if b == boxes[0] or key > best_key:
            best, best_key = b, key
    return best


def _cap_stop(
    turn_count: Optional[int],
    question_count: Optional[int],
    box_vector: Mapping[BoxId, ValueCode],
    corpus: Any,
) -> Optional[Stop]:
    """Return the Stop a budget cap forces, or None if there is room to ask."""
    if turn_count is not None and turn_count >= tunables.MAX_TURNS:
        return Stop(STOP_MAX_TURNS)
    eff_q = (
        question_count
        if question_count is not None
        else _inferred_questions(box_vector, corpus)
    )
    if eff_q >= tunables.MAX_QUESTIONS:
        return Stop(STOP_MAX_QUESTIONS)
    return None


def _hard_box_to_ask_before_speaking(
    candidates: Sequence[int],
    box_vector: Mapping[BoxId, ValueCode],
    corpus: Any,
) -> Optional[BoxId]:
    """The speaking-rule exception, as one rule for every terminal.

    T10 D4 states it for the "<=4 survivors" stop: do not stop while an unasked
    hard box is non-ANY on any survivor, "or the call stops holding schemes it
    is not allowed to speak". The reason has nothing to do with how the
    candidates were obtained. A widened match and a nearest are held under the
    same truth lock (`Filter.speakable`), so leaving a hard box unasked gags
    them too, and the caller hears an empty terminal over a corpus that held
    something. Applied to whichever set the terminal is about to speak.

    Returns the box to ask (minimax order, ties on snapshot order), or None.
    """
    if not candidates:
        return None
    unasked_non_any_hard = [
        h
        for h in SEVEN_BOXES
        if h in HARD_BOXES
        and _is_askable(h, box_vector.get(h), corpus)
        and any(_is_scheme_non_any(s, h, corpus) for s in candidates)
    ]
    if not unasked_non_any_hard:
        return None
    return _pick_best(unasked_non_any_hard, candidates, box_vector, corpus)


def _nearest_candidates(
    box_vector: Mapping[BoxId, ValueCode],
    corpus: Any,
) -> list[int]:
    """Schemes the Nearest terminal could speak: miss-set holds no hard box.

    Deliberately does NOT apply Filter.speakable(). An unasked hard box is not
    a miss, so a scheme can look like a nearest candidate here and still be
    ungagged only after that box is asked. That is exactly the gap
    _hard_box_to_ask_before_speaking() exists to close.
    """
    total = 0
    if corpus is not None and hasattr(corpus, "_scheme_ids"):
        total = len(corpus._scheme_ids)
    elif corpus is not None and hasattr(corpus, "scheme_id"):
        while corpus.scheme_id(total) != "":
            total += 1
    return [
        ix
        for ix in range(total)
        if not Filter.miss_set(box_vector, corpus, ix).intersection(HARD_BOXES)
    ]


def _inferred_questions(box_vector: Mapping[BoxId, ValueCode], corpus: Any) -> int:
    """Count questions asked so far from box_vector (opener is turn 0, not question 0).

    Used only when question_count is omitted (e.g. offline tests or standalone calls).
    Excludes `category` because per T10 D2 the category opener prompt is turn 0, not
    a demographic question chosen by the minimax planner. Live engine runs pass the
    actual runtime `question_count` explicitly.
    """
    count = 0
    for b in SEVEN_BOXES:
        if b == "category":
            continue
        val = box_vector.get(b)
        if val is not None and val != UNASKED:
            count += 1
    return count


def next_action(
    box_vector: Mapping[BoxId, ValueCode],
    corpus: Any,
    *,
    turn_count: Optional[int] = None,
    question_count: Optional[int] = None,
    stop_survivors: Optional[int] = None,
) -> Union[Ask, Widen, Stop]:
    """Determine next action for Haqdaar v2 questioning loop.

    Signature: next_action(box_vector, corpus) -> Ask(box) | Widen(box) | Stop(reason).
    `stop_survivors` moves the short-list stop (keys keep STOP_SURVIVORS; the
    talk loop asks down to 2).
    """
    stop_at = tunables.STOP_SURVIVORS if stop_survivors is None else stop_survivors
    surv = Filter.survivors(box_vector, corpus)
    n_surv = len(surv)

    # 1. Zero survivors: widening ladder or STOP_ZERO_SURVIVORS (T18 §1)
    if n_surv == 0:
        answered_soft: list[BoxId] = [
            b for b in WIDENING_ORDER if _is_answered(b, box_vector.get(b), corpus)
        ]
        if not answered_soft:
            # No rung to walk. The terminal is Nearest or Empty, so the
            # speaking-rule exception is the only thing left to check.
            gag = _hard_box_to_ask_before_speaking(
                _nearest_candidates(box_vector, corpus), box_vector, corpus
            )
            if gag is not None:
                capped = _cap_stop(turn_count, question_count, box_vector, corpus)
                return capped if capped is not None else Ask(gag)
            return Stop(STOP_ZERO_SURVIVORS)

        dropped: set[BoxId] = set()
        for rung_box in answered_soft:
            dropped.add(rung_box)
            test_vector = {k: v for k, v in box_vector.items() if k not in dropped}
            widened = Filter.survivors(test_vector, corpus)
            if len(widened) >= 1:
                gag = _hard_box_to_ask_before_speaking(widened, box_vector, corpus)
                if gag is not None:
                    capped = _cap_stop(turn_count, question_count, box_vector, corpus)
                    return capped if capped is not None else Ask(gag)
                speakable_widened = _filter_speakable(widened, test_vector, corpus)
                if len(speakable_widened) >= 1:
                    return Widen(rung_box)

        # The ladder found nothing. The terminal will be Nearest or Empty, and
        # the same rule applies to the nearest candidates.
        gag = _hard_box_to_ask_before_speaking(
            _nearest_candidates(box_vector, corpus), box_vector, corpus
        )
        if gag is not None:
            capped = _cap_stop(turn_count, question_count, box_vector, corpus)
            return capped if capped is not None else Ask(gag)

        return Stop(STOP_ZERO_SURVIVORS)

    # 2. Short-list check with Speaking-Rule Exception (T10 D3, D4)
    if n_surv <= stop_at:
        # Do not stop on "<=4" while an unasked hard box is non-ANY on any survivor.
        unasked_non_any_hard = [
            h
            for h in SEVEN_BOXES
            if h in HARD_BOXES
            and _is_askable(h, box_vector.get(h), corpus)
            and any(_is_scheme_non_any(s, h, corpus) for s in surv)
        ]
        if not unasked_non_any_hard:
            return Stop(STOP_LE_4_SURVIVORS)

        # Budget cap checks before asking
        if turn_count is not None and turn_count >= tunables.MAX_TURNS:
            return Stop(STOP_MAX_TURNS)
        eff_q = (
            question_count
            if question_count is not None
            else _inferred_questions(box_vector, corpus)
        )
        if eff_q >= tunables.MAX_QUESTIONS:
            return Stop(STOP_MAX_QUESTIONS)

        # Ask the qualifying hard box in 1.3a tie order (worst, average, easy-first).
        return Ask(_pick_best(unasked_non_any_hard, surv, box_vector, corpus))

    # 3. Budget caps: 8 turns OR 6 questions (T10 D4)
    if turn_count is not None and turn_count >= tunables.MAX_TURNS:
        return Stop(STOP_MAX_TURNS)
    eff_q = (
        question_count
        if question_count is not None
        else _inferred_questions(box_vector, corpus)
    )
    if eff_q >= tunables.MAX_QUESTIONS:
        return Stop(STOP_MAX_QUESTIONS)

    # 4. Filter askable boxes that split survivors
    askable_boxes = [
        b
        for b in SEVEN_BOXES
        if _is_askable(b, box_vector.get(b), corpus)
        and _box_splits_survivors(b, surv, box_vector, corpus)
    ]

    if not askable_boxes:
        return Stop(STOP_NO_SPLIT)

    # 5. Minimax elimination divided by expected turns; 1.3a tie order.
    return Ask(_pick_best(askable_boxes, surv, box_vector, corpus))


class Planner:
    """Namespace wrapper providing static next_action conforming to 04-INTERFACES."""

    @staticmethod
    def next_action(
        box_vector: Mapping[BoxId, ValueCode],
        corpus: Any,
        *,
        turn_count: Optional[int] = None,
        question_count: Optional[int] = None,
        stop_survivors: Optional[int] = None,
    ) -> Union[Ask, Widen, Stop]:
        return next_action(
            box_vector,
            corpus,
            turn_count=turn_count,
            question_count=question_count,
            stop_survivors=stop_survivors,
        )
