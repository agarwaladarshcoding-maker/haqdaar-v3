"""tests/test_photo_desk.py

Tests for tools.photo_desk (Pass 3):
- Photo page good (under 20 KB, no http(s):// to outside host, Cache-Control: no-store)
- Four languages page holds all send words and is under 20 KB
- Reopen drops old photos if not yet sent
- Wrong token 404 and slowed (time.sleep called)
- Wrong tokens do not block good tokens (no 429 behind tunnel)
- /photo good (saves photo and returns ok)
- /photo not a picture (400)
- /photo too big (413)
- /done runs reader in thread and sets finding & say
- Second /done on reading case ignored
- Photo app has no desk routes (/, /approve/..., /new)
- HTML escaping on desk helper page
- call_back writes next_call.json atomically and makes no phone call
- desk app /approve/{token} and /new with langs
- desk Host / Origin guard
- mobile friendly and no banned tokens
- Gujarati and Tamil labels
- desk page has viewport
"""
import json
import os
import re
import threading
import time
import unittest.mock as mock
import pytest
from fastapi.testclient import TestClient

from haqdaar.photo import cases
from tools import photo_desk

# Tiny pictures made by hand for type checking:
TINY_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb"
TINY_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"


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


def test_photo_page_four_languages_under_20kb(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case(langs=["mr", "hi", "en", "gu"], folder=tmp_path)
        client = TestClient(photo_desk.photo_app)
        resp = client.get(f"/p/{c.token}")
        assert resp.status_code == 200
        assert len(resp.content) < 20 * 1024

        content = resp.text
        # Holds send word of all four
        assert "पाठवा" in content
        assert "भेजें" in content
        assert "Send" in content
        assert "મોકલો" in content

        send_btn_match = re.search(r"<button[^>]*id=\"send-btn\"[^>]*>(.*?)</button>", content, re.DOTALL)
        assert send_btn_match is not None
        btn_text = send_btn_match.group(1)

        mr_idx = btn_text.find("पाठवा")
        hi_idx = btn_text.find("भेजें")
        en_idx = btn_text.find("Send")
        gu_idx = btn_text.find("મોકલો")
        assert mr_idx < hi_idx < en_idx < gu_idx


def test_reopen_drops_old_photos(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("hi", folder=tmp_path)
        cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
        assert len(cases.get(c.token, folder=tmp_path).photos) == 1

        client = TestClient(photo_desk.photo_app)
        resp = client.get(f"/p/{c.token}")
        assert resp.status_code == 200

        # Old photos dropped because case was not yet sent
        updated = cases.get(c.token, folder=tmp_path)
        assert len(updated.photos) == 0
        assert updated.state == "waiting"


def test_wrong_token_404_and_slowed(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}),          mock.patch("time.sleep") as mock_sleep:
        client = TestClient(photo_desk.photo_app)
        resp = client.get("/p/nonexistent")
        assert resp.status_code == 404
        assert resp.headers.get("cache-control") == "no-store"
        assert "यह लिंक अब काम नहीं करता" in resp.text
        assert mock_sleep.called
        assert mock_sleep.call_args[0][0] == 1.0


def test_wrong_tokens_do_not_block_good_tokens(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}),          mock.patch("time.sleep"):
        c = cases.new_case("hi", folder=tmp_path)
        client = TestClient(photo_desk.photo_app)

        for i in range(12):
            r = client.get(f"/p/badtoken{i:02d}")
            assert r.status_code == 404

        # Good token is never refused
        r_good = client.get(f"/p/{c.token}")
        assert r_good.status_code == 200


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

        # Run thread synchronously in test
        real_thread = threading.Thread
        def sync_thread(target=None, args=(), **kwargs):
            t = real_thread(target=target, args=args, **kwargs)
            # execute target synchronously
            if target:
                target(*args)
            return t

        with mock.patch("haqdaar.photo.reader.read", return_value=mock_finding), \
             mock.patch("tools.photo_desk.pick_scheme", return_value=("pmfby", "PM Fasal Bima")), \
             mock.patch("threading.Thread", side_effect=sync_thread):
            client = TestClient(photo_desk.photo_app)
            r = client.post(f"/p/{c.token}/done")
            assert r.status_code == 200
            assert r.json() == {"ok": True}

        updated = cases.get(c.token, folder=tmp_path)
        assert updated.state in ("read", "approved")
        assert updated.scheme == "pmfby"
        assert "Yellow wilted leaves." in updated.say
        assert "Fungal infection." in updated.say
        assert "PM Fasal Bima" in updated.say


def test_second_done_ignored(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("hi", folder=tmp_path)
        cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
        cases.mark_reading(c.token, folder=tmp_path)

        with mock.patch("threading.Thread") as mock_thread:
            client = TestClient(photo_desk.photo_app)
            r = client.post(f"/p/{c.token}/done")
            assert r.status_code == 200
            assert mock_thread.call_count == 0


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
        assert "<img src=x" not in body
        r_cases = client.get("/cases")
        assert r_cases.status_code == 200
        case_data = r_cases.json()[0]
        assert case_data["shows"] == "<script>alert(xss-shows)</script>"
        assert case_data["scheme"] == "<b>scheme</b>" 


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
        client = TestClient(photo_desk.desk_app)
        # POST /new with JSON langs
        r_new = client.post("/new", json={"langs": ["mr", "gu"]})
        assert r_new.status_code == 200
        d = r_new.json()
        tok = d["token"]
        assert len(tok) == 10
        assert d["langs"] == ["mr", "gu"]

        c_obj = cases.get(tok, folder=tmp_path)
        assert c_obj.langs == ["mr", "gu"]
        assert c_obj.lang == "mr"

        # Set finding so case can be approved
        cases.add_photo(tok, TINY_JPEG, folder=tmp_path)
        cases.set_finding(tok, {}, "", "", folder=tmp_path)

        # POST /approve/{token}
        r_app = client.post(f"/approve/{tok}", content=b"Approved helper text")
        assert r_app.status_code == 200
        assert r_app.json()["state"] == "approved"

        c = cases.get(tok, folder=tmp_path)
        assert c.state == "approved"
        assert c.say == "Approved helper text"

        next_call = tmp_path / "next_call.json"
        assert next_call.exists()
        data = json.loads(next_call.read_text(encoding="utf-8"))
        assert data["say"] == "Approved helper text"


def test_desk_host_and_origin_guard(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        client = TestClient(photo_desk.desk_app)

        # Bad host
        r_bad_host = client.get("/", headers={"Host": "attacker.com"})
        assert r_bad_host.status_code == 403

        # Good host
        r_good_host = client.get("/", headers={"Host": "localhost:8003"})
        assert r_good_host.status_code == 200

        # Bad Origin on POST
        r_bad_orig = client.post("/new", headers={"Origin": "http://evil.com"})
        assert r_bad_orig.status_code == 403

        # Good Origin on POST
        r_good_orig = client.post("/new", headers={"Origin": "http://localhost:8003"})
        assert r_good_orig.status_code == 200


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

        # 5. Steps pictograms present
        assert "[📷]" in html_text
        assert "[👁]" in html_text
        assert "[✓]" in html_text

        # 6. Script part holds NONE of =>, async , await , let , const , ?., `, fetch(
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

        assert "મોકલો" in html_text
        assert "ફોટો લો" in html_text
        assert "ફોટો પસંદ કરો" in html_text
        assert "મોકલાઈ ગયું" in html_text

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

        assert "அனுப்பு" in html_text
        assert "புகைப்படம் எடு" in html_text
        assert "புகைப்படங்களைத் தேர்ந்தெடு" in html_text
        assert "அனுப்பப்பட்டது" in html_text

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


def test_photo_auto_on_and_off(tmp_path):
    real_thread = threading.Thread
    def sync_thread(target=None, args=(), **kwargs):
        t = real_thread(target=target, args=args, **kwargs)
        if target:
            target(*args)
        return t

    # 1. PHOTO_AUTO=true: good finding
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path), "PHOTO_AUTO": "true"}), \
         mock.patch("threading.Thread", side_effect=sync_thread):
        c1 = cases.new_case("hi", folder=tmp_path)
        cases.add_photo(c1.token, TINY_JPEG, folder=tmp_path)

        good_finding = {
            "shows": "Clear crop view.",
            "wrong": "Leaf blight.",
            "sure": 0.9,
            "search": "pmfby",
            "by": "muse",
        }
        with mock.patch("haqdaar.photo.reader.read", return_value=good_finding), \
             mock.patch("tools.photo_desk.pick_scheme", return_value=("pmfby", "PM Fasal Bima")):
            client = TestClient(photo_desk.photo_app)
            r = client.post(f"/p/{c1.token}/done")
            assert r.status_code == 200

        c1_up = cases.get(c1.token, folder=tmp_path)
        assert c1_up.state == "approved"
        next_call = tmp_path / "next_call.json"
        assert next_call.exists()
        d1 = json.loads(next_call.read_text(encoding="utf-8"))
        assert d1["token"] == c1.token
        assert d1["lang"] == "hi"
        assert "Clear crop view." in d1["say"]

    # 2. PHOTO_AUTO=true: bad finding (stand-in, low sure, empty shows)
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path), "PHOTO_AUTO": "true"}), \
         mock.patch("threading.Thread", side_effect=sync_thread):
        c2 = cases.new_case("en", folder=tmp_path)
        cases.add_photo(c2.token, TINY_JPEG, folder=tmp_path)

        bad_finding = {
            "shows": "",
            "wrong": "",
            "sure": 0.2,
            "search": "",
            "by": "stand-in (the reader failed)",
        }
        with mock.patch("haqdaar.photo.reader.read", return_value=bad_finding):
            client = TestClient(photo_desk.photo_app)
            r = client.post(f"/p/{c2.token}/done")
            assert r.status_code == 200

        c2_up = cases.get(c2.token, folder=tmp_path)
        assert c2_up.state == "approved"
        d2 = json.loads((tmp_path / "next_call.json").read_text(encoding="utf-8"))
        assert d2["token"] == c2.token
        assert d2["lang"] == "en"

    # 3. PHOTO_AUTO=false: state stays read, no file until /approve
    (tmp_path / "next_call.json").unlink(missing_ok=True)
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path), "PHOTO_AUTO": "false"}), \
         mock.patch("threading.Thread", side_effect=sync_thread):
        c3 = cases.new_case("mr", folder=tmp_path)
        cases.add_photo(c3.token, TINY_JPEG, folder=tmp_path)

        with mock.patch("haqdaar.photo.reader.read", return_value=good_finding):
            client = TestClient(photo_desk.photo_app)
            r = client.post(f"/p/{c3.token}/done")
            assert r.status_code == 200

        c3_up = cases.get(c3.token, folder=tmp_path)
        assert c3_up.state == "read"
        assert not (tmp_path / "next_call.json").exists()

        # Helper calls /approve/{token}
        desk_client = TestClient(photo_desk.desk_app)
        r_app = desk_client.post(f"/approve/{c3.token}", content=b"Helper approved text")
        assert r_app.status_code == 200
        assert (tmp_path / "next_call.json").exists()
        d3 = json.loads((tmp_path / "next_call.json").read_text(encoding="utf-8"))
        assert d3["token"] == c3.token
        assert d3["say"] == "Helper approved text"


def test_get_cases_fields_and_no_full_number(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        full_number = "+919876543210"
        c = cases.new_case("hi", number=full_number, folder=tmp_path)
        cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)

        client = TestClient(photo_desk.desk_app)
        resp = client.get("/cases")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        matched = [x for x in data if x["token"] == c.token]
        assert len(matched) == 1
        item = matched[0]

        # Check required fields
        required_keys = {"token", "tail", "step", "state", "time", "age", "langs", "shows", "wrong", "scheme", "say", "photos", "is_stand_in"}
        assert required_keys.issubset(set(item.keys()))

        # Check tail has only last 2 digits
        assert item["tail"] == "10"
        assert "number" not in item

        # Verify full number never appears anywhere in the JSON response
        assert full_number not in resp.text
        assert "98765432" not in resp.text


def test_not_clear_action_sets_wrong_and_writes_file(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        c = cases.new_case("hi", folder=tmp_path)
        cases.add_photo(c.token, TINY_JPEG, folder=tmp_path)
        cases.set_finding(c.token, {"shows": "Blurry shape"}, "", "Some text", folder=tmp_path)

        client = TestClient(photo_desk.desk_app)
        r = client.post(f"/not-clear/{c.token}")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["wrong"] == "helper: not clear"

        # Check case on disk
        c_up = cases.get(c.token, folder=tmp_path)
        assert c_up.finding["wrong"] == "helper: not clear"
        assert c_up.state == "approved"

        # Check next_call.json written
        next_call = tmp_path / "next_call.json"
        assert next_call.exists()
        d = json.loads(next_call.read_text(encoding="utf-8"))
        assert d["token"] == c.token


def test_desk_html_no_alert_no_reload_has_keybar_and_buttons(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        client = TestClient(photo_desk.desk_app)
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.text

        # No alert() and no location.reload
        assert "alert(" not in body
        assert "location.reload" not in body

        # Key bar present
        assert 'id="key-bar"' in body

        # Real button elements with key in label
        buttons = re.findall(r"<button[^>]*>(.*?)</button>", body, re.DOTALL)
        assert len(buttons) >= 4
        button_texts = " ".join(buttons)
        assert "Call back (Enter)" in button_texts
        assert "Edit text (E)" in button_texts
        assert "Not clear (B)" in button_texts
        assert "New test case (N)" in button_texts or "New case (N)" in button_texts
        assert "Auto on / off (A)" in button_texts


def test_host_origin_guard_covers_new_routes(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_DIR": str(tmp_path)}):
        client = TestClient(photo_desk.desk_app)
        c = cases.new_case("hi", folder=tmp_path)

        # GET /cases with evil Host -> 403
        r_cases_bad = client.get("/cases", headers={"Host": "attacker.com"})
        assert r_cases_bad.status_code == 403

        # POST /not-clear with evil Origin -> 403
        r_nc_bad = client.post(f"/not-clear/{c.token}", headers={"Origin": "http://evil.com"})
        assert r_nc_bad.status_code == 403

        # POST /toggle-auto with evil Origin -> 403
        r_ta_bad = client.post("/toggle-auto", headers={"Origin": "http://evil.com"})
        assert r_ta_bad.status_code == 403

        # Allowed requests
        r_cases_good = client.get("/cases", headers={"Host": "localhost:8003"})
        assert r_cases_good.status_code == 200

        r_nc_good = client.post(f"/not-clear/{c.token}", headers={"Origin": "http://localhost:8003"})
        assert r_nc_good.status_code == 200

        r_ta_good = client.post("/toggle-auto", headers={"Origin": "http://localhost:8003"})
        assert r_ta_good.status_code == 200
