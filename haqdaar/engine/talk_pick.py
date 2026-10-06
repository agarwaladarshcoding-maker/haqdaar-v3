"""haqdaar/engine/talk_pick.py

The fixed part of a talk turn (step 7.13, owner's change C1): which question to ask is NOT the
model's choice. Search gives the schemes near the caller's need; the bitmask filter drops the ones
that do not fit what we know; the question picker (the same Planner the keys path uses) names the
ONE box that cuts that list fastest. Pure: no audio, no model, no I/O.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from haqdaar.contracts import tunables, vocab
from haqdaar.contracts.types import SEVEN_BOXES, TALK_BOXES, UNASKED, UNKNOWN, Ask
from haqdaar.engine import planner
from haqdaar.engine.filter import Filter

# 1.3a: stop asking at 2 or fewer left in talk. The keys path keeps the
# picker's own STOP_SURVIVORS (4). On a short list nothing is asked, not even
# man / woman: each scheme carries its mark instead.
TALK_STOP_SCHEMES = 2
TALK_OPTIONS = 3     # N1: the model is handed up to this many boxes to pick its question from

FITS = "fits"
DOES_NOT_FIT = "does not fit"
NOT_KNOWN = "not known yet"
NEAR = "near"

# N3: can a person change what stands in the way? A box not listed can be changed (move work, get a card).
# N6: the facts a person can not change (widow, disability, ...) and the home state add their rows.
CAN_CHANGE = {"age": False, "gender": False, "social_category": False, "home_state": False}
CAN_CHANGE.update({f"f_{name}": False for name, fact in vocab.FACTS.items() if not fact["change"]})


def boxes_of(corpus: Any) -> tuple[str, ...]:
    """N6: the boxes the talk walks: the seven always, a talk-only box only when this snapshot holds values for it.
    A snapshot built before N6 has none of them, so every loop below is then the loop it was."""
    return tuple(b for b in TALK_BOXES if b in SEVEN_BOXES or corpus.values(b))


class SubCorpus:
    """A corpus that holds only some of the schemes, so the filter and the picker can run on
    the search's hits. Scheme place n here = place ixs[n] in the full corpus."""

    def __init__(self, corpus: Any, ixs: Sequence[int]) -> None:
        self._corpus = corpus
        self._ixs = tuple(ixs)
        self._scheme_ids = tuple(corpus.scheme_id(i) for i in self._ixs)
        self._masks: dict[tuple[str, Any], int] = {}    # N5: the picker asks for the same (box, value) again and again

    @property
    def snapshot_id(self) -> str:
        return self._corpus.snapshot_id

    def values(self, box: str) -> tuple:
        return self._corpus.values(box)

    def mask(self, box: str, value: Any) -> int:
        held = self._masks.get((box, value))
        if held is not None:
            return held
        full = self._corpus.mask(box, value)
        out = 0
        for n, ix in enumerate(self._ixs):
            if full & (1 << ix):
                out |= 1 << n
        self._masks[(box, value)] = out
        return out

    def specificity(self, n: int) -> int:
        return self._corpus.specificity(self._ixs[n]) if 0 <= n < len(self._ixs) else 0

    def scheme_id(self, n: int) -> str:
        return self._scheme_ids[n] if 0 <= n < len(self._scheme_ids) else ""


_IX: dict[int, tuple[Any, dict[str, int]]] = {}    # N5: one id -> place map for each corpus (the corpus is kept, so its id is not reused)


def _ix_map(corpus: Any, fresh: bool = False) -> dict[str, int]:
    held = _IX.get(id(corpus))
    if held is None or held[0] is not corpus or fresh:
        places: dict[str, int] = {}
        n = 0
        while corpus.scheme_id(n) != "":
            places.setdefault(corpus.scheme_id(n), n)      # the first place wins, as the scan did
            n += 1
        held = _IX[id(corpus)] = (corpus, places)
    return held[1]


def _ix(corpus: Any, scheme_id: str) -> int:
    ix = _ix_map(corpus).get(scheme_id, -1)
    if ix >= 0 and corpus.scheme_id(ix) != scheme_id:       # the corpus changed under the map: build it again
        ix = _ix_map(corpus, fresh=True).get(scheme_id, -1)
    return ix


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
    for box in boxes_of(corpus):
        if box == "category":      # what the scheme is about, not who may get it
            continue
        needs = any(not corpus.mask(box, v) & bit for v in corpus.values(box))
        if needs and not _known(box_vector, box, corpus):
            return NOT_KNOWN
    return FITS


def marks(scheme_ids: Sequence[str], box_vector: Mapping[str, Any], corpus: Any) -> dict[str, str]:
    """N5: `mark` for many schemes at once, worked out on the masks (the same words, a few ms for 5,000)."""
    places = _ix_map(corpus)
    total = max(places.values(), default=-1) + 1
    full = (1 << total) - 1
    fit, need = full, 0
    for _box, _val, m in Filter.turn_masks(box_vector, corpus):
        fit &= m
    for box in boxes_of(corpus):
        if box == "category" or _known(box_vector, box, corpus):
            continue
        held = full
        for v in corpus.values(box):
            held &= corpus.mask(box, v)
        need |= full & ~held                    # the schemes that depend on this box, which is not known
    fits, needs = format(fit & full, f"0{total}b")[::-1], format(need, f"0{total}b")[::-1]
    out = {}
    for sid in scheme_ids:
        ix = places.get(sid, -1)
        out[sid] = NOT_KNOWN if ix < 0 else DOES_NOT_FIT if fits[ix] == "0" else NOT_KNOWN if needs[ix] == "1" else FITS
    return out


def needs_ask(scheme_id: str, box_vector: Mapping[str, Any], corpus: Any, skip: Sequence[str] = ()) -> str | None:
    """1.8 ("will I get it?"): the picker run on ONE scheme. The first box the scheme depends on that the
    caller has not been asked yet; None when every box it depends on is known (or was asked, no answer)."""
    ix = _ix(corpus, scheme_id)
    if ix < 0:
        return None
    bit = 1 << ix
    for box in boxes_of(corpus):
        if box == "category" or box in skip or box_vector.get(box) != UNASKED:
            continue
        if any(not corpus.mask(box, v) & bit for v in corpus.values(box)):
            return box
    return None


def min_cut(n: int) -> int:
    """N5: a question is worth asking when it cuts at least this many of the n schemes left (TALK_MIN_CUT of them, 1 at least)."""
    return max(1, math.ceil(round(tunables.TALK_MIN_CUT * n, 9)))   # the round: 0.1 * 30 is 3.0000000000000004


def live_values(box: str, left: Sequence[str], corpus: Any) -> list[str]:
    """N2: the values of a box that at least one of the left schemes holds, the value that holds the
    most of them first (a tie keeps the corpus order). These are the answers a key can give."""
    bits = 0
    for sid in left:
        ix = _ix(corpus, sid)
        if ix >= 0:
            bits |= 1 << ix
    held = [(corpus.mask(box, v) & bits).bit_count() for v in corpus.values(box)]
    pairs = [(n, v) for n, v in zip(held, corpus.values(box)) if n and v not in (UNASKED, UNKNOWN, "ANY")]
    if vocab.fact_of(box):         # N6: a yes / no question: 1 is yes, 2 is no
        return [v for v in vocab.YES_NO if any(v == pv for _n, pv in pairs)]
    return [v for _n, v in sorted(pairs, key=lambda p: -p[0])]


def model_boxes(left: Sequence[str], box_vector: Mapping[str, Any], corpus: Any, limit: int,
                must: Sequence[str] = ()) -> dict[str, tuple[str, ...]]:
    """N6: the talk-only boxes the model is shown this turn (so it can set a fact the caller said in free talk).
    Only a box the snapshot holds, the caller has not answered, and one of whose answers cuts the list left: the
    prompt must not grow by a line for each of 30 boxes. At most `limit` in all, the one whose worst answer leaves
    fewest first; `must` (the box asked, its options) is always in, and counts in the limit. Each box shows only the values a left scheme names (a yes / no fact: both answers)."""
    bits = 0
    for sid in left:
        ix = _ix(corpus, sid)
        if ix >= 0:
            bits |= 1 << ix
    n = bits.bit_count()
    found: list[tuple[int, str, tuple[str, ...]]] = []
    for box in boxes_of(corpus)[len(SEVEN_BOXES):]:
        if box_vector.get(box) not in (None, UNASKED):
            continue
        held = [(v, (corpus.mask(box, v) & bits).bit_count()) for v in corpus.values(box)]
        if vocab.fact_of(box):
            live = tuple(v for v, c in held if c)
        else:      # a scheme with no condition holds every value: only the values some left scheme NAMES are worth a line
            anyone = -1
            for v in corpus.values(box):
                anyone &= corpus.mask(box, v)
            live = tuple(v for v in corpus.values(box) if corpus.mask(box, v) & bits & ~anyone)
        if live and (box in must or any(0 < c < n for _v, c in held)):
            found.append((0 if box in must else max(c for _v, c in held), box, live))
    found.sort(key=lambda f: f[0])
    musts = [f for f in found if f[1] in must]
    keep = musts + [f for f in found if f[1] not in must][:max(0, limit - len(musts))]
    return {box: live for _w, box, live in keep}


@dataclass(frozen=True)
class Option:
    box: str
    left: int                      # the most schemes that can be left after any answer to it


@dataclass(frozen=True)
class Narrow:
    left: tuple[str, ...]          # the found schemes that still fit, in search order
    ask: str | None                # the ONE box to ask next; None = stop asking, show schemes
    values: tuple[str, ...] = ()   # that box's allowed values
    order: tuple[str, ...] = ()    # ask first, then the other boxes that still cut the list
    options: tuple[Option, ...] = ()   # N1: up to TALK_OPTIONS boxes, best first (ask is the first), with "at most N left"
    stop: str = ""                 # N5: why asking ended when the picker ended it ("small_cut": no box is worth a question)


def narrow(scheme_ids: Sequence[str], box_vector: Mapping[str, Any], corpus: Any) -> Narrow:
    """Search hits -> filter -> picker."""
    ixs = [ix for ix in (_ix(corpus, sid) for sid in scheme_ids) if ix >= 0]
    sub = SubCorpus(corpus, ixs)
    surv = Filter.survivors(box_vector, sub)
    left = tuple(sub.scheme_id(n) for n in surv)
    if len(left) <= TALK_STOP_SCHEMES:
        return Narrow(left, None)
    # N5: the talk is not stopped by the keys path's cap of MAX_QUESTIONS; the planner counts at most the six boxes
    # that are not the kind of help, so one more than that never stops it. The switch off keeps the old cap.
    # N6: with the switch on the talk walks every box the snapshot holds (the cap follows that list).
    walk = boxes_of(corpus) if tunables.TALK_ASK_FIRST else SEVEN_BOXES
    cap = {"max_questions": len(walk)} if tunables.TALK_ASK_FIRST else {}
    action = planner.next_action(
        box_vector, sub, stop_survivors=TALK_STOP_SCHEMES, tie_break="easy_first", boxes=walk, **cap
    )
    if not isinstance(action, Ask):
        return Narrow(left, None, stop=action.reason if tunables.TALK_ASK_FIRST and hasattr(action, "reason") else "")
    rest = [
        b for b in walk
        if b != action.box
        and planner._is_askable(b, box_vector.get(b), sub)
        and planner._box_splits_survivors(b, surv, box_vector, sub)
    ]
    rest.sort(key=lambda b: -planner._minimax_score(b, surv, box_vector, sub))
    if not tunables.TALK_ASK_FIRST:
        return Narrow(left, action.box, tuple(sub.values(action.box)), (action.box, *rest))
    # The planner's own tie rule (score, fewer left on average, easy-first order).
    easy = {b: n for n, b in enumerate(planner.EASY_FIRST)}
    boxes = (action.box, *rest)
    n = len(surv)
    worst = {b: planner._worst_left(b, surv, box_vector, sub) for b in boxes}
    need = min_cut(n)
    worth = [b for b in boxes if n - worst[b] >= need]       # the worst answer still cuts enough: minimax order stands
    if worth:
        key = lambda b: (-planner._minimax_score(b, surv, box_vector, sub),
                         planner._average_remaining(b, box_vector, sub), easy.get(b, len(easy)))
    else:                                                    # no box cuts enough in the worst case: the mean answer is next
        gain = {b: n - planner._expected_left(b, surv, box_vector, sub) for b in boxes}
        worth = [b for b in boxes if gain[b] >= need]
        key = lambda b: (-gain[b], planner._average_remaining(b, box_vector, sub), easy.get(b, len(easy)))
        if not worth:
            return Narrow(left, None, stop="small_cut")
    worth.sort(key=key)
    options = tuple(Option(b, worst[b]) for b in worth[:TALK_OPTIONS])
    ask = worth[0]
    return Narrow(left, ask, tuple(sub.values(ask)), (ask, *(b for b in boxes if b != ask)), options)


def rank(left: Sequence[str], box_vector: Mapping[str, Any], corpus: Any) -> tuple[str, ...]:
    """N5: the schemes left, best fit first: the one that asks for most of the caller's known facts by name
    (its own value for the box is not ANY, and it holds the caller's), then the order they came in."""
    places = _ix_map(corpus)
    facts = []
    for box in boxes_of(corpus):
        if box == "category" or not _known(box_vector, box, corpus):
            continue
        any_of = -1                              # the schemes that hold every value of the box: no condition on it
        for v in corpus.values(box):
            any_of &= corpus.mask(box, v)
        facts.append(corpus.mask(box, box_vector[box]) & ~any_of)
    if not facts:
        return tuple(left)
    named = {sid: sum(m >> places[sid] & 1 for m in facts) for sid in left if sid in places}
    return tuple(sorted(left, key=lambda sid: -named.get(sid, 0)))     # a stable sort: search order inside each count


@dataclass(frozen=True)
class Blocker:
    box: str
    needs: str          # what the scheme needs, in plain label words
    said: str           # what the caller said, in plain label words
    can_change: bool

    def line(self, meaning: str) -> str:
        if vocab.fact_of(self.box):      # N6: a yes / no fact: "needs" is already its plain words
            return (f"the scheme needs: {self.needs}; the caller said: {self.said} "
                    f"(can change: {'yes' if self.can_change else 'no'})")
        return (f"{meaning}: the scheme needs {self.needs}, the caller said {self.said} "
                f"(can change: {'yes' if self.can_change else 'no'})")


def _say(box: str, value: Any) -> str:
    if vocab.fact_of(box):             # N6: the caller's answer to a yes / no question: yes or no
        return str(value)
    label = (vocab.LABELS.get(value) or {}).get("en")
    if label:
        return str(label)
    if box == "age":
        return str(value).replace("-", " to ")
    return str(value).replace("_", " ").title() if box == "state" else str(value).replace("_", " ")


def _needs(box: str, ix: int, corpus: Any) -> str:
    """What scheme `ix` needs in a box: the values its mask holds (age bands that touch are one range)."""
    vals = [v for v in corpus.values(box) if v not in (UNASKED, UNKNOWN, "ANY") and corpus.mask(box, v) & (1 << ix)]
    if box == "age":
        spans: list[list[str]] = []
        for v in vals:
            lo, _, hi = str(v).replace("+", "-").partition("-")
            if spans and lo.isdigit() and spans[-1][1].isdigit() and int(lo) == int(spans[-1][1]) + 1:
                spans[-1][1] = hi
            else:
                spans.append([lo, hi])
        return " or ".join(f"{lo} to {hi}" if hi else f"{lo} and above" for lo, hi in spans)
    if vocab.fact_of(box):             # N6: the words of the one answer this scheme holds
        return " or ".join(vocab.value_words(box, v) for v in vals)
    said = [_say(box, v) for v in vals]
    return " or ".join(said[:4]) + (" or others" if len(said) > 4 else "")


def blockers(scheme_ids: Sequence[str], box_vector: Mapping[str, Any], corpus: Any) -> dict[str, tuple[Blocker, ...]]:
    """N3: for each scheme, what stands between the caller and it: one Blocker per answered box the scheme
    misses (boxes in corpus order). A box not known or not asked is never one; neither is the kind of help."""
    out: dict[str, tuple[Blocker, ...]] = {}
    for sid in scheme_ids:
        ix = _ix(corpus, sid)
        if ix < 0:
            continue
        miss = Filter.miss_set(box_vector, corpus, ix)
        out[sid] = tuple(Blocker(b, _needs(b, ix, corpus), _say(b, box_vector[b]), CAN_CHANGE.get(b, True))
                         for b in boxes_of(corpus) if b in miss and b != "category")
    return out


def near(scheme_ids: Sequence[str], box_vector: Mapping[str, Any], corpus: Any) -> list[tuple[str, tuple[Blocker, ...]]]:
    """N3: when nothing fits: the schemes of the search that miss by one box, then by two, in search order,
    TALK_NEAR_K at most. A hard box may be the miss (the point is to say it); a scheme of another kind never is near."""
    found = []
    for sid in scheme_ids:
        ix = _ix(corpus, sid)
        if ix < 0:
            continue
        miss = Filter.miss_set(box_vector, corpus, ix)
        if "category" not in miss and 1 <= len(miss) <= 2:
            found.append((len(miss), sid))
    ids = [sid for _n, sid in sorted(found, key=lambda p: p[0])][:tunables.TALK_NEAR_K]    # a stable sort: search order inside each
    return list(blockers(ids, box_vector, corpus).items())
