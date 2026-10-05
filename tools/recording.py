"""tools/recording.py

`make recording` (or `make recording ID=CA...`): fetch the line's own two-sided sound record of
a call placed with CALL_RECORD=true, save it under logs/recordings/, and print where each side
has holes. Our side of the record is what the line sent on to the phone: holes there are ours
(the app or this computer's network); a clean record with a broken sound on the phone means the
break is between the line and the phone.
"""
from __future__ import annotations

import audioop
import io
import sys
import wave
from pathlib import Path

from dotenv import load_dotenv

from haqdaar.audio.telephony import call_recording

QUIET = 30        # a 20 ms piece under this level counts as no sound
HOLE_MS = (60, 1500)   # a hole: no sound this long, with sound right before and right after


def holes(pcm: bytes, rate: int) -> list[tuple[float, int]]:
    """(second, ms) of every short stretch of no sound that has sound on both sides."""
    step = rate // 50 * 2
    level = [audioop.rms(pcm[i:i + step], 2) for i in range(0, len(pcm) - step + 1, step)]
    out, i = [], 0
    while i < len(level):
        if level[i] >= QUIET:
            i += 1
            continue
        j = i
        while j < len(level) and level[j] < QUIET:
            j += 1
        ms = (j - i) * 20
        if i > 0 and j < len(level) and HOLE_MS[0] <= ms <= HOLE_MS[1]:
            out.append((i * 0.02, ms))
        i = j
    return out


def main() -> int:
    load_dotenv(".env")
    call_sid, body = call_recording(sys.argv[1] if len(sys.argv) > 1 else "")
    if not body:
        print("no sound record for this call. Place the call with CALL_RECORD=true; the record is ready about a minute after the call ends.")
        return 1
    out = Path("logs/recordings")
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{call_sid}.wav"
    path.write_bytes(body)
    with wave.open(io.BytesIO(body)) as w:
        rate, sides, frames = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
    print(f"saved {path} ({len(frames) / rate / 2 / sides:.0f} s, {sides} side(s)). Listen to it: open {path}")
    for n in range(sides):
        pcm = audioop.tomono(frames, 2, 1 - n, n) if sides == 2 else frames
        found = holes(pcm, rate)
        long_ones = [(t, ms) for t, ms in found if ms >= 200]
        print(f"side {n + 1}: {len(found)} short stretches of no sound, {len(long_ones)} of them 0.2 s or more")
        print("   " + ", ".join(f"{t:.1f}s ({ms} ms)" for t, ms in long_ones[:40]))
    print("A voice pauses by itself between words and sentences, so a few of these are normal. Which side is ours: the one with the greeting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
