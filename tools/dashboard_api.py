"""tools/dashboard_api.py

The data door for the dashboard (`make dashboard`). It answers the dashboard's questions from
files the project already writes: call traces, the usage ledgers, the gates report, the
snapshot. It only reads, and it is its own small server on 127.0.0.1, apart from the call
server, so a slow page can never touch a live call.

It grows from tools/call_viewer.py: the call routes (`/api/calls`, `/api/calls/{key}`) and the
old call page at `/` are still served. `/api/home` is everything the Home page shows, in one go.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from haqdaar.contracts import tunables
from tools.call_viewer import Calls, Texts, make_app as make_calls_app

ROOT = Path(__file__).resolve().parent.parent
ROSTER = ROOT / "haqdaar" / "data" / "pipeline" / "schemes.yaml"
ENGINE_HEALTH = "http://127.0.0.1:8000/health"
WINDOW = timedelta(hours=24)  # "today" for a night worker: the last 24 hours, not since midnight
STRIP_MAX = 80


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


def make_app(dirs: list[Path | str], texts: Optional[Texts] = None, **home_args: Any):
    app = make_calls_app(dirs, texts)
    calls = Calls(dirs, texts)

    @app.get("/api/home")
    def get_home() -> dict[str, Any]:
        return home(calls, **home_args)

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="The dashboard's data door (reads files, 127.0.0.1 only).")
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
