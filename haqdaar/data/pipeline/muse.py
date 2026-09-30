"""haqdaar/data/pipeline/muse.py

Plan 3.4 / 3.5 — Meta's Muse Spark (owner, 30 Sep) replaces Groq for the cards and Sarvam for
the translation. Offline pipeline only: the Contributor tier may train on what we send, so no
caller's words ever go here.

A hard money cap. Every call's tokens go into data_cache/reports/muse_usage.jsonl. Before each
call the ledger is summed in rupees; at or over `MUSE_CAP_INR` the call is refused with
MuseBudgetError, which no retry loop swallows. The cap counts every run ever made with this
ledger, not only this one, so re-running cannot creep past it.

    MuseClient().call(system, user, task, slug) -> dict      same shape as GroqClient.call
    MuseTranslator().translate(text, lang, slug, field) -> str  same shape as SarvamTranslator
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from haqdaar.contracts import tunables

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
LEDGER = BASE_DIR / tunables.REPORTS_DIR / "muse_usage.jsonl"
ENDPOINT = "https://api.meta.ai/v1/chat/completions"

LANG_NAMES = {"hi": "Hindi", "mr": "Marathi"}
# Devanagari digits: Muse wrote "६,०००" in the first test; the phone voice and the gates want 0-9.
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


class MuseBudgetError(RuntimeError):
    """The rupee cap is reached. Final: never retried."""


def cost_inr(prompt_tokens: int, output_tokens: int) -> float:
    usd = (prompt_tokens * tunables.MUSE_USD_PER_M_IN + output_tokens * tunables.MUSE_USD_PER_M_OUT) / 1e6
    return usd * tunables.USD_TO_INR


def spent_inr(ledger_path: Path = LEDGER) -> float:
    if not ledger_path.exists():
        return 0.0
    total = 0.0
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        try:
            total += float(json.loads(line).get("inr", 0.0))
        except (ValueError, AttributeError):
            continue
    return total


class MuseClient:
    """One caller at a time, JSON out, reasoning at MUSE_REASONING_EFFORT."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        ledger_path: Optional[Path] = None,
        post: Any = None,
        sleep: Any = time.sleep,
    ):
        if api_key is None:
            load_dotenv()
            api_key = os.environ.get("MUSE_API_KEY")
        if not api_key:
            raise ValueError("MUSE_API_KEY must be set in environment or .env")
        self.api_key = api_key
        self.ledger_path = Path(ledger_path) if ledger_path is not None else LEDGER
        self._post = post or self._http_post
        self._sleep = sleep
        self._last_call_time = 0.0
        self.requests = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def _http_post(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | str]:
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=tunables.MUSE_TIMEOUT_S) as client:
            resp = client.post(ENDPOINT, headers=headers, json=payload)
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text

    def _check_budget(self) -> None:
        spent = spent_inr(self.ledger_path)
        if spent >= tunables.MUSE_CAP_INR:
            raise MuseBudgetError(
                f"Muse spend cap reached: ₹{spent:.2f} of ₹{tunables.MUSE_CAP_INR:.0f} "
                f"(ledger {self.ledger_path.name}). Raise MUSE_CAP_INR only with the owner's OK."
            )

    def _write_ledger(self, task: str, slug: str, prompt_tokens: int, output_tokens: int) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "task": task,
            "slug": slug,
            "model": tunables.MUSE_MODEL,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": output_tokens,
            "inr": round(cost_inr(prompt_tokens, output_tokens), 5),
        }
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"Warning: failed to write Muse usage ledger {self.ledger_path}: {e}", file=sys.stderr)

    def call(self, system_prompt: str, user_prompt: str, task: str = "", slug: str = "") -> dict[str, Any]:
        payload = {
            "model": tunables.MUSE_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "reasoning_effort": tunables.MUSE_REASONING_EFFORT,
        }
        attempts = tunables.MUSE_MAX_RETRIES
        for attempt in range(attempts):
            self._check_budget()
            gap = time.time() - self._last_call_time
            if gap < tunables.MUSE_POLITE_DELAY_S:
                self._sleep(tunables.MUSE_POLITE_DELAY_S - gap)
            self._last_call_time = time.time()
            try:
                status, data = self._post(payload)
            except Exception as e:
                if attempt == attempts - 1:
                    raise RuntimeError(f"Muse network call failed: {e}") from e
                logger.warning("Muse network error (attempt %d): %s", attempt + 1, e)
                self._sleep(tunables.MUSE_RETRY_SLEEP_S * (attempt + 1))
                continue
            if status == 429 or status >= 500:
                if attempt == attempts - 1:
                    raise RuntimeError(f"Muse HTTP {status} after {attempts} attempts: {data}")
                logger.warning("Muse HTTP %d (attempt %d), waiting", status, attempt + 1)
                self._sleep(tunables.MUSE_429_WAIT_S)
                continue
            if status != 200 or not isinstance(data, dict):
                raise RuntimeError(f"Muse API returned HTTP {status}: {data}")

            # Tokens are counted (and paid) even when the answer is unusable.
            usage = data.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion = int(usage.get("completion_tokens") or 0)
            total = int(usage.get("total_tokens") or 0)
            output_tokens = max(completion, total - prompt_tokens)  # reasoning is billed as output
            self.requests += 1
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += output_tokens
            self._write_ledger(task, slug, prompt_tokens, output_tokens)

            choices = data.get("choices") or []
            content = (choices[0].get("message", {}).get("content", "") if choices else "") or ""
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
            if not content:
                raise RuntimeError("Muse returned empty content")
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Failed to parse Muse response JSON: {e}\nRaw content: {content}") from e
        raise RuntimeError(f"Muse call failed after {attempts} attempts.")


TRANSLATE_SYSTEM = """You translate short texts for a phone helpline that reads government scheme \
information aloud to rural families in India. Translate the English text into {lang_name}.

Rules:
- Plain, everyday spoken {lang_name} that a village listener understands. Short sentences.
- Keep the meaning exactly. Add nothing, drop nothing. Do not explain.
- Write every number with the digits 0-9 (for example 6000, 2.5, 18). Never use Devanagari digits.
- Keep amounts, ages, dates and percentages exactly as in the English.
- Keep scheme names as commonly said in {lang_name} (for example "PM-KISAN" stays "पीएम-किसान").
- Keep any text inside curly braces, like {{n}}, exactly as it is.

Answer with JSON only: {{"translation": "..."}}"""


class MuseTranslator:
    """Drop-in for SarvamTranslator: translate(text, lang, slug, field) -> str."""

    def __init__(self, client: Optional[MuseClient] = None):
        self.client = client or MuseClient()
        self.requests = 0
        self.chars = 0

    def translate(self, text: str, lang: str, slug: str = "", field: str = "") -> str:
        from haqdaar.data.pipeline.p4_translate import TranslateError

        text = (text or "").strip()
        if not text:
            return ""
        if lang not in LANG_NAMES:
            raise TranslateError(f"unknown target language {lang!r}")
        system = TRANSLATE_SYSTEM.format(lang_name=LANG_NAMES[lang])
        try:
            out = self.client.call(system, text, task=f"translate_{lang}:{field}", slug=slug)
        except MuseBudgetError:
            raise
        except RuntimeError as e:
            raise TranslateError(str(e)) from e
        translated = str(out.get("translation", "")).strip().translate(_DEVANAGARI_DIGITS)
        if not translated:
            raise TranslateError("Muse returned an empty translation")
        self.requests += 1
        self.chars += len(text)
        return translated
