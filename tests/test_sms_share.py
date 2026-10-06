"""M3: the share of parts for each photo, and the cap of 5 photos, from the cut through the join."""
import random

import pytest
from PIL import Image, ImageDraw

from haqdaar.contracts import tunables
from haqdaar.keypad_sms import join, pack, share


def photo(seed):
    rnd = random.Random(seed)
    img = Image.new("RGB", (640, 480), (rnd.randrange(60, 200), 120, 60))
    d = ImageDraw.Draw(img)
    for _ in range(14):
        x, y = rnd.randrange(640), rnd.randrange(480)
        d.ellipse((x, y, x + 100, y + 80), fill=tuple(rnd.randrange(256) for _ in range(3)))
    return img


def test_the_table():
    assert [share.share_parts(n) for n in (1, 2, 3, 4, 5, 9)] == [20, 12, 10, 10, 10, 10]
    assert [share.max_parts(n) for n in range(1, 6)] == [20, 24, 30, 40, 50]
    assert share.max_parts(9) == 50                      # more than the cap counts as the cap
    assert share.max_photos() == 5


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7])
def test_cut_and_join_agree_for_any_count(n):
    cut = pack.cut_case([photo(i) for i in range(n)], "417")
    kept = min(n, 5)
    assert len(cut) == kept
    assert {c["sent"] for c in cut} == {kept}                       # the tag says how many were SENT
    assert all(c["parts"] <= share.share_parts(kept) for c in cut)
    assert sum(c["parts"] for c in cut) <= share.max_parts(kept)
    j = join.PhotoJoin()
    last = None
    for c in cut:
        for pk in c["packets"]:
            last = j.add("s", pk, owner="t", now=0.0)
    assert j.ready(last.key)
    case = j.take(last.key)
    assert case.sent == kept and len(case.photos) == kept and case.failed == 0
    assert [pl for pl, _ in case.photos] == list(range(1, kept + 1))


def test_more_photos_press_each_one_harder():
    sizes = {n: [c["w"] for c in pack.cut_case([photo(i) for i in range(n)], "1")] for n in (1, 2, 3)}
    assert min(sizes[1]) >= max(sizes[2]) >= max(sizes[3]) or min(sizes[1]) > min(sizes[3])
    assert min(sizes[1]) > min(sizes[3])


def test_the_cap_is_a_setting(monkeypatch):
    monkeypatch.setattr(tunables, "SMS_MAX_PHOTOS", 4)
    assert len(pack.cut_case([photo(i) for i in range(6)], "1")) == 4
    c = pack.cut_photo(photo(1), "1", 5, 1)                           # a phone that still says 5
    assert join.PhotoJoin().add("s", c["packets"][0]).reply == "ERR RANGE"
