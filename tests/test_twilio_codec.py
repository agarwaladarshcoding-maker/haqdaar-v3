"""tests/test_twilio_codec.py

Tests for telephony wire codec and endpoints (T05, T14, T19).
Proves parsing of all 6 inbound events, 3 outbound builders,
raw μ-law payload with no RIFF header, and stream behaviour.
"""
from __future__ import annotations
import base64
import json
import pytest
from fastapi.testclient import TestClient

from haqdaar.audio.telephony.twilio import (
    ConnectedEvent,
    StartEvent,
    MediaEvent,
    DtmfEvent,
    MarkEvent,
    StopEvent,
    parse_connected,
    parse_start,
    parse_media,
    parse_dtmf,
    parse_mark,
    parse_stop,
    parse_event,
    build_media,
    build_mark,
    build_clear,
    build_stream_twiml,
)
from haqdaar.contracts.tunables import (
    SAMPLE_RATE,
    TONE_FREQ_HZ,
    TONE_DURATION_S,
    NGROK_DOMAIN,
)
from haqdaar.server import app
from tools.tone import generate_tone, ulaw_to_pcm16


def test_parse_connected() -> None:
    sample = {
        "event": "connected",
        "protocol": "Call",
        "version": "1.0.0",
    }
    # Test specific parser and generic dispatcher
    ev1 = parse_connected(sample)
    ev2 = parse_event(json.dumps(sample))
    assert isinstance(ev1, ConnectedEvent)
    assert isinstance(ev2, ConnectedEvent)
    assert ev1.protocol == "Call"
    assert ev1.version == "1.0.0"


def test_parse_start() -> None:
    sample = {
        "event": "start",
        "sequenceNumber": "1",
        "streamSid": "MZ_test_stream",
        "start": {
            "accountSid": "AC_test_account",
            "streamSid": "MZ_test_stream",
            "callSid": "CA_test_call",
            "tracks": ["inbound"],
            "mediaFormat": {
                "encoding": "audio/x-mulaw",
                "sampleRate": 8000,
                "channels": 1,
            },
            "customParameters": {},
        },
    }
    ev = parse_event(sample)
    assert isinstance(ev, StartEvent)
    assert ev.stream_sid == "MZ_test_stream"
    assert ev.call_sid == "CA_test_call"
    assert ev.account_sid == "AC_test_account"
    assert ev.tracks == ["inbound"]
    assert ev.media_format["sampleRate"] == 8000


def test_parse_media() -> None:
    sample_payload = base64.b64encode(b"\xff\xff\xff\xff").decode("ascii")
    sample = {
        "event": "media",
        "sequenceNumber": "2",
        "streamSid": "MZ_test_stream",
        "media": {
            "track": "inbound",
            "chunk": "1",
            "timestamp": "120",
            "payload": sample_payload,
        },
    }
    ev = parse_event(sample)
    assert isinstance(ev, MediaEvent)
    assert ev.stream_sid == "MZ_test_stream"
    assert ev.payload == sample_payload
    assert ev.payload_bytes == b"\xff\xff\xff\xff"
    assert ev.track == "inbound"


def test_parse_dtmf() -> None:
    sample = {
        "event": "dtmf",
        "sequenceNumber": "3",
        "streamSid": "MZ_test_stream",
        "dtmf": {
            "track": "inbound_track",
            "digit": "1",
        },
    }
    ev = parse_event(sample)
    assert isinstance(ev, DtmfEvent)
    assert ev.stream_sid == "MZ_test_stream"
    assert ev.digit == "1"


def test_parse_mark() -> None:
    sample = {
        "event": "mark",
        "sequenceNumber": "4",
        "streamSid": "MZ_test_stream",
        "mark": {
            "name": "tone_end",
        },
    }
    ev = parse_event(sample)
    assert isinstance(ev, MarkEvent)
    assert ev.stream_sid == "MZ_test_stream"
    assert ev.name == "tone_end"


def test_parse_stop() -> None:
    sample = {
        "event": "stop",
        "sequenceNumber": "5",
        "streamSid": "MZ_test_stream",
        "stop": {
            "accountSid": "AC_test_account",
            "callSid": "CA_test_call",
        },
    }
    ev = parse_event(sample)
    assert isinstance(ev, StopEvent)
    assert ev.stream_sid == "MZ_test_stream"
    assert ev.call_sid == "CA_test_call"
    assert ev.account_sid == "AC_test_account"


def test_build_outbound_messages() -> None:
    stream_sid = "MZ_outbound_test"
    raw_audio = b"\xff" * 160  # 20ms of silence

    # 1. Media
    media_msg = build_media(stream_sid, raw_audio)
    assert media_msg["event"] == "media"
    assert media_msg["streamSid"] == stream_sid
    payload_decoded = base64.b64decode(media_msg["media"]["payload"])
    assert payload_decoded == raw_audio
    # Invariant: raw mu-law, no RIFF/WAV header
    assert not payload_decoded.startswith(b"RIFF")
    assert not payload_decoded.startswith(b"WAVE")

    # 2. Mark
    mark_msg = build_mark(stream_sid, "tone_end")
    assert mark_msg == {
        "event": "mark",
        "streamSid": stream_sid,
        "mark": {"name": "tone_end"},
    }

    # 3. Clear
    clear_msg = build_clear(stream_sid)
    assert clear_msg == {
        "event": "clear",
        "streamSid": stream_sid,
    }


def test_tone_generator_no_header() -> None:
    tone = generate_tone()
    expected_len = int(SAMPLE_RATE * TONE_DURATION_S)
    assert len(tone) == expected_len == 8000
    assert not tone.startswith(b"RIFF")
    assert not tone.startswith(b"WAVE")

    # Test decoding of tone samples to verify sine wave
    pcm_samples = [ulaw_to_pcm16(b) for b in tone[:100]]
    assert any(s > 0 for s in pcm_samples)
    assert any(s < 0 for s in pcm_samples)


def test_answer_twiml_and_health() -> None:
    client = TestClient(app)

    # /health
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json() == {"status": "ok"}

    # /answer
    answer_resp = client.post("/answer")
    assert answer_resp.status_code == 200
    assert answer_resp.headers["content-type"].startswith("text/xml")
    xml_text = answer_resp.text
    assert '<Stream url="wss://' in xml_text
    assert '/stream"' in xml_text
    assert 'keepCallAlive="false"' in xml_text
    # Invariant: stream URL takes no query string
    import re
    match = re.search(r'url="([^"]+)"', xml_text)
    assert match is not None
    assert "?" not in match.group(1)


def test_place_call_request(monkeypatch: pytest.MonkeyPatch) -> None:
    from haqdaar.audio.telephony import place_call
    import io
    import urllib.parse

    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_x")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_US_PHONE_NUMBER", "+14240000000")
    seen = {}

    def fake_open(req):
        seen["req"] = req
        return io.BytesIO(b'{"sid": "CA_new"}')

    assert place_call("+910000000000", "https://d.example/answer", fake_open) == "CA_new"
    req = seen["req"]
    assert req.full_url.endswith("/Accounts/AC_x/Calls.json")
    form = urllib.parse.parse_qs(req.data.decode())
    assert form["To"] == ["+910000000000"]
    assert form["Url"] == ["https://d.example/answer"]


def test_place_call_asks_for_a_sound_record_only_when_told(monkeypatch: pytest.MonkeyPatch) -> None:
    from haqdaar.audio.telephony import place_call
    import io
    import urllib.parse

    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_x")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_US_PHONE_NUMBER", "+14240000000")
    seen = {}

    def fake_open(req):
        seen["form"] = urllib.parse.parse_qs(req.data.decode())
        return io.BytesIO(b'{"sid": "CA_new"}')

    monkeypatch.delenv("CALL_RECORD", raising=False)
    place_call("+910000000000", "https://d.example/answer", fake_open)
    assert "Record" not in seen["form"]
    monkeypatch.setenv("CALL_RECORD", "true")
    place_call("+910000000000", "https://d.example/answer", fake_open)
    assert seen["form"]["Record"] == ["true"] and seen["form"]["RecordingChannels"] == ["dual"]


def test_recording_tool_finds_a_hole_between_sounds() -> None:
    import math
    import struct

    from tools.recording import holes

    def tone(ms: int) -> bytes:
        return b"".join(struct.pack("<h", int(8000 * math.sin(i * 0.5))) for i in range(8 * ms))

    pcm = tone(400) + b"\x00\x00" * (8 * 300) + tone(400) + b"\x00\x00" * (8 * 3000)
    assert holes(pcm, 8000) == [(0.4, 300)]      # the hole inside; the quiet at the end is not one
