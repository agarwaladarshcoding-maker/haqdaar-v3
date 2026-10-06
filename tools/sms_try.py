"""tools/sms_try.py: try the photo-by-SMS door on this laptop with real photos. It plays the phone.

    SMS_DOOR=true .venv/bin/python -m tools.photo_desk          # one terminal: the door (8002) and the desk (8003)
    .venv/bin/python -m tools.sms_try photo1.jpg [photo2.jpg ...]   # another: send the photos, show what came out

Makes a case on the desk, cuts each photo into packets exactly as the phone would (up to 5 photos), posts them to /sms,
waits for the reading, and prints what the model said and whether it went to the caller or waits for a person.
With a Muse key the reader is Muse (a few paise a read; the daily cap guard applies).
"""
import json
import os
import sys
import time
import urllib.request

from haqdaar.keypad_sms import pack

DOOR = "http://127.0.0.1:" + os.getenv("PHOTO_PORT", "8002")
DESK = "http://127.0.0.1:" + os.getenv("DESK_PORT", "8003")


def call(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main(paths):
    case = call(DESK + "/new", b"{}")
    token = case["token"]
    cuts = pack.cut_case(paths, "417")
    print(f"case {token[:3]}***; {len(cuts)} photo(s)")
    for c in cuts:
        print(f"  photo {c['place']}: {c['w']}x{c['h']}, {c['size']} bytes, {c['parts']} SMS parts, {c['n']} packets")
        for pk in c["packets"]:
            r = call(DOOR + "/sms", json.dumps({"text": pk, "sender": "+910000000000"}).encode())
            if not r.get("ok"):
                print("   door said:", r)
    for _ in range(90):                      # the idle time (3 min) is the longest wait; a whole case reads at once
        row = next((x for x in _cases() if x["token"] == token), None)
        if row and row["state"] in ("read", "approved", "called"):
            print("state:", row["state"])
            print("saw:  ", row["shows"])
            print("wrong:", row["wrong"])
            print("say:  ", row["say"])
            print("note: ", row["note"] or "(the model answered; nothing waits for a person)")
            return
        time.sleep(2)
    print("no answer yet: state", row and row["state"])


def _cases():
    got = call(DESK + "/cases")
    return got["cases"] if isinstance(got, dict) else got


if __name__ == "__main__":
    main(sys.argv[1:])
