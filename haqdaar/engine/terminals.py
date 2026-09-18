"""haqdaar/engine/terminals.py

Pure engine module implementing Step 5 terminals.
Transforms survivors + state into an ordered say() sequence of line ids,
chips, and marks for all five delivery shapes in architecture §8:
1. Direct Match (survivors > 0 and survivors <= 4)
2. Overflow (survivors > 4)
3. Widened Match (survivors == 0, widening ladder produces >= 1 survivor)
4. Nearest (survivors == 0, ladder exhausted, >= 1 soft-miss schemes)
5. Empty (survivors == 0, ladder exhausted, 0 nearest schemes)

Invariants:
- Pure: imports only from contracts/ and Filter. No I/O, no network.
- No free text: emit line IDs and marks only.
- state_unknown_disclaimer comes first when state is UNKNOWN.
- A name:<scheme_id> mark sits immediately before each name; end:<scheme_id> after its summary.
- Nearest is summary only — no section_menu, auto-advance.
- section_source_frame never comes before a summary.
- Bad-news-first ordering: in every non-exact ending, no scheme name appears before the preamble.
- In widened match, the sequence is: preamble -> drop_* -> results_widened_lead -> names.
- Truth lock: every survivor must pass Filter.speakable() before naming.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from haqdaar.contracts import tunables
from haqdaar.contracts.types import (
    BoxId,
    HARD_BOXES,
    UNASKED,
    UNKNOWN,
    WIDENING_ORDER,
)
from haqdaar.engine.filter import Filter

# Delivery shapes (architecture §8)
DELIVERY_DIRECT_MATCH: str = "direct_match"
DELIVERY_OVERFLOW: str = "overflow"
DELIVERY_WIDENED_MATCH: str = "widened_match"
DELIVERY_NEAREST: str = "nearest"
DELIVERY_EMPTY: str = "empty"

ALL_DELIVERY_SHAPES: tuple[str, ...] = (
    DELIVERY_DIRECT_MATCH,
    DELIVERY_OVERFLOW,
    DELIVERY_WIDENED_MATCH,
    DELIVERY_NEAREST,
    DELIVERY_EMPTY,
)

# Fixed line ID constants (haqdaar/contracts/types.py FIXED_LINE_IDS)
STATE_UNKNOWN_DISCLAIMER: str = "state_unknown_disclaimer"
RESULTS_EXACT_PREAMBLE: str = "results_exact_preamble"
RESULTS_OVERFLOW: str = "results_overflow"
TERMINAL_WIDENED_PREAMBLE: str = "terminal_widened_preamble"
RESULTS_WIDENED_LEAD: str = "results_widened_lead"
TERMINAL_NEAREST_PREAMBLE: str = "terminal_nearest_preamble"
TERMINAL_EMPTY: str = "terminal_empty"
SECTION_MENU: str = "section_menu"
SECTION_SOURCE_FRAME: str = "section_source_frame"
RESULTS_MORE_PROMPT: str = "results_more_prompt"


def mark_name(scheme_id: str) -> str:
    """Return provider checkpoint mark immediately before a scheme name."""
    return f"name:{scheme_id}"


def mark_end(scheme_id: str) -> str:
    """Return provider checkpoint mark immediately after a scheme summary."""
    return f"end:{scheme_id}"


def scheme_name_chunk(scheme_id: str) -> str:
    """Return line id for a scheme's name chunk."""
    return f"scheme:{scheme_id}:name"


def scheme_summary_chunk(scheme_id: str) -> str:
    """Return line id for a scheme's summary chunk."""
    return f"scheme:{scheme_id}:summary"


def _get_scheme_id(scheme: Any, corpus: Any = None) -> str:
    """Extract scheme_id string from an index, string, or dict."""
    if isinstance(scheme, str):
        return scheme
    if isinstance(scheme, dict):
        return str(scheme.get("scheme_id", ""))
    if isinstance(scheme, int):
        if corpus is not None and hasattr(corpus, "scheme_id"):
            sid = corpus.scheme_id(scheme)
            if sid:
                return sid
        if corpus is not None and hasattr(corpus, "_scheme_ids"):
            if 0 <= scheme < len(corpus._scheme_ids):
                return str(corpus._scheme_ids[scheme])
        # Never guess a scheme id from a bitmask index. A wrong id here is a
        # wrong scheme name spoken to a caller. Fail loudly instead.
        raise ValueError(
            f"cannot resolve scheme id for index {scheme}: corpus missing or out of range"
        )
    return str(scheme)


def _get_specificity(scheme: Any, corpus: Any = None) -> int:
    """Extract specificity score for ranking (higher is more specific)."""
    if corpus is not None and hasattr(corpus, "specificity"):
        if isinstance(scheme, int):
            return corpus.specificity(scheme)
        if isinstance(scheme, str):
            if hasattr(corpus, "_scheme_ids") and scheme in corpus._scheme_ids:
                return corpus.specificity(corpus._scheme_ids.index(scheme))
    return 0


def _sort_survivors(survivors: Sequence[Any], corpus: Any = None) -> list[Any]:
    """Sort survivors by specificity descending, breaking ties deterministically."""
    def sort_key(s: Any):
        spec = _get_specificity(s, corpus)
        tie = s if isinstance(s, int) else _get_scheme_id(s, corpus)
        return (-spec, tie)

    return sorted(survivors, key=sort_key)


def ranked(survivors: Sequence[Any], corpus: Any = None) -> list[Any]:
    """Public entry point for step 1.8 paging: survivors sorted specificity -> priority ->
    slug. p6 already breaks specificity ties by bit index ordered (priority, slug)
    (step 1.8), so this is exactly _sort_survivors -- no separate tie-break needed here.
    """
    return _sort_survivors(survivors, corpus)


def more_sequence(schemes: Sequence[Any], corpus: Any = None) -> tuple[str, ...]:
    """Step 1.8: the read-back "more" page -- results_more_prompt followed by the next
    page of scheme blocks (name mark -> name -> summary -> end mark -> section_menu),
    same shape as every other terminal's scheme block.
    """
    seq: list[str] = [RESULTS_MORE_PROMPT]
    seq.extend(_render_schemes_sequence(schemes, corpus, include_section_menu=True))
    return tuple(seq)


def _is_speakable(
    scheme: Any,
    box_vector: Mapping[str, Any],
    corpus: Any,
) -> bool:
    """Truth lock: run scheme candidate through Filter.speakable()."""
    return Filter.speakable(scheme, box_vector=box_vector, corpus=corpus)


def _filter_speakable(
    survivors: Sequence[Any],
    box_vector: Mapping[str, Any] | None,
    corpus: Any,
    *,
    pre_vetted: bool = False,
) -> list[Any]:
    """Filter candidate schemes, keeping only those that pass Filter.speakable().

    Fails closed. A missing box_vector is not "nothing to check" — it is no
    ability to check, and speakable() is the only thing standing between a
    caller and a scheme that fails a hard box. Silently waving schemes through
    on an omitted kwarg is how five unspeakable schemes get named, so an
    unverifiable call raises instead.

    `pre_vetted=True` is the one way past, and it is deliberately explicit: a
    caller that has already run speakable() (or is exercising sequence shape in
    a test) must say so in writing. It cannot happen by accident.
    """
    if not survivors:
        return []
    if pre_vetted:
        return list(survivors)
    if box_vector is None:
        raise ValueError(
            "cannot name schemes without box_vector: Filter.speakable() is the "
            "truth lock and must be evaluated before any scheme is named. "
            "Pass box_vector, or pre_vetted=True if speakable() already ran."
        )
    return [s for s in survivors if _is_speakable(s, box_vector, corpus)]


def _render_schemes_sequence(
    schemes: Sequence[Any],
    corpus: Any = None,
    *,
    include_section_menu: bool = True,
) -> list[str]:
    """Render scheme blocks: name mark -> name -> summary -> end mark -> (section_menu)."""
    seq: list[str] = []
    for s in schemes:
        sid = _get_scheme_id(s, corpus)
        seq.append(mark_name(sid))
        seq.append(scheme_name_chunk(sid))
        seq.append(scheme_summary_chunk(sid))
        seq.append(mark_end(sid))
        if include_section_menu:
            seq.append(SECTION_MENU)
    return seq


def direct_match(
    survivors: Sequence[Any],
    state: str | None = None,
    corpus: Any = None,
    box_vector: Mapping[str, Any] | None = None,
    *,
    pre_vetted: bool = False,
) -> tuple[str, ...]:
    """Shape 1: Direct Match (survivors > 0 and survivors <= 4).
    Order: [state_unknown_disclaimer] -> results_exact_preamble -> schemes (by specificity).
    Each scheme: name:<sid> -> name -> summary -> end:<sid> -> section_menu.
    """
    st = state if state is not None else (box_vector.get("state") if box_vector else None)
    speakable_survs = _filter_speakable(survivors, box_vector, corpus, pre_vetted=pre_vetted)
    sorted_survs = _sort_survivors(speakable_survs, corpus)

    seq: list[str] = []
    if st == UNKNOWN:
        seq.append(STATE_UNKNOWN_DISCLAIMER)
    seq.append(RESULTS_EXACT_PREAMBLE)
    seq.extend(_render_schemes_sequence(sorted_survs, corpus, include_section_menu=True))
    return tuple(seq)


def overflow(
    survivors: Sequence[Any],
    state: str | None = None,
    corpus: Any = None,
    box_vector: Mapping[str, Any] | None = None,
    *,
    pre_vetted: bool = False,
) -> tuple[str, ...]:
    """Shape 2: Overflow (survivors > 4).
    Order: [state_unknown_disclaimer] -> results_overflow -> top 3 schemes (by specificity).
    Each scheme: name:<sid> -> name -> summary -> end:<sid> -> section_menu.
    """
    st = state if state is not None else (box_vector.get("state") if box_vector else None)
    speakable_survs = _filter_speakable(survivors, box_vector, corpus, pre_vetted=pre_vetted)
    sorted_survs = _sort_survivors(speakable_survs, corpus)
    top_n = sorted_survs[:tunables.OVERFLOW_READ_CAP]

    seq: list[str] = []
    if st == UNKNOWN:
        seq.append(STATE_UNKNOWN_DISCLAIMER)
    seq.append(RESULTS_OVERFLOW)
    seq.extend(_render_schemes_sequence(top_n, corpus, include_section_menu=True))
    return tuple(seq)


def widened_match(
    survivors: Sequence[Any],
    state: str | None = None,
    dropped_boxes: Sequence[str] = (),
    corpus: Any = None,
    box_vector: Mapping[str, Any] | None = None,
    *,
    pre_vetted: bool = False,
) -> tuple[str, ...]:
    """Shape 3: Widened Match.
    Order: [state_unknown_disclaimer] -> terminal_widened_preamble -> drop_<box>... -> results_widened_lead -> schemes.
    Schemes follow T10 delivery rule: top 3 if >4, all if <=4.
    """
    st = state if state is not None else (box_vector.get("state") if box_vector else None)
    speakable_survs = _filter_speakable(survivors, box_vector, corpus, pre_vetted=pre_vetted)
    sorted_survs = _sort_survivors(speakable_survs, corpus)
    selected = (
        sorted_survs[:tunables.OVERFLOW_READ_CAP]
        if len(sorted_survs) > tunables.STOP_SURVIVORS
        else sorted_survs
    )

    seq: list[str] = []
    if st == UNKNOWN:
        seq.append(STATE_UNKNOWN_DISCLAIMER)
    seq.append(TERMINAL_WIDENED_PREAMBLE)
    for b in dropped_boxes:
        seq.append(f"drop_{b}")
    seq.append(RESULTS_WIDENED_LEAD)
    seq.extend(_render_schemes_sequence(selected, corpus, include_section_menu=True))
    return tuple(seq)


def nearest(
    nearest_schemes: Sequence[Any],
    state: str | None = None,
    corpus: Any = None,
    box_vector: Mapping[str, Any] | None = None,
    *,
    pre_vetted: bool = False,
) -> tuple[str, ...]:
    """Shape 4: Nearest.
    Order: [state_unknown_disclaimer] -> terminal_nearest_preamble FIRST -> schemes (cap NEAREST_CAP = 2).
    Restraint: summary only, NO section_menu, auto-advance.
    """
    st = state if state is not None else (box_vector.get("state") if box_vector else None)
    speakable_near = _filter_speakable(nearest_schemes, box_vector, corpus, pre_vetted=pre_vetted)
    capped_near = speakable_near[:tunables.NEAREST_CAP]

    seq: list[str] = []
    if st == UNKNOWN:
        seq.append(STATE_UNKNOWN_DISCLAIMER)
    seq.append(TERMINAL_NEAREST_PREAMBLE)
    seq.extend(_render_schemes_sequence(capped_near, corpus, include_section_menu=False))
    return tuple(seq)


def empty(
    state: str | None = None,
    box_vector: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """Shape 5: Empty.
    Order: [state_unknown_disclaimer] -> terminal_empty.
    Nothing read (no schemes or summaries).
    """
    st = state if state is not None else (box_vector.get("state") if box_vector else None)
    seq: list[str] = []
    if st == UNKNOWN:
        seq.append(STATE_UNKNOWN_DISCLAIMER)
    seq.append(TERMINAL_EMPTY)
    return tuple(seq)


def classify_shape(
    survivors: Sequence[Any] | None = None,
    state: str | None = None,
    box_vector: Mapping[str, Any] | None = None,
    corpus: Any = None,
    *,
    dropped_boxes: Sequence[str] | None = None,
    pre_vetted: bool = False,
) -> tuple[str, list[Any], list[str]]:
    """Determine delivery shape and resolve speakable schemes and dropped boxes.
    Returns (shape_name, resolved_schemes, resolved_dropped_boxes).
    """
    # 1. Resolve survivors
    if survivors is not None:
        raw_survs = list(survivors)
    elif box_vector is not None and corpus is not None:
        raw_survs = list(Filter.survivors(box_vector, corpus))
    else:
        raw_survs = []

    # 2. Filter through speakable truth lock
    speakable_survs = _filter_speakable(raw_survs, box_vector, corpus, pre_vetted=pre_vetted)

    # 3. If speakable survivors exist: Direct or Overflow
    if len(speakable_survs) > 0:
        if len(speakable_survs) <= tunables.STOP_SURVIVORS:
            return DELIVERY_DIRECT_MATCH, speakable_survs, []
        return DELIVERY_OVERFLOW, speakable_survs, []

    # 4. Zero speakable survivors: check widening ladder
    if dropped_boxes is not None and len(dropped_boxes) > 0:
        return DELIVERY_WIDENED_MATCH, speakable_survs, list(dropped_boxes)

    if box_vector is not None and corpus is not None:
        # Run widening ladder over soft boxes
        accumulated_drops: list[str] = []
        for box in WIDENING_ORDER:
            val = box_vector.get(box)
            if val is None or val == UNASKED or val == UNKNOWN:
                continue
            accumulated_drops.append(box)
            widened_vec = {k: v for k, v in box_vector.items() if k not in accumulated_drops}
            ladder_raw = Filter.survivors(widened_vec, corpus)
            ladder_speakable = _filter_speakable(ladder_raw, widened_vec, corpus)
            if len(ladder_speakable) >= 1:
                return DELIVERY_WIDENED_MATCH, ladder_speakable, accumulated_drops

        # Ladder exhausted: check nearest
        near_candidates = Filter.nearest(box_vector, corpus)
        near_speakable = _filter_speakable(near_candidates, box_vector, corpus)
        if len(near_speakable) >= 1:
            return DELIVERY_NEAREST, near_speakable[:tunables.NEAREST_CAP], []

    return DELIVERY_EMPTY, [], []


def terminal_sequence(
    survivors: Sequence[Any] | None = None,
    state: str | None = None,
    box_vector: Mapping[str, Any] | None = None,
    corpus: Any = None,
    *,
    dropped_boxes: Sequence[str] | None = None,
    shape: str | None = None,
    pre_vetted: bool = False,
) -> tuple[str, ...]:
    """Produce the ordered say() sequence of line ids, chips, and marks for a terminal."""
    # Defensive handling if box_vector was passed positionally first
    if isinstance(survivors, Mapping) and box_vector is None:
        box_vector = survivors
        corpus = state
        survivors = None
        state = None

    resolved_shape, resolved_schemes, resolved_drops = classify_shape(
        survivors=survivors,
        state=state,
        box_vector=box_vector,
        corpus=corpus,
        dropped_boxes=dropped_boxes,
        pre_vetted=pre_vetted,
    )

    chosen_shape = shape or resolved_shape

    if chosen_shape == DELIVERY_DIRECT_MATCH:
        schemes = resolved_schemes if survivors is None else survivors
        return direct_match(schemes, state=state, corpus=corpus, box_vector=box_vector, pre_vetted=pre_vetted)

    if chosen_shape == DELIVERY_OVERFLOW:
        schemes = resolved_schemes if survivors is None else survivors
        return overflow(schemes, state=state, corpus=corpus, box_vector=box_vector, pre_vetted=pre_vetted)

    if chosen_shape == DELIVERY_WIDENED_MATCH:
        schemes = resolved_schemes if survivors is None else survivors
        drops = dropped_boxes if dropped_boxes is not None else resolved_drops
        return widened_match(schemes, state=state, dropped_boxes=drops, corpus=corpus, box_vector=box_vector, pre_vetted=pre_vetted)

    if chosen_shape == DELIVERY_NEAREST:
        schemes = resolved_schemes if survivors is None else survivors
        return nearest(schemes, state=state, corpus=corpus, box_vector=box_vector, pre_vetted=pre_vetted)

    if chosen_shape == DELIVERY_EMPTY:
        return empty(state=state, box_vector=box_vector)

    raise ValueError(f"Unknown delivery shape: {chosen_shape}")


def render_terminal(
    box_vector: Mapping[str, Any] | None = None,
    corpus: Any = None,
    *,
    survivors: Sequence[Any] | None = None,
    state: str | None = None,
    dropped_boxes: Sequence[str] | None = None,
    shape: str | None = None,
    pre_vetted: bool = False,
) -> tuple[str, ...]:
    """Convenience alias for terminal_sequence."""
    return terminal_sequence(
        survivors=survivors,
        state=state,
        box_vector=box_vector,
        corpus=corpus,
        dropped_boxes=dropped_boxes,
        shape=shape,
        pre_vetted=pre_vetted,
    )


class Terminals:
    """Namespace for terminal renderers and delivery shape classifiers."""
    direct_match = staticmethod(direct_match)
    overflow = staticmethod(overflow)
    widened_match = staticmethod(widened_match)
    nearest = staticmethod(nearest)
    empty = staticmethod(empty)
    render = staticmethod(render_terminal)
    sequence = staticmethod(terminal_sequence)
    classify_shape = staticmethod(classify_shape)
    ranked = staticmethod(ranked)
    more_sequence = staticmethod(more_sequence)
