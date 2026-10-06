"""M4 + M5 + M6 through the real route and the real desk: P: packets come in, the model answers or a person does.
A stand-in reader (no model, no money). The caller is never told anything is wrong; a person answers on the desk."""
import io
import json
import random
import threading
import types

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from haqdaar.contracts import tunables
from haqdaar.keypad_sms import pack
from haqdaar.keypad_sms.join import PhotoJoin
from haqdaar.photo import cases, reader, review
from tools import photo_desk

NUMBER = "+919876543210"
GOOD = {"shows": "a pink worm in a cotton boll", "wrong": "the boll is eaten", "sure": 0.9, "search": "", "by": "muse"}


def photo(seed=1):
    rnd = random.Random(seed)
    img = Image.new("RGB", (640, 480), (rnd.randrange(60, 200), 120, 60))
    d = ImageDraw.Draw(img)
    for _ in range(14):
        x, y = rnd.randrange(640), rnd.randrange(480)
        d.ellipse((x, y, x + 100, y + 80), fill=tuple(rnd.randrange(256) for _ in range(3)))
    return img


class Sync:
    def __init__(self, target=None, args=(), daemon=None, **kw):
        self.t, self.a = target, args

    def start(self):
        self.t(*self.a)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTO_DIR", str(tmp_path))
    monkeypatch.setenv("PHOTO_AUTO", "true")
    monkeypatch.setenv("REVIEW_LABELS_FILE", str(tmp_path / "labels.jsonl"))
    monkeypatch.setattr(tunables, "SMS_DOOR", True)
    monkeypatch.setattr(tunables, "SMS_IDLE_S", 3600.0)
    monkeypatch.setattr(photo_desk, "_PHOTO_AUTO_RUNTIME", True)
    monkeypatch.setattr(photo_desk, "_pjoin", PhotoJoin())
    monkeypatch.setattr(photo_desk, "_sms_meta", {})
    monkeypatch.setattr(photo_desk, "threading", types.SimpleNamespace(Thread=Sync, Timer=threading.Timer, Lock=threading.Lock))
    monkeypatch.setattr(photo_desk, "pick_scheme", lambda term: ("", ""))
    seen, finding = [], dict(GOOD)

    def fake_read(photos, lang="en", post=None, ledger=None, note=""):
        seen.append((photos, note))
        return dict(finding)

    monkeypatch.setattr(reader, "read", fake_read)
    case = cases.new_case("hi", NUMBER)

    class Rig:
        pass

    r = Rig()
    r.door, r.desk, r.case, r.seen, r.finding, r.dir = (TestClient(photo_desk.photo_app), TestClient(photo_desk.desk_app),
                                                       case, seen, finding, tmp_path)
    r.get = lambda: cases.get(case.token)
    r.labels = lambda: [json.loads(x) for x in (tmp_path / "labels.jsonl").read_text().splitlines()] if (tmp_path / "labels.jsonl").exists() else []
    r.called = lambda: (tmp_path / "next_call.json").exists()
    yield r
    for t in list(photo_desk._ptimer.values()):
        t.cancel()


def send(rig, packets):
    return [rig.door.post("/sms", json={"text": p}).json() for p in packets]


def break_one(packets):
    p = packets[0]
    i = len(p) - 12
    return [p[:i] + ("A" if p[i] != "A" else "B") + p[i + 1:]] + packets[1:]


def files(rig):
    return [p for p in (rig.dir / rig.case.token).glob("*.jpg")] if (rig.dir / rig.case.token).exists() else []


def test_sure_and_big_the_model_answers_and_nothing_is_kept(rig):
    c = pack.cut_photo(photo(), "417", 1, 1)
    assert c["w"] >= tunables.SMS_SMALL_W
    replies = send(rig, c["packets"])
    assert replies[-1]["reply"] == "OK PHOTO 1"
    case = rig.get()
    assert case.state == "approved" and rig.called()
    assert case.photos == [] and files(rig) == []                     # wiped once answered
    assert rig.labels() == []                                         # no person, no label
    photos, note = rig.seen[0]
    assert Image.open(io.BytesIO(photos[0])).size[0] >= 512           # enlarged before the reader
    assert "tiny" in note and "low sure" in note                      # the reader is told
    assert case.finding["sms"]["reasons"] == [] and case.finding["sms"]["whole"] == 1


def test_not_sure_a_person_answers_and_the_caller_gets_nothing_meanwhile(rig):
    rig.finding["sure"] = 0.5
    send(rig, pack.cut_photo(photo(), "417", 1, 1)["packets"])
    case = rig.get()
    assert case.state == "read" and not rig.called()                  # waits on the desk; no call-back, no message
    assert len(case.photos) == 1 and len(files(rig)) == 1
    assert "sure" in case.finding["sms"]["reasons"]
    d = photo_desk._case_to_dict(case)
    assert "waits because" in d["note"] and "1 of 1 photos came" in d["note"]
    r = rig.desk.post(f"/approve/{case.token}", content=case.say.encode())
    assert r.status_code == 200
    assert rig.called() and rig.get().state == "approved"
    assert rig.get().photos == [] and files(rig) == []                # wiped after the person's answer
    (label,) = rig.labels()
    assert label["same"] is True and label["kind"] == "approve" and "sure" in label["reasons"]
    text = (rig.dir / "labels.jsonl").read_text()
    assert NUMBER[-6:] not in text and "9876" not in text             # no phone number
    assert "P:" not in text                                           # no packet, no picture


def test_a_typed_answer_is_a_label_that_differs(rig):
    rig.finding["sure"] = 0.3
    send(rig, pack.cut_photo(photo(), "417", 1, 1)["packets"])
    tok = rig.get().token
    rig.desk.post(f"/approve/{tok}", content=b"This is a stem borer, spray after a field officer visit.")
    (label,) = rig.labels()
    assert label["same"] is False and "stem borer" in label["answer"]


def test_a_small_picture_goes_to_a_person(rig, monkeypatch):
    monkeypatch.setattr(tunables, "SMS_SMALL_W", 999)
    send(rig, pack.cut_photo(photo(), "417", 1, 1)["packets"])
    case = rig.get()
    assert case.state == "read" and case.finding["sms"]["reasons"] == ["small"]
    assert not rig.called()


def test_a_lost_photo_goes_to_a_person_and_the_whole_one_is_there(rig):
    cut = pack.cut_case([photo(1), photo(2)], "417")
    send(rig, cut[0]["packets"])
    replies = send(rig, break_one(cut[1]["packets"]))
    assert replies[-1]["reply"] == "ERR JOIN"
    case = rig.get()
    assert case.state == "read" and not rig.called()
    assert len(case.photos) == 1 and "lost" in case.finding["sms"]["reasons"]
    assert "1 of 2 photos came" in photo_desk._case_to_dict(case)["note"]


def test_no_photo_came_whole_a_person_answers_from_the_callers_words(rig):
    send(rig, break_one(pack.cut_photo(photo(), "417", 1, 1)["packets"]))
    case = rig.get()
    assert case.state == "read" and not rig.called() and case.photos == []
    assert {"none", "lost"} <= set(case.finding["sms"]["reasons"])
    assert rig.seen == []                                             # the model was not even asked
    assert rig.desk.post(f"/approve/{case.token}", content=b"Please show the plant to the field officer.").status_code == 200
    assert rig.called() and rig.labels()[0]["whole"] == 0


def test_the_idle_time_hands_over_what_came(rig):
    cut = pack.cut_case([photo(1), photo(2)], "417")
    send(rig, cut[0]["packets"])                                      # photo 2 never starts
    assert rig.get().state == "waiting" and rig.case.token in photo_desk._ptimer      # the idle timer is running
    photo_desk._psms_deliver((NUMBER, "417"), force=True)             # what the timer does when it fires
    case = rig.get()
    assert case.state == "read" and "lost" in case.finding["sms"]["reasons"]
    assert case.finding["sms"]["whole"] == 1 and case.finding["sms"]["sent"] == 2


def test_not_clear_by_the_person_is_a_label_and_a_wipe(rig):
    rig.finding["sure"] = 0.2
    send(rig, pack.cut_photo(photo(), "417", 1, 1)["packets"])
    tok = rig.get().token
    assert rig.desk.post(f"/not-clear/{tok}").status_code == 200
    assert rig.labels()[0]["kind"] == "not_clear" and files(rig) == []


def test_junk_changes_nothing(rig):
    assert rig.door.post("/sms", json={"text": "P:junk"}).json() == {"ok": False, "reply": "ERR BAD"}
    assert rig.get().state == "waiting" and photo_desk._ptimer == {}


def test_a_web_photo_is_untouched_by_all_this(rig):
    buf = io.BytesIO()
    photo().save(buf, "JPEG")
    c = cases.new_case("hi", "")
    cases.add_photo(c.token, buf.getvalue())
    cases.set_finding(c.token, dict(GOOD), "", "say this")
    assert rig.desk.post(f"/approve/{c.token}", content=b"say this").status_code == 200
    assert rig.labels() == [] and len(cases.get(c.token).photos) == 1  # no label, no wipe for the web door


def test_the_old_h_door_still_works(rig):
    import base64
    from haqdaar.keypad_sms.reassembler import calculate_crc8
    data = b"\xff\xd8\xff\xe0\x00\x10JFIF" + bytes(300) + b"\xff\xd9"
    pieces = [data[i:i + 100] for i in range(0, len(data), 100)]
    out = [rig.door.post("/sms", json={"text": f"H:00a1:{n}/{len(pieces)}:{base64.b64encode(p).decode()}:{calculate_crc8(p):02x}"}).json()
           for n, p in enumerate(pieces, 1)]
    assert out[-1]["ok"] is True and len(rig.get().photos) == 1


def test_the_reader_gets_the_note_in_its_instructions(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSE_API_KEY", "x")
    got = {}

    def post(payload, key, timeout):
        got["system"] = payload["messages"][0]["content"]
        return 500, {}

    buf = io.BytesIO()
    photo().save(buf, "JPEG")
    reader._muse([buf.getvalue()], "en", post=post, ledger=tmp_path / "ledger.jsonl", note="NOTE-X")
    assert got["system"].endswith("NOTE-X") and got["system"].startswith(reader.SYSTEM)
    reader._muse([buf.getvalue()], "en", post=post, ledger=tmp_path / "ledger.jsonl")
    assert got["system"] == reader.SYSTEM


def test_wipe_photos_keeps_the_words(rig):
    buf = io.BytesIO()
    photo().save(buf, "JPEG")
    c = cases.new_case("hi", "")
    cases.add_photo(c.token, buf.getvalue())
    cases.set_finding(c.token, {"shows": "x"}, "", "say")
    cases.wipe_photos(c.token)
    c2 = cases.get(c.token)
    assert c2.photos == [] and c2.say == "say" and c2.state == "read"
    assert not list((rig.dir / c.token).glob("*.jpg"))


def test_counts_by_width(tmp_path):
    p = tmp_path / "l.jsonl"
    rows = [{"widths": [96, 112], "same": True}, {"widths": [96], "same": False}, {"widths": [128], "same": True}]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    c = review.counts(p)
    assert c == {96: {"n": 2, "same": 1}, 128: {"n": 1, "same": 1}}


def _b64(seed):
    import base64
    buf = io.BytesIO()
    photo(seed).save(buf, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def test_the_try_page_plays_the_phone(rig, monkeypatch):
    monkeypatch.setattr(photo_desk, "_door_post", lambda text: rig.door.post("/sms", json={"text": text, "sender": "+9100"}).json())
    assert rig.desk.get("/try").status_code == 200 and "Send as SMS" in rig.desk.get("/try").text
    r = rig.desk.post("/try", json={"photos": [_b64(1), _b64(2)]})
    assert r.status_code == 200
    j = r.json()
    assert j["bad"] == 0 and [c["place"] for c in j["cut"]] == [1, 2]
    case = cases.get(j["token"])
    assert case.finding["sms"]["whole"] == 2 and case.finding["sms"]["sent"] == 2     # both photos joined and read
    row = next(x for x in rig.desk.get("/cases").json() if x["token"] == j["token"])   # what the page polls
    assert row["state"] in ("approved", "read") and row["note"] != ""


def test_the_try_page_says_what_is_wrong(rig, monkeypatch):
    monkeypatch.setattr(photo_desk, "_door_post", lambda text: rig.door.post("/sms", json={"text": text}).json())
    assert rig.desk.post("/try", json={"photos": []}).status_code == 400
    assert rig.desk.post("/try", json={"photos": ["data:image/jpeg;base64,AAAA"]}).status_code == 400
    monkeypatch.setattr(tunables, "SMS_DOOR", False)
    r = rig.desk.post("/try", json={"photos": [_b64(1)]})
    assert r.status_code == 409 and "SMS_DOOR" in r.json()["detail"]


def test_the_try_page_is_not_there_when_the_door_is_off(rig, monkeypatch):
    monkeypatch.setattr(tunables, "SMS_DOOR", False)
    assert rig.desk.get("/try").status_code == 404


def test_a_picture_that_cannot_be_enlarged_is_read_as_it_is(rig, monkeypatch):
    from haqdaar.photo import sms_read

    def boom(jpeg, *a):
        raise ValueError("odd picture")

    monkeypatch.setattr(sms_read, "enlarge", boom)
    send(rig, pack.cut_photo(photo(), "417", 1, 1)["packets"])
    assert rig.get().state in ("approved", "read") and len(rig.seen) == 1     # not stuck in "reading"
    assert Image.open(io.BytesIO(rig.seen[0][0][0])).size[0] < 512             # the small one went to the reader


def test_a_second_approve_of_an_auto_answered_case_writes_no_label(rig):
    send(rig, pack.cut_photo(photo(), "417", 1, 1)["packets"])
    tok = rig.get().token
    assert rig.get().state == "approved"
    rig.desk.post(f"/approve/{tok}", content=b"again")
    assert rig.labels() == []                                                  # no person was ever asked about it


def test_a_disk_fault_while_handing_over_is_not_a_500(rig, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(cases, "add_photo", boom)
    replies = send(rig, pack.cut_photo(photo(), "417", 1, 1)["packets"])
    assert replies[-1]["ok"] is True                                          # a plain answer, not a crash
    case = rig.get()
    assert case.state == "read" and "none" in case.finding["sms"]["reasons"]  # a person answers from the caller's words


def test_a_well_formed_packet_longer_than_any_sms_is_refused_before_it_is_stored(rig):
    b = pack.cut_photo(photo(), "417", 1, 1)["packets"][0].split(":")
    b[10] = "A" * 2500                                                        # letters that parse, but 17 parts long
    assert rig.door.post("/sms", json={"text": ":".join(b)}).json() == {"ok": False, "reply": "ERR BAD"}
    assert photo_desk._pjoin.groups == {}


def test_a_packet_longer_than_any_sms_is_refused(rig):
    assert rig.door.post("/sms", json={"text": "P:" + "A" * 2500}).json() == {"ok": False, "reply": "ERR BAD"}
    assert rig.door.post("/sms", json={"text": "Q:ab:L:1:" + "A" * 2500}).json() == {"ok": False, "reply": "ERR BAD"}


def test_the_try_page_survives_a_one_dot_photo(rig, monkeypatch):
    import base64
    monkeypatch.setattr(photo_desk, "_door_post", lambda text: rig.door.post("/sms", json={"text": text, "sender": "+9100"}).json())
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), (5, 5, 5)).save(buf, "JPEG")
    r = rig.desk.post("/try", json={"photos": ["data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()]})
    assert r.status_code in (200, 400)                                         # never a 500
