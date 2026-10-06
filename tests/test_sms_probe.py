"""M7: the phone probe and the phone settings, with simulated phones. Every odd phone ends in a working send."""
import random

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from haqdaar.contracts import tunables
from haqdaar.keypad_sms import join, pack, probe
from haqdaar.keypad_sms.join import PhotoJoin
from haqdaar.keypad_sms.probe import Probe
from tools import photo_desk


def photo(seed=1):
    rnd = random.Random(seed)
    img = Image.new("RGB", (640, 480), (rnd.randrange(60, 200), 120, 60))
    d = ImageDraw.Draw(img)
    for _ in range(14):
        x, y = rnd.randrange(640), rnd.randrange(480)
        d.ellipse((x, y, x + 100, y + 80), fill=tuple(rnd.randrange(256) for _ in range(3)))
    return img


@pytest.fixture
def pr(tmp_path):
    return Probe(tmp_path / "profile.json"), tmp_path / "profile.json"


def run_probe(p, dev, header=None, ladder=probe.LADDER, sender="+91x", t0=0.0, step=1.0):
    pk = probe.probe_packets(dev, probe.expected_header() if header is None else header, ladder)
    reply = None
    for i, text in enumerate(pk):
        status, r = p.add(sender, text, now=t0 + i * step)
        assert status != "bad", text[:30]
        reply = r or reply
    return reply


def send_all(cuts):
    j = join.PhotoJoin()
    last = None
    for c in cuts:
        for pk in c["packets"]:
            last = j.add("s", pk, owner="t", now=0.0)
    assert j.ready(last.key)
    case = j.take(last.key)
    assert case.failed == 0 and len(case.photos) == len(cuts)
    return case


def test_a_standard_phone_leaves_the_header_out_and_takes_long_packets(pr):
    p, path = pr
    assert run_probe(p, "K1") == "S:0:10"                       # 20 parts arrived; a packet is never asked past 10
    assert probe.settings_for("K1", path) == {"hdr": 0, "packet_parts": 10}
    cuts = probe.cut_for_dev([photo(1)], "417", "K1", path)
    assert cuts[0]["hdr"] == 0 and max(len(x) for x in cuts[0]["packets"]) <= 10 * pack.PART_LEN
    send_all(cuts)


def test_a_phone_with_another_header_sends_the_header(pr):
    p, path = pr
    odd = b"\xff\xd8\xff\xe0" + bytes(range(200)) + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00"
    assert run_probe(p, "K2", header=odd).startswith("S:1:")
    cuts = probe.cut_for_dev([photo(2)], "417", "K2", path)
    assert cuts[0]["hdr"] == 1
    send_all(cuts)


def test_a_phone_with_a_small_parts_limit(pr):
    p, path = pr
    assert run_probe(p, "K3", ladder=(1, 3)) == "S:0:3"          # 5 and up never arrived
    st = probe.settings_for("K3", path)
    assert st["packet_parts"] == 3
    cuts = probe.cut_for_dev([photo(3)], "417", "K3", path)
    assert max(len(x) for x in cuts[0]["packets"]) <= 3 * pack.PART_LEN
    send_all(cuts)


def test_a_slow_link_is_measured_not_refused(pr):
    p, path = pr
    run_probe(p, "K4", step=40.0)
    assert probe.settings_for("K4", path)["hdr"] == 0
    assert 39.0 <= probe._load(path)["K4"]["seconds_a_packet"] <= 41.0


def test_a_lost_settings_text_means_the_safe_default_and_it_still_sends(pr):
    p, path = pr                                                   # the phone never got an answer
    assert probe.settings_for("ZZ", path) == {"hdr": 1, "packet_parts": 5}
    cuts = probe.cut_for_dev([photo(1), photo(2)], "417", "ZZ", path)
    assert cuts[0]["hdr"] == 1
    send_all(cuts)


def test_a_phone_nobody_tested_runs_a_short_probe_on_first_use(pr):
    p, path = pr
    assert run_probe(p, "N9", ladder=(5,)) == "S:0:5"
    assert probe.settings_for("N9", path) == {"hdr": 0, "packet_parts": 5}


def test_the_end_packet_is_lost_so_the_idle_read_gives_the_answer(pr):
    p, path = pr
    for i, text in enumerate(probe.probe_packets("K5", probe.expected_header())[:-1]):
        p.add("+91x", text, now=float(i))
    assert p.finish("+91x", "K5") == "S:0:10"


def test_an_empty_probe_keeps_the_safe_default_and_writes_nothing(pr):
    p, path = pr
    assert p.add("s", "Q:K6:E:")[1] == "S:1:5"
    assert not path.exists()


def test_the_unknown_code_is_never_written(pr):
    p, path = pr
    assert run_probe(p, "--") == "S:0:10"
    assert not path.exists()


def test_bad_probe_packets_are_refused_and_a_short_rung_does_not_count(pr):
    p, path = pr
    for bad in ("Q:K1:X:1:abc", "Q:K1:L:7:abc", "Q:KLM:H:1/1:abc", "Q:K1:H:2/1:abc", "Q:K1:H:1/1:a b", "hello"):
        assert p.add("s", bad)[0] == "bad", bad
    head = "Q:K7:L:5:"
    short = head + probe._filler(5, head)[:-1]                      # one letter short: the packet was cut
    assert p.add("s", short)[0] == "bad"
    p.add("s", "Q:K7:L:3:" + probe._filler(3, "Q:K7:L:3:"))
    assert p.add("s", "Q:K7:E:")[1] == "S:1:3"


def test_two_failed_photos_with_the_header_out_turn_the_header_back_on(pr, monkeypatch):
    p, path = pr
    run_probe(p, "K8")                                              # the probe said: header out is fine
    assert probe.settings_for("K8", path)["hdr"] == 0
    monkeypatch.setattr(join, "_header", lambda w, h, q: b"\xff\xd8\xff\xd9")   # the server and the phone now differ
    j = PhotoJoin()
    outs = []
    for seed in (1, 2):
        c = pack.cut_photo(photo(seed), "417", 1, 1, dev="K8", hdr=0)
        res = [j.add("s", x, now=0.0) for x in c["packets"]][-1]
        assert res.status == "dropped" and res.lock == 4 and res.hdr == 0 and res.dev == "K8"
        outs.append(p.note_failure(res.dev))
    assert outs[0] is None and outs[1] == "S:1:10"
    assert p.note_failure("K8") is None                              # told once
    assert probe.settings_for("K8", path)["hdr"] == 1
    monkeypatch.undo()
    send_all(probe.cut_for_dev([photo(3)], "417", "K8", path))       # the next photo goes with its header and joins


def test_a_bad_check_is_not_blamed_on_the_header(pr):
    p, path = pr
    run_probe(p, "K9")
    c = pack.cut_photo(photo(1), "417", 1, 1, dev="K9", hdr=0)
    pk = list(c["packets"])
    i = len(pk[0]) - 12
    pk[0] = pk[0][:i] + ("A" if pk[0][i] != "A" else "B") + pk[0][i + 1:]
    j = PhotoJoin()
    res = [j.add("s", x, now=0.0) for x in pk][-1]
    assert res.lock == 3                                             # a damaged packet, not a header problem


def test_the_door_answers_a_probe_and_tells_a_failing_phone(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTO_DIR", str(tmp_path))
    monkeypatch.setattr(tunables, "SMS_DOOR", True)
    monkeypatch.setattr(tunables, "SMS_IDLE_S", 3600.0)
    monkeypatch.setattr(photo_desk, "_probe", Probe(tmp_path / "profile.json"))
    monkeypatch.setattr(photo_desk, "_pjoin", PhotoJoin())
    sent = []
    monkeypatch.setattr(photo_desk, "_settings_sender", lambda to, text: sent.append((to, text)))
    c = TestClient(photo_desk.photo_app)
    try:
        replies = [c.post("/sms", json={"text": t, "sender": "+91999"}).json() for t in probe.probe_packets("D1", probe.expected_header())]
        assert replies[-1] == {"ok": True, "reply": "S:0:10"}        # no case is open, and none is needed
        assert sent == [("+91999", "S:0:10")]
        assert c.post("/sms", json={"text": "Q:D1:Z:1:a", "sender": "+91999"}).json()["reply"] == "ERR BAD"
        from haqdaar.photo import cases
        monkeypatch.setattr(join, "_header", lambda w, h, q: b"\xff\xd8\xff\xd9")
        got = []
        for seed in (1, 2):
            cases.new_case("hi", "+91999")                            # one case for each caller's photo
            for pk in pack.cut_photo(photo(seed), "417", 1, 1, dev="D1", hdr=0)["packets"]:
                got.append(c.post("/sms", json={"text": pk, "sender": "+91999"}).json())
        flagged = [g for g in got if "settings" in g]
        assert len(flagged) == 1 and flagged[0]["settings"] == "S:1:10"   # the 2nd failure, once
        assert sent[-1] == ("+91999", "S:1:10")
    finally:
        for t in list(photo_desk._probe_timer.values()) + list(photo_desk._ptimer.values()):
            t.cancel()
