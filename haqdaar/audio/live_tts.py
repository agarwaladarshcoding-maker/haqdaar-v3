"""haqdaar/audio/live_tts.py

Step 7.2 (C1) — say a sentence made during the call, in the same voice as the recorded lines.

`speak(text, lang)` asks Sarvam's streaming text-to-speech endpoint (bulbul:v3, the same speaker
and pace as `render.py`) for 8 kHz mu-law and gives the bytes back whole. `stream(text, lang)`
gives the same sound piece by piece as it arrives (7.14); the Mouth plays it with `play_stream`.

It never raises. Any failure, or running past QA_TTS_TIMEOUT_S, gives None and the caller
falls back to saying nothing.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Iterator, Optional

from dotenv import load_dotenv

from haqdaar import net
from haqdaar.audio.render import TTS_LANG, wav_to_ulaw
from haqdaar.contracts import tunables

ENDPOINT = "https://api.sarvam.ai/text-to-speech/stream"
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# How "%" is spoken. The voice reads the sign as nothing, or as the English word.
PERCENT_WORD: dict[str, str] = {"hi": " प्रतिशत", "mr": " टक्के", "en": " percent"}


def clean(text: str, lang: str) -> str:
    """Text the voice can read: no markdown, no odd dashes, "%" as a word."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)      # [label](url) -> label
    text = re.sub(r"[*_`#>]+", "", text)                      # emphasis, code, headings, quotes
    text = re.sub(r"^\s*[-+]\s+", "", text, flags=re.M)       # bullet markers
    text = text.replace("‑", "-").replace("‐", "-")
    text = text.replace("%", PERCENT_WORD.get(lang, " percent"))
    return re.sub(r"\s+", " ", text).strip()


def _as_ulaw(body: bytes) -> bytes:
    """Raw mu-law as it is; a WAV container (some codecs send one) is opened first."""
    if body[:4] == b"RIFF":
        return wav_to_ulaw(body)
    return body


def stream(text: str, lang: str) -> Iterator[bytes]:
    """One text in one language -> 8 kHz mu-law, piece by piece as Sarvam sends it (7.14).
    Raises on a failure or past QA_TTS_TIMEOUT_S. Nothing to say: yields nothing. Costs Sarvam money per call."""
    deadline = time.monotonic() + tunables.QA_TTS_TIMEOUT_S
    load_dotenv(BASE_DIR / ".env")
    key = os.environ.get("SARVAM_API_KEY", "")
    text = clean(text, lang)
    if not key or not text or lang not in TTS_LANG:
        return
    payload = {
        "text": text,
        "target_language_code": TTS_LANG[lang],
        "speaker": tunables.TTS_SPEAKERS[lang],
        "model": tunables.TTS_MODEL,
        "pace": tunables.LIVE_TTS_PACE,
        "speech_sample_rate": tunables.SAMPLE_RATE,
        "output_audio_codec": "mulaw",
    }
    wav: list[bytes] = []                       # a WAV container cannot be opened piece by piece
    first = True
    # A network error before any sound is tried once more, with the same timeout; the deadline
    # check below still ends a slow stream, so the worst case is one more QA_TTS_TIMEOUT_S.
    with net.stream(
        "POST", ENDPOINT, headers={"api-subscription-key": key},
        json=payload, timeout=tunables.QA_TTS_TIMEOUT_S,
    ) as response:
        if response.status_code != 200:
            raise RuntimeError(f"live voice: http {response.status_code}")
        for chunk in response.iter_bytes():
            if time.monotonic() > deadline:
                raise TimeoutError("live voice: too slow")
            if not chunk:
                continue
            if wav or (first and chunk[:4] == b"RIFF"):
                wav.append(chunk)
            else:
                yield chunk
            first = False
    if wav:
        yield wav_to_ulaw(b"".join(wav))


def speak(text: str, lang: str) -> Optional[bytes]:
    """One text in one language -> 8 kHz mu-law bytes, or None. Costs Sarvam money per call."""
    try:
        body = b"".join(stream(text, lang))
        return body or None
    except Exception:
        return None
