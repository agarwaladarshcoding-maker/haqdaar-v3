"""haqdaar/engine/talk_pick.py

The fixed part of a talk turn (step 7.13, owner's change C1): which question to ask is NOT the
model's choice. Search gives the schemes near the caller's need; the bitmask filter drops the ones
that do not fit what we know; the question picker (the same Planner the keys path uses) names the
ONE box that cuts that list fastest. Pure: no audio, no model, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from haqdaar.contracts.types import SEVEN_BOXES, UNASKED, UNKNOWN, Ask
from haqdaar.engine import planner
from haqdaar.engine.filter import Filter

# 1.3a: stop asking at 2 or fewer left in talk. The keys path keeps the
# picker's own STOP_SURVIVORS (4). On a short list nothing is asked, not even
# man / woman: each scheme carries its mark instead.
TALK_STOP_SCHEMES = 2

FITS = "fits"
DOES_NOT_FIT = "does not fit"
NOT_KNOWN = "not known yet"


class SubCorpus:
    """A corpus that holds only some of the schemes, so the filter and the picker can run on
    the search's hits. Scheme place n here = place ixs[n] in the full corpus."""

    def __init__(self, corpus: Any, ixs: Sequence[int]) -> None:
        self._corpus = corpus
        self._ixs = tuple(ixs)
        self._scheme_ids = tuple(corpus.scheme_id(i) for i in self._ixs)

    @property
    def snapshot_id(self) -> str:
        return self._corpus.snapshot_id

    def values(self, box: str) -> tuple:
        return self._corpus.values(box)

    def mask(self, box: str, value: Any) -> int:
        full = self._corpus.mask(box, value)
        out = 0
        for n, ix in enumerate(self._ixs):
            if full & (1 << ix):
                out |= 1 << n
        return out

    def specificity(self, n: int) -> int:
        return self._corpus.specificity(self._ixs[n]) if 0 <= n < len(self._ixs) else 0

    def scheme_id(self, n: int) -> str:
        return self._scheme_ids[n] if 0 <= n < len(self._scheme_ids) else ""


def _ix(corpus: Any, scheme_id: str) -> int:
    n = 0
    while corpus.scheme_id(n) != "":
        if corpus.scheme_id(n) == scheme_id:
            return n
        n += 1
    return -1


def _known(box_vector: Mapping[str, Any], box: str, corpus: Any) -> bool:
    val = box_vector.get(box)
    return val is not None and val not in (UNASKED, UNKNOWN) and val in corpus.values(box)


def mark(scheme_id: str, box_vector: Mapping[str, Any], corpus: Any) -> str:
    """fits / does not fit / not known yet, from what the caller has told us so far."""
    ix = _ix(corpus, scheme_id)
    if ix < 0:
        return NOT_KNOWN
    if Filter.miss_set(box_vector, corpus, ix):
        return DOES_NOT_FIT
    bit = 1 << ix
    for box in SEVEN_BOXES:
        if box == "category":      # what the scheme is about, not who may get it
            continue
        needs = any(not corpus.mask(box, v) & bit for v in corpus.values(box))
        if needs and not _known(box_vector, box, corpus):
            return NOT_KNOWN
    return FITS


@dataclass(frozen=True)
class Narrow:
    left: tuple[str, ...]          # the found schemes that still fit, in search order
    ask: str | None                # the ONE box to ask next; None = stop asking, show schemes
    values: tuple[str, ...] = ()   # that box's allowed values
    order: tuple[str, ...] = ()    # ask first, then the other boxes that still cut the list


def narrow(scheme_ids: Sequence[str], box_vector: Mapping[str, Any], corpus: Any) -> Narrow:
    """Search hits -> filter -> picker."""
    ixs = [ix for ix in (_ix(corpus, sid) for sid in scheme_ids) if ix >= 0]
    sub = SubCorpus(corpus, ixs)
    surv = Filter.survivors(box_vector, sub)
    left = tuple(sub.scheme_id(n) for n in surv)
    if len(left) <= TALK_STOP_SCHEMES:
        return Narrow(left, None)
    action = planner.next_action(box_vector, sub, stop_survivors=TALK_STOP_SCHEMES)
    if not isinstance(action, Ask):
        return Narrow(left, None)
    rest = [
        b for b in SEVEN_BOXES
        if b != action.box
        and planner._is_askable(b, box_vector.get(b), sub)
        and planner._box_splits_survivors(b, surv, box_vector, sub)
    ]
    rest.sort(key=lambda b: -planner._minimax_score(b, surv, box_vector, sub))
    return Narrow(left, action.box, tuple(sub.values(action.box)), (action.box, *rest))
