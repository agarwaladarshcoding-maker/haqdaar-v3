"""haqdaar/model/client.py

Groq raw httpx client for HAQDAAR v2.
Temperature 0, JSON output mode, 2.0s timeout, never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Optional

from dotenv import load_dotenv
import httpx

from haqdaar.contracts import tunables

BASE_DIR = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class ModelClientResponse:
    success: bool
    data: dict[str, Any] | None
    error: str | None = None
    is_429: bool = False
    is_timeout: bool = False
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class GroqModelClient:
    """Low-latency raw httpx client for Groq structured JSON outputs.

    - Fixed temperature: 0
    - JSON mode: response_format={"type": "json_object"}
    - Timeout: default 2.0s (overridable via MODEL_TIMEOUT_S)
    - Never raises: any network failure, timeout, 429, or unparseable response
      is trapped and returned as a typed failure response.
    - Usage recorded to reports ledger.
    """

    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        ledger_path: Optional[Path] = None,
    ) -> None:
        if api_key is None:
            load_dotenv()
            api_key = os.environ.get("GROQ_API_KEY", "")
        self.api_key = api_key

        # Prefer llama-3.3-70b-versatile or llama-3.1-8b-instant for fast low-latency JSON
        default_model = os.environ.get("GROQ_ROUTER_MODEL", os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"))
        self.model = model or default_model

        self.timeout = float(timeout) if timeout is not None else tunables.MODEL_TIMEOUT_S

        self.ledger_path: Path = (
            Path(ledger_path)
            if ledger_path is not None
            else BASE_DIR / tunables.REPORTS_DIR / "groq_usage.jsonl"
        )

    def _write_ledger(
        self,
        task: str,
        prompt_tokens: int,
        completion_tokens: int,
        error: str | None = None,
    ) -> None:
        """Append usage record to reports ledger without letting write failures interrupt."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "task": task,
            "model": self.model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "error": error,
        }
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def call(
        self,
        messages: list[dict[str, str]],
        task: str = "model_router",
    ) -> ModelClientResponse:
        """Call Groq API with JSON mode and timeout. Never raises."""
        if not self.api_key:
            return ModelClientResponse(
                success=False,
                data=None,
                error="no_key",
                latency_s=0.0,
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "haqdaar/0.1",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        t0 = time.monotonic()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.endpoint, headers=headers, json=payload)
            latency = time.monotonic() - t0

            if resp.status_code == 200:
                body = resp.json()
                usage = body.get("usage", {})
                p_tok = usage.get("prompt_tokens", 0)
                c_tok = usage.get("completion_tokens", 0)
                self._write_ledger(task, p_tok, c_tok)

                choices = body.get("choices", [])
                if not choices:
                    return ModelClientResponse(
                        success=False,
                        data=None,
                        error="empty_choices",
                        latency_s=latency,
                    )

                content_str = choices[0].get("message", {}).get("content", "")
                try:
                    parsed = json.loads(content_str)
                    return ModelClientResponse(
                        success=True,
                        data=parsed,
                        latency_s=latency,
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                    )
                except json.JSONDecodeError:
                    return ModelClientResponse(
                        success=False,
                        data=None,
                        error="json_parse_error",
                        latency_s=latency,
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                    )

            if resp.status_code == 429:
                self._write_ledger(task, 0, 0, error="http_429")
                return ModelClientResponse(
                    success=False,
                    data=None,
                    error="http_429",
                    is_429=True,
                    latency_s=latency,
                )

            err_tag = f"http_{resp.status_code}"
            self._write_ledger(task, 0, 0, error=err_tag)
            return ModelClientResponse(
                success=False,
                data=None,
                error=err_tag,
                latency_s=latency,
            )

        except httpx.TimeoutException:
            latency = time.monotonic() - t0
            self._write_ledger(task, 0, 0, error="timeout")
            return ModelClientResponse(
                success=False,
                data=None,
                error="timeout",
                is_timeout=True,
                latency_s=latency,
            )
        except Exception as e:
            latency = time.monotonic() - t0
            err_msg = f"{type(e).__name__}: {e}"
            self._write_ledger(task, 0, 0, error=err_msg)
            return ModelClientResponse(
                success=False,
                data=None,
                error=err_msg,
                latency_s=latency,
            )
