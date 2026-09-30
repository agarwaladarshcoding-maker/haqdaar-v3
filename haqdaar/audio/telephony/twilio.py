"""haqdaar/audio/telephony/twilio.py

Twilio Media Streams protocol codec (T05, T14, T19).
Only telephony wire protocol details live here.

Inbound events: connected, start, media, dtmf, mark, stop.
Outbound events: media, mark, clear.
"""
from __future__ import annotations
import base64
import json
from typing import Any

# The events are the provider-neutral ones from base.py (D12); this file only maps Twilio's
# JSON onto them and back. Re-exported so `from ...twilio import StartEvent` keeps working.
from haqdaar.audio.telephony.base import (  # noqa: F401
    ConnectedEvent,
    DtmfEvent,
    InboundEvent,
    MarkEvent,
    MediaEvent,
    StartEvent,
    StopEvent,
)


def _to_dict(data: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(data, str):
        return json.loads(data)
    return data


def parse_connected(data: str | dict[str, Any]) -> ConnectedEvent:
    d = _to_dict(data)
    return ConnectedEvent(
        protocol=d.get("protocol", "Call"),
        version=d.get("version", "1.0.0"),
        raw=d,
    )


def parse_start(data: str | dict[str, Any]) -> StartEvent:
    d = _to_dict(data)
    start = d.get("start", {})
    stream_sid = d.get("streamSid") or start.get("streamSid", "")
    call_sid = start.get("callSid", "")
    account_sid = start.get("accountSid", "")
    tracks = start.get("tracks", [])
    media_format = start.get("mediaFormat", {})
    custom_params = start.get("customParameters", {})
    return StartEvent(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=account_sid,
        tracks=tracks,
        media_format=media_format,
        custom_parameters=custom_params,
        raw=d,
    )


def parse_media(data: str | dict[str, Any]) -> MediaEvent:
    d = _to_dict(data)
    media = d.get("media", {})
    stream_sid = d.get("streamSid", "")
    payload = media.get("payload", "")
    track = media.get("track", "inbound")
    chunk = str(media.get("chunk", ""))
    timestamp = str(media.get("timestamp", ""))
    return MediaEvent(
        stream_sid=stream_sid,
        payload=payload,
        track=track,
        chunk=chunk,
        timestamp=timestamp,
        raw=d,
    )


def parse_dtmf(data: str | dict[str, Any]) -> DtmfEvent:
    d = _to_dict(data)
    dtmf = d.get("dtmf", {})
    stream_sid = d.get("streamSid", "")
    digit = str(dtmf.get("digit", ""))
    track = dtmf.get("track", "")
    return DtmfEvent(
        stream_sid=stream_sid,
        digit=digit,
        track=track,
        raw=d,
    )


def parse_mark(data: str | dict[str, Any]) -> MarkEvent:
    d = _to_dict(data)
    mark = d.get("mark", {})
    stream_sid = d.get("streamSid", "")
    name = mark.get("name", "")
    return MarkEvent(
        stream_sid=stream_sid,
        name=name,
        raw=d,
    )


def parse_stop(data: str | dict[str, Any]) -> StopEvent:
    d = _to_dict(data)
    stop = d.get("stop", {})
    stream_sid = d.get("streamSid", "")
    call_sid = stop.get("callSid", "")
    account_sid = stop.get("accountSid", "")
    return StopEvent(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=account_sid,
        raw=d,
    )


def parse_event(data: str | dict[str, Any]) -> InboundEvent:
    d = _to_dict(data)
    event_type = d.get("event")
    if event_type == "connected":
        return parse_connected(d)
    elif event_type == "start":
        return parse_start(d)
    elif event_type == "media":
        return parse_media(d)
    elif event_type == "dtmf":
        return parse_dtmf(d)
    elif event_type == "mark":
        return parse_mark(d)
    elif event_type == "stop":
        return parse_stop(d)
    else:
        raise ValueError(f"Unknown telephony event: {event_type}")


def build_media(stream_sid: str, payload: str | bytes) -> dict[str, Any]:
    """Build outbound media event with base64 encoded audio payload (no RIFF/WAV header)."""
    if isinstance(payload, bytes):
        payload = base64.b64encode(payload).decode("ascii")
    return {
        "event": "media",
        "streamSid": stream_sid,
        "media": {
            "payload": payload,
        },
    }


def build_mark(stream_sid: str, name: str) -> dict[str, Any]:
    """Build outbound mark event to track playback checkpoint."""
    return {
        "event": "mark",
        "streamSid": stream_sid,
        "mark": {
            "name": name,
        },
    }


def build_clear(stream_sid: str) -> dict[str, Any]:
    """Build outbound clear event to stop currently buffered audio."""
    return {
        "event": "clear",
        "streamSid": stream_sid,
    }


def build_stream_twiml(stream_url: str, keep_call_alive: bool = False) -> str:
    """Build TwiML XML to connect call to bidirectional WebSocket stream.
    
    Hard rule: keepCallAlive='false' (T14).
    """
    keep_alive_str = "true" if keep_call_alive else "false"
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<Response>\n"
        f"  <Connect>\n"
        f'    <Stream url="{stream_url}" keepCallAlive="{keep_alive_str}"/>\n'
        f"  </Connect>\n"
        f"</Response>"
    )


def _api(path: str, data: dict[str, str] | None = None, opener: Any = None) -> dict[str, Any]:
    """Call the provider REST API with keys from the environment. Never logs secrets."""
    import os
    import urllib.parse
    import urllib.request

    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/{path}", data=body
    )
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    with (opener or urllib.request.urlopen)(req) as resp:
        return json.loads(resp.read())


def place_call(to_number: str, answer_url: str, opener: Any = None) -> str:
    """Ask the line to ring `to_number`; when picked up it fetches `answer_url`. Returns call SID."""
    import os

    form = {
        "To": to_number,
        "From": os.environ["TWILIO_US_PHONE_NUMBER"],
        "Url": answer_url,
        "Method": "POST",
    }
    return _api("Calls.json", form, opener)["sid"]


def recent_calls(limit: int = 5) -> list[dict[str, Any]]:
    """Last calls, newest first, each with its provider warnings under "notices"."""
    calls = _api(f"Calls.json?PageSize={limit}")["calls"]
    for c in calls:
        c["notices"] = _api(f"Calls/{c['sid']}/Notifications.json")["notifications"]
    return calls


def point_number_at(answer_url: str) -> str:
    """Set the line's own number to fetch `answer_url` when someone dials in. Returns the old URL."""
    import os
    import urllib.parse

    number = urllib.parse.quote(os.environ["TWILIO_US_PHONE_NUMBER"])
    found = _api(f"IncomingPhoneNumbers.json?PhoneNumber={number}")["incoming_phone_numbers"]
    if not found:
        raise RuntimeError("line number not found on this account")
    old = found[0]["voice_url"]
    if old != answer_url:
        _api(f"IncomingPhoneNumbers/{found[0]['sid']}.json",
             {"VoiceUrl": answer_url, "VoiceMethod": "POST"})
    return old
