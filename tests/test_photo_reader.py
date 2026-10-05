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
"""
import os
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

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}),          mock.patch("httpx.post", return_value=mock_resp) as mock_post:
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
    # 1. Missing keys
    mock_resp1 = mock.Mock()
    mock_resp1.status_code = 200
    mock_resp1.json.return_value = {"shows": "Only shows"}

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}),          mock.patch("httpx.post", return_value=mock_resp1):
        res = reader.read([b"image_bytes"], lang="en")
        assert res["by"] == "stand-in (the reader failed)"

    # 2. Wrong type for sure
    mock_resp2 = mock.Mock()
    mock_resp2.status_code = 200
    mock_resp2.json.return_value = {
        "shows": "Spots",
        "wrong": "Pest",
        "sure": "very sure",
        "search": "pest control",
    }

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}),          mock.patch("httpx.post", return_value=mock_resp2):
        res = reader.read([b"image_bytes"], lang="en")
        assert res["by"] == "stand-in (the reader failed)"


def test_http_reader_timeout():
    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}),          mock.patch("httpx.post", side_effect=httpx.TimeoutException("timed out")):
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

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}),          mock.patch("httpx.post", return_value=mock_resp):
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

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}),          mock.patch("httpx.post", return_value=mock_resp):
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

    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}),          mock.patch("httpx.post", return_value=mock_resp):
        res = reader.read([b"img"])
        assert res["sure"] == 1.0
        assert len(res["shows"]) == 400
        assert len(res["wrong"]) == 400
        assert len(res["search"]) == 400


def test_read_never_raises():
    with mock.patch.dict(os.environ, {"PHOTO_READER": "http", "PHOTO_READER_URL": "http://localhost:9999/predict"}),          mock.patch("httpx.post", side_effect=Exception("Unexpected catastrophic failure")):
        res = reader.read([])
        assert isinstance(res, dict)
        assert res["by"] == "stand-in (the reader failed)"
