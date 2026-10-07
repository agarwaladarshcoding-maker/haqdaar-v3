"""tests/test_photo_cases.py

Tests for haqdaar.photo.cases store.
Covers:
- token shape and path checks (no path traversal, regex ^[a-z2-9]{10}$)
- 24-hour age check
- wrong type / magic bytes
- size > 5 MB
- 7th photo limit
- multiple photos in order
- drop_photos
- state transitions & rules
- mark_called wiping number from disk
- number not in link
- number_tail
- open_cases order (newest first, age <= 24h)
- sweep
"""
import json
import pytest
from haqdaar.photo import cases

# Tiny picture magic bytes
TINY_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb"
TINY_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
TINY_WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x00"


def test_token_shape_and_validation(tmp_path):
    c = cases.new_case("hi", "+919876543210", folder=tmp_path)
    assert len(c.token) == 10
    assert cases.TOKEN_RE.match(c.token)

    # Invalid tokens return None from get, not error
    assert cases.get("../../../etc", folder=tmp_path) is None
    assert cases.get("123", folder=tmp_path) is None
    assert cases.get("ABCDEFGHIJ", folder=tmp_path) is None  # capital letters not allowed
    assert cases.get("l" * 10, folder=tmp_path) is None        # letter l not in alphabet

    # get with valid token
    fetched = cases.get(c.token, folder=tmp_path)
    assert fetched is not None
    assert fetched.token == c.token
    assert fetched.lang == "hi"
    assert fetched.number == "+919876543210"


def test_24_hour_age(tmp_path):
    t0 = 1000000.0
    c = cases.new_case("mr", folder=tmp_path, now=t0)

    # Within 24 hours (24 * 3600 = 86400)
    assert cases.get(c.token, folder=tmp_path, now=t0 + 86399) is not None

    # After 24 hours
    assert cases.get(c.token, folder=tmp_path, now=t0 + 86401) is None


def test_photo_wrong_type(tmp_path):
    c = cases.new_case("en", folder=tmp_path)
    with pytest.raises(ValueError, match="this is not a photo"):
        cases.add_photo(c.token, b"not a real photo bytes", folder=tmp_path)


def test_photo_too_big(tmp_path):
    c = cases.new_case("en", folder=tmp_path)
    # JPEG magic bytes followed by > 5 MB
    big_photo = TINY_JPEG + b"0" * (5 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="the photo is too big"):
        cases.add_photo(c.token, big_photo, folder=tmp_path)


def test_seven_photos_limit(tmp_path):
    c = cases.new_case("hi", folder=tmp_path)
    for i in range(6):
        c = cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
    assert len(c.photos) == 6

    with pytest.raises(ValueError, match="six photos at most"):
        cases.add_photo(c.token, TINY_PNG, folder=tmp_path)


def test_many_photos_order_and_types(tmp_path):
    c = cases.new_case("gu", folder=tmp_path)
    c = cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
    c = cases.add_photo(c.token, TINY_PNG, folder=tmp_path)
    c = cases.add_photo(c.token, TINY_WEBP, folder=tmp_path)

    assert c.photos == ["1.jpg", "2.png", "3.webp"]

    data1, mime1 = cases.photo_bytes(c.token, 0, folder=tmp_path)
    assert data1 == TINY_JPEG
    assert mime1 == "image/jpeg"

    data2, mime2 = cases.photo_bytes(c.token, 1, folder=tmp_path)
    assert data2 == TINY_PNG
    assert mime2 == "image/png"

    data3, mime3 = cases.photo_bytes(c.token, 2, folder=tmp_path)
    assert data3 == TINY_WEBP
    assert mime3 == "image/webp"

    with pytest.raises(IndexError):
        cases.photo_bytes(c.token, 3, folder=tmp_path)


def test_drop_photos(tmp_path):
    c = cases.new_case("ta", folder=tmp_path)
    cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
    cases.add_photo(c.token, TINY_PNG, folder=tmp_path)
    assert len(cases.get(c.token, folder=tmp_path).photos) == 2

    c = cases.drop_photos(c.token, folder=tmp_path)
    assert c.photos == []
    assert c.state == "waiting"

    # files on disk deleted
    case_dir = tmp_path / c.token
    assert not (case_dir / "1.jpg").exists()
    assert not (case_dir / "2.png").exists()


def test_state_transitions(tmp_path):
    c = cases.new_case("hi", folder=tmp_path)
    assert c.state == "waiting"

    # Photo added -> state becomes photo
    c = cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
    assert c.state == "photo"

    # Cannot approve before read
    with pytest.raises(ValueError, match="cannot approve"):
        cases.approve(c.token, "Approval say", folder=tmp_path)

    # set_finding -> state becomes read
    c = cases.set_finding(c.token, {"shows": "pest"}, "pmfby", "Say text", folder=tmp_path)
    assert c.state == "read"
    assert c.scheme == "pmfby"
    assert c.say == "Say text"

    # Approve -> state becomes approved
    c = cases.approve(c.token, "Helper edited say", folder=tmp_path)
    assert c.state == "approved"
    assert c.say == "Helper edited say"

    # Approve again is allowed
    c = cases.approve(c.token, "Second helper edit", folder=tmp_path)
    assert c.state == "approved"
    assert c.say == "Second helper edit"

    # A photo may not pull an approved case back (audit 4): the helper's answer would be thrown away
    with pytest.raises(ValueError, match="not taking photos"):
        cases.add_photo(c.token, TINY_PNG, folder=tmp_path)
    assert cases.get(c.token, folder=tmp_path).state == "approved"

    # Adding a photo to an open case keeps resetting finding/scheme/say
    c2 = cases.new_case("hi", folder=tmp_path)
    cases.add_photo(c2.token, TINY_JPEG, folder=tmp_path)
    c2 = cases.add_photo(c2.token, TINY_PNG, folder=tmp_path)
    assert c2.state == "photo"
    assert c2.finding == {}
    assert c2.scheme == ""
    assert c2.say == ""


def test_mark_called_wipes_number(tmp_path):
    c = cases.new_case("hi", "+919876543210", folder=tmp_path)
    cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
    cases.set_finding(c.token, {}, "", "", folder=tmp_path)
    cases.approve(c.token, "ok", folder=tmp_path)

    called = cases.mark_called(c.token, folder=tmp_path)
    assert called.state == "called"
    assert called.number == ""

    # Verify directly from disk file
    raw = json.loads((tmp_path / c.token / "case.json").read_text(encoding="utf-8"))
    assert raw["number"] == ""
    assert "+919876543210" not in (tmp_path / c.token / "case.json").read_text(encoding="utf-8")


def test_link_and_number_tail(tmp_path):
    c = cases.new_case("hi", "+919876543210", folder=tmp_path)
    lnk = cases.link(c, "http://localhost:8002")
    assert lnk == f"http://localhost:8002/p/{c.token}"
    assert "9876543210" not in lnk

    tail = cases.number_tail(c)
    assert tail == "3210"

    # No number
    c_no_num = cases.new_case("en", "", folder=tmp_path)
    assert cases.number_tail(c_no_num) == ""


def test_open_cases_order_and_expiry(tmp_path):
    t0 = 1000000.0
    c1 = cases.new_case("hi", folder=tmp_path, now=t0)
    c2 = cases.new_case("mr", folder=tmp_path, now=t0 + 100)
    c3 = cases.new_case("en", folder=tmp_path, now=t0 + 200)

    # Newest first
    open_list = cases.open_cases(folder=tmp_path, now=t0 + 300)
    assert [c.token for c in open_list] == [c3.token, c2.token, c1.token]

    # Advance time so c1 and c2 are older than 24h (86400s)
    # c1 made at t0 -> expires at t0 + 86400
    # c2 made at t0 + 100 -> expires at t0 + 86500
    # c3 made at t0 + 200 -> expires at t0 + 86600
    open_now = cases.open_cases(folder=tmp_path, now=t0 + 86550)
    assert [c.token for c in open_now] == [c3.token]


def test_sweep(tmp_path):
    t0 = 1000000.0
    c_old = cases.new_case("hi", folder=tmp_path, now=t0)
    cases.add_photo(c_old.token, TINY_JPEG, folder=tmp_path)

    c_new = cases.new_case("en", folder=tmp_path, now=t0 + 86000)
    cases.add_photo(c_new.token, TINY_PNG, folder=tmp_path)

    # Sweep at t0 + 86405: c_old is > 24 hours old
    deleted = cases.sweep(folder=tmp_path, now=t0 + 86405)
    assert deleted == 1
    assert not (tmp_path / c_old.token).exists()
    assert (tmp_path / c_new.token).exists()


def test_langs_rules(tmp_path):
    # order preserved, duplicates removed, unknown dropped, max 4
    c = cases.new_case("hi", langs=["mr", "hi", "mr", "xyz", "gu", "ta", "en"], folder=tmp_path)
    assert c.langs == ["mr", "hi", "gu", "ta"]
    assert c.lang == "mr"

    # empty langs becomes ["hi"]
    c2 = cases.new_case("hi", langs=[], folder=tmp_path)
    assert c2.langs == ["hi"]
    assert c2.lang == "hi"

    # old single lang works
    c3 = cases.new_case("ta", folder=tmp_path)
    assert c3.langs == ["ta"]
    assert c3.lang == "ta"

    # token regex rejects trailing newline
    assert not cases.TOKEN_RE.match(c.token + "\n")


def test_mark_reading(tmp_path):
    c = cases.new_case("hi", folder=tmp_path)
    c = cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
    assert c.state == "photo"

    c = cases.mark_reading(c.token, folder=tmp_path)
    assert c.state == "reading"
    fetched = cases.get(c.token, folder=tmp_path)
    assert fetched.state == "reading"


# --- audit 7 Oct ---

def test_add_photo_refuses_a_case_that_is_being_read_or_answered(tmp_path):
    c = cases.new_case("hi", folder=tmp_path)
    cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
    cases.mark_reading(c.token, folder=tmp_path)
    with pytest.raises(ValueError, match="not taking photos"):
        cases.add_photo(c.token, TINY_PNG, folder=tmp_path)
    assert cases.get(c.token, folder=tmp_path).state == "reading" and len(cases.get(c.token, folder=tmp_path).photos) == 1


def test_mark_reading_is_a_compare_and_set(tmp_path):
    c = cases.new_case("hi", folder=tmp_path)
    cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
    assert cases.mark_reading(c.token, folder=tmp_path).state == "reading"
    assert cases.mark_reading(c.token, folder=tmp_path) is False          # the second reader loses
    cases.set_finding(c.token, {}, "", "", folder=tmp_path)
    assert cases.mark_reading(c.token, folder=tmp_path) is False          # and a read case is not read again


def test_mark_not_clear_only_for_a_case_that_was_read(tmp_path):
    c = cases.new_case("hi", folder=tmp_path)
    with pytest.raises(ValueError, match="cannot mark"):
        cases.mark_not_clear(c.token, folder=tmp_path)                    # waiting
    cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
    cases.mark_reading(c.token, folder=tmp_path)
    with pytest.raises(ValueError, match="cannot mark"):
        cases.mark_not_clear(c.token, folder=tmp_path)                    # being read: the reader would overwrite it
    cases.set_finding(c.token, {"shows": "x"}, "", "", folder=tmp_path)
    assert cases.mark_not_clear(c.token, folder=tmp_path).state == "approved"


def test_photos_added_at_the_same_time_are_all_kept(tmp_path, monkeypatch):
    import threading
    import time
    c = cases.new_case("hi", folder=tmp_path)
    real = cases._save

    def slow(case, folder=None):                       # widen the gap between read and write
        time.sleep(0.02)
        real(case, folder)

    monkeypatch.setattr(cases, "_save", slow)
    ts = [threading.Thread(target=cases.add_photo, args=(c.token, TINY_JPEG, tmp_path)) for _ in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    got = cases.get(c.token, folder=tmp_path)
    assert len(got.photos) == 5 and len(set(got.photos)) == 5
    assert len(list((tmp_path / c.token).glob("*.jpg"))) == 5


def test_set_say_keeps_the_state(tmp_path):
    c = cases.new_case("hi", folder=tmp_path)
    with pytest.raises(ValueError):
        cases.set_say(c.token, "x", folder=tmp_path)
    cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
    cases.set_finding(c.token, {}, "", "old", folder=tmp_path)
    got = cases.set_say(c.token, "new words", folder=tmp_path)
    assert got.say == "new words" and got.state == "read"


def test_the_p_facts_survive_on_disk(tmp_path):
    c = cases.new_case("hi", folder=tmp_path)
    cases.set_sms_meta(c.token, {"sent": 2, "whole": 1, "widths": [300]}, folder=tmp_path)
    assert cases.get(c.token, folder=tmp_path).sms_meta == {"sent": 2, "whole": 1, "widths": [300]}


def test_a_held_case_outlives_the_day_and_the_sweep_says_so(tmp_path, capsys):
    import os
    import time
    c = cases.new_case("hi", folder=tmp_path, now=time.time() - 30 * 3600)
    cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
    cases.set_finding(c.token, {"sms": {"reasons": ["sure"]}}, "", "", folder=tmp_path)
    assert cases.get(c.token, folder=tmp_path) is not None and [x.token for x in cases.open_cases(tmp_path)] == [c.token]
    assert cases.sweep(tmp_path) == 0                                      # a person was asked: it is kept
    old = time.time() - 80 * 3600                                          # nobody touched it for 80 h
    os.utime(tmp_path / c.token / "case.json", (old, old))
    assert cases.get(c.token, folder=tmp_path) is None
    assert cases.sweep(tmp_path) == 1
    assert "swept while held" in capsys.readouterr().out
    plain = cases.new_case("hi", folder=tmp_path, now=time.time() - 30 * 3600)   # a case nobody was asked about goes at 24 h
    assert cases.sweep(tmp_path) == 1 and not (tmp_path / plain.token).exists()
