"""Step 3: Door 0 on the server. A photo cut into SMS pieces comes in by the stand-in route, mixed order,
one double, one late piece; the case ends with the same photo and goes to reading by the same path as Door 1."""
import base64
import time
import unittest.mock as mock

import pytest
from fastapi.testclient import TestClient

from haqdaar.contracts import tunables
from haqdaar.keypad_sms.reassembler import SMSReassemblyManager, calculate_crc8
from haqdaar.photo import cases
from tools import photo_desk

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00" + bytes(range(256)) * 3 + b"\xff\xd9"


def _pieces(data: bytes, msg_id: int = 0x00A1, size: int = 100) -> list[str]:
    parts = [data[i:i + size] for i in range(0, len(data), size)]
    return [f"H:{msg_id:04x}:{n}/{len(parts)}:{base64.b64encode(p).decode()}:{calculate_crc8(p):02x}"
            for n, p in enumerate(parts, 1)]


@pytest.fixture
def door(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTO_DIR", str(tmp_path))
    monkeypatch.setattr(tunables, "SMS_DOOR", True)
    monkeypatch.setattr(tunables, "SMS_DONE_S", 60.0)
    monkeypatch.setattr(photo_desk, "_sms", SMSReassemblyManager())
    monkeypatch.setattr(photo_desk, "_sms_done", set())
    ran = []
    monkeypatch.setattr(photo_desk, "_process_done", lambda token: ran.append(token))
    case = cases.new_case("hi", "+919876543210")
    yield TestClient(photo_desk.photo_app), case, ran
    for t in list(photo_desk._sms_timer.values()):
        t.cancel()


def _send(client, text):
    return client.post("/sms", json={"text": text}).json()


def _wait(ran, n=1):
    for _ in range(100):
        if len(ran) >= n:
            return
        time.sleep(0.02)


def test_mixed_order_double_and_late_piece_end_in_the_same_photo_and_read(door):
    client, case, ran = door
    p = _pieces(JPEG)
    assert len(p) >= 4
    order = [p[2], p[0], p[0], p[3]] + p[4:]            # mixed order, one double
    for text in order:
        r = _send(client, text)
        assert r["ok"] and r["reply"].startswith(("NACK", "ACK"))
    assert cases.get(case.token).photos == []           # a late piece is still missing
    assert "MISSING 2" in r["reply"]
    r = _send(client, p[1])                              # the late piece
    assert r["reply"].endswith("OK")
    got = cases.get(case.token)
    assert len(got.photos) == 1 and cases.photo_bytes(case.token, 0)[0] == JPEG
    assert _send(client, p[1])["ok"] and len(cases.get(case.token).photos) == 1   # a double after the end adds nothing
    assert _send(client, "H:DONE")["ok"]
    _wait(ran)
    assert ran == [case.token]                          # the same _process_done as Door 1
    assert cases.get(case.token).state == "reading"


def test_two_minutes_with_no_new_piece_counts_as_done(door, monkeypatch):
    client, case, ran = door
    monkeypatch.setattr(tunables, "SMS_DONE_S", 0.1)
    for text in _pieces(JPEG):
        _send(client, text)
    _wait(ran)
    assert ran == [case.token]


def test_flag_off_the_route_is_not_there(door, monkeypatch):
    client, case, ran = door
    monkeypatch.setattr(tunables, "SMS_DOOR", False)
    assert client.post("/sms", json={"text": _pieces(JPEG)[0]}).status_code == 404
    assert cases.get(case.token).photos == []


def test_no_open_case_drops_the_piece(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTO_DIR", str(tmp_path))
    monkeypatch.setattr(tunables, "SMS_DOOR", True)
    r = TestClient(photo_desk.photo_app).post("/sms", json={"text": _pieces(JPEG)[0]}).json()
    assert r == {"ok": False, "reply": "ERR NO_CASE"}


def test_bad_pieces_and_limits_and_no_number_in_reply(door):
    client, case, ran = door
    assert _send(client, "hello")["reply"] == "ERR INVALID_PACKET"
    assert client.post("/sms", json={}).status_code == 400
    for i in range(cases.MAX_PHOTOS + 1):               # six photos at most
        for text in _pieces(JPEG, msg_id=i + 1):
            r = _send(client, text)
    assert r["ok"] is False and "six photos" in r["reply"]
    assert len(cases.get(case.token).photos) == cases.MAX_PHOTOS
    assert "9876" not in str(r)


def test_the_app_page_can_read_the_reply(door):
    client, case, ran = door
    r = client.post("/sms", content='{"text": "hello"}', headers={"Content-Type": "text/plain", "Origin": "http://127.0.0.1:8080"})
    assert r.headers["access-control-allow-origin"] == "*" and r.json()["reply"] == "ERR INVALID_PACKET"


def test_app_page_is_small_and_has_no_outside_file():
    page = (cases.Path(__file__).parent.parent / "keypad_app" / "index.html").read_text(encoding="utf-8")
    assert len(page.encode()) < 20 * 1024
    assert "src=\"http" not in page and "href=\"http" not in page and "sms:" not in page   # nothing opens the phone's SMS screen


def test_shrink_fits_ten_sms_for_a_plain_photo():
    from PIL import Image
    from tools import sms_shrink
    data, _ = sms_shrink.shrink(Image.new("RGB", (800, 600), (40, 120, 40)))
    assert sms_shrink.sms_count(len(data)) <= sms_shrink.MAX_SMS


def test_phone_demo_page_shows_the_sms_and_picks_the_door_by_data():
    page = (cases.Path(__file__).parent.parent / "keypad_app" / "demo.html").read_text(encoding="utf-8")
    assert "Open the Haqdaar app" in page and "index.html?embed=1" in page and "MOBILE DATA" in page
    assert "src=\"http" not in page and "href=\"http" not in page
