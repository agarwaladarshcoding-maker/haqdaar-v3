"""tools/sms_shrink.py  (Phase 4, step 4)

Runs real photos through the same shrink steps the keypad app uses and prints the size and the SMS
count of each. The app: draw the photo at the first size of LADDER that makes a JPEG of at most
CHUNK * MAX_SMS bytes; cut it into pieces of CHUNK bytes. Here PIL stands in for the phone's canvas, so
sizes are close, not exact (a phone's JPEG header can be a little bigger).

    .venv/bin/python -m tools.sms_shrink photo1.jpg photo2.jpg ...
"""
from __future__ import annotations

import io
import sys

from PIL import Image

CHUNK = 105          # bytes a piece carries: 140 letters of base64 + "H:ffff:10/10:" + ":cc" = 156, under 160
MAX_SMS = 10
LADDER = [(96, 72, 24), (80, 60, 20), (72, 54, 20), (64, 48, 20), (64, 48, 12), (48, 36, 15), (40, 30, 10)]   # width, height, quality


def shrink(img: Image.Image) -> tuple[bytes, tuple[int, int, int]]:
    for w, h, q in LADDER:
        buf = io.BytesIO()
        img.resize((w, h)).save(buf, "JPEG", quality=q)
        if len(buf.getvalue()) <= CHUNK * MAX_SMS:
            return buf.getvalue(), (w, h, q)
    return buf.getvalue(), (w, h, q)         # nothing fits: the smallest step is sent as it is


def sms_count(n_bytes: int) -> int:
    return -(-n_bytes // CHUNK)


def main(paths: list[str]) -> None:
    print(f"budget {CHUNK * MAX_SMS} bytes = {MAX_SMS} SMS of {CHUNK} bytes")
    for p in paths:
        data, (w, h, q) = shrink(Image.open(p).convert("RGB"))
        print(f"{p.rsplit('/', 1)[-1][:36]:36} -> {w}x{h} q{q}  {len(data):5} bytes  {sms_count(len(data)):2} SMS")


if __name__ == "__main__":
    main(sys.argv[1:])
