"""Plan 2.7 — a scripted fake call through /stream reaches closing_farewell.

Runs on a snapshot of the real 12 schemes built in a temp dir with silent stubs, over the real
websocket route, with the silence gaps shortened so the test is quick.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from haqdaar import server
from haqdaar.contracts import tunables
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.data.pipeline.texts import _load_schemes

DERIVED = Path(__file__).resolve().parent.parent / "data_cache" / "derived"


@pytest.fixture
def phone(tmp_path, monkeypatch):
    for name, value in {
        "SNAPSHOTS_DIR": str(tmp_path / "snapshots"),
        "AUDIO_DIR": str(tmp_path / "audio"),
        "CALL_LOGS_DIR": str(tmp_path / "calls"),
        "SILENCE_GAP_S": 0.2,
        "TURN0_GAP_S": 0.2,
        "HANGUP_WAIT_S": 1.0,
        "KEY_GUARD_MS": 0,  # the scripted caller presses the moment a prompt starts
    }.items():
        monkeypatch.setattr(tunables, name, value)
    build_snapshot(
        _load_schemes(DERIVED), snapshot_id="real", snapshots_dir=tmp_path / "snapshots",
        audio_dir=tmp_path / "audio", render_stubs=True,
    )
    server._CALL.clear()
    yield tmp_path
    server._CALL.clear()


def _call(keys: list[str], number: str = "+919800000000") -> list[dict]:
    client = TestClient(server.app)
    client.post("/answer", content=f"CallSid=CA42&From={number.replace('+', '%2B')}",
                headers={"Content-Type": "application/x-www-form-urlencoded"})
    got: list[dict] = []
    with client.websocket_connect("/stream") as ws:
        ws.send_text(json.dumps({
            "event": "start", "streamSid": "MZ1",
            "start": {"streamSid": "MZ1", "callSid": "CA42", "accountSid": "AC1",
                      "tracks": ["inbound"], "mediaFormat": {}, "customParameters": {}},
        }))

        def read_until(event: str) -> None:
            while True:
                got.append(ws.receive_json())
                if got[-1].get("event") == event:
                    return

        # Step 7.0b: one prompt takes one key. So the caller waits for a prompt to sound,
        # presses, waits for the line to stop (clear), then waits for the next prompt.
        try:
            read_until("mark")
            for k in keys:
                ws.send_text(json.dumps({"event": "dtmf", "streamSid": "MZ1", "dtmf": {"digit": k}}))
                read_until("clear")
                read_until("mark")
            while True:
                got.append(ws.receive_json())
        except WebSocketDisconnect:
            pass
    return got


def _said(got: list[dict]) -> list[str]:
    return [m["mark"]["name"].split(":", 1)[1] for m in got if m.get("event") == "mark"]


@pytest.mark.parametrize("lang_key,lang", [("1", "hi"), ("2", "mr"), ("3", "en")])
def test_a_scripted_call_reaches_the_goodbye(phone, lang_key, lang):
    got = _call([lang_key, "1", "1"] + ["9"] * 8 + ["2", "2"])
    said = _said(got)
    assert said[-1] == "closing_farewell"
    assert any(m.get("event") == "media" for m in got)
    log_rows = [json.loads(l) for l in next((phone / "calls").glob("*.jsonl")).read_text().splitlines()]
    assert {"lang": lang, "lang_source": "keypad", "turn_n": 0} in log_rows
    assert any("slug" in row for row in log_rows)


def test_the_log_keeps_only_a_hash_of_the_number(phone):
    _call(["3", "1", "1"] + ["9"] * 8 + ["2", "2"], number="+919812345678")
    text = next((phone / "calls").glob("*.jsonl")).read_text()
    assert "9812345678" not in text
    first = json.loads(text.splitlines()[0])
    assert first["caller_hash"] == server.caller_hash("+919812345678")


def test_a_keypad_question_is_followed_by_its_menu(phone):
    got = _call(["3"])  # pick English, then stay silent until the call gives up
    said = _said(got)
    menu_start = said.index("opener_prompt")
    menu = said[menu_start + 1:said.index("keypad_unknown_suffix", menu_start)]
    assert menu[:4] == ["chip_category_farming", "key_1", "chip_category_business_loans", "key_2"]
    assert said[-1] == "closing_farewell"  # silence ladder ends the call politely


def test_one_caller_guard_refuses_second_call(phone):
    """While a call is active on /stream, a second connection is refused busy with code 1008."""
    client = TestClient(server.app)
    assert not server.is_call_active()

    with client.websocket_connect("/stream") as ws1:
        assert server.is_call_active()

        # Second connection should be refused
        try:
            with client.websocket_connect("/stream") as ws2:
                # If accepted, Starlette immediately raises WebSocketDisconnect on close(1008)
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    ws2.receive_text()
                assert exc_info.value.code == 1008
        except WebSocketDisconnect as exc_info:
            assert exc_info.code == 1008

        # First connection is still active and unimpacted
        assert server.is_call_active()

    # Once ws1 closes, active call lock is released
    assert not server.is_call_active()


def test_caller_hash_pruning_on_abandoned_answer():
    """Stale caller hash entries from abandoned /answer calls are pruned and do not leak."""
    client = TestClient(server.app)
    client.post("/answer", content="CallSid=CA_abandoned_1&From=%2B919999999999",
                headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert "CA_abandoned_1" in server._CALLER_HASH
    assert "CA_abandoned_1" in server._CALLER_HASH_TS

    # Force prune with max_age_s=0.0
    server._prune_caller_hashes(max_age_s=0.0)
    assert "CA_abandoned_1" not in server._CALLER_HASH
    assert "CA_abandoned_1" not in server._CALLER_HASH_TS


def test_clips_malformed_scheme_token_does_not_crash():
    """Malformed scheme tokens with fewer than 3 parts return empty list without crashing."""
    from haqdaar.audio.phone import PhoneAudio

    class DummyCorpus:
        language = "en"
        def chunks(self, sid, lang):
            return ()
        def audio(self, *args):
            return ""
        def values(self, box):
            return ()

    class DummyMouth:
        pass

    class DummyTurn:
        pass

    phone_audio = PhoneAudio(DummyCorpus(), None, DummyMouth(), DummyTurn(), lambda: None)
    # Malformed tokens without 3 parts
    assert phone_audio._clips("scheme:") == []
    assert phone_audio._clips("scheme:foo") == []
    assert phone_audio._clips("scheme:a:b:c") == []
