"""haqdaar/photo/reader.py

Reader Plug Contract for Local Photo Model & Muse:
---------------------------------------------------
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
    "wrong": str,    # What seems wrong or damage observed
    "details": str,  # Optional. Everything seen, for the talk model: writing read out word by word, what is filled in, what can not be read
    "sure": float,   # Confidence score between 0.0 and 1.0
    "search": str    # A few English keywords for scheme search (e.g. "crop loss insurance")
}
Any missing keys, incorrect types, HTTP error status, or timeout -> reader failure.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Optional
import dotenv
import httpx

from haqdaar.contracts import tunables
from haqdaar.data.pipeline import muse
from haqdaar.model import muse_talk

DETAILS_CHARS = 1200     # cap of the long description kept for the talk model

DOSE_PATTERN = re.compile(
    r"(?i)(?:(?:\b\d+(?:\.\d+)?|\d+)\s*(?:ml|l|g|gm|kg|mg|grams?|litres?|liters?|मिली|लीटर|ग्राम|किलो|गोली|गोलियां|गोलियाँ|tablets?)(?=[^\wऀ-ॿ]|$)|(?:\btablets?\b|\bगोली\b|\bगोलियां\b|\bगोलियाँ\b))",
    re.UNICODE,
)

SYSTEM = (
    "You look at photos sent by a caller of a help line for government schemes in India. "
    "Say only what can be seen. Answer in JSON with exactly: "
    "shows (one short sentence: what the photos show), "
    "wrong (one short sentence: the damage or problem that can be seen, or \"\" if none), "
    "details (for the helper who will talk to the caller and can not see the photo; up to 150 words, plain English. "
    "Tell everything that can be seen: each thing, its colour, its state, how much of it is damaged, the place. "
    "If there is any writing (a form, a letter, a notice, a card, a bill, a message): say what kind of paper it is, "
    "then read it out word by word as written, with the English meaning if it is in another language; "
    "for a form name each field, what is filled in it, and which fields are empty. "
    "Say plainly which parts you can not read. "
    "Do not write out an ID, bank, card or phone number: say only that it is there), "
    "sure (a number 0 to 1), "
    "search (3 to 6 English words to search government schemes with, like \"crop loss insurance\" or \"house damage flood help\", or \"\" if the photo has nothing to do with a need). "
    "Never name a medicine, a chemical or a dose. Never guess who a person is. "
    "If the photo is not clear, say so and give a low sure."
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
    search = _cut_dose_sentences(search)
    details = _cut_dose_sentences(str(data.get("details", "") or ""))[:DETAILS_CHARS]

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
        "details": details,
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
        "details": result["details"] if isinstance(result.get("details"), str) else "",
        "by": "http",
    }


def _detect_mime(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _muse(photos: list[bytes], lang: str = "en", post: Any = None, ledger: Any = None) -> dict[str, Any]:
    ledger_path = Path(ledger or muse.LEDGER)

    # 1. Money guard comes FIRST: no call is made
    if muse_talk._refused(ledger_path):
        return {
            "shows": "Photos came. No reader is set yet.",
            "wrong": "",
            "sure": 0.0,
            "search": "",
            "by": "stand-in (Muse is closed for today)",
        }

    key = os.getenv("MUSE_API_KEY", "").strip()
    if not key:
        return {
            "shows": "Photos came. No reader is set yet.",
            "wrong": "",
            "sure": 0.0,
            "search": "",
            "by": "stand-in (the reader failed)",
        }

    timeout = float(os.getenv("PHOTO_READER_TIMEOUT_S", "30"))

    # Send at most the first 4 photos with correct mime type
    user_content: list[dict[str, Any]] = [{"type": "text", "text": "Look at these photos."}]
    for p in photos[:4]:
        mime = _detect_mime(p)
        b64 = base64.b64encode(p).decode("ascii")
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })

    payload = {
        "model": tunables.MUSE_MODEL,
        "reasoning_effort": "minimal",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_content},
        ],
    }

    post_fn = post or muse_talk._post
    try:
        status, data = post_fn(payload, key, timeout)
    except Exception:
        return {
            "shows": "Photos came. No reader is set yet.",
            "wrong": "",
            "sure": 0.0,
            "search": "",
            "by": "stand-in (the reader failed)",
        }

    if status != 200 or not isinstance(data, dict):
        return {
            "shows": "Photos came. No reader is set yet.",
            "wrong": "",
            "sure": 0.0,
            "search": "",
            "by": "stand-in (the reader failed)",
        }

    # Write ledger after every 200 answer
    usage = data.get("usage") or {}
    p_tok = int(usage.get("prompt_tokens") or 0)
    out = max(int(usage.get("completion_tokens") or 0), int(usage.get("total_tokens") or 0) - p_tok)
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "task": "photo",
                "slug": "",
                "model": tunables.MUSE_MODEL,
                "prompt_tokens": p_tok,
                "completion_tokens": out,
                "inr": round(muse.cost_inr(p_tok, out), 5),
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass

    choices = data.get("choices") or []
    content = (choices[0].get("message", {}).get("content", "") if choices else "") or ""
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        parsed = json.loads(content)
    except Exception:
        parsed = None

    if not isinstance(parsed, dict):
        return {
            "shows": "Photos came. No reader is set yet.",
            "wrong": "",
            "sure": 0.0,
            "search": "",
            "by": "stand-in (the reader failed)",
        }

    shows_val = parsed.get("shows")
    if not isinstance(shows_val, str) or not shows_val.strip():
        return {
            "shows": "Photos came. No reader is set yet.",
            "wrong": "",
            "sure": 0.0,
            "search": "",
            "by": "stand-in (the reader failed)",
        }

    wrong_val = parsed.get("wrong")
    wrong = wrong_val if isinstance(wrong_val, str) else ""

    search_val = parsed.get("search")
    search = search_val if isinstance(search_val, str) else ""

    sure_val = parsed.get("sure")
    if isinstance(sure_val, bool):
        sure = 1.0 if sure_val else 0.0
    elif isinstance(sure_val, (int, float)):
        sure = float(sure_val)
    else:
        sure = 0.0
    sure = max(0.0, min(1.0, sure))

    details_val = parsed.get("details")
    return {
        "shows": shows_val,
        "wrong": wrong,
        "sure": sure,
        "search": search,
        "details": details_val if isinstance(details_val, str) else "",
        "by": "muse",
    }


READERS: dict[str, Callable[..., dict[str, Any]]] = {
    "stand-in": _stand_in,
    "http": _http,
    "muse": _muse,
}


def read(photos: list[bytes], lang: str = "en", post: Any = None, ledger: Any = None) -> dict[str, Any]:
    dotenv.load_dotenv()
    mode = os.getenv("PHOTO_READER", "auto").strip()
    if mode == "auto":
        if os.getenv("MUSE_API_KEY", "").strip():
            reader_name = "muse"
        else:
            reader_name = "stand-in"
    else:
        reader_name = mode

    reader_fn = READERS.get(reader_name)
    if reader_fn is None:
        fallback = _stand_in(photos, lang)
        fallback["by"] = "stand-in (the reader failed)"
        return _sanitize_output(fallback, fallback["by"])

    try:
        if reader_name == "muse":
            raw_res = reader_fn(photos, lang, post=post, ledger=ledger)
        else:
            raw_res = reader_fn(photos, lang)
        by = raw_res.get("by", reader_name)
        return _sanitize_output(raw_res, by)
    except Exception:
        fallback = _stand_in(photos, lang)
        fallback["by"] = "stand-in (the reader failed)"
        return _sanitize_output(fallback, fallback["by"])
