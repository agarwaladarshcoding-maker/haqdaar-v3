"""haqdaar/photo/back_msg.py

The call-back that never reached the caller (not picked up, rejected, dropped): the answer goes by SMS
instead, as text and as a link to a sound file made with the same voice. `send` is the one door; it
sends once per case. The text is what the call-back would have said (same model step, same "usable"
rule, same translation); an in-call call-back does not use this module. The number is only ever
used for the SMS: never logged, never printed, never returned.
Also here: the demo's 1 / 2 / 3 ask (PHOTO_BACK_ASK), shared by tools/mac_call.py and tools/photo_back.py.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from haqdaar.contracts import tunables
from haqdaar.engine.talk import BACK_SAY_CHARS, _HINDI_DIGITS, _call, _sentences
from haqdaar.photo import cases, in_call
from haqdaar.prompts import talk as prompt

SMS_PREFIX = {"hi": "हकदार: ", "mr": "हकदार: ", "gu": "હકદાર: ", "ta": "ஹக்தார்: "}   # "Haqdaar: " for the rest
SOUND_WORD = {"en": "Listen", "hi": "सुनें", "mr": "ऐका", "gu": "સાંભળો", "ta": "கேளுங்கள்"}
_LOCK = threading.Lock()        # a status call and the end of the call can both ask: the second finds the marker


def _dir(name: str) -> Path:
    return cases._base_dir() / name


def _model() -> Any:
    from haqdaar.model.router import Model

    return Model()


def _translate(sent: str, lang: str) -> str:
    """One sentence in the case's language; the same rule as the talk's `_back_sentence`."""
    if not sent.isascii():
        return sent
    from haqdaar.model import middle

    try:
        return " ".join(o.text for o in middle.reply_in(sent, lang)) or sent
    except Exception:
        return sent


def answer_text(token: str, model: Any = None, translate: Optional[Callable[[str, str], str]] = None) -> tuple[str, str]:
    """(text, lang): what the call-back would have said for this case. ("", "") when there is no such case."""
    case = cases.get(token)
    if case is None:
        return "", ""
    lang = case.lang
    if in_call.is_bad(case.finding):
        return prompt.PHOTO["bad"].get(lang, prompt.PHOTO["bad"]["en"]), lang
    text = case.say                                     # the desk's text is English
    first, photo = in_call.first_call_blocks(token) if tunables.PHOTO_FIRST_CALL else ("", "")
    if "CALLER: " in first and photo:
        try:
            data = _call(model if model is not None else _model(), prompt.back_opening(first, photo, case.say))
        except Exception:
            data = None
        said = str((data or {}).get("say") or "").strip().translate(_HINDI_DIGITS)
        if said and len(said) <= BACK_SAY_CHARS and said.isascii():
            text = said
    if lang != "en" and tunables.PHOTO_BACK_TRANSLATE:
        tr = translate or _translate
        said = []
        for s in _sentences(text):
            t = tr(s, lang)
            said.append(tr(s, lang) if t.isascii() else t)      # still English: the translator failed, one more try
        text = " ".join(said) or text
    return text, lang


def make_sound(token: str, text: str, lang: str, tts: Any = None) -> str:
    """Render `text` to PHOTO_DIR/sound/<token>.wav; give its link, or "" when the voice failed (the text still goes)."""
    try:
        from haqdaar.audio import render

        wav = render.ulaw_to_wav((tts or render.SarvamTTS()).speak(text, lang))
        cases._write_bytes_atomic(_dir("sound") / f"{token}.wav", wav)
    except Exception:
        return ""
    base = os.environ.get("PHOTO_SOUND_URL") or os.environ.get("PHOTO_BASE_URL", "http://127.0.0.1:8002")   # the demo's own tunnel first
    return f"{base.rstrip('/')}/s/{token}.wav"


def message(token: str) -> Optional[dict[str, Any]]:
    """The message that went for a case ({"token", "lang", "text", "link", "why", "made"}), or None."""
    try:
        return json.loads((_dir("sent") / f"{token}.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def send(token: str, why: str, sms: Optional[Callable[[str, str], Any]] = None, model: Any = None,
         translate: Optional[Callable[[str, str], str]] = None, tts: Any = None, show: Optional[bool] = None,
         out: Callable[[str], Any] = lambda line: print(line, flush=True)) -> dict[str, Any]:
    """Send the case's answer by SMS, once. {"token", "sent", "why"}; never raises. A sent (or shown) message
    clears the waiting call-back (`in_call.done`); one that could not go leaves it for the next call.
    `show` (default PHOTO_SHOW_LINK): with no number the message is printed, as send_link does for a Mac call."""
    res: dict[str, Any] = {"token": token, "sent": False, "why": ""}
    try:
        with _LOCK:
            case = cases.get(token)
            if case is None:
                res["why"] = "no case"
            elif (_dir("sent") / f"{token}.json").exists():
                res["why"] = "already sent"
            else:
                _send(case, why, res, sms, model, translate, tts, tunables.PHOTO_SHOW_LINK if show is None else show, out)
    except Exception as exc:
        res["why"] = f"failed: {type(exc).__name__}"
    return res


def _send(case: cases.Case, why: str, res: dict[str, Any], sms: Any, model: Any, translate: Any, tts: Any,
          show: bool, out: Callable[[str], Any]) -> None:
    to = case.number
    if not to and not show:
        to = os.environ.get("CALL_ME_NUMBER", "")       # a Mac call has no number: the owner's own phone
    if not to and not show:
        res["why"] = "no number"
        return
    text, lang = answer_text(case.token, model, translate)
    link = make_sound(case.token, text, lang, tts)
    plain = body = SMS_PREFIX.get(lang, "Haqdaar: ") + text
    if link:
        body += f" {SOUND_WORD.get(lang, SOUND_WORD['en'])}: {link}"
    if not case.number and show:
        out(f"PHOTO MESSAGE: {' '.join(body.split())}")
        phone = os.environ.get("CALL_ME_NUMBER", "") if tunables.PHOTO_BACK_ASK else ""
        if phone:                                       # the demo: the owner's own phone gets it too
            local = "//127.0.0.1" in link or "//localhost" in link      # a phone can not open this Mac's own address
            try:
                (sms or in_call._sms)(phone, plain if local else body)
                out("PHOTO MESSAGE: sent to your phone too" + (" (text only: the sound link has no public address)" if local and link else ""))
            except Exception as exc:
                out(f"PHOTO MESSAGE: the SMS to your phone did not go ({type(exc).__name__})")
    else:
        try:
            (sms or in_call._sms)(to, body)
        except Exception as exc:
            res["why"] = f"sms failed: {type(exc).__name__}"
            return
    cases._write_json_atomic(_dir("sent") / f"{case.token}.json",
                             {"token": case.token, "lang": lang, "text": text, "link": link, "why": why, "made": time.time()})
    res.update(sent=True, why=why)
    in_call.done(case.token, in_call.is_bad(case.finding))


def back_token() -> str:
    """The token of the call-back that waits now, "" for none. Taken when a call starts."""
    try:
        back = in_call.pending() if tunables.PHOTO_IN_CALL else None
    except Exception:
        back = None
    return str(back["token"]) if back else ""


def catch_drop(token: str) -> Optional[threading.Thread]:
    """A call that began as the call-back of `token` has ended. The file is still there: the answer was not
    said in full (the caller hung up, or the line broke), so it goes by SMS. In a thread: it calls a model and a voice."""
    if not token or (in_call.pending() or {}).get("token") != token:
        return None
    thread = threading.Thread(target=send, args=(token, "dropped"), daemon=True)
    thread.start()
    return thread


def ask_case(read: Callable[[], str] = input, say: Callable[[str], Any] = print) -> int:
    """Demo (PHOTO_BACK_ASK): which case to play. 1 picked up, 2 not picked up, 3 picked up but the call drops.
    Anything else is asked again; the end of input or Ctrl+C is 1."""
    say("The answer is ready. Which case?  1 = picked up   2 = not picked up   3 = picked up, then the call drops")
    while True:
        try:
            got = str(read()).strip()
        except (EOFError, KeyboardInterrupt):
            return 1
        if got in ("1", "2", "3"):
            return int(got)
        say("type 1, 2 or 3")


def demo_choice(token: str, choice: int, show: Optional[bool] = None) -> bool:
    """Carry out the case picked by `ask_case`. True: ring the call-back now (1, or 3 with the drop flag set).
    False: no ring (2: the message goes straight away)."""
    if choice == 2:
        send(token, "not picked (demo)", show=show)
        return False
    if choice == 3:
        in_call.set_drop(token)
    return True
