"""Plan v5 step 1.0: the guards on the phone line and "the line stays smooth".

Over the real routes, on the same stub snapshot as tests/test_phone_call.py. No network.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from haqdaar import server
from haqdaar.audio.mouth import Mouth
from haqdaar.audio.telephony import SIGNATURE_HEADER, build_end_twiml, build_stream_twiml, request_is_signed
from haqdaar.contracts import tunables
from tests.test_phone_call import _call, _said, phone  # noqa: F401  (the fixture)

FORM = {"Content-Type": "application/x-www-form-urlencoded"}
TOKEN = "test-token"


def _sign(url: str, fields: dict[str, str]) -> str:
    text = url + "".join(k + fields[k] for k in sorted(fields))
    return base64.b64encode(hmac.new(TOKEN.encode(), text.encode(), hashlib.sha1).digest()).decode()


def _start(ws, call: str = "CA42", stream: str = "MZ1") -> None:
    ws.send_text(json.dumps({
        "event": "start", "streamSid": stream,
        "start": {"streamSid": stream, "callSid": call, "accountSid": "AC1",
                  "tracks": ["inbound"], "mediaFormat": {}, "customParameters": {}},
    }))


def _until(ws, event: str) -> list[dict]:
    got = []
    while True:
        got.append(ws.receive_json())
        if got[-1].get("event") == event:
            return got


def _free(seconds: float = 5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if not server.is_call_active() and server._LINE is None:
            return True
        time.sleep(0.02)
    return False


def _log_rows(folder, seconds: float = 5.0) -> list[dict]:
    """The call's log, once the engine thread has closed it."""
    end = time.monotonic() + seconds
    while True:
        rows = [json.loads(l) for l in next((folder / "calls").glob("*.jsonl")).read_text().splitlines()]
        if (rows and "stop" in rows[-1]) or time.monotonic() > end:
            return rows
        time.sleep(0.02)


@pytest.fixture
def signed(monkeypatch):
    monkeypatch.setattr(tunables, "PHONE_CHECK", True)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(server, "NGROK_DOMAIN", "line.test")


@pytest.fixture
def kept(phone, monkeypatch):  # noqa: F811
    """A dropped stream keeps the call; the caller is quiet for long, so the call does not end by itself."""
    monkeypatch.setattr(tunables, "LINE_RECONNECT", True)
    monkeypatch.setattr(server, "NGROK_DOMAIN", "line.test")
    for name in ("SILENCE_GAP_S", "TURN0_GAP_S", "SILENCE_REMIND_S", "SILENCE_HANGUP_S"):
        monkeypatch.setattr(tunables, name, 30)
    yield phone
    line = server._LINE
    if line is not None:
        server._finish(line)
    assert _free()


# --- the request is the phone provider's ------------------------------------------------

def test_a_signature_is_checked(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    url, fields = "https://line.test/answer", {"CallSid": "CA1", "From": "+91980", "Empty": ""}
    good = _sign(url, fields)
    assert request_is_signed(url, fields, good)
    assert not request_is_signed(url, {**fields, "From": "+91981"}, good)
    assert not request_is_signed(url + "x", fields, good)
    assert not request_is_signed(url, fields, "")
    monkeypatch.delenv("TWILIO_AUTH_TOKEN")
    assert not request_is_signed(url, fields, good)


def test_answer_takes_only_a_signed_request(signed):
    client = TestClient(server.app)
    body = "CallSid=CA77&From=%2B919800000000&Blank="
    assert client.post("/answer", content=body, headers=FORM).status_code == 403
    assert client.post("/answer", content=body, headers={**FORM, SIGNATURE_HEADER: "bad"}).status_code == 403
    assert "CA77" not in server._CALLER_HASH
    good = _sign("https://line.test/answer", {"CallSid": "CA77", "From": "+919800000000", "Blank": ""})
    reply = client.post("/answer", content=body, headers={**FORM, SIGNATURE_HEADER: good})
    assert reply.status_code == 200 and '<Stream url="wss://line.test/stream"' in reply.text
    assert server._CALLER_HASH.pop("CA77") == server.caller_hash("+919800000000")
    server._CALLER_HASH_TS.pop("CA77", None)


def test_the_stream_takes_only_a_call_that_answer_saw(phone, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tunables, "PHONE_CHECK", True)
    client = TestClient(server.app)
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/stream") as ws:
            _start(ws, call="CA_nobody")
            ws.receive_json()
    assert closed.value.code == 1008
    assert _free()
    assert not list((phone / "calls").glob("*.jsonl"))


def test_a_socket_that_sends_no_start_is_closed(monkeypatch):
    monkeypatch.setattr(tunables, "STREAM_START_WAIT_S", 0.2)
    client = TestClient(server.app)
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/stream") as ws:
            ws.receive_json()
    assert closed.value.code == 1008
    assert _free()


def test_the_open_pages_and_the_tone_route_are_gone():
    client = TestClient(server.app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/tone"):
            pass
    assert client.get("/health").json() == {"status": "ok"}


# --- the cap and the line report -----------------------------------------------------------

def test_a_call_ends_with_a_line_report(phone):  # noqa: F811
    got = _call(["3", "1", "1"] + ["9"] * 8 + ["2", "2"])
    assert _said(got)[-1] == "closing_farewell"
    assert _free()
    rows = _log_rows(phone)
    assert "stop" in rows[-1]
    report = rows[-2]
    assert report["ev"] == "line" and "invalid" not in report
    assert report["why"] == "we ended the call" and report["drops"] == 0
    assert report["ahead_s"] > 0
    assert set(report) >= {"gap_s", "stt_ms", "model_ms", "voice_ms"}
    trace = next((phone / "calls" / "trace").glob("*.jsonl")).read_text()
    assert "line    report: closed because we ended the call" in trace


def test_a_call_is_closed_at_the_cap(phone, monkeypatch):  # noqa: F811
    for name in ("SILENCE_GAP_S", "TURN0_GAP_S", "SILENCE_REMIND_S", "SILENCE_HANGUP_S"):
        monkeypatch.setattr(tunables, name, 30)
    monkeypatch.setattr(tunables, "CALL_CEILING_S", 1)
    t0 = time.monotonic()
    _call([])
    assert time.monotonic() - t0 < 10
    assert _free()
    rows = _log_rows(phone)
    assert rows[-2]["ev"] == "line" and rows[-2]["why"] == "the call passed 1 s"


def test_the_report_says_the_caller_hung_up(phone, monkeypatch):  # noqa: F811
    for name in ("SILENCE_GAP_S", "TURN0_GAP_S", "SILENCE_REMIND_S", "SILENCE_HANGUP_S"):
        monkeypatch.setattr(tunables, name, 30)
    client = TestClient(server.app)
    with client.websocket_connect("/stream") as ws:
        _start(ws)
        _until(ws, "mark")
        ws.send_text(json.dumps({"event": "stop", "streamSid": "MZ1"}))
    assert _free()
    assert _log_rows(phone)[-2]["why"] == "the caller hung up"


# --- a dropped stream is opened again ---------------------------------------------------------

def test_the_answer_names_the_ask_again_address_only_when_on(monkeypatch):
    monkeypatch.setattr(server, "NGROK_DOMAIN", "line.test")
    client = TestClient(server.app)
    assert "action=" not in client.post("/answer").text
    monkeypatch.setattr(tunables, "LINE_RECONNECT", True)
    assert '<Connect action="https://line.test/answer-again" method="POST">' in client.post("/answer").text
    assert build_stream_twiml("wss://x/stream") == build_stream_twiml("wss://x/stream", again_url="")


def test_ask_again_for_a_call_we_do_not_hold_hangs_up(monkeypatch):
    monkeypatch.setattr(tunables, "LINE_RECONNECT", True)
    reply = TestClient(server.app).post("/answer-again", content="CallSid=CA_gone", headers=FORM)
    assert reply.status_code == 200 and reply.text == build_end_twiml()
    assert "<Hangup/>" in reply.text and "<Say" not in reply.text and "<Stream" not in reply.text


def test_ask_again_must_be_signed(signed, monkeypatch):
    monkeypatch.setattr(tunables, "LINE_RECONNECT", True)
    assert TestClient(server.app).post("/answer-again", content="CallSid=CA1", headers=FORM).status_code == 403


def test_a_dropped_stream_is_opened_again_and_the_talk_goes_on(kept):
    client = TestClient(server.app)
    with client.websocket_connect("/stream") as ws:
        _start(ws)
        first = _until(ws, "mark")          # the greeting is sent; its mark is never sent back
    greeting = first[-1]["mark"]["name"]
    line = server._LINE
    assert line is not None and line.dropped_at is not None and not line.finished
    assert server.is_call_active()          # the line is still this caller's

    reply = client.post("/answer-again", content="CallSid=CA42", headers=FORM)
    assert '<Stream url="wss://line.test/stream"' in reply.text and "<Hangup" not in reply.text

    with client.websocket_connect("/stream") as ws:
        _start(ws, stream="MZ2")
        again = _until(ws, "mark")
        assert again[-1]["mark"]["name"] == greeting                  # said again, under its old mark
        assert all(m["streamSid"] == "MZ2" for m in again)
        assert sum(len(m["media"]["payload"]) for m in again[:-1]) == \
            sum(len(m["media"]["payload"]) for m in first[:-1])       # the whole clip, from its start
        assert server._LINE is line and line.dropped_at is None and line.drops == 1
        ws.send_text(json.dumps({"event": "mark", "streamSid": "MZ2", "mark": {"name": greeting}}))
        ws.send_text(json.dumps({"event": "dtmf", "streamSid": "MZ2", "dtmf": {"digit": "3"}}))
        nxt = _until(ws, "mark")                                       # the same engine takes the key
        assert nxt[-1]["mark"]["name"].endswith(":opener_short_prompt")
        ws.send_text(json.dumps({"event": "stop", "streamSid": "MZ2"}))
    assert _free()
    rows = _log_rows(kept)
    assert sum("call_id" in r for r in rows) == 1                      # one call, one log
    assert {"lang": "en", "lang_source": "keypad", "turn_n": 0} in rows
    assert rows[-2]["ev"] == "line" and rows[-2]["drops"] == 1 and rows[-2]["why"] == "the caller hung up"


def test_a_stream_that_does_not_come_back_ends_the_call(kept, monkeypatch):
    monkeypatch.setattr(tunables, "LINE_RECONNECT_WAIT_S", 0.5)
    with TestClient(server.app).websocket_connect("/stream") as ws:
        _start(ws)
        _until(ws, "mark")
    assert server._LINE is not None
    assert _free()
    assert "did not come back" in _log_rows(kept)[-2]["why"]


def test_after_too_many_drops_the_caller_is_told(kept, monkeypatch):
    monkeypatch.setattr(tunables, "LINE_RECONNECT_TRIES", 1)
    client = TestClient(server.app)
    with client.websocket_connect("/stream") as ws:
        _start(ws)
        _until(ws, "mark")
    assert "<Stream" in client.post("/answer-again", content="CallSid=CA42", headers=FORM).text
    reply = client.post("/answer-again", content="CallSid=CA42", headers=FORM).text
    assert reply == build_end_twiml(line_dropped=True)
    assert "<Say" in reply and "Please call again." in reply and reply.rstrip().endswith("</Response>")
    assert _free()


def test_a_new_call_takes_the_line_from_a_dropped_one(kept):
    client = TestClient(server.app)
    with client.websocket_connect("/stream") as ws:
        _start(ws)
        _until(ws, "mark")
    old = server._LINE
    client.post("/answer", content="CallSid=CA43&From=%2B919811111111", headers=FORM)
    with client.websocket_connect("/stream") as ws:
        _start(ws, call="CA43", stream="MZ9")
        _until(ws, "mark")
        assert old.finished and server._LINE is not old and server._LINE.call_id == "CA43"
        ws.send_text(json.dumps({"event": "stop", "streamSid": "MZ9"}))
    assert _free()


def test_a_second_caller_is_still_refused_while_a_call_is_up(kept):
    client = TestClient(server.app)
    with client.websocket_connect("/stream") as ws:
        _start(ws)
        _until(ws, "mark")
        client.post("/answer", content="CallSid=CA43&From=%2B919811111111", headers=FORM)
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect("/stream") as other:
                _start(other, call="CA43", stream="MZ9")
                other.receive_json()
        assert closed.value.code == 1008
        assert server._LINE.call_id == "CA42" and not server._LINE.finished
        ws.send_text(json.dumps({"event": "stop", "streamSid": "MZ1"}))
    assert _free()
    server._CALLER_HASH.pop("CA43", None)
    server._CALLER_HASH_TS.pop("CA43", None)


# --- the mouth on a new stream -----------------------------------------------------------------

def test_rebind_says_again_only_what_was_not_played():
    old, new = [], []
    clock = [100.0]
    mouth = Mouth(old.append, "MZ1", clock=lambda: clock[0])
    mouth.play([("one", b"\x01" * 8000), ("two", b"\x02" * 4000)])
    marks = [m["mark"]["name"] for m in old if m["event"] == "mark"]
    mouth.on_mark(marks[0])                      # "one" played to its end
    assert mouth.ahead_max == pytest.approx(1.5)
    clock[0] = 110.0                             # the line was down for a while
    assert mouth.remaining() == 0.0
    assert mouth.rebind(new.append, "MZ2") == 1
    assert [m["event"] for m in new][-2:] == ["media", "mark"]
    assert new[-1]["mark"]["name"] == marks[1] and new[0]["streamSid"] == "MZ2"
    assert b"".join(base64.b64decode(m["media"]["payload"]) for m in new[:-1]) == b"\x02" * 4000
    assert mouth.remaining() == pytest.approx(0.5)
    mouth.on_mark(marks[1])
    assert mouth.remaining() == 0.0 and mouth.clip_heard("two")
    sent_before = len(old)
    mouth.play([("three", b"\x03" * 800)])       # later sound goes to the new stream
    assert len(old) == sent_before and new[-1]["mark"]["name"].endswith(":three")
    assert mouth.rebind(new.append, "MZ3") == 1  # nothing is lost on a second drop either


def test_a_late_piece_of_live_voice_is_logged_as_a_hole() -> None:
    """5 Oct: a piece of streamed voice that comes after the sound sent so far ran out is a hole
    the caller hears. The log says how long, and the end time of the clip moves with it."""
    from haqdaar.audio.mouth import Mouth

    now = [100.0]
    lines: list[str] = []
    mouth = Mouth(lambda m: None, "S", clock=lambda: now[0], log=lines.append)

    def pieces():
        yield b"\xff" * 4000          # 0.5 s of sound
        now[0] += 0.9                  # the next piece comes 0.4 s after that ran out
        yield b"\xff" * 4000

    mouth.play_stream("answer", pieces())
    assert any("ran dry for 400 ms" in x for x in lines), lines
    assert abs(mouth._play_until - 101.4) < 0.01
