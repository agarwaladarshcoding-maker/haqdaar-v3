"""haqdaar/contracts/types.py

UNOWNED. Shared types, markers, and interfaces matching 04-INTERFACES.md.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
from typing import Literal, Union

from haqdaar.contracts import tunables

# Frozen interface primitives
RenderKey = str
ValueCode = str
BoxId = str
Lang = Literal["en", "hi", "mr", "bn", "gu", "kn", "ml", "od", "pa", "ta", "te"]
# Every language Sarvam hears, translates and speaks: our code -> Sarvam's code. The ONE list:
# the ear, the translate step and the live voice all read it. A new Sarvam language is one line here.
SARVAM_CODES: dict[str, str] = {
    "hi": "hi-IN", "mr": "mr-IN", "en": "en-IN", "bn": "bn-IN", "gu": "gu-IN", "kn": "kn-IN",
    "ml": "ml-IN", "od": "od-IN", "pa": "pa-IN", "ta": "ta-IN", "te": "te-IN",
}
LangSource = Literal["keypad", "voice", "default"]

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

# N6: the boxes the TALK can ask and filter on. The keys path keeps the seven (menus, clips, the planner's
# defaults); the talk adds what the seven can not cut a big kind with: what the scheme gives, the kind inside the
# kind, the whole list of states, and yes / no facts (a box named f_<fact>, values yes / no). A snapshot
# that has not been built with a box simply does not hold it: the talk takes that as "nothing to ask".
FACT_NAMES: tuple[str, ...] = (
    "bpl_card", "ration_card", "widow", "disability", "owns_farm_land", "rural", "pregnant", "student",
    "girl_child", "senior_alone", "minority", "income_tax_payer", "govt_employee", "bank_account", "aadhaar",
    "shop_or_trade", "new_business", "kutcha_house", "breadwinner_died", "migrant_worker",
)
FACT_BOXES: tuple[BoxId, ...] = tuple(f"f_{n}" for n in FACT_NAMES)
TALK_BOXES: tuple[BoxId, ...] = SEVEN_BOXES + ("gives", "sub_kind", "home_state") + FACT_BOXES

HARD_BOXES: frozenset[BoxId] = frozenset({"state", "gender", "social_category"})
# Widening order (T10 D6, amended 13 Sep): income_band -> age -> occupation.
# `category` is a soft box but it is NOT widened. It is the subject the caller
# phoned about (Door A); dropping it answers a question they did not ask, and
# with it in the ladder "ladder exhausted" and "no scheme with a soft-only
# miss-set" become the same condition, which made delivery shape 4 (NEAREST)
# unreachable in every corpus.
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

# 49 fixed line IDs (05-DATA-CONTRACT.md §4)
FIXED_LINE_IDS: tuple[str, ...] = (
    "greeting_trilingual",
    "consent_notice",
    "opener_prompt",
    "opener_short_prompt",
    "did_not_get_reply",
    "waiting_for_reply",
    "one_moment",
    "unclear_prompt",
    "anything_else",
    "door_a_option_1",
    "door_a_option_2",
    "door_a_option_none",
    "door_a_downgrade_to_b",
    "q_state",
    "state_q_maharashtra",
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
    "results_more_prompt",
    "keypad_only_mode",
    "state_unknown_disclaimer",
    "results_exact_preamble",
    "results_overflow",
    "terminal_widened_preamble",
    "drop_income_band",
    "drop_age",
    "drop_occupation",
    "results_widened_lead",
    "terminal_nearest_preamble",
    "terminal_empty",
    "closing_farewell",
)


# Input union (04-INTERFACES.md § Audio)
@dataclass(frozen=True)
class Digit:
    digit: str
    prompt_n: int = -1
    cut_clip: str = ""
    heard_ms: int = -1


@dataclass(frozen=True)
class Speech:
    text: str
    discarded_transcript: str | None = None
    prompt_n: int = -1
    cut_clip: str = ""
    heard_ms: int = -1
    lang: str = ""          # what the speech service heard (7.1)
    english: bool = False   # True when `text` is an English translation of the speech (7.1)
    # 7.14 stage times, for the log only: two Speech with the same words are still equal.
    end_ms: int = field(default=-1, compare=False)   # quiet the ear waited to end the caller's turn
    stt_ms: int = field(default=-1, compare=False)   # time speech-to-text took


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
    also_question: bool = False  # the caller also asked something (7.1, kind BOTH)


@dataclass
class SchemeEntry:
    """Scheme entry indexed for Door A matching (shared by engine + data loader)."""
    slug: str
    priority: int = 2
    names: dict[str, str] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    distinctive_tokens: set[str] = field(default_factory=set)


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


@dataclass(frozen=True)
class Question:
    """The caller asked something (7.1). Only made when QA_ENABLED is on."""
    pass


ModelTurnResult = Union[Answer, Clarify, Repeat, Meta, Unclear, Question]
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
