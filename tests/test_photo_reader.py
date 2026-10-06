"""tests/test_photo_reader.py

Tests for haqdaar.photo.reader:
- stand-in exact output
- http reader good
- bad JSON / missing keys / wrong types
- timeout
- no URL
- unknown PHOTO_READER
- dose guard (English and Hindi units cut out, safe sentences kept)
- clamp sure (0..1)
- length truncation (<= 400 chars)
- read never raises
- muse reader:
  - good answer
  - wrong types made right (wrong: false, sure: true, missing search)
  - guard refuses -> no post call made
  - 500 error
  - bad JSON
  - timeout
  - more than 4 photos -> exactly 4 sent with correct mime types
  - ledger line written to tmp ledger
  - auto mode with and without key (stopping load_dotenv from reading real file)
"""
import json
import os
from pathlib import Path
import unittest.mock as mock
import httpx
import pytest

from haqdaar.photo import reader


def test_stand_in_exact_output():
    with mock.patch.dict(os.environ, {"PHOTO_READER": "stand-in"}):
        res = reader.read([b"fake_jpeg_1", b"fake_jpeg_2"], lang="en")
        assert res == {
            "shows": "Photos came. No reader is set yet.",
            "wrong": "",
            "sure": 0.0,
            "search": "",
            "details": "",
            "by": "stand-in",
        }


def test_unknown_reader_fallback():
    with mock.patch.dict(os.environ, {"PHOTO_READER": "super_ai_reader"}):
        res = reader.read([b"fake_jpeg"], lang="hi")
        assert res["by"] == "stand-in (the reader failed)"
        assert res["sure"] == 0.0
        assert res["shows"] == "Photos came. No reader is set yet."


def test_http_reader_no_url():
    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": ""}):
        res = reader.read([b"fake_jpeg"], lang="en")
        assert res["by"] == "stand-in (the reader failed)"


def test_http_reader_good():
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "shows": "Leaves turning yellow",
        "wrong": "Leaf blight suspected",
        "sure": 0.85,
        "search": "crop insurance leaf blight",
    }

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}), \
         mock.patch("httpx.post", return_value=mock_resp) as mock_post:
        res = reader.read([b"image_bytes_here"], lang="hi")
        assert res["by"] == "http"
        assert res["shows"] == "Leaves turning yellow"
        assert res["wrong"] == "Leaf blight suspected"
        assert res["sure"] == 0.85
        assert res["search"] == "crop insurance leaf blight"
        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["lang"] == "hi"
        assert len(call_kwargs["json"]["photos"]) == 1


def test_http_reader_bad_json():
    mock_resp1 = mock.Mock()
    mock_resp1.status_code = 200
    mock_resp1.json.return_value = {"shows": "Only shows"}

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}), \
         mock.patch("httpx.post", return_value=mock_resp1):
        res = reader.read([b"image_bytes"], lang="en")
        assert res["by"] == "stand-in (the reader failed)"

    mock_resp2 = mock.Mock()
    mock_resp2.status_code = 200
    mock_resp2.json.return_value = {
        "shows": "Spots",
        "wrong": "Pest",
        "sure": "very sure",
        "search": "pest control",
    }

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}), \
         mock.patch("httpx.post", return_value=mock_resp2):
        res = reader.read([b"image_bytes"], lang="en")
        assert res["by"] == "stand-in (the reader failed)"


def test_http_reader_timeout():
    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}), \
         mock.patch("httpx.post", side_effect=httpx.TimeoutException("timed out")):
        res = reader.read([b"image_bytes"], lang="mr")
        assert res["by"] == "stand-in (the reader failed)"


def test_dose_guard_english():
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "shows": "Leaf spots observed. Spray 250ml per acre now. Healthy roots.",
        "wrong": "Apply 5 kg urea. Fungal growth detected.",
        "sure": 0.7,
        "search": "fungal crop scheme",
    }

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}), \
         mock.patch("httpx.post", return_value=mock_resp):
        res = reader.read([b"img"])
        assert "250ml" not in res["shows"]
        assert "Spray 250ml" not in res["shows"]
        assert "Leaf spots observed." in res["shows"]
        assert "Healthy roots." in res["shows"]
        assert "5 kg" not in res["wrong"]
        assert "Fungal growth detected." in res["wrong"]


def test_dose_guard_hindi():
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "shows": "पत्ती में छेद हैं। 50 मिली दवा डालें। नियमित पानी दें।",
        "wrong": "10 किलो यूरिया का प्रयोग करें।",
        "sure": 0.9,
        "search": "krishi bima",
    }

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}), \
         mock.patch("httpx.post", return_value=mock_resp):
        res = reader.read([b"img"])
        assert "50 मिली" not in res["shows"]
        assert "पत्ती में छेद हैं।" in res["shows"]
        assert "नियमित पानी दें।" in res["shows"]
        assert res["wrong"] == ""


def test_clamp_sure_and_cut_length():
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    long_text = "A" * 500
    mock_resp.json.return_value = {
        "shows": long_text,
        "wrong": long_text,
        "sure": 2.5,
        "search": long_text,
    }

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}), \
         mock.patch("httpx.post", return_value=mock_resp):
        res = reader.read([b"img"])
        assert res["sure"] == 1.0
        assert len(res["shows"]) == 400
        assert len(res["wrong"]) == 400
        assert len(res["search"]) == 400


def test_read_never_raises():
    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}), \
         mock.patch("httpx.post", side_effect=Exception("Unexpected catastrophic failure")):
        res = reader.read([])
        assert isinstance(res, dict)
        assert res["by"] == "stand-in (the reader failed)"


# --- Muse Reader Tests ---

def test_muse_good_answer(tmp_path):
    ledger_file = tmp_path / "ledger.jsonl"
    resp_data = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "shows": "A flooded crop field.",
                    "wrong": "Waterlogging damage to standing crops.",
                    "sure": 0.95,
                    "search": "flood crop damage insurance",
                })
            }
        }],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 40,
            "total_tokens": 160,
        },
    }

    def fake_post(payload, key, timeout):
        assert key == "muse_key_test"
        assert timeout == 30.0
        return 200, resp_data

    with mock.patch.dict(os.environ, {"PHOTO_READER": "muse", "MUSE_API_KEY": "muse_key_test"}):
        res = reader.read([b"\xff\xd8\xff_fake_jpg"], lang="hi", post=fake_post, ledger=ledger_file)
        assert res["by"] == "muse"
        assert res["shows"] == "A flooded crop field."
        assert res["wrong"] == "Waterlogging damage to standing crops."
        assert res["sure"] == 0.95
        assert res["search"] == "flood crop damage insurance"

    # Ledger check
    assert ledger_file.exists()
    lines = ledger_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["task"] == "photo"
    assert row["prompt_tokens"] == 120
    assert row["completion_tokens"] == 40


def test_muse_wrong_types_made_right(tmp_path):
    ledger_file = tmp_path / "ledger.jsonl"
    resp_data = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "shows": "A broken house wall.",
                    "wrong": False,
                    "sure": True,
                    "search": None,
                })
            }
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }

    def fake_post(payload, key, timeout):
        return 200, resp_data

    with mock.patch.dict(os.environ, {"PHOTO_READER": "muse", "MUSE_API_KEY": "test_key"}):
        res = reader.read([b"\xff\xd8\xff_fake"], lang="en", post=fake_post, ledger=ledger_file)
        assert res["by"] == "muse"
        assert res["shows"] == "A broken house wall."
        assert res["wrong"] == ""
        assert res["sure"] == 1.0
        assert res["search"] == ""


def test_muse_empty_shows_fails(tmp_path):
    ledger_file = tmp_path / "ledger.jsonl"
    resp_data = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "shows": "",
                    "wrong": "Some damage",
                    "sure": 0.5,
                    "search": "help",
                })
            }
        }],
    }

    def fake_post(payload, key, timeout):
        return 200, resp_data

    with mock.patch.dict(os.environ, {"PHOTO_READER": "muse", "MUSE_API_KEY": "test_key"}):
        res = reader.read([b"\xff\xd8\xff_fake"], lang="en", post=fake_post, ledger=ledger_file)
        assert res["by"] == "stand-in (the reader failed)"


def test_muse_guard_refuses_no_post_called(tmp_path):
    mock_post = mock.Mock()
    with mock.patch.dict(os.environ, {"PHOTO_READER": "muse", "MUSE_API_KEY": "test_key"}), \
         mock.patch("haqdaar.model.muse_talk._refused", return_value="muse_cap"):
        res = reader.read([b"img"], post=mock_post, ledger=tmp_path / "ledger.jsonl")
        assert res["by"] == "stand-in (Muse is closed for today)"
        assert mock_post.call_count == 0


def test_muse_500_error(tmp_path):
    def fake_post(payload, key, timeout):
        return 500, "Internal Server Error"

    with mock.patch.dict(os.environ, {"PHOTO_READER": "muse", "MUSE_API_KEY": "test_key"}):
        res = reader.read([b"img"], post=fake_post, ledger=tmp_path / "ledger.jsonl")
        assert res["by"] == "stand-in (the reader failed)"


def test_muse_bad_json(tmp_path):
    def fake_post(payload, key, timeout):
        return 200, {"choices": [{"message": {"content": "bad json"}}]}

    with mock.patch.dict(os.environ, {"PHOTO_READER": "muse", "MUSE_API_KEY": "test_key"}):
        res = reader.read([b"img"], post=fake_post, ledger=tmp_path / "ledger.jsonl")
        assert res["by"] == "stand-in (the reader failed)"


def test_muse_timeout(tmp_path):
    def fake_post(payload, key, timeout):
        raise httpx.TimeoutException("timed out")

    with mock.patch.dict(os.environ, {"PHOTO_READER": "muse", "MUSE_API_KEY": "test_key"}):
        res = reader.read([b"img"], post=fake_post, ledger=tmp_path / "ledger.jsonl")
        assert res["by"] == "stand-in (the reader failed)"


def test_muse_more_than_4_photos_only_4_sent(tmp_path):
    captured_payload = {}

    def fake_post(payload, key, timeout):
        nonlocal captured_payload
        captured_payload = payload
        return 200, {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "shows": "Photos checked.",
                        "wrong": "",
                        "sure": 0.8,
                        "search": "scheme",
                    })
                }
            }],
        }

    p1 = b"\xff\xd8\xff_jpeg1"
    p2 = b"\x89PNG\r\n\x1a\n_png2"
    p3 = b"RIFF1234WEBP_webp3"
    p4 = b"\xff\xd8\xff_jpeg4"
    p5 = b"\xff\xd8\xff_jpeg5"
    p6 = b"\xff\xd8\xff_jpeg6"

    with mock.patch.dict(os.environ, {"PHOTO_READER": "muse", "MUSE_API_KEY": "test_key"}):
        res = reader.read([p1, p2, p3, p4, p5, p6], post=fake_post, ledger=tmp_path / "ledger.jsonl")
        assert res["by"] == "muse"

    user_content = captured_payload["messages"][1]["content"]
    assert user_content[0] == {"type": "text", "text": "Look at these photos."}
    # Exactly 4 image_url items
    image_items = user_content[1:]
    assert len(image_items) == 4

    assert image_items[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert image_items[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert image_items[2]["image_url"]["url"].startswith("data:image/webp;base64,")
    assert image_items[3]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_auto_mode_with_key(monkeypatch, tmp_path):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("PHOTO_READER", "auto")
    monkeypatch.setenv("MUSE_API_KEY", "auto_key_present")

    called = False

    def fake_post(payload, key, timeout):
        nonlocal called
        called = True
        return 200, {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "shows": "Auto mode test.",
                        "wrong": "",
                        "sure": 0.88,
                        "search": "auto scheme",
                    })
                }
            }],
        }

    res = reader.read([b"img"], post=fake_post, ledger=tmp_path / "ledger.jsonl")
    assert called is True
    assert res["by"] == "muse"
    assert res["shows"] == "Auto mode test."


def test_auto_mode_without_key(monkeypatch, tmp_path):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("PHOTO_READER", "auto")
    monkeypatch.delenv("MUSE_API_KEY", raising=False)

    mock_post = mock.Mock()
    res = reader.read([b"img"], post=mock_post, ledger=tmp_path / "ledger.jsonl")
    assert mock_post.call_count == 0
    assert res["by"] == "stand-in"
    assert res["shows"] == "Photos came. No reader is set yet."


def test_dose_guard_search_and_units():
    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "shows": "Take 10 mg medicine. Crop is yellow.",
        "wrong": "Use 2 gm powder and 1 tablet. Root rot.",
        "sure": 0.8,
        "search": "crop loss. take 1 गोली tablet 500mg.",
    }

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}), \
         mock.patch("httpx.post", return_value=mock_resp):
        res = reader.read([b"img"])
        assert "10 mg" not in res["shows"]
        assert "Crop is yellow." in res["shows"]
        assert "2 gm" not in res["wrong"]
        assert "tablet" not in res["wrong"]
        assert "Root rot." in res["wrong"]
        assert "गोली" not in res["search"]
        assert "tablet" not in res["search"]
        assert "crop loss." in res["search"]


# --- 6 Oct: the long description for the talk model ------------------------------------

def _muse_answer(**fields):
    body = {"shows": "A filled form on a table.", "wrong": "", "sure": 0.8, "search": "loan form", **fields}
    return {"choices": [{"message": {"content": json.dumps(body)}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


def test_muse_is_asked_to_read_writing_out_and_the_details_come_through(tmp_path):
    asked = {}

    def fake_post(payload, key, timeout):
        asked["system"] = payload["messages"][0]["content"]
        return 200, _muse_answer(details="A loan form. Name: filled. Amount: 50,000. Signature: empty.")

    with mock.patch.dict(os.environ, {"PHOTO_READER": "muse", "MUSE_API_KEY": "k"}):
        res = reader.read([b"\xff\xd8\xff_x"], post=fake_post, ledger=tmp_path / "l.jsonl")
    assert "details" in asked["system"] and "word by word" in asked["system"] and "can not read" in asked["system"]
    assert res["details"] == "A loan form. Name: filled. Amount: 50,000. Signature: empty."
    assert res["shows"] == "A filled form on a table."        # the spoken sentence stays short


def test_details_missing_or_wrong_type_is_empty_and_long_is_cut(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_READER": "muse", "MUSE_API_KEY": "k"}):
        res = reader.read([b"x"], post=lambda p, k, t: (200, _muse_answer()), ledger=tmp_path / "l.jsonl")
        assert res["details"] == "" and res["by"] == "muse"
        res = reader.read([b"x"], post=lambda p, k, t: (200, _muse_answer(details=["a"])), ledger=tmp_path / "l.jsonl")
        assert res["details"] == ""
        res = reader.read([b"x"], post=lambda p, k, t: (200, _muse_answer(details="word " * 900)), ledger=tmp_path / "l.jsonl")
        assert len(res["details"]) <= reader.DETAILS_CHARS


def test_details_never_carry_a_dose(tmp_path):
    with mock.patch.dict(os.environ, {"PHOTO_READER": "muse", "MUSE_API_KEY": "k"}):
        res = reader.read([b"x"], post=lambda p, k, t: (200, _muse_answer(details="Yellow leaves. Spray 20 ml in water. Soil is dry.")),
                          ledger=tmp_path / "l.jsonl")
    assert "ml" not in res["details"] and "Yellow leaves." in res["details"] and "Soil is dry." in res["details"]
