"""haqdaar/model/middle.py

Reply half of English in the middle (step 1.4a). English reply in, caller
language out, one sentence at a time so the voice can start on the first.

- "en": each sentence comes back as it is, no network call.
- hi, mr, gu, ta: each sentence goes through AnswerTranslator (sarvam-translate:v1).
- Any other code: one item with the text "not supported", marked failed.
- Fixed guard on every sentence, no model: numbers must match both ways, and a
  scheme name in the English must come out unchanged or in the target tongue.
- A failed sentence gets one more try. A still-failed sentence, a time-out, or a
  network error comes back marked failed. Never give a failed text out as passed.
- Never raises.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Iterator

from haqdaar.model.translate import AnswerTranslator

LANGS = ("hi", "mr", "gu", "ta")

_ABBREV = re.compile(r"\b(?:Rs|No|Dr|St|Mr|Mrs|Ms)\.", re.I)
_END = re.compile(r"[.!?।]+(?=\s|$)")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_NUM = re.compile(r"[0-9०-९૦-૯௦-௯][0-9०-९૦-૯௦-௯,]*")
_TO_LATIN = str.maketrans("०१२३४५६७८९૦૧૨૩૪૫૬૭૮૯௦௧௨௩௪௫௬௭௮௯", "0123456789" * 3)


@dataclass
class Out:
    text: str  # what to say; "" when failed and nothing usable came back
    ok: bool  # True means it passed the guard and may be spoken
    ms: int  # time spent on this sentence


def split_sentences(text: str) -> list[str]:
    """Cut into sentences in order. "Rs. 500" and "No. 2" do not cut."""
    masked = _ABBREV.sub(lambda m: m.group(0)[:-1] + "․", text)
    cuts = [m.end() for m in _END.finditer(masked)]
    parts, start = [], 0
    for end in cuts:
        parts.append(masked[start:end])
        start = end
    parts.append(masked[start:])
    out = []
    for part in parts:
        sent = part.replace("․", ".").strip()
        if sent:
            out.append(sent)
    return out


def _norm(text: str) -> str:
    return " ".join(_PUNCT.sub(" ", str(text).lower()).split())


def _numbers(text: str) -> set[str]:
    """Every number in the text. Latin and Devanagari, Gujarati, Tamil digits
    count as the same; "6,000" and "6000" are the same. Words do not count."""
    return {m.replace(",", "") for m in _NUM.findall(text.translate(_TO_LATIN))} - {""}


def scheme_names() -> list[dict]:
    """ONE place that reads the scheme names the data holds today.

    Reads rows the way haqdaar/data/scheme_index.py does (read only): the
    CURRENT snapshot id, then schemes.jsonl, fields scheme_name_en/hi/mr and
    aliases_en/hi/mr. Short spoken names per scheme get plugged in here at
    the merge. Never raises: any bad file gives [].
    """
    try:
        root = os.environ.get("SNAPSHOTS_DIR", "snapshots")
        try:
            with open(os.path.join(root, "CURRENT"), encoding="utf-8") as f:
                sid = f.read().strip()
        except OSError:
            return []
        if not sid:
            return []
        out: list[dict] = []
        with open(os.path.join(root, sid, "schemes.jsonl"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict) or not row.get("scheme_id"):
                    continue
                item: dict = {}
                for lang in ("en", "hi", "mr"):
                    names: list[str] = []
                    raw = [row.get("scheme_name_" + lang)] + list(row.get("aliases_" + lang) or [])
                    for name in raw:
                        normed = _norm(name or "")
                        if normed and normed not in names:
                            names.append(normed)
                    item[lang] = names
                out.append(item)
        return out
    except Exception:
        return []


def guard_ok(en: str, out: str, lang: str, names: list[dict] | None = None) -> bool:
    """Fixed guard for one sentence pair. True means the output may be spoken."""
    if _numbers(en) != _numbers(out):
        return False
    if names is None:
        names = scheme_names()
    norm_en = " " + _norm(en) + " "
    norm_out = " " + _norm(out) + " "
    want = lang if lang in ("hi", "mr") else ""
    for item in names:
        own = [_norm(name) for name in item.get("en", [])]
        if not any(" " + name + " " in norm_en for name in own):
            continue
        if any(" " + name + " " in norm_out for name in own):
            continue
        if want and any(_norm(name) in norm_out for name in item.get(want, [])):
            continue
        return False
    return True


def _timeout() -> float:
    try:
        return float(os.environ.get("MIDDLE_TIMEOUT_S", "3.0"))
    except ValueError:
        return 3.0


def reply_in(reply_en: str, lang: str) -> Iterator[Out]:
    """English reply in, caller language out, one sentence at a time."""
    if lang == "en":
        for sent in split_sentences(reply_en):
            yield Out(text=sent, ok=True, ms=0)
        return
    if lang not in LANGS:
        yield Out(text="not supported", ok=False, ms=0)
        return
    try:
        translator = AnswerTranslator(timeout=_timeout())
    except Exception:
        translator = None
    try:
        names = scheme_names()
    except Exception:
        names = []
    for sent in split_sentences(reply_en or ""):
        start = time.monotonic()
        text, ok = "", False
        try:
            for _ in range(2):
                got = None
                try:
                    if translator is not None:
                        got = translator.translate(sent, lang)
                except Exception:
                    got = None
                if got and got.strip() and guard_ok(sent, got, lang, names):
                    text, ok = got, True
                    break
                text = got or ""
        except Exception:
            text, ok = "", False
        yield Out(text=text, ok=ok, ms=int((time.monotonic() - start) * 1000))
