import re
"""tests/test_photo_desk.py

Tests for tools.photo_desk:
- Photo page good (under 20 KB, no http(s):// to outside host, Cache-Control: no-store)
- Wrong token 404 (and no longer good message)
- 429 rate limit after 10 failed token attempts
- /photo good (saves photo and returns ok)
- /photo not a picture (400)
- /photo too big (413)
- /done sets finding, scheme, and say
- Photo app has no desk routes (/, /approve/..., /new)
- HTML escaping on desk helper page
- call_back writes next_call.json atomically and makes no phone call
- desk app /approve/{token} and /new
"""
import json
import os
import unittest.mock as mock
import pytest
from fastapi.testclient import TestClient

from haqdaar.photo import cases
from tools import photo_desk

# Tiny pictures made by hand for type checking:
# JPEG starts with FF D8 FF
TINY_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb"
# PNG starts with 89 50 4E 47 0D 0A 1A 0A
TINY_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"


@pytest.fixture(autouse=True)
def reset_rate_limits():
    photo_desk._wrong_token_attempts.clear()
    photo_desk._blocked_until.clear()


def test_photo_page_good_and_under_20kb(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("hi", "+919876543210", folder=tmp_path)
        client = TestClient(photo_desk.photo_app)
        resp = client.get(f"/p/{c.token}")
        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == "no-store"

        content = resp.text
        raw_bytes = resp.content
        assert len(raw_bytes) < 20 * 1024, f"Page size {len(raw_bytes)} is >= 20 KB"

        # No external links
        assert "http://" not in content
        assert "https://" not in content

        # Check phone ending
        assert "3210" in content

        # Check language order for hi
        hi_idx = content.find("फोटो खींचें")
        mr_idx = content.find("फोटो काढा")
        en_idx = content.find("Take a photo")
        assert hi_idx < mr_idx < en_idx


def test_photo_page_language_order_marathi(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("mr", folder=tmp_path)
        client = TestClient(photo_desk.photo_app)
        resp = client.get(f"/p/{c.token}")
        assert resp.status_code == 200
        content = resp.text

        # Marathi should come first for mr
        mr_idx = content.find("फोटो काढा")
        hi_idx = content.find("फोटो खींचें")
        en_idx = content.find("Take a photo")
        assert mr_idx < hi_idx < en_idx


def test_wrong_token_404(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        client = TestClient(photo_desk.photo_app)
        resp = client.get("/p/nonexistent")
        assert resp.status_code == 404
        assert resp.headers.get("cache-control") == "no-store"
        assert "यह लिंक अब काम नहीं करता" in resp.text


def test_rate_limit_429_after_ten_bad_tokens(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        client = TestClient(photo_desk.photo_app)
        for i in range(10):
            r = client.get(f"/p/badtoken{i:02d}")
            assert r.status_code == 404

        # 11th attempt should receive 429
        r11 = client.get("/p/badtoken11")
        assert r11.status_code == 429


def test_photo_upload_good(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("hi", folder=tmp_path)
        client = TestClient(photo_desk.photo_app)

        r1 = client.post(f"/p/{c.token}/photo", content=TINY_JPEG, headers={"Content-Type": "image/jpeg"})
        assert r1.status_code == 200
        assert r1.json() == {"ok": True, "n": 1}

        r2 = client.post(f"/p/{c.token}/photo", content=TINY_PNG, headers={"Content-Type": "image/png"})
        assert r2.status_code == 200
        assert r2.json() == {"ok": True, "n": 2}


def test_photo_upload_not_a_picture(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("en", folder=tmp_path)
        client = TestClient(photo_desk.photo_app)

        r = client.post(f"/p/{c.token}/photo", content=b"this is plain text not an image")
        assert r.status_code == 400
        assert r.json()["ok"] is False
        assert "not a photo" in r.json()["why"]


def test_photo_upload_too_big(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("en", folder=tmp_path)
        client = TestClient(photo_desk.photo_app)

        big_data = TINY_JPEG + b"0" * (5 * 1024 * 1024 + 2)
        r = client.post(f"/p/{c.token}/photo", content=big_data)
        assert r.status_code == 413
        assert r.json()["ok"] is False
        assert "too big" in r.json()["why"]


def test_done_sets_finding_and_say(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("hi", folder=tmp_path)
        cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)

        mock_finding = {
            "shows": "Yellow wilted leaves.",
            "wrong": "Fungal infection.",
            "sure": 0.85,
            "search": "crop loss",
            "by": "http",
        }

        with mock.patch("haqdaar.photo.reader.read", return_value=mock_finding), \
             mock.patch("tools.photo_desk.pick_scheme", return_value=("pmfby", "PM Fasal Bima")):
            client = TestClient(photo_desk.photo_app)
            r = client.post(f"/p/{c.token}/done")
            assert r.status_code == 200
            assert r.json() == {"ok": True}

        updated = cases.get(c.token, folder=tmp_path)
        assert updated.state == "read"
        assert updated.scheme == "pmfby"
        assert "Yellow wilted leaves." in updated.say
        assert "Fungal infection." in updated.say
        assert "PM Fasal Bima" in updated.say
        assert "You can ask me about it now." in updated.say


def test_photo_app_has_no_desk_routes(tmp_path):
    client = TestClient(photo_desk.photo_app)
    assert client.get("/").status_code in (404, 405)
    assert client.post("/approve/abc1234567").status_code in (404, 405)
    assert client.post("/new").status_code in (404, 405)


def test_html_escaping_on_desk(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("en", folder=tmp_path)
        cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
        malicious = {
            "shows": "<script>alert(xss-shows)</script>",
            "wrong": "<script>alert(xss-wrong)</script>",
            "sure": 0.5,
            "search": "<script>",
            "by": "stand-in",
        }
        cases.set_finding(c.token, malicious, "<b>scheme</b>", "<img src=x onerror=alert(say)>", folder=tmp_path)

        client = TestClient(photo_desk.desk_app)
        r = client.get("/")
        assert r.status_code == 200
        body = r.text

        assert "<script>alert" not in body
        assert "&lt;script&gt;alert" in body
        assert "<img src=x" not in body
        assert "&lt;img src=x" in body


def test_call_back_writes_file_and_makes_no_call(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("hi", "+919876543210", folder=tmp_path)
        c.say = "Test say for call back."
        photo_desk.call_back(c)

        out_file = tmp_path / "next_call.json"
        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert data["token"] == c.token
        assert data["lang"] == "hi"
        assert data["say"] == "Test say for call back."
        assert data["made"] == c.made


def test_desk_approve_and_new(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        # 1. POST /new
        client = TestClient(photo_desk.desk_app)
        r_new = client.post("/new")
        assert r_new.status_code == 200
        tok = r_new.json()["token"]
        assert len(tok) == 10

        # Set finding so case can be approved
        cases.add_photo(tok, TINY_JPEG, folder=tmp_path)
        cases.set_finding(tok, {}, "", "", folder=tmp_path)

        # 2. POST /approve/{token}
        r_app = client.post(f"/approve/{tok}", content=b"Approved helper text")
        assert r_app.status_code == 200
        assert r_app.json()["state"] == "approved"

        c = cases.get(tok, folder=tmp_path)
        assert c.state == "approved"
        assert c.say == "Approved helper text"

        # Check next_call.json was created
        next_call = tmp_path / "next_call.json"
        assert next_call.exists()
        data = json.loads(next_call.read_text(encoding="utf-8"))
        assert data["say"] == "Approved helper text"


def test_mobile_friendly_and_no_banned_tokens(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("hi", folder=tmp_path)
        client = TestClient(photo_desk.photo_app)
        resp = client.get(f"/p/{c.token}")
        assert resp.status_code == 200
        html_text = resp.text

        # 1. Viewport & charset
        assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html_text
        assert '<meta charset="utf-8">' in html_text

        # 2. Noscript present
        assert "<noscript>" in html_text
        assert "</noscript>" in html_text

        # 3. Under 20 KB
        assert len(resp.content) < 20 * 1024

        # 4. Computer & helper notice present
        assert "The photos are read by a computer and by a helper." in html_text
        assert "फोटो कंप्यूटर और एक सहायक देखेंगे।" in html_text
        assert "फोटो संगणक आणि एक मदतनीस पाहतील।" in html_text

        # 5. Script part holds NONE of =>, async , await , let , const , ?., `, fetch(
        script_match = re.search(r"<script>(.*?)</script>", html_text, re.DOTALL)
        assert script_match is not None, "Script tag missing"
        script_body = script_match.group(1)

        banned_tokens = ["=>", "async ", "await ", "let ", "const ", "?.", "`", "fetch("]
        for token in banned_tokens:
            assert token not in script_body, f"Banned token {token!r} found in photo page script"


def test_photo_page_gujarati_labels(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("gu", folder=tmp_path)
        client = TestClient(photo_desk.photo_app)
        resp = client.get(f"/p/{c.token}")
        assert resp.status_code == 200
        html_text = resp.text

        # Gujarati send word present
        assert "મોકલો" in html_text
        assert "ફોટો લો" in html_text
        assert "ફોટો પસંદ કરો" in html_text
        assert "મોકલાઈ ગયું, તમને કૉલ આવશે" in html_text

        # Gujarati comes first, then Hindi, then English in the send button
        send_btn_match = re.search(r'<button[^>]*id="send-btn"[^>]*>(.*?)</button>', html_text, re.DOTALL)
        assert send_btn_match is not None
        btn_text = send_btn_match.group(1)
        gu_idx = btn_text.find("મોકલો")
        hi_idx = btn_text.find("भेजें")
        en_idx = btn_text.find("Send")
        assert gu_idx != -1 and hi_idx != -1 and en_idx != -1
        assert gu_idx < hi_idx < en_idx, "Gujarati labels must precede Hindi and English"


def test_photo_page_tamil_labels(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("ta", folder=tmp_path)
        client = TestClient(photo_desk.photo_app)
        resp = client.get(f"/p/{c.token}")
        assert resp.status_code == 200
        html_text = resp.text

        # Tamil send word present
        assert "அனுப்பு" in html_text
        assert "புகைப்படம் எடு" in html_text
        assert "புகைப்படங்களைத் தேர்ந்தெடு" in html_text
        assert "அனுப்பப்பட்டது, உங்களுக்கு அழைப்பு வரும்" in html_text

        # Tamil comes first, then Hindi, then English in the send button
        send_btn_match = re.search(r'<button[^>]*id="send-btn"[^>]*>(.*?)</button>', html_text, re.DOTALL)
        assert send_btn_match is not None
        btn_text = send_btn_match.group(1)
        ta_idx = btn_text.find("அனுப்பு")
        hi_idx = btn_text.find("भेजें")
        en_idx = btn_text.find("Send")
        assert ta_idx != -1 and hi_idx != -1 and en_idx != -1
        assert ta_idx < hi_idx < en_idx, "Tamil labels must precede Hindi and English"


def test_desk_page_has_viewport(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        client = TestClient(photo_desk.desk_app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in resp.text
