"""Focused tests for tools/stress.py check_truth nearest handling (T18 §2)."""
from tools.stress import _scheme_index, check_truth


class _FakeCorpus:
    """Two schemes: s1 matches state=X + income LOW; s2 matches state=X only."""

    _scheme_ids = ("s1", "s2")
    _masks = {
        ("state", "X"): 0b11,
        ("state", "Y"): 0b00,
        ("income_band", "LOW"): 0b01,
        ("income_band", "HIGH"): 0b00,
    }

    def scheme_id(self, ix):
        return self._scheme_ids[ix] if ix < len(self._scheme_ids) else ""

    def mask(self, box, value):
        return self._masks.get((box, value), 0)


def _rows(*rows):
    return list(rows)


def test_bogus_nearest_with_survivors_is_flagged():
    """A nearest emitted while matches exist is an engine bug, not an excuse."""
    corpus = _FakeCorpus()
    rows = _rows(
        {"class": "ANSWER", "box": "state", "value": "X"},
        {"slug": "s2", "ending": "nearest", "ladder_rung": 0},
    )
    problems = check_truth(rows, corpus, _scheme_index(corpus))
    assert any("nearest" in p and "survivors" in p for p in problems), problems


def test_honest_nearest_with_soft_miss_passes():
    """Zero survivors under full masks: soft-box miss is excused (T18 §2)."""
    corpus = _FakeCorpus()
    rows = _rows(
        {"class": "ANSWER", "box": "state", "value": "X"},
        {"class": "ANSWER", "box": "income_band", "value": "HIGH"},
        {"slug": "s2", "ending": "nearest", "ladder_rung": 2},
    )
    assert check_truth(rows, corpus, _scheme_index(corpus)) == []


def test_nearest_with_hard_box_miss_is_flagged():
    """The excuse never covers hard boxes."""
    corpus = _FakeCorpus()
    rows = _rows(
        {"class": "ANSWER", "box": "state", "value": "Y"},
        {"slug": "s2", "ending": "nearest", "ladder_rung": 2},
    )
    problems = check_truth(rows, corpus, _scheme_index(corpus))
    assert any("hard box" in p for p in problems), problems
