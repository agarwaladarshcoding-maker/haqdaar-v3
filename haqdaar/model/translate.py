"""haqdaar/model/translate.py

English -> Hindi/Marathi for an answer text (step 7.1, ENGLISH_PIPE). Sarvam translate with
sarvam-translate:v1: on 4 Oct it got all 6 money and age sentences right, while mayura:v1 turned
"6,000" into "three thousand two hundred". Do not switch to mayura. Never raises.
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv

from haqdaar import net
from haqdaar.contracts import tunables

TARGET_CODES = {"hi": "hi-IN", "mr": "mr-IN"}


class AnswerTranslator:
    endpoint = "https://api.sarvam.ai/translate"
    model = "sarvam-translate:v1"

    def __init__(self, api_key: Optional[str] = None, timeout: Optional[float] = None) -> None:
        if api_key is None:
            load_dotenv()
            api_key = os.environ.get("SARVAM_API_KEY", "")
        self.api_key = api_key
        self.timeout = timeout

    def translate(self, text: str, lang: str) -> Optional[str]:
        """The text in the caller's language, or None on any failure or time-out."""
        target = TARGET_CODES.get(lang)
        if not self.api_key or not target or not text.strip():
            return None
        timeout = self.timeout if self.timeout is not None else tunables.QA_TRANSLATE_TIMEOUT_S
        try:
            resp = net.post(
                self.endpoint,
                headers={"api-subscription-key": self.api_key, "Content-Type": "application/json"},
                json={
                    "input": text,
                    "source_language_code": "en-IN",
                    "target_language_code": target,
                    "model": self.model,
                },
                timeout=timeout,
            )
            if resp.status_code != 200:
                return None
            out = resp.json().get("translated_text")
            return out.strip() if isinstance(out, str) and out.strip() else None
        except Exception:
            return None
