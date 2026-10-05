"""haqdaar/audio/telephony/__init__.py

Telephony package isolating wire protocol and vendor codecs (T05).
No files outside this package may reference vendor names.

D12 (plan 2.4): the events come from base.py; the functions come from the provider module
named by tunables.PHONE_PROVIDER. Everything outside this package imports from here only.
"""
from __future__ import annotations

import importlib

from haqdaar.audio.telephony.base import (
    PROVIDER_FUNCTIONS,
    ConnectedEvent,
    DtmfEvent,
    InboundEvent,
    MarkEvent,
    MediaEvent,
    StartEvent,
    StopEvent,
)
from haqdaar.contracts import tunables

provider = importlib.import_module(f"haqdaar.audio.telephony.{tunables.PHONE_PROVIDER}")
_missing = [name for name in PROVIDER_FUNCTIONS if not callable(getattr(provider, name, None))]
if _missing:
    raise ImportError(f"phone provider {tunables.PHONE_PROVIDER!r} lacks: {', '.join(_missing)}")

parse_event = provider.parse_event
build_media = provider.build_media
build_mark = provider.build_mark
build_clear = provider.build_clear
build_stream_twiml = provider.build_stream_twiml
build_end_twiml = provider.build_end_twiml
request_is_signed = provider.request_is_signed
number_answers_at = provider.number_answers_at
SIGNATURE_HEADER: str = provider.SIGNATURE_HEADER
place_call = provider.place_call
point_number_at = provider.point_number_at
recent_calls = provider.recent_calls
call_recording = provider.call_recording

__all__ = [
    "ConnectedEvent",
    "StartEvent",
    "MediaEvent",
    "DtmfEvent",
    "MarkEvent",
    "StopEvent",
    "InboundEvent",
    "parse_event",
    "build_media",
    "build_mark",
    "build_clear",
    "build_stream_twiml",
    "build_end_twiml",
    "request_is_signed",
    "number_answers_at",
    "SIGNATURE_HEADER",
    "place_call",
    "point_number_at",
    "recent_calls",
    "call_recording",
    "provider",
]
