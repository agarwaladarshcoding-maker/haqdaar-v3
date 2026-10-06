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


def build_stream_twiml(stream_url: str, keep_call_alive: bool = False, again_url: str = "") -> str:
    """Build TwiML XML to connect call to bidirectional WebSocket stream.
    
    Hard rule: keepCallAlive='false' (T14).
    `again_url` (step 1.0): asked by the line when the stream ends, so a dropped stream can be opened again.
    """
    keep_alive_str = "true" if keep_call_alive else "false"
    action = f' action="{again_url}" method="POST"' if again_url else ""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<Response>\n"
        f"  <Connect{action}>\n"
        f'    <Stream url="{stream_url}" keepCallAlive="{keep_alive_str}"/>\n'
        f"  </Connect>\n"
        f"</Response>"
    )


# Step 1.0: said by the line's own voice when a dropped stream can not be opened again. No clip of
# ours can be played then (our sound goes through the stream). Step 1.6 gives it recorded words.
LINE_DROPPED_WORDS: tuple[tuple[str, str], ...] = (
    ("hi-IN", "लाइन कट गई। कृपया फिर से कॉल करें।"),
    ("en-IN", "The line dropped. Please call again."),
)


def build_end_twiml(line_dropped: bool = False) -> str:
    """The reply that ends the call. `line_dropped`: first say so, in the line's own voice."""
    said = "".join(f'  <Say language="{lang}">{words}</Say>\n' for lang, words in LINE_DROPPED_WORDS)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<Response>\n"
        f"{said if line_dropped else ''}"
        f"  <Hangup/>\n"
        f"</Response>"
    )


SIGNATURE_HEADER = "X-Twilio-Signature"


def request_is_signed(url: str, form: dict[str, str], signature: str) -> bool:
    """True when `signature` is the provider's own for a request to `url` with these POST fields.

    HMAC-SHA1 of the url plus every field name and value (sorted by name), keyed with the account's
    auth token, in base64. No token in the environment: nothing can be checked, so False.
    """
    import hashlib
    import hmac
    import os

    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not token or not signature:
        return False
    text = url + "".join(k + form[k] for k in sorted(form))
    want = base64.b64encode(hmac.new(token.encode(), text.encode("utf-8"), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(want, signature)


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


def place_call(to_number: str, answer_url: str, opener: Any = None, status_url: str = "") -> str:
    """Ask the line to ring `to_number`; when picked up it fetches `answer_url`. Returns call SID.
    `status_url`: the line posts there how the call ended (no-answer, busy, failed, canceled, completed)."""
    import os

    form = {
        "To": to_number,
        "From": os.environ["TWILIO_US_PHONE_NUMBER"],
        "Url": answer_url,
        "Method": "POST",
    }
    if status_url:
        form["StatusCallback"] = status_url
        form["StatusCallbackMethod"] = "POST"
    if os.environ.get("CALL_RECORD", "").strip().lower() in ("1", "true", "yes", "on"):
        # 5 Oct: the sound cut on the phone while our own log showed none. The line's own record
        # of the call (caller on one side, us on the other) says on which side of it the cut is.
        form["Record"] = "true"
        form["RecordingChannels"] = "dual"
    return _api("Calls.json", form, opener)["sid"]


def send_sms(to_number: str, text: str, opener: Any = None) -> str:
    """Send one text message from the line's own number. Returns the message SID."""
    import os

    form = {"To": to_number, "From": os.environ["TWILIO_US_PHONE_NUMBER"], "Body": text}
    return _api("Messages.json", form, opener)["sid"]


def call_recording(call_sid: str = "") -> tuple[str, bytes]:
    """The line's own two-sided sound record of a call (the newest one when no id is given), as
    (call id, WAV bytes). ("", b"") when there is none: the call was not placed with CALL_RECORD."""
    import os
    import urllib.request

    path = f"Recordings.json?CallSid={call_sid}&PageSize=1" if call_sid else "Recordings.json?PageSize=1"
    found = _api(path)["recordings"]
    if not found:
        return "", b""
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Recordings/{found[0]['sid']}.wav?RequestedChannels=2"
    )
    auth = base64.b64encode(f"{sid}:{os.environ['TWILIO_AUTH_TOKEN']}".encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req) as resp:
        return found[0]["call_sid"], resp.read()


def recent_calls(limit: int = 5) -> list[dict[str, Any]]:
    """Last calls, newest first, each with its provider warnings under "notices"."""
    calls = _api(f"Calls.json?PageSize={limit}")["calls"]
    for c in calls:
        c["notices"] = _api(f"Calls/{c['sid']}/Notifications.json")["notifications"]
    return calls


def _line_number() -> dict[str, Any]:
    import os
    import urllib.parse

    number = urllib.parse.quote(os.environ["TWILIO_US_PHONE_NUMBER"])
    found = _api(f"IncomingPhoneNumbers.json?PhoneNumber={number}")["incoming_phone_numbers"]
    if not found:
        raise RuntimeError("line number not found on this account")
    return found[0]


def number_answers_at() -> str:
    """The URL the line's own number fetches now when someone dials in. Changes nothing."""
    return _line_number()["voice_url"]


def point_number_at(answer_url: str) -> str:
    """Set the line's own number to fetch `answer_url` when someone dials in. Returns the old URL."""
    found = _line_number()
    old = found["voice_url"]
    if old != answer_url:
        _api(f"IncomingPhoneNumbers/{found['sid']}.json",
             {"VoiceUrl": answer_url, "VoiceMethod": "POST"})
    return old
