"""M2: join P: packets back into photos. Four locks. Memory only. Plain words.

One caller at a time: packets are grouped by (sender, case field). Inside a group each photo is joined by
itself, so one bad photo never takes the others down. The four locks, all on the server:
  1. same case and same photo stamp; a re-sent photo has a new stamp, so a late packet of the first try can
     never mix into the second; the first try to come out whole for a place wins
  2. put in the order of k, never of arrival; a double is ignored; a double with other bytes, or packets that
     disagree on the photo's facts, drop that photo
  3. the length is the stated length and the 6 letter check of the whole photo matches
  4. with the header put back, the whole picture decodes to the stated size (a cut-off picture fails)
A failed photo is dropped whole and nothing half-joined is ever read.
"""

import base64
import binascii
import io
import math
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from PIL import Image

from haqdaar.contracts import tunables

from . import pack, share

MAX_PACKETS = 64   # one photo is never more than this many packets
MAX_GROUPS = 16    # groups held at once; the oldest goes first
MAX_DELIVERED = 256   # photos remembered after they were handed over, so a late double is not joined again
MAX_RETIRED = 200     # stamps one group may remember


@lru_cache(maxsize=64)
def _header(w, h, q):
    return pack.make_header(w, h, q)


@dataclass
class _Photo:
    facts: tuple
    chunks: dict = field(default_factory=dict)
    check: Optional[str] = None
    parts: int = 0


@dataclass
class _Group:
    sender: str
    case: str
    sent: int
    born: float
    last: float
    owner: str = ""
    sessions: dict = field(default_factory=dict)   # (place, stamp) -> _Photo
    whole: dict = field(default_factory=dict)      # place -> JPEG bytes
    stamps: dict = field(default_factory=dict)     # place -> the stamp of the whole photo
    failed: set = field(default_factory=set)       # places with no photo left
    retired: set = field(default_factory=set)      # (place, stamp) that must be ignored from now on


@dataclass
class Result:
    status: str          # stored dup photo dropped ignored bad
    reply: str
    key: Optional[tuple] = None
    why: str = ""
    lock: int = 0        # for a dropped photo: 3 = length or whole-photo check, 4 = the picture did not open
    dev: str = "--"
    hdr: int = 1


@dataclass
class Case:
    key: tuple
    owner: str
    sent: int
    photos: list         # [(place, JPEG bytes)] in the caller's order
    failed: int          # sent photos that did not come whole


def _facts(p):
    return (p["n"], p["step"], p["size"], p["hdr"], p["dev"], p["sent"])


def _jpeg_of(p, body):
    """Locks 3 and 4: the whole photo bytes -> (the JPEG file, 0), or (None, the lock that failed)."""
    if len(body) != p["size"] or pack.check_of(body) != p["check"]:
        return None, 3
    w, h = pack.SIZE_LADDER[p["step"]]
    jpeg = body if p["hdr"] else _header(w, h, int(tunables.SMS_JPEG_Q)) + body
    if not jpeg.endswith(b"\xff\xd9"):
        return None, 4
    try:
        im = Image.open(io.BytesIO(jpeg))
        im.load()
        if im.format != "JPEG" or im.size != (w, h):
            return None, 4
    except Exception:
        return None, 4
    return jpeg, 0


class PhotoJoin:
    def __init__(self):
        self.groups = {}
        self.delivered = {}    # (sender, case, place, stamp) -> time handed over

    def sweep(self, now=None):
        """Drop groups older than the case limit. Returns how many went."""
        now = time.monotonic() if now is None else now
        old = [k for k, g in self.groups.items() if now - g.born > tunables.SMS_CASE_S]
        for k in old:
            del self.groups[k]
        for k in [k for k, t in self.delivered.items() if now - t > tunables.SMS_CASE_S]:
            del self.delivered[k]
        return len(old)

    def _kill(self, g, place, stamp, retire=True):
        """Drop one try. retire: its stamp is ignored from now on (a bad try); not for a whole-photo failure, so the
        same photo sent again can still come through."""
        g.sessions.pop((place, stamp), None)
        if retire and len(g.retired) < MAX_RETIRED:
            g.retired.add((place, stamp))
        if place not in g.whole and not any(pl == place for pl, _ in g.sessions):
            g.failed.add(place)

    def add(self, sender, text, owner="", now=None):
        now = time.monotonic() if now is None else now
        self.sweep(now)
        p = pack.parse_packet(text)
        if p is None:
            return Result("bad", "ERR BAD")
        if (p["n"] > MAX_PACKETS or p["sent"] > share.max_photos() or p["place"] > p["sent"]
                or p["step"] >= len(pack.SIZE_LADDER)):
            return Result("bad", "ERR RANGE")
        key = (str(sender), p["case"])
        if (key[0], key[1], p["place"], p["stamp"]) in self.delivered:   # a late double of a photo already handed over
            return Result("ignored", "OK LATE", key)
        g = self.groups.get(key)
        if g is None:
            if len(self.groups) >= MAX_GROUPS:
                del self.groups[min(self.groups, key=lambda k: self.groups[k].born)]
            g = self.groups[key] = _Group(str(sender), p["case"], p["sent"], now, now, owner)
        g.last = now
        place, stamp = p["place"], p["stamp"]
        sk = (place, stamp)
        if g.sent != p["sent"]:
            return Result("dropped", "ERR FACTS", key, "sent differs")
        if place in g.whole:
            return Result("ignored", "OK LATE", key)
        if sk in g.retired:                          # a bad try: its photo is lost, the route must not call this ok
            return Result("ignored", "OK LATE", key, "retired")
        ph = g.sessions.get(sk)
        if ph is None:
            if len(g.sessions) >= 3 * g.sent + 2:        # more tries than a case can have: refuse, do not grow
                return Result("bad", "ERR BUSY", key)
            ph = g.sessions[sk] = _Photo(_facts(p))
            g.failed.discard(place)
        elif ph.facts != _facts(p):
            self._kill(g, place, stamp)
            return Result("dropped", "ERR FACTS", key, "facts differ")
        old = ph.chunks.get(p["k"])
        if old is not None:
            if old == p["payload"] and (p["check"] is None or p["check"] == ph.check):
                return Result("dup", "OK DUP", key)
            self._kill(g, place, stamp)
            return Result("dropped", "ERR CONFLICT", key, "same k, other bytes")
        ph.parts += math.ceil(len(text) / pack.PART_LEN)
        if ph.parts > share.share_parts(g.sent):
            self._kill(g, place, stamp)
            return Result("dropped", "ERR TOO_BIG", key, "more parts than the share")
        ph.chunks[p["k"]] = p["payload"]
        if p["check"] is not None:
            ph.check = p["check"]
        if len(ph.chunks) < p["n"] or ph.check is None:
            return Result("stored", "OK %d/%d" % (p["k"], p["n"]), key)
        text_all = "".join(ph.chunks[k] for k in range(1, p["n"] + 1))
        try:
            body = base64.b64decode(text_all, validate=True)
        except (binascii.Error, ValueError):
            body = b""
        jpeg, lock = _jpeg_of({**p, "check": ph.check}, body) if body else (None, 3)
        if jpeg is None:
            self._kill(g, place, stamp, retire=False)
            return Result("dropped", "ERR JOIN", key, "a lock failed", lock, p["dev"], p["hdr"])
        g.whole[place] = jpeg
        g.stamps[place] = stamp
        for other in [s for s in g.sessions if s[0] == place]:
            g.sessions.pop(other, None)
            g.retired.add(other)
        g.failed.discard(place)
        return Result("photo", "OK PHOTO %d" % place, key)

    def ready(self, key):
        g = self.groups.get(key)
        return bool(g and all(i in g.whole or i in g.failed for i in range(1, g.sent + 1)))

    def take(self, key, force=False, now=None):
        """The case, when every sent photo is whole or lost (or force: the idle time is up). Removes it."""
        g = self.groups.get(key)
        if g is None or not (force or self.ready(key)):
            return None
        del self.groups[key]
        now = time.monotonic() if now is None else now
        for i in g.whole:
            if len(self.delivered) >= MAX_DELIVERED:
                del self.delivered[min(self.delivered, key=self.delivered.get)]
            self.delivered[(g.sender, g.case, i, g.stamps[i])] = now
        photos = [(i, g.whole[i]) for i in sorted(g.whole)]
        return Case(key, g.owner, g.sent, photos, g.sent - len(photos))
