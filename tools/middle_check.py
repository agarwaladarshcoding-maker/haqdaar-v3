"""tools/middle_check.py — real-service check for step 1.4a. Owner runs this.

Reads a file of English replies, sends each through the real Sarvam service
for hi, mr, gu, ta, and prints per sentence: passed or failed, the
milliseconds, the output.

Owner command:
  YES=1 .venv/bin/python tools/middle_check.py fixtures/middle_replies.txt
"""
import os
import sys

print("this spends Sarvam credits")

if os.environ.get("YES") != "1":
    print("set YES=1 to run this check")
    sys.exit(0)

from haqdaar.model.middle import reply_in

path = sys.argv[1] if len(sys.argv) > 1 else "fixtures/middle_replies.txt"
with open(path, encoding="utf-8") as f:
    replies = [line.strip() for line in f if line.strip()]

for i, reply in enumerate(replies, 1):
    print("--- reply %d: %s" % (i, reply))
    for lang in ("hi", "mr", "gu", "ta"):
        for j, out in enumerate(reply_in(reply, lang), 1):
            mark = "passed" if out.ok else "failed"
            print("[%s s%d] %s %dms: %s" % (lang, j, mark, out.ms, out.text))
