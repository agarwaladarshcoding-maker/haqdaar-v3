"""tools/photo_back.py  (Phase 4, step 5)

The line calls the caller back by itself. Watches PHOTO_DIR/next_call.json (written by the photo desk
when a photo is read); for each new file it takes the number from the case, waits until no call is live,
then rings it with place_call. One call per file. A Mac call (no number) or no PHOTO_BACK_URL: it only says
"answer is ready" and rings the terminal bell. The number is never printed in full.

    make photo-back            watch
    python -m tools.photo_back --once [--dry]
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

from haqdaar.contracts import tunables
from haqdaar.photo import cases

OLD_S = 30 * 60        # a file older than this is skipped (the call side skips it too)
SPACE_S = 10 * 60      # one caller at a time: a second call waits until the last one placed is this old
RETRY_S = 30


def _live(url: str) -> bool:
    """Is a call live on the call server? Ask its /live. Not reachable: say no (the call will fail by itself)."""
    p = urllib.parse.urlsplit(url)
    try:
        with urllib.request.urlopen(f"{p.scheme}://{p.netloc}/live", timeout=2) as r:
            return bool(json.loads(r.read()).get("active"))
    except Exception:
        return False


def _place(number: str, url: str, status_url: str = "") -> str:
    from haqdaar.audio.telephony import twilio
    return twilio.place_call(number, url, status_url=status_url)


def _send(token: str, why: str) -> Any:
    from haqdaar.photo import back_msg
    return back_msg.send(token, why)


def _ask() -> int:
    from haqdaar.photo import back_msg
    return back_msg.ask_case()


def _demo(token: str, choice: int) -> bool:
    from haqdaar.photo import back_msg
    return back_msg.demo_choice(token, choice)


class PhotoBack:
    def __init__(self, dry: bool = False, now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
                 place: Callable[[str, str], str] = _place, live: Callable[[str], bool] = _live,
                 out: Callable[[str], None] = print, bell: Callable[[], None] = lambda: sys.stdout.write("\a"),
                 send: Callable[[str, str], Any] = _send, ask: Callable[[], int] = _ask,
                 tty: Callable[[], bool] = lambda: sys.stdin.isatty(), demo: Callable[[str, int], bool] = _demo):
        self.dry, self.now, self.sleep, self.place, self.live, self.out, self.bell = dry, now, sleep, place, live, out, bell
        self.send, self.ask, self.tty, self.demo = send, ask, tty, demo
        self.seen: set[tuple[str, float]] = set()
        self.last_placed = 0.0

    def _say(self, text: str) -> None:
        self.out(f"{time.strftime('%H:%M:%S', time.localtime(self.now()))} {text}")

    def look(self) -> None:
        """One look at next_call.json."""
        path = cases._base_dir() / "next_call.json"
        try:
            age = self.now() - path.stat().st_mtime
            data = json.loads(path.read_text(encoding="utf-8"))
            token, made = str(data["token"]), float(data["made"])
        except Exception:
            return                                   # no file, or a broken one: skipped, the loop goes on
        if (token, made) in self.seen:
            return
        self.seen.add((token, made))                 # one call per file, even when the call fails
        if age > OLD_S:
            self._say(f"case {token}: the answer is older than 30 minutes, skipped")
            return
        case = cases.get(token)
        number = case.number if case else ""         # kept in memory only
        url = os.getenv("PHOTO_BACK_URL", "").strip()
        if not number or not url:
            self._say(f"answer is ready for case {token}: run  make mac-call  to hear it")
            self.bell()
            return
        tail = number[-2:]
        if self.dry:
            self._say(f"(dry) would ring ***{tail} for case {token}")
            return
        if tunables.PHOTO_BACK_ASK:                  # demo: which case to play
            if not self.tty():
                self._say("PHOTO_BACK_ASK is on but there is no terminal: playing case 1 (picked up)")
            elif not self.demo(token, self.ask()):
                return
        self.sleep(float(os.getenv("PHOTO_BACK_WAIT_S", "20")))     # a caller still on the line can hang up
        while self.last_placed and self.now() - self.last_placed < SPACE_S:
            self.sleep(2)
        while self.live(url):
            self.sleep(2)
        for attempt in (1, 2):
            try:
                sid = self._ring(number, url, token)
                self.last_placed = self.now()
                self._say(f"case {token} ***{tail} call {sid}")
                return
            except Exception as exc:
                self._say(f"case {token} ***{tail}: the call failed ({type(exc).__name__})" + (", trying once more" if attempt == 1 else ", giving up"))
                if attempt == 1:
                    self.sleep(RETRY_S)
        self.send(token, "ring failed")              # the call never started: the answer goes by SMS

    def _ring(self, number: str, url: str, token: str) -> str:
        """Place the call; the line tells /back-status how it ended. A `place` that takes two arguments gets two."""
        if len(inspect.signature(self.place).parameters) < 3:
            return self.place(number, url)
        p = urllib.parse.urlsplit(url)
        return self.place(number, url, f"{p.scheme}://{p.netloc}/back-status?token={urllib.parse.quote(token, safe='')}")


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Ring the caller back when a photo answer is ready.")
    ap.add_argument("--once", action="store_true", help="look one time and leave")
    ap.add_argument("--dry", action="store_true", help="do everything but place the call")
    args = ap.parse_args(argv)
    pb = PhotoBack(dry=args.dry)
    try:
        while True:
            pb.look()
            if args.once:
                return
            time.sleep(2)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
