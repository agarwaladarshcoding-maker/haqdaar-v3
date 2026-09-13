"""tools/calls.py

`make calls` — last calls on the phone line and any warnings logged against them.
Use it after a test call to check what the provider saw.
"""
from __future__ import annotations
import sys
import urllib.parse

from dotenv import load_dotenv

from haqdaar.audio.telephony import recent_calls

KNOWN = {
    "31921": "stream socket closed without a clean goodbye (seen when the line hangs up or drops)",
}


def main() -> int:
    load_dotenv(".env")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    for c in recent_calls(limit):
        to = (c.get("to") or "")[:-4] + "xxxx"
        print(f"{c['start_time']}  {c['direction']:<13} {c['status']:<10} {c['duration']:>4} s  to {to}  ..{c['sid'][-6:]}")
        for n in c["notices"]:
            text = n.get("message_text") or ""
            msg = urllib.parse.parse_qs(text).get("parserMessage", [text])[0]
            print(f"    warning {n['error_code']}: {msg[:150] or KNOWN.get(n['error_code'], n['more_info'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
