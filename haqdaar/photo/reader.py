"""haqdaar/photo/reader.py

Reader Plug Contract for Local Photo Model:
-------------------------------------------
Endpoint: POST {PHOTO_READER_URL}
Headers: Content-Type: application/json
Request Body:
{
    "lang": "hi" | "mr" | "en" | "gu" | "ta",
    "photos": ["<base64 jpeg bytes>", ...]
}
Response (200 OK):
{
    "shows": str,    # What the photos show (e.g. crop/disease observation)
    "wrong": str,    # What seems wrong or diagnosis
    "sure": float,   # Confidence score between 0.0 and 1.0
    "search": str    # A few English keywords for scheme search (e.g. "crop loss insurance")
}
Any missing keys, incorrect types, HTTP error status, or timeout -> reader failure.
"""
from __future__ import annotations

import base64
import os
import re
from typing import Any, Callable
import httpx

DOSE_PATTERN = re.compile(
    r"(?i)(?:\d+(?:\.\d+)?|\d+)\s*(?:ml|l|g|kg|grams?|litres?|liters?|मिली|लीटर|ग्राम|किलो)(?=[^\wऀ-ॿ]|$)",
    re.UNICODE,
)


def _cut_dose_sentences(text: str) -> str:
    if not text:
        return ""
    tokens = re.split(r"([.?!।\n]+)", text)
    kept_chunks: list[str] = []
    i = 0
    while i < len(tokens):
        s = tokens[i]
        delim = tokens[i + 1] if i + 1 < len(tokens) else ""
        if not s.strip():
            if not DOSE_PATTERN.search(s):
                kept_chunks.append(s + delim)
        else:
            if not DOSE_PATTERN.search(s):
                kept_chunks.append(s + delim)
        i += 2
    res = "".join(kept_chunks).strip()
    res = re.sub(r" +", " ", res)
    return res


def _sanitize_output(data: dict[str, Any], by_name: str) -> dict[str, Any]:
    shows = str(data.get("shows", ""))
    wrong = str(data.get("wrong", ""))
    search = str(data.get("search", ""))

    shows = _cut_dose_sentences(shows)
    wrong = _cut_dose_sentences(wrong)

    shows = shows[:400]
    wrong = wrong[:400]
    search = search[:400]

    try:
        sure = float(data.get("sure", 0.0))
        sure = max(0.0, min(1.0, sure))
    except (ValueError, TypeError):
        sure = 0.0

    return {
        "shows": shows,
        "wrong": wrong,
        "sure": sure,
        "search": search,
        "by": by_name,
    }


def _stand_in(photos: list[bytes], lang: str = "en") -> dict[str, Any]:
    return {
        "shows": "Photos came. No reader is set yet.",
        "wrong": "",
        "sure": 0.0,
        "search": "",
        "by": "stand-in",
    }


def _http(photos: list[bytes], lang: str = "en") -> dict[str, Any]:
    url = os.getenv("PHOTO_READER_URL", "").strip()
    if not url:
        raise ValueError("PHOTO_READER_URL not set")

    timeout_s = float(os.getenv("PHOTO_READER_TIMEOUT_S", "20"))
    b64_photos = [base64.b64encode(p).decode("ascii") for p in photos]
    payload = {
        "lang": lang,
        "photos": b64_photos,
    }

    resp = httpx.post(url, json=payload, timeout=timeout_s)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP status {resp.status_code}")

    result = resp.json()
    if not isinstance(result, dict):
        raise TypeError("Expected JSON object response")

    for k in ("shows", "wrong", "sure", "search"):
        if k not in result:
            raise KeyError(f"Missing key: {k}")

    if not isinstance(result["shows"], str) or not isinstance(result["wrong"], str) or not isinstance(result["search"], str):
        raise TypeError("Invalid string fields in response")

    if not isinstance(result["sure"], (int, float)):
        raise TypeError("Invalid sure numeric field in response")

    return {
        "shows": result["shows"],
        "wrong": result["wrong"],
        "sure": float(result["sure"]),
        "search": result["search"],
        "by": "http",
    }


READERS: dict[str, Callable[[list[bytes], str], dict[str, Any]]] = {
    "stand-in": _stand_in,
    "http": _http,
}


def read(photos: list[bytes], lang: str = "en") -> dict[str, Any]:
    reader_name = os.getenv("PHOTO_READER", "stand-in").strip()
    reader_fn = READERS.get(reader_name)

    if reader_fn is None:
        fallback = _stand_in(photos, lang)
        fallback["by"] = "stand-in (the reader failed)"
        return _sanitize_output(fallback, fallback["by"])

    try:
        raw_res = reader_fn(photos, lang)
        by = raw_res.get("by", reader_name)
        return _sanitize_output(raw_res, by)
    except Exception:
        fallback = _stand_in(photos, lang)
        fallback["by"] = "stand-in (the reader failed)"
        return _sanitize_output(fallback, fallback["by"])
