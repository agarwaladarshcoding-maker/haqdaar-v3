"""haqdaar/photo/cases.py

The case store for photo submissions (Step 4.1).
One folder per case inside a base folder (default data_cache/photo/,
given by PHOTO_DIR or argument): case.json and photos next to it.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

MAX_PHOTOS = 6
MAX_BYTES = 5 * 1024 * 1024
TTL_SECONDS = 24 * 3600
TOKEN_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
TOKEN_RE = re.compile(r"^[a-z2-9]{10}$")


@dataclass
class Case:
    token: str           # 10 letters and digits, random; the only thing in the link
    lang: str            # "hi", "mr", "en", "gu", "ta"
    number: str          # the caller's phone number, "" when not known (a Mac call)
    made: float          # unix time
    state: str           # "waiting" -> "photo" -> "read" -> "approved" -> "called"
    photos: list[str] = field(default_factory=list)    # file names of the photos, in the order they came
    finding: dict = field(default_factory=dict)        # what reader.read gave, {} until read
    scheme: str = ""     # scheme id picked by the search, "" until set
    say: str = ""        # the text that will be said on the call-back, "" until set


def _base_dir(folder: Path | str | None = None) -> Path:
    if folder is not None:
        return Path(folder)
    env = os.getenv("PHOTO_DIR")
    if env:
        return Path(env)
    return Path("data_cache") / "photo"


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8")
    try:
        json.dump(data, temp_file, ensure_ascii=False, indent=2)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        os.replace(temp_file.name, path)
    except Exception:
        if os.path.exists(temp_file.name):
            try:
                os.remove(temp_file.name)
            except OSError:
                pass
        raise


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False)
    try:
        temp_file.write(data)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        os.replace(temp_file.name, path)
    except Exception:
        if os.path.exists(temp_file.name):
            try:
                os.remove(temp_file.name)
            except OSError:
                pass
        raise


def _save(case: Case, folder: Path | str | None = None) -> None:
    base = _base_dir(folder)
    case_path = base / case.token / "case.json"
    _write_json_atomic(case_path, asdict(case))


def _load_case_dict(d: dict[str, Any]) -> Case:
    return Case(
        token=str(d.get("token", "")),
        lang=str(d.get("lang", "en")),
        number=str(d.get("number", "")),
        made=float(d.get("made", 0.0)),
        state=str(d.get("state", "waiting")),
        photos=list(d.get("photos", [])),
        finding=dict(d.get("finding", {})),
        scheme=str(d.get("scheme", "")),
        say=str(d.get("say", "")),
    )


def new_case(lang: str, number: str = "", folder: Path | str | None = None, now: float | None = None) -> Case:
    base = _base_dir(folder)
    base.mkdir(parents=True, exist_ok=True)
    for _ in range(100):
        t = "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(10))
        if not (base / t).exists():
            token = t
            break
    else:
        raise RuntimeError("could not generate unique token")

    made_time = float(now if now is not None else time.time())
    case = Case(
        token=token,
        lang=lang,
        number=str(number),
        made=made_time,
        state="waiting",
        photos=[],
        finding={},
        scheme="",
        say="",
    )
    _save(case, folder)
    return case


def _get_raw(token: str, folder: Path | str | None = None) -> Case | None:
    if not token or not TOKEN_RE.match(token):
        return None
    base = _base_dir(folder)
    case_path = base / token / "case.json"
    if not case_path.exists():
        return None
    try:
        data = json.loads(case_path.read_text(encoding="utf-8"))
        return _load_case_dict(data)
    except Exception:
        return None


def get(token: str, folder: Path | str | None = None, now: float | None = None) -> Case | None:
    case = _get_raw(token, folder=folder)
    if case is None:
        return None
    current_time = float(now if now is not None else time.time())
    if (current_time - case.made) > TTL_SECONDS:
        return None
    return case


def link(case: Case, base_url: str | None = None) -> str:
    base = base_url or os.getenv("PHOTO_BASE_URL", "http://127.0.0.1:8002")
    b = base.rstrip('/')
    return f"{b}/p/{case.token}"


def number_tail(case: Case) -> str:
    if not case.number:
        return ""
    digits = [c for c in case.number if c.isdigit()]
    if not digits:
        return ""
    return "".join(digits[-4:])


def _image_type(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xff\xd8\xff") or data.startswith(b"\xff\xd8"):
        return "jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return "", ""


def add_photo(token: str, data: bytes, folder: Path | str | None = None, now: float | None = None) -> Case:
    case = _get_raw(token, folder=folder)
    if not token or not TOKEN_RE.match(token):
        raise ValueError("case not found")
    if case is None:
        raise ValueError("case not found")
    if len(data) > MAX_BYTES:
        raise ValueError("the photo is too big")
    ext, _ = _image_type(data)
    if not ext:
        raise ValueError("this is not a photo")
    if len(case.photos) >= MAX_PHOTOS:
        raise ValueError("six photos at most")

    base = _base_dir(folder)
    case_dir = base / token
    case_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{len(case.photos) + 1}.{ext}"
    _write_bytes_atomic(case_dir / filename, data)

    case.photos.append(filename)
    case.state = "photo"
    case.finding = {}
    case.scheme = ""
    case.say = ""
    _save(case, folder)
    return case


def drop_photos(token: str, folder: Path | str | None = None, now: float | None = None) -> Case:
    case = _get_raw(token, folder=folder)
    if not token or not TOKEN_RE.match(token):
        raise ValueError("case not found")
    if case is None:
        raise ValueError("case not found")

    base = _base_dir(folder)
    case_dir = base / token
    for p in case.photos:
        photo_path = case_dir / p
        if photo_path.exists():
            try:
                photo_path.unlink()
            except OSError:
                pass

    case.photos = []
    case.state = "waiting"
    case.finding = {}
    case.scheme = ""
    case.say = ""
    _save(case, folder)
    return case


def photo_bytes(token: str, n: int, folder: Path | str | None = None, now: float | None = None) -> tuple[bytes, str]:
    case = _get_raw(token, folder=folder)
    if not token or not TOKEN_RE.match(token):
        raise ValueError("case not found")
    if case is None:
        raise ValueError("case not found")
    if n < 0 or n >= len(case.photos):
        raise IndexError("photo index out of range")

    base = _base_dir(folder)
    filename = case.photos[n]
    path = base / token / filename
    if not path.exists():
        raise FileNotFoundError("photo file missing")
    data = path.read_bytes()
    _, mime = _image_type(data)
    if not mime:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in ("jpg", "jpeg"):
            mime = "image/jpeg"
        elif ext == "png":
            mime = "image/png"
        elif ext == "webp":
            mime = "image/webp"
        else:
            mime = "application/octet-stream"
    return data, mime


def set_finding(token: str, finding: dict, scheme: str, say: str, folder: Path | str | None = None, now: float | None = None) -> Case:
    case = _get_raw(token, folder=folder)
    if not token or not TOKEN_RE.match(token):
        raise ValueError("case not found")
    if case is None:
        raise ValueError("case not found")
    case.finding = dict(finding)
    case.scheme = str(scheme)
    case.say = str(say)
    case.state = "read"
    _save(case, folder)
    return case


def approve(token: str, say: str, folder: Path | str | None = None, now: float | None = None) -> Case:
    case = _get_raw(token, folder=folder)
    if not token or not TOKEN_RE.match(token):
        raise ValueError("case not found")
    if case is None:
        raise ValueError("case not found")
    if case.state not in ("read", "approved"):
        raise ValueError(f"cannot approve case in state {case.state}")
    case.say = str(say)
    case.state = "approved"
    _save(case, folder)
    return case


def mark_called(token: str, folder: Path | str | None = None, now: float | None = None) -> Case:
    case = _get_raw(token, folder=folder)
    if not token or not TOKEN_RE.match(token):
        raise ValueError("case not found")
    if case is None:
        raise ValueError("case not found")
    case.number = ""
    case.state = "called"
    _save(case, folder)
    return case


def open_cases(folder: Path | str | None = None, now: float | None = None) -> list[Case]:
    base = _base_dir(folder)
    if not base.exists():
        return []
    current_time = float(now if now is not None else time.time())
    cases: list[Case] = []
    for entry in base.iterdir():
        if entry.is_dir() and TOKEN_RE.match(entry.name):
            case_file = entry / "case.json"
            if case_file.exists():
                try:
                    data = json.loads(case_file.read_text(encoding="utf-8"))
                    c = _load_case_dict(data)
                    if (current_time - c.made) <= TTL_SECONDS:
                        cases.append(c)
                except Exception:
                    continue
    cases.sort(key=lambda c: c.made, reverse=True)
    return cases


def sweep(folder: Path | str | None = None, now: float | None = None) -> int:
    base = _base_dir(folder)
    if not base.exists():
        return 0
    current_time = float(now if now is not None else time.time())
    deleted = 0
    for entry in base.iterdir():
        if entry.is_dir() and TOKEN_RE.match(entry.name):
            case_file = entry / "case.json"
            is_expired = False
            if case_file.exists():
                try:
                    data = json.loads(case_file.read_text(encoding="utf-8"))
                    made = float(data.get("made", 0.0))
                    if (current_time - made) > TTL_SECONDS:
                        is_expired = True
                except Exception:
                    is_expired = True
            else:
                is_expired = True
            if is_expired:
                shutil.rmtree(entry, ignore_errors=True)
                deleted += 1
    return deleted
