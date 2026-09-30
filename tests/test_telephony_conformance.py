"""Plan 2.4 (D12) — every phone provider gives the same functions and the same events."""
from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

import haqdaar.audio.telephony as telephony
from haqdaar.audio.telephony import base

PROVIDERS = [
    m.name for m in pkgutil.iter_modules(telephony.__path__) if m.name != "base"
]


def test_twilio_is_a_provider():
    assert "twilio" in PROVIDERS


@pytest.mark.parametrize("name", PROVIDERS)
def test_provider_has_every_function_with_the_right_parameters(name):
    module = importlib.import_module(f"haqdaar.audio.telephony.{name}")
    for fn_name, params in base.PROVIDER_FUNCTIONS.items():
        fn = getattr(module, fn_name, None)
        assert callable(fn), f"{name} lacks {fn_name}"
        assert tuple(inspect.signature(fn).parameters) == params, f"{name}.{fn_name}"


def test_twilio_events_are_the_shared_ones():
    from haqdaar.audio.telephony import twilio

    ev = twilio.parse_event({"event": "dtmf", "streamSid": "S", "dtmf": {"digit": "5"}})
    assert type(ev) is base.DtmfEvent and ev.digit == "5"
    assert twilio.StartEvent is base.StartEvent


def test_the_package_serves_the_chosen_provider():
    assert telephony.provider.__name__.endswith("." + telephony.tunables.PHONE_PROVIDER)
    assert telephony.build_clear is telephony.provider.build_clear


def test_nothing_outside_telephony_names_a_vendor():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "haqdaar"
    for path in root.rglob("*.py"):
        if "telephony" in path.parts:
            continue
        text = path.read_text(encoding="utf-8").lower()
        assert "telephony.twilio" not in text, f"{path} imports the vendor module directly"
