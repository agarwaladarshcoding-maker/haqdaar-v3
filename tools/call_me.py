"""tools/call_me.py

Backup for the smoke call: the line rings YOUR phone instead of you dialing in.
    python -m tools.call_me              # rings CALL_ME_NUMBER from .env
    python -m tools.call_me +91XXXXXXXXXX
Needs `make run` (it brings up the tunnel).
"""
from __future__ import annotations
import os
import sys
import urllib.error

from dotenv import load_dotenv

from haqdaar.audio.telephony import place_call


def main() -> int:
    load_dotenv()
    to = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CALL_ME_NUMBER", "")
    domain = os.environ.get("NGROK_DOMAIN", "")
    if not to or not domain:
        print("need a number (arg or CALL_ME_NUMBER) and NGROK_DOMAIN in .env")
        return 1
    try:
        call_sid = place_call(to, f"https://{domain}/answer")
    except urllib.error.HTTPError as e:
        print(f"call refused: HTTP {e.code} {e.read().decode(errors='replace')}")
        return 1
    print(f"ringing {to[:-4]}xxxx  call {call_sid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
