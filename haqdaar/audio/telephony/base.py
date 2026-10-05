"""haqdaar/audio/telephony/base.py

D12 (plan 2.4) — what any phone provider must give the rest of the code.

The call only ever needs: the six events a live call sends us, three things we send back
(audio, a playback mark, "stop playing"), the reply that tells the provider to open the audio
stream, and three account actions for the tools (ring a number, point the line at us, list
recent calls). The events are plain data and live here, so they belong to no provider.
A provider is a module in this package with every name in PROVIDER_FUNCTIONS;
`PHONE_PROVIDER` picks which one. An Indian provider is one more file.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Union


@dataclass(frozen=True)
class ConnectedEvent:
    protocol: str = "Call"
    version: str = "1.0.0"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StartEvent:
    stream_sid: str
    call_sid: str
    account_sid: str
    tracks: list[str] = field(default_factory=list)
    media_format: dict[str, Any] = field(default_factory=dict)
    custom_parameters: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaEvent:
    stream_sid: str
    payload: str  # base64 encoded string
    track: str = "inbound"
    chunk: str = ""
    timestamp: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def payload_bytes(self) -> bytes:
        return base64.b64decode(self.payload)


@dataclass(frozen=True)
class DtmfEvent:
    stream_sid: str
    digit: str
    track: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarkEvent:
    stream_sid: str
    name: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StopEvent:
    stream_sid: str
    call_sid: str = ""
    account_sid: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


InboundEvent = Union[
    ConnectedEvent, StartEvent, MediaEvent, DtmfEvent, MarkEvent, StopEvent
]

# Every provider module defines these, with these parameters (checked by
# tests/test_telephony_conformance.py):
#   parse_event(data) -> InboundEvent          one raw message from the call's socket
#   build_media(stream_sid, payload) -> dict   8 kHz mu-law audio to play
#   build_mark(stream_sid, name) -> dict       tell me when playback reaches here
#   build_clear(stream_sid) -> dict            drop everything queued (a key was pressed)
#   build_stream_twiml(stream_url, keep_call_alive=False, again_url="") -> str
#                                              the /answer reply that opens the stream
#   build_end_twiml(line_dropped=False) -> str the reply that ends the call
#   request_is_signed(url, form, signature) -> bool            the request came from the provider
#   number_answers_at() -> str                 where dial-ins go now; changes nothing
#   place_call(to_number, answer_url, opener=None) -> str      ring a number; call id
#   point_number_at(answer_url) -> str         dial-ins go to answer_url; old url
#   recent_calls(limit=5) -> list[dict]        newest first
#   call_recording(call_sid="") -> (call id, WAV bytes)        the line's own sound record of a call
PROVIDER_FUNCTIONS: dict[str, tuple[str, ...]] = {
    "parse_event": ("data",),
    "build_media": ("stream_sid", "payload"),
    "build_mark": ("stream_sid", "name"),
    "build_clear": ("stream_sid",),
    "build_stream_twiml": ("stream_url", "keep_call_alive", "again_url"),
    "build_end_twiml": ("line_dropped",),
    "request_is_signed": ("url", "form", "signature"),
    "number_answers_at": (),
    "place_call": ("to_number", "answer_url", "opener"),
    "point_number_at": ("answer_url",),
    "recent_calls": ("limit",),
    "call_recording": ("call_sid",),
}
