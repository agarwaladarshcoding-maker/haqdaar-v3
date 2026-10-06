"""haqdaar/engine/filter.py

Pure filtering engine for Haqdaar v2 (T09, T10, T18, 04-INTERFACES).
Masks, survivors, tally, miss-set, speakable, and nearest ranking.
"""
from __future__ import annotations

from haqdaar.contracts import tunables
from haqdaar.contracts.types import (
    ANY,
    HARD_BOXES,
    SEVEN_BOXES,
    UNASKED,
    UNKNOWN,
    BoxId,
    ValueCode,
)

__all__ = [
    "Filter",
    "build_masks",
    "turn_masks",
    "survivors",
    "tally",
    "miss_set",
    "speakable",
    "nearest",
]


def _get_scheme_count(corpus):
    if corpus is None:
        return 0
    if hasattr(corpus, "_scheme_ids"):
        return len(corpus._scheme_ids)
    if hasattr(corpus, "scheme_id"):
        count = 0
        while corpus.scheme_id(count) != "":
            count += 1
        return count
    if isinstance(corpus, (list, tuple)):
        return len(corpus)
    if isinstance(corpus, dict):
        # Heuristic for dict corpora (masks mapping (box, val) to int mask):
        # Assumes every scheme bit (0..N-1) is set in at least one mask,
        # so combined.bit_length() gives the total scheme count N.
        # If the highest scheme index bit is never set in any mask, this would
        # undercount. In production, Corpus is a Corpus object with _scheme_ids.
        combined = 0
        for m in corpus.values():
            if isinstance(m, int):
                combined |= m
        return combined.bit_length()
    return 0


def _get_mask(corpus, box, val):
    if corpus is None:
        return 0
    if hasattr(corpus, "mask"):
        m = corpus.mask(box, val)
        if m == 0 and not isinstance(val, str):
            m = corpus.mask(box, str(val))
        return m
    if isinstance(corpus, dict):
        if (box, val) in corpus:
            return corpus[(box, val)]
        if (box, str(val)) in corpus:
            return corpus[(box, str(val))]
    return 0


def _get_answered_masks(box_vector, corpus):
    if not box_vector:
        return []
    retained = []
    for box, val in box_vector.items():
        if val is None or val == UNASKED or val == UNKNOWN:
            continue
        if not isinstance(corpus, dict) and hasattr(corpus, "values"):
            box_vals = corpus.values(box)
            if box_vals:
                if val not in box_vals and str(val) not in [str(x) for x in box_vals]:
                    continue
        m = _get_mask(corpus, box, val)
        retained.append((box, val, m))
    return retained


def build_masks(schemes, boxes=None):
    if boxes is None:
        boxes_set = set(SEVEN_BOXES)
        for s in schemes:
            for k in s.keys():
                if k not in (
                    "scheme_id",
                    "name",
                    "summary",
                    "chunks",
                    "aliases_en",
                    "aliases_hi",
                    "aliases_mr",
                    "gate_notes",
                    "source_url",
                    "source_sha256",
                    "fetched_on",
                    "facets_source",
                    "facets_verified_by",
                    "facets_verified_on",
                    "scheme_name_en",
                    "scheme_name_hi",
                    "scheme_name_mr",
                    "myscheme_slug",
                    "department",
                    "level",
                ):
                    boxes_set.add(k)
        boxes_list = list(boxes_set)
    else:
        boxes_list = list(boxes)

    masks = {}
    for box in boxes_list:
        val_set = set()
        for s in schemes:
            val = s.get(box)
            if val is None and "facets" in s:
                val = s["facets"].get(box)
            if val is not None and val != ANY and val != "ANY":
                if isinstance(val, (list, tuple, set)):
                    for v in val:
                        if v != ANY and v != "ANY":
                            val_set.add(v)
                else:
                    val_set.add(val)

        for val in val_set:
            mask_val = 0
            for i, s in enumerate(schemes):
                bit = 2**i
                s_val = s.get(box)
                if s_val is None and "facets" in s:
                    s_val = s["facets"].get(box)

                if s_val is None or s_val == ANY or s_val == "ANY":
                    mask_val |= bit
                elif isinstance(s_val, (list, tuple, set)):
                    if ANY in s_val or "ANY" in s_val or val in s_val or str(val) in [str(x) for x in s_val]:
                        mask_val |= bit
                elif str(s_val) == str(val):
                    mask_val |= bit

            masks[(box, val)] = mask_val
            if not isinstance(val, str):
                masks[(box, str(val))] = mask_val

    return masks


def turn_masks(box_vector=None, corpus=None, *, vector=None):
    bv = box_vector if box_vector is not None else (vector or {})
    return _get_answered_masks(bv, corpus)


def _keys_only(indices, corpus, include_talk_only):
    """The keys path never counts a scheme held for the talk only (it can not read it out), so its
    short-list and questions are the same as with a snapshot without those schemes. The talk picker
    works on a SubCorpus (no `_talk_only`) or asks for them, so it still counts them."""
    held = getattr(corpus, "_talk_only", None)
    if include_talk_only or not isinstance(held, frozenset) or not held:
        return indices
    return tuple(i for i in indices if i not in held)


def survivors(box_vector=None, corpus=None, *, vector=None, include_talk_only=False):
    bv = box_vector if box_vector is not None else (vector or {})
    answered = _get_answered_masks(bv, corpus)
    total_schemes = _get_scheme_count(corpus)
    all_indices = tuple(range(total_schemes))
    if not answered:
        return _keys_only(all_indices, corpus, include_talk_only)

    combined_mask = None
    for box, val, m in answered:
        if combined_mask is None:
            combined_mask = m
        else:
            combined_mask = combined_mask & m

    if combined_mask is None:
        return _keys_only(all_indices, corpus, include_talk_only)

    # N5: read the bits of the one combined mask (the same places as testing 2**i for each scheme, far faster on 1,000+)
    bits = format(combined_mask & ((1 << total_schemes) - 1), f"0{total_schemes}b")[::-1]
    return _keys_only(tuple(i for i, c in enumerate(bits) if c == "1"), corpus, include_talk_only)


def tally(box_vector=None, corpus=None, *, vector=None):
    bv = box_vector if box_vector is not None else (vector or {})
    answered = _get_answered_masks(bv, corpus)
    total_schemes = _get_scheme_count(corpus)
    res = {}
    for i in range(total_schemes):
        bit = 2**i
        count = 0
        for box, val, m in answered:
            if bool(m & bit):
                count += 1
        res[i] = count
    return res


def miss_set(box_vector=None, corpus=None, ix=0, *, vector=None):
    bv = box_vector if box_vector is not None else (vector or {})
    answered = _get_answered_masks(bv, corpus)
    bit = 2**ix
    missing = []
    for box, val, m in answered:
        if not bool(m & bit):
            missing.append(box)
    return frozenset(missing)


def speakable(scheme, box_vector=None, corpus=None, *, vector=None):
    bv = box_vector if box_vector is not None else (vector or {})

    target = scheme
    if isinstance(target, str) and corpus is not None:
        if hasattr(corpus, "_scheme_ids"):
            if target in corpus._scheme_ids:
                target = corpus._scheme_ids.index(target)
        elif hasattr(corpus, "scheme_id"):
            idx = 0
            while corpus.scheme_id(idx) != "":
                if corpus.scheme_id(idx) == target:
                    target = idx
                    break
                idx += 1

    if isinstance(target, dict) and target.get("talk_only") is True:
        return False         # N6: no recorded clips: the keys path can not read it out
    if isinstance(target, dict):
        for box in HARD_BOXES:
            s_val = target.get(box)
            if s_val is None and "facets" in target:
                s_val = target["facets"].get(box)

            is_any = False
            if s_val is None or s_val == ANY or s_val == "ANY":
                is_any = True
            elif isinstance(s_val, (list, tuple, set)):
                if ANY in s_val or "ANY" in s_val:
                    is_any = True

            if not is_any:
                vec_val = bv.get(box)
                if vec_val is None or vec_val == UNASKED or vec_val == UNKNOWN:
                    return False
                if isinstance(s_val, (list, tuple, set)):
                    if str(vec_val) not in [str(x) for x in s_val]:
                        return False
                else:
                    if str(vec_val) != str(s_val):
                        return False
        return True

    if isinstance(target, int):
        talk_only = getattr(corpus, "_talk_only", None)    # N6: a scheme held for the talk only is never speakable here
        if isinstance(talk_only, frozenset) and target in talk_only:
            return False
        bit = 2**target
        for box in HARD_BOXES:
            is_any = False
            vals = None
            if corpus is not None and not isinstance(corpus, dict) and hasattr(corpus, "values"):
                vals = corpus.values(box)
            elif isinstance(corpus, dict):
                if "values" in corpus and callable(corpus["values"]):
                    vals = corpus["values"](box)
                elif "values" in corpus and isinstance(corpus["values"], dict):
                    vals = corpus["values"].get(box, [])
                else:
                    vals = [v for k in corpus.keys() if isinstance(k, tuple) and len(k) == 2 and k[0] == box]

            if vals is not None:
                if not vals:
                    # An empty closed set means no scheme in the snapshot is
                    # non-ANY on this box, so there is nothing to vet. Treating
                    # it as "not ANY" refused every scheme in a corpus where the
                    # box is universally ANY (e.g. all-nationwide `state`).
                    is_any = True
                elif vals:
                    all_set = True
                    for v in vals:
                        m = _get_mask(corpus, box, v)
                        if not bool(m & bit):
                            all_set = False
                            break
                    if all_set:
                        is_any = True
            if not is_any:
                vec_val = bv.get(box)
                if vec_val is None or vec_val == UNASKED or vec_val == UNKNOWN:
                    return False
                m = _get_mask(corpus, box, vec_val)
                if not bool(m & bit):
                    return False
        return True

    return False


def nearest(box_vector=None, corpus=None, *, vector=None):
    bv = box_vector if box_vector is not None else (vector or {})
    if corpus is None:
        return ()

    total_schemes = _get_scheme_count(corpus)
    tallies = tally(bv, corpus)

    candidates = []
    for ix in range(total_schemes):
        ms = miss_set(bv, corpus, ix)
        if not bool(ms.intersection(HARD_BOXES)):
            if speakable(ix, bv, corpus):
                candidates.append(ix)

    def sort_key(ix):
        spec = 0
        if hasattr(corpus, "specificity"):
            spec = corpus.specificity(ix)
        return (-tallies[ix], -spec, ix)

    ranked = sorted(candidates, key=sort_key)
    return tuple(ranked[:tunables.NEAREST_CAP])


class Filter:
    """Filter engine component (T09, T10, T18, 04-INTERFACES)."""

    def __init__(self, box_vector=None, corpus=None, *, vector=None):
        self.box_vector = box_vector if box_vector is not None else (vector or {})
        self.corpus = corpus

    def get_turn_masks(self):
        return _get_answered_masks(self.box_vector, self.corpus)

    def get_survivors(self):
        return survivors(self.box_vector, self.corpus)

    def get_tally(self):
        return tally(self.box_vector, self.corpus)

    def get_miss_set(self, ix=0):
        return miss_set(self.box_vector, self.corpus, ix)

    def get_nearest(self):
        return nearest(self.box_vector, self.corpus)

    def is_speakable(self, scheme):
        return speakable(scheme, self.box_vector, self.corpus)

    @staticmethod
    def turn_masks(box_vector=None, corpus=None, *, vector=None):
        bv = box_vector if box_vector is not None else (vector or {})
        return _get_answered_masks(bv, corpus)

    @staticmethod
    def survivors(box_vector=None, corpus=None, *, vector=None, include_talk_only=False):
        return survivors(box_vector, corpus, vector=vector, include_talk_only=include_talk_only)

    @staticmethod
    def tally(box_vector=None, corpus=None, *, vector=None):
        return tally(box_vector, corpus, vector=vector)

    @staticmethod
    def miss_set(box_vector=None, corpus=None, ix=0, *, vector=None):
        return miss_set(box_vector, corpus, ix, vector=vector)

    @staticmethod
    def speakable(scheme, box_vector=None, corpus=None, *, vector=None):
        return speakable(scheme, box_vector, corpus, vector=vector)

    @staticmethod
    def nearest(box_vector=None, corpus=None, *, vector=None):
        return nearest(box_vector, corpus, vector=vector)

    @staticmethod
    def build_masks(schemes, boxes=None):
        return build_masks(schemes, boxes)
