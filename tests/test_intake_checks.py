"""A scheme held for the talk only (no clip: the keys path can not read it out) must not move the keys path.
The same corpus is made twice, with and without three talk-only schemes; the keys path (Filter.survivors and the
Planner with their default arguments) must give the same answer in both. The talk picker still counts them."""
from haqdaar.contracts.types import SEVEN_BOXES
from haqdaar.data.corpus import Corpus
from haqdaar.engine import talk_pick
from haqdaar.engine.filter import Filter
from haqdaar.engine.planner import Planner

VALUES = {
    "category": ("farming", "health"),
    "state": ("MAHARASHTRA", "OTHER"),
    "gender": ("female", "male", "other"),
    "social_category": ("GEN", "OBC", "SC", "ST"),
    "age": ("0-13", "14-17", "18-35", "36-39", "40-40", "41-79", "80+"),
    "income_band": (),
    "occupation": ("farmer", "worker"),
}
# live schemes: two farming schemes that differ on gender, one health; talk-only: three farming schemes
LIVE = [{"category": ("farming",), "gender": ("female",)}, {"category": ("farming",), "gender": ("male",)},
        {"category": ("health",)}]
TALK = [{"category": ("farming",)}, {"category": ("farming",), "occupation": ("farmer",)},
        {"category": ("farming",), "state": ("MAHARASHTRA",)}]


def _corpus(rows, talk_from):
    masks = {(b, v): sum(1 << i for i, r in enumerate(rows) if b not in r or v in r[b])
             for b in SEVEN_BOXES for v in VALUES[b]}
    ids = tuple(f"s{i}" for i in range(len(rows)))
    return Corpus("t", masks, dict(VALUES), ids, tuple(len(r) - 1 for r in rows), {}, {}, {}, {},
                  talk_only=frozenset(ids[talk_from:]))


def _pair():
    return _corpus(LIVE, len(LIVE)), _corpus(LIVE + TALK, len(LIVE))


def test_the_keys_path_survivors_leave_out_talk_only_schemes():
    bare, mixed = _pair()
    for bv in ({}, {"category": "farming"}, {"category": "farming", "gender": "female"}):
        assert Filter.survivors(bv, mixed) == Filter.survivors(bv, bare)
    assert len(Filter.survivors({"category": "farming"}, mixed, include_talk_only=True)) == 5


def test_the_keys_path_planner_gives_the_same_action_with_or_without_them():
    bare, mixed = _pair()
    for bv in ({"category": "farming"}, {"category": "health"}, {"category": "farming", "gender": "male"}, {}):
        assert Planner.next_action(bv, mixed) == Planner.next_action(bv, bare)


def test_the_talk_picker_still_counts_them():
    _bare, mixed = _pair()
    got = talk_pick.narrow(list(mixed._scheme_ids), {"category": "farming"} | {b: "__UNASKED__" for b in SEVEN_BOXES if b != "category"}, mixed)
    assert {"s3", "s4", "s5"} <= set(got.left)
