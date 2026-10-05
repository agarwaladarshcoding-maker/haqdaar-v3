"""tools/stage_check.py

Run this a few minutes before a demo call: `make stage-check`. It says, in plain lines, whether
each thing the call needs is ready, and what to do when it is not. It places no call. It costs
one two-word Sarvam sentence and one full-size Groq prompt per model (about 2,500 tokens each).

Made on 5 Oct after `make call-me` sat silent in the hackathon hall: the hall's network let out
only the web ports, so the Cloudflare tunnel never connected and the phone never rang.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from haqdaar.contracts import tunables
from tools.tunnel import cloudflare_blocked

PORT = 8000
problems: list[str] = []


def line(ok: bool, what: str, fix: str = "") -> None:
    print(f"  {'ok     ' if ok else 'PROBLEM'}  {what}" + (f"\n           -> {fix}" if fix and not ok else ""), flush=True)
    if not ok:
        problems.append(what)


def http(url: str, headers: dict[str, str], body: dict | None = None, timeout: float = 15) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "haqdaar", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, repr(e)


def main() -> int:
    load_dotenv(".env")
    env = os.environ
    print("settings")
    for name in ("CALL_ME_NUMBER", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "SARVAM_API_KEY", "GROQ_API_KEY", "NGROK_DOMAIN"):
        line(bool(env.get(name)), f"{name} is set", "add it to .env")

    print("this computer")
    with socket.socket() as s:
        busy = s.connect_ex(("127.0.0.1", PORT)) == 0
    line(not busy, f"port {PORT} is free", f"an old server holds it: lsof -nP -iTCP:{PORT} -sTCP:LISTEN, then stop it")
    cache = Path(tempfile.gettempdir()) / "fastembed_cache"
    line(cache.exists(), "the search model is on this computer", "the first start will download 220 MB: start once before the demo")

    print("the network (the way in for the phone company)")
    blocked = cloudflare_blocked()
    try:
        socket.create_connection(("connect.ngrok-agent.com", 443), timeout=5).close()
        ngrok_ok = True
    except OSError:
        ngrok_ok = False
    print(f"  {'note   ' if blocked else 'ok     '}  Cloudflare tunnel (port 7844): {'BLOCKED here' if blocked else 'open'}")
    line(ngrok_ok or not blocked, f"ngrok (port 443): {'open' if ngrok_ok else 'blocked'}"
         + (" -> make call-me will use ngrok by itself" if blocked and ngrok_ok else ""),
         "no tunnel can get out on this network: use a phone hotspot")

    print("the phone company (Twilio)")
    sid, token = env.get("TWILIO_ACCOUNT_SID", ""), env.get("TWILIO_AUTH_TOKEN", "")
    auth = {"Authorization": "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode()}
    code, text = http(f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json", auth)
    status = (json.loads(text).get("status") if code == 200 else "") or ""
    line(code == 200 and status == "active", f"account answers (http {code}, {status or text[:80]})", "check the Twilio keys in .env")
    code, text = http(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json", auth)
    if code == 200:
        bal = json.loads(text)
        line(float(bal.get("balance", 0)) > 1.0, f"balance {bal.get('balance')} {bal.get('currency')}", "top up Twilio")

    print("the voice and the ear (Sarvam)")
    code, text = http("https://api.sarvam.ai/text-to-speech/stream", {"api-subscription-key": env.get("SARVAM_API_KEY", "")},
                      {"text": "ठीक है।", "target_language_code": "hi-IN", "speaker": tunables.TTS_SPEAKERS["hi"],
                       "model": tunables.TTS_MODEL, "pace": 1.0, "speech_sample_rate": 8000, "output_audio_codec": "mulaw"})
    line(code == 200, f"Sarvam makes sound (http {code}{'' if code == 200 else ', ' + text[:120]})",
         "402 = no credit left: top up Sarvam or put a new key in .env")

    print("the model (Groq), in the order the call tries them")
    working = 0
    for model in [m.strip() for m in tunables.TALK_MODELS.split(",") if m.strip()]:
        code, text = http("https://api.groq.com/openai/v1/chat/completions", {"Authorization": f"Bearer {env.get('GROQ_API_KEY', '')}"},
                          {"model": model, "messages": [{"role": "user", "content": "word " * 2500 + "Say ok."}], "max_tokens": 4})
        day = "tokens per day" in text
        print(f"  {'ok     ' if code == 200 else 'note   '}  {model}: " + (
            "answers a full-size prompt" if code == 200 else
            "its DAY of tokens is used up (the call moves to the next model)" if day else f"http {code} {text[:100]}"), flush=True)
        working += code == 200
    line(working > 0, f"{working} model(s) can answer now", "all models are refused: wait, or use another Groq key")

    print()
    if problems:
        print(f"NOT READY: {len(problems)} problem(s): " + "; ".join(problems))
        return 1
    print("READY. Next:  TALK_ONLY=true make call-me")
    return 0


if __name__ == "__main__":
    sys.exit(main())
