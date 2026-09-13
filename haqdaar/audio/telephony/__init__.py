"""haqdaar/audio/telephony/__init__.py

Telephony package isolating wire protocol and vendor codecs (T05).
No files outside this package may reference vendor names.
"""
from __future__ import annotations

from haqdaar.audio.telephony.twilio import (
    ConnectedEvent,
    StartEvent,
    MediaEvent,
    DtmfEvent,
    MarkEvent,
    StopEvent,
    InboundEvent,
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
    place_call,
    point_number_at,
    recent_calls,
)

__all__ = [
    "ConnectedEvent",
    "StartEvent",
    "MediaEvent",
    "DtmfEvent",
    "MarkEvent",
    "StopEvent",
    "InboundEvent",
    "parse_connected",
    "parse_start",
    "parse_media",
    "parse_dtmf",
    "parse_mark",
    "parse_stop",
    "parse_event",
    "build_media",
    "build_mark",
    "build_clear",
    "build_stream_twiml",
    "place_call",
    "point_number_at",
    "recent_calls",
]
