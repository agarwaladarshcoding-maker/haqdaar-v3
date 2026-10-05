"""haqdaar/model/muse_talk.py

Muse as a model of the talk chain (owner, 5 Oct: Groq's free day limit ran out on a demo day).
A TALK_MODELS entry "muse:<model name>" comes here. ONE try, a short timeout, never raises:
any failure is handed back so the chain moves to the next model. The money guard of the
pipeline's Muse client is kept: the same ledger, the same caps, the same day block.
Note: the caller's words go to Muse on this path (its Contributor tier may train on them).
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv
import httpx

from haqdaar.contracts import tunables
from haqdaar.data.pipeline import muse
from haqdaar.model.client import ModelClientResponse

PREFIX = "muse:"


def _post(payload: dict[str, Any], key: str, timeout: float) -> tuple[int, Any]:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(muse.ENDPOINT, headers=headers, json=payload)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, resp.text


def _refused(ledger: Any) -> str:
    """Why the money guard says no, or "" when Muse is open."""
    if muse.spent_inr(ledger) >= tunables.MUSE_CAP_INR:
        return "muse_cap"
    if muse.blocked_day(ledger) == muse.muse_day():
        return "muse_blocked"
    if muse.spent_today_inr(ledger) >= tunables.MUSE_DAILY_CAP_INR:
        return "muse_day_cap"
    return ""


def call(messages: list[dict[str, str]], task: str = "talk", timeout: Optional[float] = None,
         model: str = "", post: Any = None, ledger: Any = None, api_key: Optional[str] = None) -> ModelClientResponse:
    name = model[len(PREFIX):] if model.startswith(PREFIX) else model
    ledger = ledger or muse.LEDGER
    if api_key is None:
        load_dotenv()
        api_key = os.environ.get("MUSE_API_KEY", "")
    if not api_key:
        return ModelClientResponse(success=False, data=None, error="no_key", is_429=True)
    why = _refused(ledger)
    if why:                                    # is_429: the chain goes on to the next model
        return ModelClientResponse(success=False, data=None, error=why, is_429=True)
    payload = {"model": name, "messages": messages, "response_format": {"type": "json_object"},
               "reasoning_effort": tunables.TALK_MUSE_EFFORT}
    t0 = time.monotonic()
    try:
        status, data = (post or _post)(payload, api_key, max(timeout or 0.0, tunables.TALK_MUSE_TIMEOUT_S))
    except httpx.TimeoutException:
        return ModelClientResponse(success=False, data=None, error="timeout", is_timeout=True, is_429=True,
                                   latency_s=time.monotonic() - t0)
    except Exception as e:
        return ModelClientResponse(success=False, data=None, error=f"{type(e).__name__}: {e}", is_429=True,
                                   latency_s=time.monotonic() - t0)
    latency = time.monotonic() - t0
    if status != 200 or not isinstance(data, dict):
        return ModelClientResponse(success=False, data=None, error=f"http_{status}", is_429=True, latency_s=latency)
    usage = data.get("usage") or {}
    p_tok = int(usage.get("prompt_tokens") or 0)
    out = max(int(usage.get("completion_tokens") or 0), int(usage.get("total_tokens") or 0) - p_tok)
    try:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "task": task, "slug": "",
                                "model": name, "prompt_tokens": p_tok, "completion_tokens": out,
                                "inr": round(muse.cost_inr(p_tok, out), 5)}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    choices = data.get("choices") or []
    content = (choices[0].get("message", {}).get("content", "") if choices else "") or ""
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        parsed = json.loads(content)
    except ValueError:
        parsed = None
    if not isinstance(parsed, dict):
        return ModelClientResponse(success=False, data=None, error="json_parse_error", is_429=True,
                                   latency_s=latency, prompt_tokens=p_tok, completion_tokens=out)
    return ModelClientResponse(success=True, data=parsed, latency_s=latency, prompt_tokens=p_tok,
                               completion_tokens=out)
