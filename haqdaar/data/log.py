"""haqdaar/data/log.py

Log persistence for Haqdaar v2 (T16, T16-amendment, T17, T18, T24, Data Contract §5).
Writes one JSONL file per call to logs/<call_id>.jsonl.
Strict rule: Log.write never raises — malformed records are persisted with invalid: True.
Flush after every write for durability before next audio prompt.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any, Optional, Union
import warnings

from haqdaar.contracts.log_schema import (
    CallCloseRecord,
    CallOpenRecord,
    DeliveryRecord,
    LangSwitchRecord,
    LogRecord,
    STOP_REASONS,
    StopReason,
    TURN_CLASSES,
    TurnClass,
    TurnLogRecord,
    UNKNOWN_SOURCES,
)
from haqdaar.contracts.types import Lang, LangSource


class Log:
    """Durably writes call logs line by line in JSONL format."""

    def __init__(
        self,
        file_path: Path | str,
        call_id: str,
        snapshot_id: str,
    ) -> None:
        self.call_id = call_id
        self.snapshot_id = snapshot_id
        self.path = Path(file_path)
        self.file_path = self.path
        self._file = open(self.path, "a", encoding="utf-8")
        self._closed = False
        self.tap = None  # the call trace sets this to get a copy of every line (must not raise)

    @classmethod
    def open(
        cls,
        call_id: str,
        snapshot_id: str,
        caller_hash: str = "",
        lang: Lang = "hi",
        lang_source: LangSource = "default",
        logs_dir: Path | str = "logs",
        t0: float = 0.0,
    ) -> Log:
        """Open a new call log and write the CallOpenRecord header."""
        logs_path = Path(logs_dir)
        logs_path.mkdir(parents=True, exist_ok=True)
        file_path = logs_path / f"{call_id}.jsonl"

        instance = cls(
            file_path=file_path,
            call_id=call_id,
            snapshot_id=snapshot_id,
        )

        open_record = CallOpenRecord(
            call_id=call_id,
            snapshot_id=snapshot_id,
            caller_hash=caller_hash,
            lang=lang,
            lang_source=lang_source,
            t0=t0,
        )
        instance.write(open_record)
        return instance

    def write(self, line: Union[dict[str, Any], LogRecord, Any]) -> None:
        """Write a log record as a single JSON line and flush.

        FROZEN ERROR BEHAVIOR: Log.write NEVER raises.
        If a record fails schema validation, it is written anyway carrying
        invalid: True with a warning to stderr.
        """
        try:
            if self._closed:
                warnings.warn(f"Log.write called on closed log {self.call_id}", UserWarning)
                return

            serialized, is_invalid = self._format_and_validate(line)
            json_str = json.dumps(serialized, ensure_ascii=False)
            self._file.write(json_str + "\n")
            self._file.flush()
            if self.tap is not None:
                self.tap(serialized)
        except Exception as exc:
            # Absolute fail-safe: never kill the call
            try:
                warnings.warn(f"Log.write exception: {exc}", UserWarning)
                fallback = {
                    "raw": str(line),
                    "invalid": True,
                    "error": str(exc),
                }
                self._file.write(json.dumps(fallback, ensure_ascii=False) + "\n")
                self._file.flush()
            except Exception:
                pass

    def _format_and_validate(self, line: Any) -> tuple[dict[str, Any], bool]:
        """Convert line to a JSON-serializable dict and validate schema rules."""
        is_invalid = False

        if isinstance(line, TurnLogRecord):
            raw = asdict(line)
            data: dict[str, Any] = {
                "turn_n": raw["turn_n"],
                "class": raw["turn_class"],
            }
            for k in (
                "transcript",
                "box",
                "value",
                "span",
                "unknown_source",
                "discarded_transcript",
                "t_name",
                "t_end",
                "candidate_count",
                "silence_n",
                "invalid",
                "answer",
            ):
                if raw.get(k) is not None:
                    data[k] = raw[k]

            if data["class"] not in TURN_CLASSES or not isinstance(data["turn_n"], int):
                is_invalid = True
                data["invalid"] = True
                warnings.warn(f"Malformed TurnLogRecord: {line}", UserWarning)

            if raw.get("invalid") is True:
                is_invalid = True
                data["invalid"] = True

            return data, is_invalid

        elif isinstance(line, CallOpenRecord):
            raw = asdict(line)
            return {k: v for k, v in raw.items() if v is not None}, False

        elif isinstance(line, CallCloseRecord):
            raw = asdict(line)
            data = {k: v for k, v in raw.items() if v is not None}
            if data.get("stop") not in STOP_REASONS:
                is_invalid = True
                data["invalid"] = True
                warnings.warn(f"Malformed CallCloseRecord stop reason: {line}", UserWarning)
            return data, is_invalid

        elif isinstance(line, LangSwitchRecord):
            raw = asdict(line)
            return {k: v for k, v in raw.items() if v is not None}, False

        elif isinstance(line, DeliveryRecord):
            raw = asdict(line)
            return {k: v for k, v in raw.items() if v is not None}, False

        elif isinstance(line, dict):
            data = dict(line)
            if "turn_class" in data and "class" not in data:
                data["class"] = data.pop("turn_class")

            # Check if it represents a mode line or lang line or open line
            if "mode" in data or "lang" in data or "call_id" in data:
                # Valid one-off records (e.g. keypad_only mode entry, lang switch, etc.)
                pass

            # Check if it represents a turn line
            elif "class" in data or "turn_n" in data:
                if (
                    "class" not in data
                    or data["class"] not in TURN_CLASSES
                    or "turn_n" not in data
                    or not isinstance(data["turn_n"], int)
                ):
                    is_invalid = True
                    data["invalid"] = True
                    warnings.warn(f"Malformed turn log dict: {line}", UserWarning)

            # Check if it represents a close line
            elif "stop" in data:
                if data["stop"] not in STOP_REASONS:
                    is_invalid = True
                    data["invalid"] = True
                    warnings.warn(f"Malformed close dict stop reason: {line}", UserWarning)
            else:
                # Unrecognized record structure
                is_invalid = True
                data["invalid"] = True
                warnings.warn(f"Unrecognized log record structure: {line}", UserWarning)

            # Omit None values
            clean_data = {k: v for k, v in data.items() if v is not None}
            return clean_data, is_invalid

        else:
            is_invalid = True
            warnings.warn(f"Non-dict, non-dataclass log line: {type(line)}", UserWarning)
            return {"raw": str(line), "invalid": True}, True

    def close(
        self,
        reason: StopReason | str,
        ladder_rung: Optional[int] = None,
        mode: Optional[str] = None,
    ) -> None:
        """Write the CallCloseRecord and close the file handle."""
        if self._closed:
            return
        close_rec = CallCloseRecord(
            stop=reason,  # type: ignore[arg-type]
            ladder_rung=ladder_rung,
            mode=mode,  # type: ignore[arg-type]
        )
        self.write(close_rec)
        self._closed = True
        try:
            self._file.close()
        except Exception:
            pass

    def __enter__(self) -> Log:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if not self._closed:
            self.close(reason="ended")
