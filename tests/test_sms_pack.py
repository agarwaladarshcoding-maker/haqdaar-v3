"""M1: the cut. Cut then join gives the same bytes. Plain words."""

import base64
import io
import random

from PIL import Image, ImageDraw

from haqdaar.keypad_sms.pack import (
    B64,
    PART_LEN,
    SIZE_LADDER,
    check_of,
    cut_photo,
    encode_jpeg,
    make_header,
    parse_packet,
    split_header,
    stamp_of,
)
from haqdaar.keypad_sms.share import share_parts


def pest(seed, w=640, h=480):
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h), (60, 140, 60))
    d = ImageDraw.Draw(img)
    for _ in range(400):
        x, y = rnd.randrange(w), rnd.randrange(h)
        g = rnd.randrange(40, 200)
        d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(g // 3, g, g // 4))
    for _ in range(25):
        x, y = rnd.randrange(w), rnd.randrange(h)
        d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=(30, 25, 10))
    return img


def join_packets(packets, hdr):
    """Plain test join for now: parse, order by k, join payloads, decode bytes."""
    got = {}
    facts = None
    for p in packets:
        r = parse_packet(p)
        assert r is not None
        key = (r["case"], r["sent"], r["place"], r["stamp"])
        if facts is None:
            facts = (key, r["n"], r["step"], r["size"], r["hdr"])
        assert (key, r["n"], r["step"], r["size"], r["hdr"]) == facts
        assert r["k"] not in got or got[r["k"]] == r["payload"]
        got[r["k"]] = r["payload"]
    assert sorted(got) == list(range(1, facts[1] + 1))
    body = base64.b64decode("".join(got[k] for k in sorted(got)))
    assert len(body) == facts[3]
    assert check_of(body) == packets[-1].rsplit(":", 1)[1]
    full = (make_header(*SIZE_LADDER[facts[2]], 45) + body) if hdr == 0 else body
    img = Image.open(io.BytesIO(full))
    img.load()  # strict: a cut-off picture fails here
    assert img.size == SIZE_LADDER[facts[2]]
    return body


def test_share_parts():
    assert share_parts(1) == 20
    assert share_parts(2) == 12
    assert share_parts(3) == 10
    assert share_parts(5) == 10


def test_stamp_and_check():
    assert len(stamp_of(b"abc")) == 3
    assert len(check_of(b"abc")) == 6
    assert stamp_of(b"abc") == stamp_of(b"abc")
    assert check_of(b"abc") != check_of(b"abd")
    assert set(stamp_of(b"x") + check_of(b"x")) <= set(B64)


def test_header_roundtrip():
    w, h = SIZE_LADDER[3]
    head = make_header(w, h, 45)
    raw = encode_jpeg(pest(1).crop((160, 120, 480, 360)), w, h, 45)
    body = split_header(raw)[1]
    img = Image.open(io.BytesIO(head + body))
    img.load()
    assert img.size == (w, h)


def test_cut_join_hdr0():
    cut = cut_photo(pest(11), "c7", 1, 1)
    assert join_packets(cut["packets"], 0) is not None
    assert cut["parts"] <= 20


def test_cut_join_hdr1():
    cut = cut_photo(pest(12), "c8", 1, 1, hdr=1)
    assert join_packets(cut["packets"], 1) is not None


def test_one_photo_big_enough():
    for seed in (21, 22, 23):
        cut = cut_photo(pest(seed), "c9", 1, 1)
        assert cut["w"] >= 144 and cut["h"] >= 108, cut


def test_share_budgets():
    photos = [pest(s) for s in (31, 32, 33)]
    for sent, per in ((1, 20), (2, 12), (3, 10)):
        for i in range(sent):
            cut = cut_photo(photos[i], "c%d" % sent, sent, i + 1)
            assert cut["parts"] <= per, (sent, cut["parts"])
            assert cut["sent"] == sent and cut["place"] == i + 1


def test_packet_shapes():
    cut = cut_photo(pest(41), "c10", 2, 1, dev="ab")
    assert len(cut["packets"]) == cut["n"] > 0
    for i, p in enumerate(cut["packets"], 1):
        assert len(p) <= 5 * PART_LEN, len(p)
        r = parse_packet(p)
        assert (r["k"], r["n"]) == (i, cut["n"])
        assert (r["sent"], r["place"], r["dev"]) == (2, 1, "ab")
        assert (r["check"] is None) == (i != cut["n"])
    assert cut["packets"][-1].endswith(":" + cut["check"])


def test_packet_parts_setting():
    cut = cut_photo(pest(42), "c11", 1, 1, packet_parts=3)
    for p in cut["packets"]:
        assert len(p) <= 3 * PART_LEN


def test_gsm_letters():
    cut = cut_photo(pest(43), "c12", 1, 1)
    ok = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:;+,/=-")
    for p in cut["packets"]:
        assert set(p) <= ok, set(p) - ok


def test_bad_packets():
    assert parse_packet("H:00a1:1/2:eA==:3f") is None
    assert parse_packet("P:only:three") is None
    cut = cut_photo(pest(44), "c13", 1, 1)
    assert parse_packet(cut["packets"][0] + ":XXXXXX") is None  # check on a non-last packet


def test_a_tiny_picture_still_cuts():
    from haqdaar.keypad_sms.pack import cut_photo, parse_packet
    c = cut_photo(Image.new("RGB", (1, 1), (9, 9, 9)), "417", 1, 1)
    assert parse_packet(c["packets"][0]) is not None
