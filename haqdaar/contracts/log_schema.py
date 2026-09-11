"""haqdaar/contracts/log_schema.py

Frozen log record types and schemas for call logs (T16, T24, Data Contract §5).
Strict rule: types and numbers only, no runtime logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Union

from haqdaar.contracts.types import BoxId, Lang, LangSource, ValueCode

# Turn Classes (T16 §2, T11, T14 §4)
TurnClass = Literal[
    "ANSWER",
    "CLARIFY",
    "REPEAT",
    "META",
    "UNCLEAR",
    "NOISE",
    "SILENCE",
]

TURN_CLASSES: tuple[TurnClass, ...] = (
    "ANSWER",
    "CLARIFY",
    "REPEAT",
    "META",
    "UNCLEAR",
    "NOISE",
    "SILENCE",
)

# UNKNOWN Sources (T16 §2, T11)
UnknownSource = Literal["declined", "keypad_dropped"]
UNKNOWN_SOURCES: tuple[UnknownSource, ...] = ("declined", "keypad_dropped")

# Stop Reasons (T10 §D4, T16 §2, T18, Data Contract §5)
STOP_LE_4_SURVIVORS = "survivors_le_4"
STOP_MAX_TURNS = "max_turns"
STOP_MAX_QUESTIONS = "max_questions"
STOP_NO_SPLIT = "no_split"
STOP_ZERO_SURVIVORS = "zero_survivors"

StopReason = Literal[
    "survivors_le_4",
    "max_turns",
    "max_questions",
    "no_split",
    "zero_survivors",
]

STOP_REASONS: tuple[str, ...] = (
    STOP_LE_4_SURVIVORS,
    STOP_MAX_TURNS,
    STOP_MAX_QUESTIONS,
    STOP_NO_SPLIT,
    STOP_ZERO_SURVIVORS,
)


@dataclass(frozen=True)
class CallOpenRecord:
    """Call open line (Data Contract §5, T24)."""
    call_id: str
    snapshot_id: str
    caller_hash: str
    lang: Lang
    lang_source: LangSource
    t0: float = 0.0


@dataclass(frozen=True)
class TurnLogRecord:
    """Per-turn line (T16 §2, T14, T24, Data Contract §5).
    Omitted / None fields are omitted in JSON serialization."""
    turn_n: int
    turn_class: TurnClass
    transcript: Optional[str] = None
    box: Optional[BoxId] = None
    value: Optional[ValueCode] = None
    span: Optional[str] = None
    unknown_source: Optional[UnknownSource] = None
    discarded_transcript: Optional[str] = None
    t_name: Optional[float] = None
    t_end: Optional[float] = None
    candidate_count: Optional[int] = None
    silence_n: Optional[int] = None
    invalid: Optional[bool] = None


@dataclass(frozen=True)
class LangSwitchRecord:
    """Mid-call '*' language switch (T24 amendment, written once per switch)."""
    lang: Lang
    lang_source: LangSource = "keypad"
    turn_n: Optional[int] = None


@dataclass(frozen=True)
class CallCloseRecord:
    """Closing line (T16 §2, T18, Data Contract §5)."""
    stop: StopReason
    ladder_rung: Optional[int] = None
    mode: Optional[Literal["voice", "keypad_only"]] = None


LogRecord = Union[CallOpenRecord, TurnLogRecord, LangSwitchRecord, CallCloseRecord]
