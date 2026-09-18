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
DEFAULT_TTS_MODEL: str = os.environ.get("DEFAULT_TTS_MODEL", "sarvam:bulbul:v1")

# Default voice IDs per language
VOICE_IDS: dict[str, str] = {
    "en": os.environ.get("VOICE_ID_EN", "en-IN-female"),
    "hi": os.environ.get("VOICE_ID_HI", "hi-IN-female"),
    "mr": os.environ.get("VOICE_ID_MR", "mr-IN-female"),
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

