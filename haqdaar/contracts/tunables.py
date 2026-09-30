"""haqdaar/contracts/tunables.py

UNOWNED. Every tunable lives here and changes with no ceremony at all.
Hardcode nothing.
"""
from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

# Telephony & stream tunables (06-BUILD-PLAN.md Step 1)
TONE_FREQ_HZ: int = int(os.environ.get("TONE_FREQ_HZ", 440))
TONE_DURATION_S: float = float(os.environ.get("TONE_DURATION_S", 1.0))
TONE_AMPLITUDE: float = float(os.environ.get("TONE_AMPLITUDE", 0.5))
NGROK_DOMAIN: str = os.environ.get("NGROK_DOMAIN", "")
# D12: which module in haqdaar/audio/telephony/ talks to the phone line.
PHONE_PROVIDER: str = os.environ.get("PHONE_PROVIDER", "twilio")

# Timing and thresholds (04-INTERFACES.md § What is not frozen)
ENDPOINT_MS: int = int(os.environ.get("ENDPOINT_MS", 700))
RESPONSE_BUDGET_S: float = float(os.environ.get("RESPONSE_BUDGET_S", 1.2))
MODEL_TIMEOUT_S: float = float(os.environ.get("MODEL_TIMEOUT_S", 2.0))
SILENCE_GAP_S: int = int(os.environ.get("SILENCE_GAP_S", 6))
TURN0_GAP_S: int = int(os.environ.get("TURN0_GAP_S", 4))
MAX_TURNS: int = int(os.environ.get("MAX_TURNS", 8))
MAX_QUESTIONS: int = int(os.environ.get("MAX_QUESTIONS", 6))
STOP_SURVIVORS: int = int(os.environ.get("STOP_SURVIVORS", 4))
NEAREST_CAP: int = int(os.environ.get("NEAREST_CAP", 2))
OVERFLOW_READ_CAP: int = int(os.environ.get("OVERFLOW_READ_CAP", 3))
MODEL_FAILURES_TO_KEYPAD: int = int(os.environ.get("MODEL_FAILURES_TO_KEYPAD", 2))
BOX_STRIKES_TO_KEYPAD: int = int(os.environ.get("BOX_STRIKES_TO_KEYPAD", 2))
KEYPAD_CARDINALITY_MAX: int = int(os.environ.get("KEYPAD_CARDINALITY_MAX", 9))
ALIAS_FLOOR: int = int(os.environ.get("ALIAS_FLOOR", 3))
CALL_CEILING_S: int = int(os.environ.get("CALL_CEILING_S", 600))
MAX_SOURCE_AGE_DAYS: int = int(os.environ.get("MAX_SOURCE_AGE_DAYS", 14))

# Audio cache and storage tiers (03-ARCHITECTURE.md §10.1, 04-INTERFACES.md)
AUDIO_CACHE_MB: int = int(os.environ.get("AUDIO_CACHE_MB", 512))
AUDIO_PREFETCH_ON_STOP: bool = (
    os.environ.get("AUDIO_PREFETCH_ON_STOP", "true").lower() in ("true", "1", "yes")
)
AUDIO_TIER2: str = os.environ.get("AUDIO_TIER2", "none")  # "none" | "s3" | "r2"
AUDIO_WARM_ON_BOOT: bool = (
    os.environ.get("AUDIO_WARM_ON_BOOT", "true").lower() in ("true", "1", "yes")
)

# Render and audio format constants
SAMPLE_RATE: int = int(os.environ.get("SAMPLE_RATE", 8000))
TAIL_PAD_MS: int = int(os.environ.get("TAIL_PAD_MS", 120))
# Sarvam TTS (plan 2.1). The bot speaks of itself as a woman in Hindi and Marathi ("पाई",
# "सांगते"), so every speaker here must be a woman's voice. One speaker per language; change one
# and only that language re-renders, because the speaker and pace are part of the render key.
TTS_MODEL: str = os.environ.get("TTS_MODEL", "bulbul:v3")
DEFAULT_TTS_MODEL: str = os.environ.get("DEFAULT_TTS_MODEL", f"sarvam:{TTS_MODEL}")
TTS_SPEAKERS: dict[str, str] = {
    "en": os.environ.get("TTS_SPEAKER_EN", "priya"),
    "hi": os.environ.get("TTS_SPEAKER_HI", "priya"),
    "mr": os.environ.get("TTS_SPEAKER_MR", "priya"),
}
# 15 Sep: the owner said the voice was too fast at 1.0.
TTS_PACE: float = float(os.environ.get("TTS_PACE", 0.9))
TTS_WORKERS: int = int(os.environ.get("TTS_WORKERS", 3))
TTS_TIMEOUT_S: float = float(os.environ.get("TTS_TIMEOUT_S", 60))
TTS_MAX_ATTEMPTS: int = int(os.environ.get("TTS_MAX_ATTEMPTS", 5))
TTS_RETRY_BACKOFF_S: float = float(os.environ.get("TTS_RETRY_BACKOFF_S", 2.0))
# 30 Sep: Sarvam sent 429 after ~50 requests in the first minute. Start requests at least this
# far apart across all workers (~46 a minute), and wait longer after a 429.
TTS_MIN_GAP_S: float = float(os.environ.get("TTS_MIN_GAP_S", 1.3))
TTS_429_WAIT_S: float = float(os.environ.get("TTS_429_WAIT_S", 15.0))
# "#" twice replays the last line slower, stretched at play time (plan 2.5).
SLOW_PACE: float = float(os.environ.get("SLOW_PACE", 0.8))
# Audio goes down the line in frames of this many mu-law bytes (8000 = 1 s), each clip then a mark.
FRAME_BYTES: int = int(os.environ.get("FRAME_BYTES", 8000))

# Voice IDs per language, as they go into the render key.
VOICE_IDS: dict[str, str] = {
    lang: f"{speaker}@{TTS_PACE}" for lang, speaker in TTS_SPEAKERS.items()
}

# Directories and paths
AUDIO_DIR: str = os.environ.get("AUDIO_DIR", "audio")
SNAPSHOTS_DIR: str = os.environ.get("SNAPSHOTS_DIR", "snapshots")
RAW_CACHE_DIR: str = os.environ.get("RAW_CACHE_DIR", "data_cache/raw")
EXTRACT_CACHE_DIR: str = os.environ.get("EXTRACT_CACHE_DIR", "data_cache/extract")
DERIVED_DIR: str = os.environ.get("DERIVED_DIR", "data_cache/derived")
REPORTS_DIR: str = os.environ.get("REPORTS_DIR", "data_cache/reports")

# Groq model and extraction pipeline (06-BUILD-PLAN.md Step 8)
GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_REASONING_EFFORT: str = os.environ.get("GROQ_REASONING_EFFORT", "low")
GROQ_POLITE_DELAY_S: float = float(os.environ.get("GROQ_POLITE_DELAY_S", 2.0))
SUMMARY_WORD_TARGET: int = int(os.environ.get("SUMMARY_WORD_TARGET", 35))
SUMMARY_WORD_TOLERANCE: int = int(os.environ.get("SUMMARY_WORD_TOLERANCE", 10))
GROQ_MAX_RETRIES: int = int(os.environ.get("GROQ_MAX_RETRIES", 6))
GROQ_TIMEOUT_S: float = float(os.environ.get("GROQ_TIMEOUT_S", 45.0))
GROQ_RETRY_SLEEP_S: float = float(os.environ.get("GROQ_RETRY_SLEEP_S", 2.0))
GROQ_429_DEFAULT_WAIT_S: float = float(os.environ.get("GROQ_429_DEFAULT_WAIT_S", 5.0))
GROQ_429_MIN_WAIT_S: float = float(os.environ.get("GROQ_429_MIN_WAIT_S", 1.0))
GROQ_429_PAD_S: float = float(os.environ.get("GROQ_429_PAD_S", 1.5))
ALIAS_BENEFITS_CHARS: int = int(os.environ.get("ALIAS_BENEFITS_CHARS", 300))
# An alias on this many schemes or more is a category word and is dropped from all (T12)
ALIAS_CATEGORY_WORD_MIN: int = int(os.environ.get("ALIAS_CATEGORY_WORD_MIN", 3))
# A scrape/derive run fails only if fewer than this many schemes survive quarantine (D2)
MIN_SCHEMES: int = int(os.environ.get("MIN_SCHEMES", 8))

# Spoken cards (step 1.9, D3). A card is read aloud on a phone call, so it is capped in words;
# CARD_OVERLAP_MIN is the share of a card's content words that must also appear in the source,
# which is how a card is held to the source instead of being trusted.
CARD_MAX_WORDS: int = int(os.environ.get("CARD_MAX_WORDS", 55))
CARD_OVERLAP_MIN: float = float(os.environ.get("CARD_OVERLAP_MIN", 0.6))
CARDS_FILE: str = os.environ.get("CARDS_FILE", "data_cache/derived/cards.jsonl")


# Translation (plan item 1.9, D4). Hindi and Marathi come from Sarvam Translate, not Groq, so
# Groq's small daily budget stays with the live call. Every number below was probed against the
# live API on 20 Sep 2026 and written to .agent/NOTES.md; TRANSLATE_CHAR_LIMIT in particular is
# the API's own cap (2001 characters returns a 400), not a guess.
TRANSLATE_MODEL: str = os.environ.get("TRANSLATE_MODEL", "sarvam-translate:v1")
TRANSLATE_CHAR_LIMIT: int = int(os.environ.get("TRANSLATE_CHAR_LIMIT", 2000))
TRANSLATE_TIMEOUT_S: float = float(os.environ.get("TRANSLATE_TIMEOUT_S", 60))
TRANSLATE_MIN_GAP_S: float = float(os.environ.get("TRANSLATE_MIN_GAP_S", 0.2))
# One read timed out on the first real run of the 12. A timeout or a 5xx/429 is retried; a 402
# (no credits) or a 400 (bad input) is final and is never retried.
TRANSLATE_MAX_ATTEMPTS: int = int(os.environ.get("TRANSLATE_MAX_ATTEMPTS", 3))
TRANSLATE_RETRY_BACKOFF_S: float = float(os.environ.get("TRANSLATE_RETRY_BACKOFF_S", 2.0))
# Cache invalidation lives with the other prompt versions, in p2_derive.PROMPT_VERSIONS
# ("translate_hi"/"translate_mr"): bump it there after a model or numeral-format change.

# Gates (plan item 1.10, D5). Five gates decide whether a scheme may be spoken in a language.
# A number below GATE_NUMBER_MIN is allowed to arrive as a word: Sarvam turns "3 installments"
# into "तीन", seen first-hand on pm-kisan. Amounts (6000, 200000) are never spelled out, so
# anything at or above the floor must survive the translation as digits.
GATE_NUMBER_MIN: int = int(os.environ.get("GATE_NUMBER_MIN", 100))
GATE_LENGTH_RATIO_MAX: float = float(os.environ.get("GATE_LENGTH_RATIO_MAX", 1.6))
GATE_SCRIPT_MIN: float = float(os.environ.get("GATE_SCRIPT_MIN", 0.8))
GATES_FILE: str = os.environ.get("GATES_FILE", "data_cache/derived/gates.jsonl")
# G3 counts words, not characters (Devanagari uses more characters per word), and skips text
# shorter than this: turning "Aadhaar Card." into a spoken sentence must add words.
GATE_LENGTH_MIN_WORDS: int = int(os.environ.get("GATE_LENGTH_MIN_WORDS", 12))
