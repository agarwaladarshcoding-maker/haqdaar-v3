"""haqdaar/contracts/types.py

UNOWNED. Shared types, markers, and interfaces matching 04-INTERFACES.md.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from typing import Literal, Union

from haqdaar.contracts import tunables

# Frozen interface primitives
RenderKey = str
ValueCode = str
BoxId = str
Lang = Literal["en", "hi", "mr"]
LangSource = Literal["keypad", "default"]

# Special markers
UNASKED = "__UNASKED__"
UNKNOWN = "UNKNOWN"
ANY = "ANY"

# Seven-box roster (T10, 03-ARCHITECTURE §7.2)
SEVEN_BOXES: tuple[BoxId, ...] = (
    "category",
    "state",
    "gender",
    "social_category",
    "age",
    "income_band",
    "occupation",
)

HARD_BOXES: frozenset[BoxId] = frozenset({"state", "gender", "social_category"})
# Widening order (T10 D6, amended 13 Sep): income_band -> age -> occupation.
# `category` is a soft box but it is NOT widened. It is the subject the caller
# phoned about (Door A); dropping it answers a question they did not ask, and
# with it in the ladder "ladder exhausted" and "no scheme with a soft-only
# miss-set" become the same condition, which made delivery shape 4 (NEAREST)
# unreachable in every corpus. See WORK.md §9 22.
WIDENING_ORDER: tuple[BoxId, ...] = ("income_band", "age", "occupation")

# Six scheme read-back chunks in order (05-DATA-CONTRACT.md §1E)
SCHEME_CHUNKS: tuple[str, ...] = (
    "name",
    "summary",
    "benefit_text",
    "who_can_apply",
    "documents",
    "how_to_apply",
)

# 46 fixed line IDs (05-DATA-CONTRACT.md §4)
FIXED_LINE_IDS: tuple[str, ...] = (
    "greeting_trilingual",
    "consent_notice",
    "opener_prompt",
    "unclear_prompt",
    "anything_else",
    "door_a_option_1",
    "door_a_option_2",
    "door_a_option_none",
    "door_a_downgrade_to_b",
    "q_state",
    "q_gender",
    "q_social_category",
    "q_age",
    "q_income_band",
    "q_occupation",
    "rephrase_state",
    "rephrase_gender",
    "rephrase_social_category",
    "rephrase_age",
    "rephrase_income_band",
    "rephrase_occupation",
    "keypad_gender",
    "keypad_social_category",
    "keypad_age",
    "keypad_income_band",
    "keypad_occupation",
    "keypad_unknown_suffix",
    "bundle_confirm_intro",
    "confirm_bundle_opener",
    "confirm_yn_suffix",
    "silence_presence",
    "section_menu",
    "section_source_frame",
    "next_scheme_intro",
    "no_more_schemes",
    "keypad_only_mode",
    "state_unknown_disclaimer",
    "results_exact_preamble",
    "results_overflow",
    "terminal_widened_preamble",
    "drop_income_band",
    "drop_age",
    "drop_occupation",
    "drop_category",
    "results_widened_lead",
    "terminal_nearest_preamble",
    "terminal_empty",
    "closing_farewell",
)


# Input union (04-INTERFACES.md § Audio)
@dataclass(frozen=True)
class Digit:
    digit: str


@dataclass(frozen=True)
class Speech:
    text: str
    discarded_transcript: str | None = None


@dataclass(frozen=True)
class Noise:
    pass


@dataclass(frozen=True)
class Silence:
    n: int


@dataclass(frozen=True)
class Hangup:
    pass


Input = Union[Digit, Speech, Noise, Silence, Hangup]


# Planner actions (04-INTERFACES.md § Engine)
@dataclass(frozen=True)
class Ask:
    box: BoxId


@dataclass(frozen=True)
class Widen:
    box: BoxId


@dataclass(frozen=True)
class Stop:
    reason: str


Action = Union[Ask, Widen, Stop]


# Model stamps and outputs (04-INTERFACES.md § Model)
@dataclass(frozen=True)
class Stamp:
    box: str  # box name or "scheme" pseudo-box
    value: ValueCode
    span: str


@dataclass(frozen=True)
class Answer:
    box: BoxId
    value: ValueCode
    span: str


@dataclass(frozen=True)
class Clarify:
    box: BoxId


@dataclass(frozen=True)
class Repeat:
    pass


@dataclass(frozen=True)
class Meta:
    command: str


@dataclass(frozen=True)
class Unclear:
    reason: str = "unclear"


ModelTurnResult = Union[Answer, Clarify, Repeat, Meta, Unclear]
# T17 §3 names this type `TurnResult`; T17 wins over any other spelling.
TurnResult = ModelTurnResult


def compute_render_key(
    text: str,
    lang: str,
    voice_id: str | None = None,
    tts_model: str | None = None,
    sample_rate: int | None = None,
) -> RenderKey:
    """Compute content-addressed render_key = sha256(text ‖ lang ‖ voice_id ‖ tts_model ‖ 8000)."""
    if voice_id is None:
        voice_id = tunables.VOICE_IDS.get(lang, "default")
    if tts_model is None:
        tts_model = tunables.DEFAULT_TTS_MODEL
    if sample_rate is None:
        sample_rate = tunables.SAMPLE_RATE
    raw = f"{text}{lang}{voice_id}{tts_model}{sample_rate}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
