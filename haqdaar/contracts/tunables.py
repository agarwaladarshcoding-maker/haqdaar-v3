"""haqdaar/contracts/tunables.py

UNOWNED. Every tunable lives here and changes with no ceremony at all.
Hardcode nothing.
"""
from __future__ import annotations
import os

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
