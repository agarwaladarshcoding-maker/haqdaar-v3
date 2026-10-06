"""M2: the join of P: packets. Every lock, every failure. No model, no phone, no money."""
import random

from PIL import Image, ImageDraw

from haqdaar.keypad_sms import join as J
from haqdaar.keypad_sms import pack


def photo(seed=1, size=(640, 480)):
    rnd = random.Random(seed)
    img = Image.new("RGB", size, (rnd.randrange(60, 200), 120, 60))
    d = ImageDraw.Draw(img)
    for _ in range(12):
        x, y = rnd.randrange(size[0]), rnd.randrange(size[1])
        d.ellipse((x, y, x + 90, y + 70), fill=tuple(rnd.randrange(256) for _ in range(3)))
    return img


def cut(seed=1, sent=1, place=1, case="417", **kw):
    return pack.cut_photo(photo(seed), case, sent, place, **kw)


def feed(j, packets, sender="s1"):
    return [j.add(sender, p, owner="tok", now=0.0) for p in packets]


def decoded_size(jpeg):
    import io
    return Image.open(io.BytesIO(jpeg)).size


def test_one_photo_joins_whole():
    c = cut()
    j = J.PhotoJoin()
    res = feed(j, c["packets"])
    assert [r.status for r in res] == ["stored"] * (c["n"] - 1) + ["photo"]
    case = j.take(res[-1].key)
    assert case.sent == 1 and case.failed == 0 and case.owner == "tok"
    assert decoded_size(case.photos[0][1]) == (c["w"], c["h"])
    assert j.groups == {}


def test_out_of_order_and_last_packet_first():
    c = cut()
    pk = list(c["packets"])
    for order in (pk[::-1], pk[1:] + pk[:1]):
        j = J.PhotoJoin()
        res = feed(j, order)
        assert res[-1].status == "photo"
        assert j.take(res[-1].key).photos[0][0] == 1


def test_double_is_ignored_and_does_not_count_twice():
    c = cut()
    j = J.PhotoJoin()
    feed(j, c["packets"][:1])
    assert j.add("s1", c["packets"][0], now=0.0).status == "dup"
    res = feed(j, c["packets"][1:])
    assert res[-1].status == "photo"


def test_double_with_other_bytes_drops_the_photo():
    c = cut()
    j = J.PhotoJoin()
    feed(j, c["packets"][:1])
    p = c["packets"][0]
    i = p.rindex(":") + 1
    other = p[:i] + ("B" if p[i] != "B" else "C") + p[i + 1:]
    r = j.add("s1", other, now=0.0)
    assert r.status == "dropped"
    # the rest of that try is ignored, nothing is read
    assert all(x.status in ("ignored", "dropped") for x in feed(j, c["packets"][1:]))
    case = j.take(r.key)
    assert case.photos == [] and case.failed == 1


def test_a_lost_packet_never_joins():
    c = cut()
    j = J.PhotoJoin()
    res = feed(j, c["packets"][:1] + c["packets"][2:])
    assert all(r.status == "stored" for r in res)
    assert j.take(res[-1].key) is None                      # not ready
    case = j.take(res[-1].key, force=True)                  # the idle time is up
    assert case.photos == [] and case.failed == 1


def test_one_changed_byte_fails_the_whole_check():
    c = cut()
    pk = list(c["packets"])
    p = pk[0]
    i = len(p) - 10
    pk[0] = p[:i] + ("A" if p[i] != "A" else "B") + p[i + 1:]
    j = J.PhotoJoin()
    res = feed(j, pk)
    assert res[-1].status == "dropped" and res[-1].reply == "ERR JOIN"


def test_cut_off_picture_fails():
    c = cut()
    j = J.PhotoJoin()
    pk = list(c["packets"])
    # shorten the last payload; length and check no longer match
    last = pk[-1].split(":")
    last[10] = last[10][:-8]
    pk[-1] = ":".join(last)
    res = feed(j, pk)
    assert res[-1].status == "dropped"


def test_header_not_standard_fails_lock_4():
    c = cut(hdr=0)
    j = J.PhotoJoin()
    old = J._header
    J._header = lambda w, h, q: b"\xff\xd8\xff\xd9" + b"x" * 10      # a different header
    try:
        res = feed(j, c["packets"])
    finally:
        J._header = old
    assert res[-1].status == "dropped" and res[-1].reply == "ERR JOIN"


def test_hdr_on_photo_joins_too():
    c = cut(hdr=1)
    j = J.PhotoJoin()
    res = feed(j, c["packets"])
    assert res[-1].status == "photo"


def test_two_photos_do_not_mix_even_with_packets_in_one_row():
    a, b = cut(1, 2, 1), cut(2, 2, 2)
    row = []
    for x, y in zip(a["packets"], b["packets"]):
        row += [y, x]
    row += a["packets"][len(b["packets"]):] + b["packets"][len(a["packets"]):]
    j = J.PhotoJoin()
    res = feed(j, row)
    case = j.take(res[-1].key)
    assert [pl for pl, _ in case.photos] == [1, 2] and case.failed == 0
    assert decoded_size(case.photos[0][1]) == (a["w"], a["h"])


def test_one_photo_of_three_lost_the_others_go_on():
    cs = [cut(i, 3, i) for i in (1, 2, 3)]
    j = J.PhotoJoin()
    res = feed(j, cs[0]["packets"] + cs[2]["packets"] + cs[1]["packets"][:-1])
    key = res[0].key
    assert not j.ready(key)
    case = j.take(key, force=True)
    assert [pl for pl, _ in case.photos] == [1, 3] and case.failed == 1


def test_ready_when_every_sent_photo_is_whole():
    cs = [cut(i, 2, i) for i in (1, 2)]
    j = J.PhotoJoin()
    res = feed(j, cs[0]["packets"])
    assert not j.ready(res[-1].key)
    res = feed(j, cs[1]["packets"])
    assert j.ready(res[-1].key)


def test_a_late_packet_of_the_first_try_never_mixes_into_the_second():
    first = cut(1)
    second = pack.cut_photo(photo(9), "417", 1, 1)               # the photo sent again: a new stamp
    assert first["stamp"] != second["stamp"]
    j = J.PhotoJoin()
    feed(j, first["packets"][:-1])                               # the first try stalls
    res = feed(j, second["packets"])                             # the second comes whole
    assert res[-1].status == "photo"
    late = j.add("s1", first["packets"][-1], now=1.0)            # the first one's last packet arrives late
    assert late.status == "ignored"
    case = j.take(res[-1].key)
    assert decoded_size(case.photos[0][1]) == (second["w"], second["h"])


def test_packets_of_a_dropped_try_stay_ignored():
    c = cut()
    j = J.PhotoJoin()
    feed(j, c["packets"][:1])
    p = c["packets"][0]
    i = p.rindex(":") + 1
    j.add("s1", p[:i] + ("B" if p[i] != "B" else "C") + p[i + 1:], now=0.0)
    assert j.add("s1", c["packets"][1], now=0.0).status == "ignored"


def test_facts_must_agree():
    c = cut()
    j = J.PhotoJoin()
    feed(j, c["packets"][:1])
    bits = c["packets"][1].split(":")
    bits[7] = str(int(bits[7]) + 1)                               # another length
    assert j.add("s1", ":".join(bits), now=0.0).reply == "ERR FACTS"


def test_sent_must_agree_in_a_case():
    j = J.PhotoJoin()
    a, b = cut(1, 2, 1), cut(2, 3, 2)
    feed(j, a["packets"][:1])
    assert j.add("s1", b["packets"][0], now=0.0).reply == "ERR FACTS"


def test_two_senders_are_two_groups():
    c = cut()
    j = J.PhotoJoin()
    feed(j, c["packets"][:1], "a")
    res = feed(j, c["packets"][1:], "b")                           # b never sent packet 1
    assert all(r.status == "stored" for r in res)
    assert len(j.groups) == 2
    assert j.take(res[-1].key, force=True).photos == []


def test_range_and_junk_are_refused():
    j = J.PhotoJoin()
    assert j.add("s", "hello").status == "bad"
    assert j.add("s", "H:0001:1/2:AAAA:00").status == "bad"       # the old tag is not ours
    c = cut(1, 2, 1)
    bits = c["packets"][0].split(":")
    bits[3] = "3"                                                  # place 3 of 2 photos
    assert j.add("s", ":".join(bits)).reply == "ERR RANGE"
    bits = c["packets"][0].split(":")
    bits[2] = "9"                                                  # 9 photos: over the cap
    assert j.add("s", ":".join(bits)).reply == "ERR RANGE"
    bits = c["packets"][0].split(":")
    bits[6] = "99"                                                 # a step that is not in the ladder
    assert j.add("s", ":".join(bits)).reply == "ERR RANGE"


def test_a_photo_over_its_share_is_dropped():
    big = cut(1, 1, 1)                                             # one photo: a share of 20 parts
    assert big["parts"] > 10
    packets = []
    for p in big["packets"]:
        b = p.split(":")
        b[2] = "3"                                                 # the tag now says 3 photos: a share of 10 parts
        packets.append(":".join(b))
    res = feed(J.PhotoJoin(), packets)
    assert any(r.reply == "ERR TOO_BIG" for r in res)
    assert not any(r.status == "photo" for r in res)


def test_a_server_restart_drops_everything():
    c = cut()
    j = J.PhotoJoin()
    feed(j, c["packets"][:-1])
    j2 = J.PhotoJoin()                                            # the process came up again
    r = j2.add("s1", c["packets"][-1], now=0.0)
    assert r.status == "stored"
    assert j2.take(r.key, force=True).photos == []


def test_stale_groups_are_removed_and_the_group_count_is_bounded():
    c = cut()
    j = J.PhotoJoin()
    j.add("s1", c["packets"][0], now=0.0)
    assert j.sweep(now=10 ** 6) == 1 and j.groups == {}
    for i in range(J.MAX_GROUPS + 5):
        j.add("s%d" % i, c["packets"][0], now=float(i))
    assert len(j.groups) == J.MAX_GROUPS


def test_a_failed_place_can_be_sent_again():
    c = cut()
    j = J.PhotoJoin()
    feed(j, c["packets"][:1])
    p = c["packets"][0]
    i = p.rindex(":") + 1
    r = j.add("s1", p[:i] + ("B" if p[i] != "B" else "C") + p[i + 1:], now=0.0)
    assert j.ready(r.key)                                          # the one photo is lost
    again = pack.cut_photo(photo(5), "417", 1, 1)
    res = feed(j, again["packets"])
    assert res[-1].status == "photo"
    assert j.take(res[-1].key).failed == 0
