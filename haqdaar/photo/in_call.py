"""haqdaar/photo/in_call.py

Steps 4.2 / 4.3: the photo link in a talk call, and the call-back that opens the next call.
send_link makes a case and texts its link; pending says whether a read photo waits for a call-back
(tools/photo_desk.py writes PHOTO_DIR/next_call.json); done closes it. No model, no voice. The
number is only ever passed in and used for the SMS: never logged, never returned.
"""
from __future__ import annotations

import inspect
import json
import os
import time
from typing import Any, Callable, Optional

from haqdaar.contracts import tunables
from haqdaar.photo import cases

SMS_TEXT = "Haqdaar: send your photo here: {link} No internet? Open the Haqdaar app."


def _sms(to_number: str, text: str) -> str:
    from haqdaar.audio import telephony

    return telephony.provider.send_sms(to_number, text)


def send_link(lang: str, langs: list[str], number: str,
              sms: Optional[Callable[[str, str], Any]] = None) -> dict[str, Any]:
    """Make a case, text its link. {"token", "link", "sent", "why"}; an SMS fault never raises."""
    kw: dict[str, Any] = {}
    if "langs" in inspect.signature(cases.new_case).parameters:   # the photo desk worker adds it; both orders must work
        kw["langs"] = list(langs)
    case = cases.new_case(lang, number, **kw)
    link = cases.link(case)
    out: dict[str, Any] = {"token": case.token, "link": link, "sent": False, "why": ""}
    if not number and tunables.PHOTO_SHOW_LINK:             # a Mac call: no SMS; the link is shown on the terminal
        print(f"PHOTO LINK: {link}", flush=True)
        out.update(sent=True, why="shown")
        return out
    to = number or os.environ.get("CALL_ME_NUMBER", "")     # a Mac call has no number: the owner's own phone
    if not to:
        out["why"] = "no number"
        return out
    try:
        (sms or _sms)(to, SMS_TEXT.format(link=link))
        out["sent"] = True
    except Exception as exc:
        out["why"] = f"sms failed: {type(exc).__name__}"
    return out


def _file() -> Any:
    return cases._base_dir() / "next_call.json"


def is_bad(finding: dict[str, Any]) -> bool:
    """The photo could not be read: the reader is unsure, it was the stand-in, it saw nothing, or a helper
    marked it "not clear". `wrong` is the damage SEEN in the photo, so a filled `wrong` is a good read."""
    try:
        sure = float(finding.get("sure", 0.0) or 0.0)
    except (TypeError, ValueError):
        sure = 0.0
    return bool(sure < tunables.PHOTO_SURE_MIN
                or not str(finding.get("shows", "") or "").strip()
                or str(finding.get("wrong", "") or "").startswith("helper:")
                or str(finding.get("by", "") or "").startswith("stand-in"))


def pending(now: Optional[float] = None) -> Optional[dict[str, Any]]:
    """The call-back that waits: {"token", "lang", "say", "bad"}, or None (none, broken, or too old).
    The age is the file's: the case's own `made` is when the link was sent, which may be hours back."""
    path = _file()
    try:
        age = float(now if now is not None else time.time()) - path.stat().st_mtime
        data = json.loads(path.read_text(encoding="utf-8"))
        token = str(data["token"])
    except Exception:
        return None
    if age > tunables.PHOTO_PENDING_S:
        return None
    case = cases.get(token)
    if case is None:
        return None
    return {"token": token, "lang": str(data.get("lang") or case.lang), "say": str(data.get("say", "")),
            "bad": is_bad(case.finding)}


def save_first_call(token: str, call_id: str, told: list[str]) -> bool:
    """Step 2: keep what the call-back needs on the case. A save fault never stops the hangup (False, so it is logged)."""
    try:
        cases.set_first_call(token, call_id, told)
        return True
    except Exception:
        return False


def first_call_blocks(token: str) -> tuple[str, str]:
    """Step 6: (what was said in the first call, what the photo shows), each capped, each its own text.
    The first call is its log, found by the call id saved on the case. "" for a part that is not there; never raises."""
    from pathlib import Path

    from haqdaar.data import log_text

    first = photo = ""
    try:
        case = cases.get(token)
        if case is None:
            return "", ""
        cid = case.call_id
        path = Path(tunables.CALL_LOGS_DIR) / f"{cid}.jsonl"
        if cid and "/" not in cid and ".." not in cid and path.exists():
            first = log_text.log_text(log_text.read_rows(path), tunables.PHOTO_FIRST_CHARS)
        f = case.finding or {}
        if not is_bad(f):
            photo = "; ".join(x for x in (str(f.get("shows", "")).strip(), str(f.get("wrong", "")).strip()) if x)[:tunables.PHOTO_RESULT_CHARS]
    except Exception:
        pass
    return first, photo


def done(token: str, bad: bool) -> None:
    """The call-back was made: the file goes. A bad photo: the case is open again (the same link works)."""
    try:
        _file().unlink()
    except OSError:
        pass
    try:
        cases.drop_photos(token) if bad else cases.mark_called(token)
    except ValueError:
        pass
