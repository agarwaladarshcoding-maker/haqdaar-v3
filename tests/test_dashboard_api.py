"""Step 6.1 — the dashboard's data door: GET /api/home. All offline, all on temp files."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi.testclient import TestClient

from tests.test_call_viewer import TRACE
from tools.call_viewer import Calls, Texts
from tools.dashboard_api import home, make_app, scheme_counts

NOW = datetime(2026, 10, 3, 1, 0, 0)  # one hour after the call in TRACE


def _world(tmp_path, groq_rows=(), tunnel_line="tunnel  number now answers at x.trycloudflare.com"):
    """A tiny copy of the files the data door reads."""
    reports, snaps, logs = tmp_path / "reports", tmp_path / "snapshots", tmp_path / "logs"
    (snaps / "snapA").mkdir(parents=True)
    (logs / "trace").mkdir(parents=True)
    reports.mkdir()
    (snaps / "CURRENT").write_text("snapA")
    (snaps / "snapA" / "manifest.json").write_text(json.dumps({"num_schemes": 2, "created_at": "2026-10-01T21:29:44"}))
    (reports / "gates.json").write_text(json.dumps({
        "ok": 5, "roster_size": 6, "quarantined_count": 1, "quarantined_slugs": ["pmsby"],
        "per_language": {"en": 5, "hi": 5, "mr": 4}}))
    (reports / "audit_3_7.md").write_text("| a | PENDING |\n| b | PENDING |\n| c | OK |\n")
    (reports / "sarvam_tts_usage.jsonl").write_text('{"chars": 100}\n{"chars": 50}\n')
    (reports / "stt_usage.jsonl").write_text('{"success": true, "audio_duration_s": 3.2}\n{"success": false, "audio_duration_s": 1.0}\n')
    (reports / "groq_usage.jsonl").write_text("".join(json.dumps(r) + "\n" for r in groq_rows))
    (reports / "muse_usage.jsonl").write_text('{"ts": "2026-09-30T10:00:00+00:00", "inr": 12.5}\n')
    (logs / "server.log").write_text(f"12:00:00.000  start\n{tunnel_line}\nINFO: started\n")
    (logs / "trace" / "CA1.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in TRACE) + "\n")
    calls = Calls([logs], Texts(tmp_path / "no_snapshots"))
    return dict(calls=calls, reports_dir=reports, snapshots_dir=snaps, server_log=logs / "server.log",
                now=NOW, muse_ledger=reports / "muse_usage.jsonl")


def test_home_has_every_part_the_page_shows(tmp_path):
    data = home(probe=lambda: True, **_world(tmp_path))

    assert data["engine"]["on"] is True and data["engine"]["snapshot"] == "snapA"
    assert data["engine"]["live_call"] is None
    assert data["schemes"] == {**data["schemes"], "checked": 5, "live": 2, "no_voice": 3,
                               "set_aside": 1, "set_aside_slugs": ["pmsby"]}
    n = data["numbers"]
    assert n["calls"] == 1 and n["all_calls"] == 1 and n["phone_calls"] == 1
    assert n["avg_length_s"] == 30.1 and n["slowest_reply_s"] == 2.0 and n["reply_budget_s"] == 1.2
    muse = data["money"]["muse"]
    assert muse["all"] == 12.5 and muse["today"] == 0.0 and muse["cap"] == 60.0 and muse["open"] is True
    units = {u["name"]: u for u in data["money"]["units"]}
    assert units["Sarvam voice"]["value"] == 150 and units["Sarvam speech-to-text"]["note"] == "1 of 2 worked"

    call = data["recent"][0]
    assert call["call_id"] == "CA1" and call["problems"] == 2
    kinds = [m["k"] for m in call["strip"]]
    assert kinds[:4] == ["ai", "key", "ai", "speech"] and "problem" in kinds
    assert call["strip"][0]["s"] == 10.0


def test_needs_a_look_names_what_is_wrong_worst_first(tmp_path):
    bad_groq = [{"task": "model_opener", "model": "llama-3.3-70b-versatile", "error": "http_404"}] * 2
    world = _world(tmp_path, groq_rows=bad_groq,
                   tunnel_line="tunnel  could not update the number (HTTP Error 401: Unauthorized)")
    needs = home(probe=lambda: False, **world)["needs"]
    titles = [n["title"] for n in needs]

    assert [n["level"] for n in needs] == sorted((n["level"] for n in needs), key=["bad", "warn", "info"].index)
    assert "Twilio refused the login" in titles and "Groq cannot run the engine's model" in titles
    assert "The engine is off" in titles
    assert "Call CA1 had 2 problems" in titles
    assert "3 checked schemes have no voice yet" in titles
    assert "2 audit verdicts are waiting for you" in titles
    assert "No real phone call yet" not in titles  # CA1 is a phone call
    groq = next(n for n in needs if n["title"].startswith("Groq"))
    assert "http_404" in groq["detail"] and groq["page"] == "settings"


def test_a_healthy_system_asks_for_little(tmp_path):
    world = _world(tmp_path, groq_rows=[{"task": "model_opener", "error": None}])
    titles = [n["title"] for n in home(probe=lambda: True, **world)["needs"]]
    assert "The engine is off" not in titles
    assert not any(t.startswith(("Twilio", "Groq", "Muse")) for t in titles)


def test_missing_files_give_zeros_not_a_crash(tmp_path):
    counts = scheme_counts(tmp_path / "nope", tmp_path / "nope", tmp_path / "nope.yaml")
    assert counts["live"] == 0 and counts["checked"] == 0 and counts["snapshot"] == ""
    data = home(Calls([tmp_path]), reports_dir=tmp_path, snapshots_dir=tmp_path, server_log=tmp_path / "x.log",
                probe=lambda: False, now=NOW, muse_ledger=tmp_path / "none.jsonl")
    assert data["recent"] == [] and data["numbers"]["calls"] == 0 and data["numbers"]["avg_length_s"] is None
    assert "No real phone call yet" in [n["title"] for n in data["needs"]]


def test_the_route_serves_home_and_keeps_the_call_routes(tmp_path):
    world = _world(tmp_path)
    calls = world.pop("calls")
    app = make_app(calls._dirs, Texts(tmp_path / "no_snapshots"), probe=lambda: True,
                   **{k: v for k, v in world.items()})
    client = TestClient(app)
    data = client.get("/api/home").json()
    assert data["engine"]["on"] is True and data["recent"][0]["key"] == "CA1"
    assert client.get("/api/calls/CA1").json()["info"]["call_id"] == "CA1"


# --- step D3: the Live call page ---------------------------------------------------------

import time  # noqa: E402
import urllib.error  # noqa: E402

from tools.dashboard_api import Ringer, TypedCalls  # noqa: E402

DASH = {"X-Haqdaar": "dashboard"}


def _wait(check, tries=200):
    for _ in range(tries):
        if check():
            return True
        time.sleep(0.02)
    return False


def _live_app(tmp_path, **kw):
    logs = tmp_path / "logs"
    tests = TypedCalls(logs_dir=logs, snapshot=None, idle_s=kw.pop("idle_s", 5))
    app = make_app([logs], Texts(tmp_path / "no_snapshots"), tests=tests, probe=kw.pop("probe", lambda: True),
                   reports_dir=tmp_path, snapshots_dir=tmp_path, server_log=tmp_path / "x.log",
                   muse_ledger=tmp_path / "none.jsonl", **kw)
    return TestClient(app), tests


def test_a_typed_test_call_runs_step_by_step_and_shows_as_a_call(tmp_path, capsys):
    client, tests = _live_app(tmp_path)
    assert client.get("/api/live").json()["test"] is None

    key = client.post("/api/test-call", headers=DASH).json()["key"]
    assert _wait(lambda: client.get("/api/live").json()["test"]["waiting"] == "language")
    assert client.post("/api/test-call", headers=DASH).status_code == 409  # one at a time

    client.post("/api/test-call/input", headers=DASH, json={"text": "2"})
    assert _wait(lambda: client.get("/api/live").json()["test"]["waiting"] == "words")
    call = client.get(f"/api/calls/{key}").json()
    assert call["info"]["lang"] == "mr" and call["info"]["source"] == "sim" and not call["info"]["finished"]
    assert call["items"][1]["text"] == "pressed 2"

    client.post("/api/test-call/input", headers=DASH, json={"text": "hangup"})
    assert _wait(lambda: not tests.active)
    capsys.readouterr()
    state = client.get("/api/live").json()["test"]
    assert state == {"key": key, "active": False, "error": "", "waiting": None}
    info = client.get(f"/api/calls/{key}").json()["info"]
    assert info["finished"] and info["ended"] == "caller hung up"
    assert client.post("/api/test-call/input", headers=DASH, json={"text": "1"}).status_code == 409


def test_a_test_call_nobody_answers_hangs_up_by_itself(tmp_path, capsys):
    client, tests = _live_app(tmp_path, idle_s=0.05)
    client.post("/api/test-call", headers=DASH)
    assert _wait(lambda: not tests.active)
    capsys.readouterr()
    assert tests.error == ""


def test_actions_are_refused_without_the_dashboard_header(tmp_path):
    client, tests = _live_app(tmp_path)
    for path in ("/api/call-me", "/api/test-call", "/api/test-call/input"):
        assert client.post(path, json={"text": "1"}).status_code == 403
    assert tests.key is None


def test_ringer_rings_only_the_saved_number_and_says_why_when_it_cannot(tmp_path, monkeypatch):
    host = tmp_path / "tunnel_host"
    placed: list[tuple[str, str]] = []
    now = [100.0]

    def place(number, url):
        placed.append((number, url))
        return "CA123"

    def ring(probe=lambda: True, place=place, live=None):
        return Ringer(probe=probe, place=place, host_file=host, clock=lambda: now[0]).ring(live)

    def refused(**kw):
        try:
            ring(**kw)
        except RuntimeError as e:
            return str(e)
        return ""

    monkeypatch.delenv("CALL_ME_NUMBER", raising=False)
    monkeypatch.delenv("NGROK_DOMAIN", raising=False)
    assert "engine is off" in refused(probe=lambda: False)
    assert "already live" in refused(live="CA9")
    assert "CALL_ME_NUMBER" in refused()
    monkeypatch.setenv("CALL_ME_NUMBER", "+919800000090")
    assert "no public address" in refused()
    host.write_text("x.trycloudflare.com\n")
    assert placed == []

    assert ring() == "CA123"
    assert placed == [("+919800000090", "https://x.trycloudflare.com/answer")]

    def bad_login(number, url):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", None, None)

    assert "Twilio refused the call (HTTP 401). Check the Twilio keys" in refused(place=bad_login)

    again = Ringer(place=place, probe=lambda: True, host_file=host, clock=lambda: now[0])
    again.ring(None)
    try:
        again.ring(None)
        raise AssertionError("rang twice in a row")
    except RuntimeError as e:
        assert "just rung" in str(e)
    now[0] += 30
    assert again.ring(None) == "CA123"


def test_call_me_route_passes_the_reason_to_the_page(tmp_path, monkeypatch):
    monkeypatch.delenv("CALL_ME_NUMBER", raising=False)
    client, _ = _live_app(tmp_path, probe=lambda: False)
    r = client.post("/api/call-me", headers=DASH)
    assert r.status_code == 409 and "engine is off" in r.json()["detail"]
    live = client.get("/api/live").json()
    assert live["engine"] == {"on": False, "live_call": None, "phone_tail": ""}
