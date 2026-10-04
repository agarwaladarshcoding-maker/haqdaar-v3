"""tools/dashboard_api.py

The data door for the dashboard (`make dashboard`). It answers the dashboard's questions from
files the project already writes: call traces, the usage ledgers, the gates report, the
snapshot. It is its own small server on 127.0.0.1, apart from the call server, so a slow page
can never touch a live call.

It does two things besides reading, both for the Live call page, and both only when the
request carries the dashboard's header (so another web page open in the browser cannot fire them):
ring the owner's saved number (`/api/call-me`), and run a typed test call (`/api/test-call`).

It grows from tools/call_viewer.py: the call routes (`/api/calls`, `/api/calls/{key}`) and the
old call page at `/` are still served. `/api/home` is everything the Home page shows, in one go.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import Body, Depends, Header, HTTPException

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Hangup, Noise, Silence, Speech
from haqdaar.sim import FakeAudio, run_sim
from tools.call_viewer import Calls, Texts, make_app as make_calls_app

ROOT = Path(__file__).resolve().parent.parent
ROSTER = ROOT / "haqdaar" / "data" / "pipeline" / "schemes.yaml"
ENGINE_HEALTH = "http://127.0.0.1:8000/health"
WINDOW = timedelta(hours=24)  # "today" for a night worker: the last 24 hours, not since midnight
STRIP_MAX = 80
TUNNEL_HOST = Path("logs") / "tunnel_host"  # the engine's public address, written by `make run`
TEST_IDLE_S = 300.0   # a typed test call nobody answers hangs up by itself
RING_GAP_S = 20.0     # do not ring the phone twice in a row
KEYS = set("0123456789*#")


def engine_is_on(url: str = ENGINE_HEALTH) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.4) as r:
            return r.status == 200
    except Exception:
        return False


def _rows(path: Path) -> list[dict[str, Any]]:
    """A JSONL ledger as dicts. A missing file or a bad line is nothing, not an error."""
    out: list[dict[str, Any]] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if isinstance(row, dict):
                out.append(row)
    except Exception:
        pass
    return out


def _json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# --- the parts of the Home page --------------------------------------------------------

def scheme_counts(reports_dir: Path, snapshots_dir: Path, roster: Path = ROSTER) -> dict[str, Any]:
    """How many schemes are chosen, checked, live on calls, waiting for a voice, set aside."""
    gates = _json(reports_dir / "gates.json")
    try:
        import yaml

        chosen = len((yaml.safe_load(roster.read_text(encoding="utf-8")) or {}).get("schemes") or [])
    except Exception:
        chosen = int(gates.get("roster_size") or 0)
    snapshot, live, made = "", 0, ""
    try:
        snapshot = (snapshots_dir / "CURRENT").read_text(encoding="utf-8").strip()
        manifest = _json(snapshots_dir / snapshot / "manifest.json")
        live, made = int(manifest.get("num_schemes") or 0), str(manifest.get("created_at") or "")
    except Exception:
        pass
    checked = int(gates.get("ok") or 0)
    return {
        "chosen": chosen, "checked": checked, "live": live, "no_voice": max(checked - live, 0),
        "set_aside": int(gates.get("quarantined_count") or 0),
        "set_aside_slugs": list(gates.get("quarantined_slugs") or []),
        "languages": dict(gates.get("per_language") or {}),
        "snapshot": snapshot, "snapshot_made": made,
    }


def money(reports_dir: Path, muse_ledger: Optional[Path] = None, now: Optional[datetime] = None) -> dict[str, Any]:
    """Muse in rupees against its caps. Every other service in the units its ledger counts."""
    from haqdaar.data.pipeline import muse

    ledger = Path(muse_ledger) if muse_ledger is not None else muse.LEDGER
    day = muse.muse_day(now)
    today, total = muse.spent_today_inr(ledger, now), muse.spent_inr(ledger)
    blocked = muse.blocked_day(ledger) == day
    tts, stt = _rows(reports_dir / "sarvam_tts_usage.jsonl"), _rows(reports_dir / "stt_usage.jsonl")
    groq, translate = _rows(reports_dir / "groq_usage.jsonl"), _rows(reports_dir / "sarvam_usage.jsonl")
    heard = [r for r in stt if r.get("success")]
    return {
        "muse": {
            "day": day, "today": round(today, 2), "day_cap": tunables.MUSE_DAILY_CAP_INR,
            "all": round(total, 2), "cap": tunables.MUSE_CAP_INR, "blocked": blocked,
            "open": not blocked and today < tunables.MUSE_DAILY_CAP_INR and total < tunables.MUSE_CAP_INR,
        },
        "units": [
            {"name": "Sarvam voice", "value": sum(int(r.get("chars") or 0) for r in tts),
             "unit": "characters", "note": f"{len(tts)} clips made"},
            {"name": "Sarvam speech-to-text", "value": round(sum(float(r.get("audio_duration_s") or 0) for r in stt)),
             "unit": "seconds heard", "note": f"{len(heard)} of {len(stt)} worked"},
            {"name": "Sarvam translate", "value": sum(int(r.get("chars") or 0) for r in translate),
             "unit": "characters", "note": f"{len(translate)} texts"},
            {"name": "Groq", "value": len(groq), "unit": "requests",
             "note": f"{sum(1 for r in groq if r.get('error'))} failed"},
        ],
    }


def numbers(infos: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """The four figures on top, over the last 24 hours."""
    def recent(info: dict[str, Any]) -> bool:
        try:
            return now - datetime.fromisoformat(info["at"]) <= WINDOW
        except Exception:
            return False

    window = [i for i in infos if recent(i)]
    judged = [i for i in window if i.get("verdict")]
    timed = [i for i in window if i.get("timed")]
    replies = [i["slowest_reply_s"] for i in timed if i.get("slowest_reply_s") is not None]
    return {
        "window": "last 24 hours", "calls": len(window), "judged": len(judged),
        "passed": sum(1 for i in judged if i["verdict"]["passed"]),
        "avg_length_s": round(sum(i["duration_s"] for i in timed) / len(timed), 1) if timed else None,
        "slowest_reply_s": max(replies) if replies else None,
        "reply_budget_s": tunables.RESPONSE_BUDGET_S,
        "all_calls": len(infos), "phone_calls": sum(1 for i in infos if i.get("source") == "phone"),
    }


def strip(call: dict[str, Any]) -> list[dict[str, Any]]:
    """A call as a row of marks for the call tape: AI bars (with seconds) and caller ticks."""
    marks: list[dict[str, Any]] = []
    for item in call.get("items", []):
        if item["who"] == "ai":
            marks.append({"k": "ai", "s": item.get("dur") or 0})
        elif item["who"] == "caller":
            marks.append({"k": item.get("kind", "key"), "bad": item.get("cls") in ("UNCLEAR", "NOISE")})
        elif item["who"] == "problem":
            marks.append({"k": "problem"})
    return marks[:STRIP_MAX]


def needs_a_look(engine_on: bool, schemes: dict[str, Any], cash: dict[str, Any],
                 infos: list[dict[str, Any]], reports_dir: Path, server_log: Path) -> list[dict[str, str]]:
    """What the owner should look at, worst first. Each line says what is wrong and what to do."""
    out: list[dict[str, str]] = []

    def add(level: str, title: str, detail: str, page: str = "") -> None:
        out.append({"level": level, "title": title, "detail": detail, "page": page})

    if not engine_on:
        add("warn", "The engine is off", "No call can be placed. Start it with: make run", "system")
    try:  # the last word from the tunnel about the phone number
        tunnel = [x for x in server_log.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
                  if x.startswith("tunnel")]
        if tunnel and "could not update the number" in tunnel[-1]:
            add("bad", "Twilio refused the login", tunnel[-1].split("tunnel", 1)[1].strip()
                + ". Check the Twilio keys in .env.", "settings")
    except Exception:
        pass
    asks = [r for r in _rows(reports_dir / "groq_usage.jsonl") if str(r.get("task", "")).startswith("model")][-3:]
    if asks and all(r.get("error") for r in asks):
        add("bad", "Groq cannot run the engine's model",
            f"Last answer: {asks[-1].get('error')} for {asks[-1].get('model')}. "
            "Calls drop to keypad after two spoken answers. Fix the Groq key.", "settings")
    muse = cash["muse"]
    if muse["blocked"]:
        add("warn", "Muse is blocked for today", f"Spend day {muse['day']}. It opens again at 05:00.", "usage")
    elif muse["all"] >= 0.8 * muse["cap"] or muse["today"] >= 0.8 * muse["day_cap"]:
        add("warn", "Muse is near its cap", f"₹{muse['today']} of ₹{muse['day_cap']:.0f} today, "
            f"₹{muse['all']} of ₹{muse['cap']:.0f} in all.", "usage")
    for info in infos[:20]:
        verdict = info.get("verdict")
        if verdict and not verdict["passed"]:
            add("bad", f"Call {info['call_id']} failed the judge", verdict["reason"], f"calls#{info['key']}")
        elif info.get("problems"):
            add("warn", f"Call {info['call_id']} had {info['problems']} problem"
                + ("s" if info["problems"] > 1 else ""), "Open the call to see where.", f"calls#{info['key']}")
    if schemes["no_voice"]:
        add("warn", f"{schemes['no_voice']} checked schemes have no voice yet",
            "They pass every check but cannot be spoken on a call until their clips are made.", "schemes")
    try:
        pending = (reports_dir / "audit_3_7.md").read_text(encoding="utf-8").count("PENDING")
        if pending:
            add("info", f"{pending} audit verdicts are waiting for you", "The 3.7 read of the cards.", "schemes")
    except Exception:
        pass
    if schemes["set_aside"]:
        add("info", f"{schemes['set_aside']} schemes are set aside", ", ".join(schemes["set_aside_slugs"]), "schemes")
    if not any(i.get("source") == "phone" for i in infos):
        add("info", "No real phone call yet", "Every call so far is a typed test call. "
            "The engine has not been heard on a real phone.", "live")
    order = {"bad": 0, "warn": 1, "info": 2}
    return sorted(out, key=lambda x: order[x["level"]])


def home(calls: Calls, reports_dir: Path | str | None = None, snapshots_dir: Path | str | None = None,
         server_log: Path | str = "logs/server.log", probe: Callable[[], bool] = engine_is_on,
         now: Optional[datetime] = None, muse_ledger: Optional[Path] = None) -> dict[str, Any]:
    """Everything the Home page shows."""
    now = now or datetime.now()
    reports = Path(reports_dir or tunables.REPORTS_DIR)
    found = calls.all()
    infos = [{"key": key, **call["info"]} for key, call in found.items()]
    on = probe()
    schemes = scheme_counts(reports, Path(snapshots_dir or tunables.SNAPSHOTS_DIR))
    cash = money(reports, muse_ledger)
    live = next((i["key"] for i in infos if i.get("live")), None)
    return {
        "at": now.isoformat(timespec="seconds"),
        "engine": {"on": on, "live_call": live, "snapshot": schemes["snapshot"],
                   "snapshot_made": schemes["snapshot_made"], "line": "closed to the public",
                   "phone_tail": (os.environ.get("CALL_ME_NUMBER") or "")[-2:]},
        "numbers": numbers(infos, now),
        "needs": needs_a_look(on, schemes, cash, infos, reports, Path(server_log)),
        "schemes": schemes,
        "money": cash,
        "recent": [{**info, "strip": strip(found[info["key"]])} for info in infos[:5]],
    }


# --- the typed test call ---------------------------------------------------------------

class TypedCaller(FakeAudio):
    """The sim's caller, fed from the dashboard instead of the terminal.

    The engine runs on its own thread and waits here for the next thing the owner types:
    a key, some words, "silence", or "hangup". Nothing typed for TEST_IDLE_S hangs up.
    """

    def __init__(self, idle_s: float = TEST_IDLE_S) -> None:
        super().__init__()
        self.inbox: "queue.Queue[str]" = queue.Queue()
        self.waiting: Optional[str] = None  # what the engine is waiting for, for the page's hint
        self._idle_s = idle_s

    def _take(self, kind: str) -> str:
        self.waiting = kind
        try:
            return self.inbox.get(timeout=self._idle_s).strip()
        except queue.Empty:
            return "hangup"
        finally:
            self.waiting = None

    def _get_next_raw_input(self, prompt: str) -> str:  # the language pick at the start
        typed = self._take("language")
        return "h" if typed.lower() in ("h", "hangup") else typed

    def _next_input(self, profile: str = "normal") -> Digit | Noise | Silence | Hangup | Speech:
        typed = self._take("words" if profile == "spoken" else "key")
        low = typed.lower()
        if low in ("h", "hangup"):
            return Hangup()
        if low in ("", "s", "silence"):
            self._silence_count += 1
            return Silence(n=self._silence_count)
        self._silence_count = 0
        if typed in KEYS:
            return Digit(digit=typed)
        # With QA on, words typed at a yes/no or a menu are heard too, so a question can be typed there.
        if profile == "spoken" or (tunables.QA_ENABLED and profile in ("confirm", "readback")):
            # Typed ASCII counts as already English; the real speech service would have translated it.
            if tunables.ENGLISH_PIPE and typed.isascii():
                return Speech(text=typed, lang="en", english=True)
            return Speech(text=typed)
        return Noise()  # words when only a key will do: the engine hears a sound it cannot use


class TypedCalls:
    """One typed test call at a time, on the CURRENT snapshot. Free: no phone, no paid API."""

    def __init__(self, logs_dir: Path | str = "logs", snapshot: Optional[str] = "CURRENT",
                 idle_s: float = TEST_IDLE_S) -> None:
        self._logs_dir, self._snapshot, self._idle_s = str(logs_dir), snapshot, idle_s
        self._lock = threading.Lock()
        self.key: Optional[str] = None
        self.error = ""
        self._caller: Optional[TypedCaller] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> str:
        with self._lock:
            if self.active:
                raise RuntimeError("A test call is already going on.")
            self.key, self.error = f"test_{int(time.time() * 1000)}", ""
            self._caller = TypedCaller(self._idle_s)
            self._thread = threading.Thread(target=self._run, args=(self.key, self._caller), daemon=True)
            self._thread.start()
            return self.key

    def _run(self, key: str, caller: TypedCaller) -> None:
        try:
            run_sim(call_id=key, logs_dir=self._logs_dir, snapshot=self._snapshot, audio=caller,
                    real_model=tunables.QA_ENABLED)
        except Exception as e:  # shown on the page; a test call must never take the door down
            self.error = f"The test call stopped: {e!r}"

    def say(self, text: str) -> None:
        if not self.active or self._caller is None:
            raise RuntimeError("No test call is going on.")
        self._caller.inbox.put(text)

    def state(self) -> Optional[dict[str, Any]]:
        if self.key is None:
            return None
        return {"key": self.key, "active": self.active, "error": self.error,
                "waiting": self._caller.waiting if self.active and self._caller else None}


# --- ring my phone ---------------------------------------------------------------------

class Ringer:
    """Rings the owner's saved number, and only that number. The page never sends one."""

    def __init__(self, probe: Callable[[], bool] = engine_is_on, place: Optional[Callable[[str, str], str]] = None,
                 host_file: Path = TUNNEL_HOST, clock: Callable[[], float] = time.monotonic) -> None:
        self._probe, self._place, self._host_file, self._clock = probe, place, host_file, clock
        self._last = -RING_GAP_S

    def ring(self, live_call: Optional[str]) -> str:
        """Place the call and return its id. Raises RuntimeError with words the page can show."""
        if not self._probe():
            raise RuntimeError("The engine is off. Start it with: make run")
        if live_call:
            raise RuntimeError("A call is already live. One call at a time.")
        if self._clock() - self._last < RING_GAP_S:
            raise RuntimeError("Your phone was just rung. Wait a few seconds.")
        number = os.environ.get("CALL_ME_NUMBER", "")
        if not number:
            raise RuntimeError("No phone number is saved. Put CALL_ME_NUMBER in .env.")
        try:
            host = self._host_file.read_text(encoding="utf-8").strip()
        except Exception:
            host = ""
        host = host or os.environ.get("NGROK_DOMAIN", "")
        if not host:
            raise RuntimeError("The engine has no public address yet. Start it with: make run")
        place = self._place
        if place is None:
            from haqdaar.audio.telephony import place_call as place
        try:
            sid = place(number, f"https://{host}/answer")
        except urllib.error.HTTPError as e:
            why = "Check the Twilio keys in .env." if e.code == 401 else "See make calls for what Twilio says."
            raise RuntimeError(f"Twilio refused the call (HTTP {e.code}). {why}") from None
        except Exception as e:
            raise RuntimeError(f"The call could not be placed: {type(e).__name__}.") from None
        self._last = self._clock()
        return sid


def from_dashboard(x_haqdaar: str = Header(default="")) -> None:
    """Actions need the dashboard's header. A plain web page cannot send it across sites."""
    if x_haqdaar != "dashboard":
        raise HTTPException(status_code=403, detail="Only the dashboard may do this.")


def make_app(dirs: list[Path | str], texts: Optional[Texts] = None, tests: Optional[TypedCalls] = None,
             ringer: Optional[Ringer] = None, **home_args: Any):
    app = make_calls_app(dirs, texts)
    calls = Calls(dirs, texts)
    probe = home_args.get("probe", engine_is_on)
    tests = tests or TypedCalls()
    ringer = ringer or Ringer(probe=probe)

    def live_call() -> Optional[str]:
        return next((key for key, call in calls.all().items()
                     if call["info"].get("live") and call["info"].get("source") == "phone"), None)

    @app.get("/api/home")
    def get_home() -> dict[str, Any]:
        return home(calls, **home_args)

    @app.get("/api/live")
    def get_live() -> dict[str, Any]:
        """What the Live call page needs every second: the engine, the phone call, the test call."""
        return {"engine": {"on": probe(), "live_call": live_call(),
                           "phone_tail": (os.environ.get("CALL_ME_NUMBER") or "")[-2:]},
                "test": tests.state()}

    @app.post("/api/call-me", dependencies=[Depends(from_dashboard)])
    def post_call_me() -> dict[str, str]:
        try:
            return {"sid": ringer.ring(live_call())}
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @app.post("/api/test-call", dependencies=[Depends(from_dashboard)])
    def post_test_call() -> dict[str, str]:
        try:
            return {"key": tests.start()}
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @app.post("/api/test-call/input", dependencies=[Depends(from_dashboard)])
    def post_test_input(text: str = Body(default="", embed=True, max_length=300)) -> dict[str, bool]:
        try:
            tests.say(text)
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"ok": True}

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="The dashboard's data door (127.0.0.1 only).")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--dirs", nargs="*", default=[tunables.CALL_LOGS_DIR, "logs"],
                        help="log folders to look in; each holds a trace/ folder")
    args = parser.parse_args()

    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()
    print(f"dashboard data door: http://127.0.0.1:{args.port}   (this computer only)")
    uvicorn.run(make_app(args.dirs), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
