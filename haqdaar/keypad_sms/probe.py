"""M7: find, for each phone model, if its JPEG header can be left out and how many parts one long SMS may have.

Packets of the probe (plain GSM letters, like the photo packets):
  Q:<dev>:H:<i>/<n>:<payload>   the header the phone's own JPEG maker made for the test picture, in pieces
  Q:<dev>:L:<parts>:<payload>   one packet that is exactly <parts> parts long, filled with a fixed pattern
  Q:<dev>:E:                    the end of the probe
The answer is ONE short text: S:<hdr>:<parts>  (hdr 1 = send the header too, parts = the packet size to use).
The safe default is today's way: header on, 5 parts, one packet at a time. A phone nobody tested, a lost answer,
or a failed probe only costs picture size; it never stops a send. The profile holds one line for each phone code:
no picture, no phone number.
"""
import base64
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

from haqdaar.contracts import tunables

from . import pack

LADDER = (1, 3, 5, 10, 15, 20)       # parts, the sizes the probe tries
DEFAULT = {"hdr": 1, "packet_parts": 5}
MAX_PACKET_PARTS = 10                # a packet is never asked to be longer, however much the phone allows
TEST_SIZE = (96, 72)                 # the test picture the phone's JPEG maker is asked to make
FAILS_TO_FLIP = 2                    # real photos (from different senders) that fail the picture lock with the header left out
MAX_SESSIONS = 64                    # probes held at once
MAX_PIECE = 5 * pack.PART_LEN        # letters in one header piece
DEV_RE = re.compile(r"\A(--|[A-Za-z0-9]{2})\Z")


def profile_path() -> Path:
    return Path(os.environ.get("PHONE_PROFILE_FILE", "data_cache/phone_profile.json"))


def _load(path: Optional[Path] = None) -> dict:
    try:
        return json.loads((path or profile_path()).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict, path: Optional[Path] = None) -> None:
    path = path or profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def settings_text(hdr: int, parts: int) -> str:
    return "S:%d:%d" % (hdr, parts)


def settings_for(dev: str, path: Optional[Path] = None) -> dict:
    """What the cut should use for this phone code: {"hdr", "packet_parts"}. The safe default when it is not known."""
    row = _load(path).get(str(dev))
    if not row:
        return dict(DEFAULT)
    hdr = 0 if row.get("header_ok") is True else 1
    parts = row.get("max_parts")
    parts = min(int(parts), MAX_PACKET_PARTS) if parts else DEFAULT["packet_parts"]
    return {"hdr": hdr, "packet_parts": max(1, parts)}


def cut_for_dev(images, case, dev="--", path: Optional[Path] = None, **kw):
    """The cut of M1 with the settings of this phone (laptop and tests; the phone app does the same)."""
    st = settings_for(dev, path)
    return pack.cut_case(images, case, dev=dev, hdr=st["hdr"], packet_parts=st["packet_parts"], **kw)


def expected_header() -> bytes:
    return pack.make_header(TEST_SIZE[0], TEST_SIZE[1], int(tunables.SMS_JPEG_Q))


def _filler(parts: int, head: str) -> str:
    n = parts * pack.PART_LEN - len(head)
    return (pack.B64 * (n // len(pack.B64) + 1))[:n]


def probe_packets(dev: str, header: bytes, ladder=LADDER, piece_parts: int = 5) -> list:
    """What a phone sends for a probe. `header` is what its own JPEG maker made for the test picture."""
    out = []
    text = base64.b64encode(header).decode("ascii")
    room = piece_parts * pack.PART_LEN - len("Q:%s:H:99/99:" % dev)
    pieces = [text[i:i + room] for i in range(0, len(text), room)] or [""]
    for i, piece in enumerate(pieces, 1):
        out.append("Q:%s:H:%d/%d:%s" % (dev, i, len(pieces), piece))
    for parts in ladder:
        head = "Q:%s:L:%d:" % (dev, parts)
        out.append(head + _filler(parts, head))
    out.append("Q:%s:E:" % dev)
    return out


class Probe:
    def __init__(self, path: Optional[Path] = None):
        self.path = path
        self.sessions = {}     # (sender, dev) -> {"head": {i: text}, "n": int, "rungs": {parts: time}}
        self._fail_senders = {}   # dev -> senders already counted

    def add(self, sender: str, text: str, now: Optional[float] = None):
        """(status, reply): status bad | stored | done; reply is the settings text when the probe is done."""
        now = time.monotonic() if now is None else now
        bits = text.split(":")
        if len(bits) < 4 or bits[0] != "Q" or not DEV_RE.match(bits[1]) or bits[2] not in ("H", "L", "E"):
            return "bad", None
        dev, kind = bits[1], bits[2]
        if kind == "E":
            return "done", self.finish(sender, dev)
        if len(bits) != 5:
            return "bad", None
        skey = (str(sender), dev)
        sess = self.sessions.get(skey) or {"head": {}, "n": 0, "rungs": {}}   # kept only once the packet is good
        if kind == "H":
            try:
                i, n = (int(x) for x in bits[3].split("/"))
            except ValueError:
                return "bad", None
            if (not (1 <= i <= n <= 16) or not bits[4] or len(bits[4]) > MAX_PIECE
                    or any(c not in pack.B64 + "=" for c in bits[4])):
                return "bad", None
            if sess["n"] and sess["n"] != n:
                return "bad", None
            sess["n"] = n
            sess["head"][i] = bits[4]
            self._keep(skey, sess)
            return "stored", None
        try:
            parts = int(bits[3])
        except ValueError:
            return "bad", None
        head = "Q:%s:L:%d:" % (dev, parts)
        if parts not in LADDER or text != head + _filler(parts, head):
            return "bad", None                      # the wrong length or letters: this size did not arrive whole
        sess["rungs"][parts] = now
        self._keep(skey, sess)
        return "stored", None

    def _keep(self, skey, sess):
        if skey not in self.sessions and len(self.sessions) >= MAX_SESSIONS:
            del self.sessions[next(iter(self.sessions))]      # the oldest probe goes
        self.sessions[skey] = sess

    def finish(self, sender: str, dev: str) -> str:
        """Read what came, keep the line for this phone code, give the settings text. Never raises."""
        sess = self.sessions.pop((str(sender), dev), None) or {"head": {}, "n": 0, "rungs": {}}
        header_ok = None
        if sess["n"] and len(sess["head"]) == sess["n"]:
            try:
                got = base64.b64decode("".join(sess["head"][i] for i in range(1, sess["n"] + 1)), validate=True)
                header_ok = got == expected_header()
            except Exception:
                header_ok = False
        rungs = sess["rungs"]
        times = [rungs[k] for k in sorted(rungs)]
        gaps = sorted(b - a for a, b in zip(times, times[1:]))
        secs = round(gaps[len(gaps) // 2], 2) if gaps else None
        try:
            data = _load(self.path)
            row = dict(data.get(dev) or {})
            if header_ok is not None:
                row["header_ok"] = header_ok
                row["fails"] = 0
            if rungs:
                row["max_parts"] = max(rungs)
            if secs is not None:
                row["seconds_a_packet"] = secs
            if dev != "--" and (header_ok is not None or rungs):
                data[dev] = row
                _save(data, self.path)
            st = {"hdr": 0 if row.get("header_ok") is True else 1,
                  "packet_parts": min(int(row["max_parts"]), MAX_PACKET_PARTS) if row.get("max_parts") else DEFAULT["packet_parts"]}
        except Exception:
            st = dict(DEFAULT)
        return settings_text(st["hdr"], st["packet_parts"])

    def note_failure(self, dev: str, sender: Optional[str] = None) -> Optional[str]:
        """A real photo failed the picture lock with the header left out. After FAILS_TO_FLIP of them for the same
        phone code the header goes back on; the settings text is returned once, then None. With a sender, each sender
        counts once, so one sender can not turn the header on for a whole phone model."""
        if dev == "--" or not DEV_RE.match(dev):
            return None
        if sender is not None:
            seen = self._fail_senders.setdefault(dev, set())
            if str(sender) in seen:
                return None
            if len(seen) < 256:
                seen.add(str(sender))
        try:
            data = _load(self.path)
            row = dict(data.get(dev) or {})
            if row.get("header_ok") is False:
                return None
            row["fails"] = int(row.get("fails", 0)) + 1
            flip = row["fails"] >= FAILS_TO_FLIP
            if flip:
                row["header_ok"] = False
            data[dev] = row
            _save(data, self.path)
            if flip:
                return settings_text(1, settings_for(dev, self.path)["packet_parts"])
        except Exception:
            pass
        return None
