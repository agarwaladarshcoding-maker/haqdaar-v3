"""tests/test_model.py

Unit tests for haqdaar/model/ (plan 4.2).
All tests are strictly offline and fake the HTTP layer (never touch the network).
Verifies:
- Span guard: values kept only if words appear in transcript ("farmer" must not add "low income").
- Failure accounting: timeout/429 counts as failure; 2 failures -> keypad-only.
- Never raises on any network/provider failure.
- Class precedence: META > ANSWER > CLARIFY > REPEAT > UNCLEAR.
- Opener alias fast-path and stamp extraction.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from haqdaar.contracts.types import (
    Answer,
    Clarify,
    Meta,
    Repeat,
    Stamp,
    Unclear,
)
from haqdaar.model.client import GroqModelClient, ModelClientResponse
from haqdaar.model.router import Model
from haqdaar.model.span_guard import (
    SpanGuard,
    is_box_compatible_span,
    is_value_in_closed_set,
    normalize_text,
    span_in_transcript,
)


# --- Helper fakes ------------------------------------------------------------

class FakeGroqClient(GroqModelClient):
    """Scripted fake GroqModelClient for deterministic offline testing."""

    def __init__(self, responses: list[ModelClientResponse] | None = None) -> None:
        super().__init__(api_key="fake_key_groq")
        self.responses: list[ModelClientResponse] = responses or []
        self.call_history: list[list[dict[str, str]]] = []

    def call(self, messages: list[dict[str, str]], task: str = "model_router") -> ModelClientResponse:
        self.call_history.append(messages)
        if self.responses:
            return self.responses.pop(0)
        return ModelClientResponse(success=True, data={})


class FakeCorpusWithAliases:
    """Mock corpus supporting alias_lookup and values."""

    def alias_lookup(self, text: str, lang: str = "en") -> tuple[str, ...]:
        lower = text.lower()
        if "kisan credit" in lower or "kcc" in lower:
            return ("S1",)
        if "atal pension" in lower or "apy" in lower:
            return ("apy",)
        return ()

    def values(self, box: str) -> tuple[str, ...]:
        if box == "occupation":
            return ("farmer", "artisan", "worker", "weaver")
        if box == "state":
            return ("MAHARASHTRA", "OTHER")
        if box == "gender":
            return ("female", "male", "other")
        return ()


# --- SpanGuard unit tests ----------------------------------------------------

def test_span_guard_normalization():
    """normalize_text handles NFC, nuktas, punctuation, and casing."""
    assert normalize_text("Hello, World!") == "hello world"
    # Hindi nukta: ज़ (U+091C + U+093C) folded to ज (U+091C)
    assert normalize_text("क़र्ज़") == "कर्ज"


def test_span_guard_string_containment():
    """span_in_transcript checks that span words exist in transcript."""
    tx = "I am a female farmer in Bihar looking for agriculture schemes."
    assert span_in_transcript(tx, "farmer")
    assert span_in_transcript(tx, "female farmer")
    assert span_in_transcript(tx, "Bihar")
    assert span_in_transcript(tx, "agriculture")

    # Not in transcript
    assert not span_in_transcript(tx, "low income")
    assert not span_in_transcript(tx, "Maharashtra")
    assert not span_in_transcript(tx, "doctor")
    assert not span_in_transcript(tx, "")


def test_span_guard_farmer_must_not_add_low_income():
    """CRITICAL: 'Farmer' must never smuggle in 'low income' (hallucinated extra box dropped)."""
    transcript = "I am a farmer from Bihar."

    # Model returns occupation=farmer (valid span) AND income_band=<100000 (hallucinated span)
    stamps = [
        Stamp(box="occupation", value="farmer", span="farmer"),
        Stamp(box="income_band", value="<100000", span="low income"),
    ]

    filtered = SpanGuard.filter_stamps(transcript, stamps)
    assert len(filtered) == 1
    assert filtered[0].box == "occupation"
    assert filtered[0].value == "farmer"

    # Even if model attempts to claim span='farmer' for income_band
    leak_stamp = Stamp(box="income_band", value="<100000", span="farmer")
    assert not SpanGuard.validate_stamp(transcript, leak_stamp)


def test_span_guard_box_compatibility():
    """is_box_compatible_span prevents cross-box keyword leakage."""
    assert is_box_compatible_span("income_band", "six lakh rupees")
    assert is_box_compatible_span("income_band", "50000")
    assert not is_box_compatible_span("income_band", "farmer")
    assert not is_box_compatible_span("income_band", "female")

    assert is_box_compatible_span("age", "19 years")
    assert is_box_compatible_span("age", "35")
    assert not is_box_compatible_span("age", "weaver")

    assert is_box_compatible_span("gender", "female")
    assert is_box_compatible_span("gender", "महिला")
    assert not is_box_compatible_span("gender", "farmer")


def test_span_guard_closed_set_validation():
    """Only values in the closed vocabulary or valid numbers/bands are accepted."""
    assert is_value_in_closed_set("occupation", "farmer")
    assert is_value_in_closed_set("occupation", "weaver")
    assert not is_value_in_closed_set("occupation", "software_engineer")

    assert is_value_in_closed_set("state", "MAHARASHTRA")
    assert is_value_in_closed_set("state", "OTHER")
    assert not is_value_in_closed_set("state", "CALIFORNIA")

    assert is_value_in_closed_set("category", "farming")
    assert is_value_in_closed_set("category", "education")
    assert not is_value_in_closed_set("category", "space_travel")


# --- Model failure accounting and keypad-only tests --------------------------

def test_model_initial_failure_state():
    """Model starts with 0 failures and keypad_only False."""
    model = Model()
    assert model.failures == 0
    assert not model.keypad_only


def test_model_timeout_counts_as_failure():
    """A timeout increments model failures and returns Unclear."""
    client = FakeGroqClient(
        responses=[
            ModelClientResponse(success=False, data=None, error="timeout", is_timeout=True)
        ]
    )
    model = Model(client=client)

    res = model.turn("I am a farmer", box="occupation")
    assert isinstance(res, Unclear)
    assert res.reason == "timeout"
    assert model.failures == 1
    assert not model.keypad_only


def test_model_429_counts_as_failure():
    """A 429 rate limit increments model failures and returns Unclear."""
    client = FakeGroqClient(
        responses=[
            ModelClientResponse(success=False, data=None, error="http_429", is_429=True)
        ]
    )
    model = Model(client=client)

    res = model.turn("I am a farmer", box="occupation")
    assert isinstance(res, Unclear)
    assert res.reason == "http_429"
    assert model.failures == 1
    assert not model.keypad_only


def test_model_two_failures_trigger_keypad_only():
    """2 failures trigger keypad-only mode for the rest of the call (no further network calls)."""
    client = FakeGroqClient(
        responses=[
            ModelClientResponse(success=False, data=None, error="http_429", is_429=True),
            ModelClientResponse(success=False, data=None, error="timeout", is_timeout=True),
            # Third call should NOT be consumed because keypad_only blocks network
            ModelClientResponse(success=True, data={"class": "ANSWER", "value": "farmer", "span": "farmer"}),
        ]
    )
    model = Model(client=client)

    # 1. First failure
    res1 = model.turn("I am a farmer", box="occupation")
    assert isinstance(res1, Unclear)
    assert model.failures == 1
    assert not model.keypad_only

    # 2. Second failure
    res2 = model.turn("I am a farmer", box="occupation")
    assert isinstance(res2, Unclear)
    assert model.failures == 2
    assert model.keypad_only

    # 3. Third turn: degraded to keypad-only, never reaches client
    res3 = model.turn("I am a farmer", box="occupation")
    assert isinstance(res3, Unclear)
    assert res3.reason == "keypad_only"
    # Client should only have been called twice
    assert len(client.call_history) == 2

    # Opener also respects keypad_only
    res_opener = model.opener("I am a farmer")
    assert isinstance(res_opener, Unclear)
    assert res_opener.reason == "keypad_only"
    assert len(client.call_history) == 2


def test_model_normal_unclear_is_not_failure():
    """A caller saying an unclear or off-topic statement is NOT a model failure."""
    client = FakeGroqClient(
        responses=[
            ModelClientResponse(success=True, data={"class": "UNCLEAR", "reason": "off_topic"})
        ]
    )
    model = Model(client=client)

    res = model.turn("blah blah blah", box="occupation")
    assert isinstance(res, Unclear)
    assert res.reason == "off_topic"
    assert model.failures == 0  # Still 0 failures!
    assert not model.keypad_only


# --- Model.turn classification and precedence tests --------------------------

def test_model_turn_answer_success():
    """Valid ANSWER returning in-transcript span produces typed Answer."""
    client = FakeGroqClient(
        responses=[
            ModelClientResponse(
                success=True,
                data={
                    "class": "ANSWER",
                    "box": "occupation",
                    "value": "farmer",
                    "span": "farmer",
                },
            )
        ]
    )
    model = Model(client=client)

    res = model.turn("I am a farmer looking for schemes", box="occupation")
    assert isinstance(res, Answer)
    assert res.box == "occupation"
    assert res.value == "farmer"
    assert res.span == "farmer"
    assert model.failures == 0


def test_model_turn_answer_span_drop():
    """ANSWER with hallucinated span not in transcript drops to Unclear."""
    client = FakeGroqClient(
        responses=[
            ModelClientResponse(
                success=True,
                data={
                    "class": "ANSWER",
                    "box": "income_band",
                    "value": "<100000",
                    "span": "low income",
                },
            )
        ]
    )
    model = Model(client=client)

    # Transcript has no "low income"
    res = model.turn("I am a farmer", box="income_band")
    assert isinstance(res, Unclear)
    assert res.reason == "span_drop"
    assert model.failures == 0  # Degraded politeness, not a model provider failure


def test_model_turn_meta_precedence():
    """META intent returns Meta command."""
    client = FakeGroqClient(
        responses=[
            ModelClientResponse(
                success=True,
                data={
                    "class": "META",
                    "command": "change_lang_mr",
                },
            )
        ]
    )
    model = Model(client=client)

    res = model.turn("मराठी मध्ये सांगा", box="occupation")
    assert isinstance(res, Meta)
    assert res.command == "change_lang_mr"


def test_model_turn_clarify():
    """CLARIFY returns Clarify(box)."""
    client = FakeGroqClient(
        responses=[
            ModelClientResponse(
                success=True,
                data={"class": "CLARIFY", "box": "occupation"},
            )
        ]
    )
    model = Model(client=client)

    res = model.turn("What does occupation mean?", box="occupation")
    assert isinstance(res, Clarify)
    assert res.box == "occupation"


def test_model_turn_repeat():
    """REPEAT returns Repeat()."""
    client = FakeGroqClient(
        responses=[
            ModelClientResponse(
                success=True,
                data={"class": "REPEAT"},
            )
        ]
    )
    model = Model(client=client)

    res = model.turn("Please say that again", box="occupation")
    assert isinstance(res, Repeat)


def test_model_turn_empty_transcript():
    """Empty or whitespace transcript immediately returns Unclear without API call."""
    client = FakeGroqClient()
    model = Model(client=client)

    res = model.turn("   ", box="occupation")
    assert isinstance(res, Unclear)
    assert res.reason == "empty_transcript"
    assert len(client.call_history) == 0


# --- Model.opener tests ------------------------------------------------------

def test_model_opener_alias_fast_path():
    """Exact alias match in corpus runs before model call."""
    corpus = FakeCorpusWithAliases()
    client = FakeGroqClient(
        responses=[
            ModelClientResponse(
                success=True,
                data={"stamps": [{"box": "occupation", "value": "farmer", "span": "farmer"}]},
            )
        ]
    )
    model = Model(corpus=corpus, client=client)

    stamps = model.opener("I want Kisan Credit Scheme as a farmer", lang="en")
    assert isinstance(stamps, list)
    boxes = {s.box for s in stamps}
    assert "scheme" in boxes
    assert "occupation" in boxes


def test_model_opener_demographic_extraction():
    """Opener extracts multiple demographic facets filtered by SpanGuard."""
    tx = "I am a female farmer in Bihar looking for agriculture schemes."
    client = FakeGroqClient(
        responses=[
            ModelClientResponse(
                success=True,
                data={
                    "stamps": [
                        {"box": "category", "value": "farming", "span": "agriculture"},
                        {"box": "state", "value": "OTHER", "span": "Bihar"},
                        {"box": "gender", "value": "female", "span": "female"},
                        {"box": "occupation", "value": "farmer", "span": "farmer"},
                        {"box": "income_band", "value": "<100000", "span": "poor"},  # Hallucinated!
                    ]
                },
            )
        ]
    )
    model = Model(client=client)

    stamps = model.opener(tx, lang="en")
    assert isinstance(stamps, list)
    # The hallucinated 'poor' income_band must be dropped
    assert len(stamps) == 4
    boxes = {s.box: s.value for s in stamps}
    assert boxes["category"] == "farming"
    assert boxes["state"] == "OTHER"
    assert boxes["gender"] == "female"
    assert boxes["occupation"] == "farmer"
    assert "income_band" not in boxes


def test_model_opener_empty_transcript():
    """Empty opener transcript returns empty list without calling API."""
    client = FakeGroqClient()
    model = Model(client=client)

    assert model.opener("") == []
    assert model.opener("   ") == []
    assert len(client.call_history) == 0


# --- Raw GroqModelClient network error handling (never raises) --------------

def test_groq_client_never_raises_on_http_error(monkeypatch, tmp_path):
    """GroqModelClient catches all HTTP status errors and exceptions without raising."""
    ledger = tmp_path / "groq_usage.jsonl"
    client = GroqModelClient(api_key="fake_key", ledger_path=ledger)

    # 1. 500 Server error
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *args, **kwargs: httpx.Response(500, request=httpx.Request("POST", "http://testserver")),
    )
    resp = client.call([{"role": "user", "content": "hello"}])
    assert not resp.success
    assert resp.error == "http_500"

    # 2. 429 Rate limit
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *args, **kwargs: httpx.Response(429, request=httpx.Request("POST", "http://testserver")),
    )
    resp = client.call([{"role": "user", "content": "hello"}])
    assert not resp.success
    assert resp.is_429
    assert resp.error == "http_429"

    # 3. Timeout exception
    def _timeout(*args, **kwargs):
        raise httpx.TimeoutException("Read timed out")

    monkeypatch.setattr(httpx.Client, "post", _timeout)
    resp = client.call([{"role": "user", "content": "hello"}])
    assert not resp.success
    assert resp.is_timeout
    assert resp.error == "timeout"

    # 4. JSON parse error
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not json at all"}}]},
            request=httpx.Request("POST", "http://testserver"),
        ),
    )
    resp = client.call([{"role": "user", "content": "hello"}])
    assert not resp.success
    assert resp.error == "json_parse_error"


def test_groq_client_missing_key_returns_error(tmp_path):
    """GroqModelClient returns error immediately when api_key is missing."""
    client = GroqModelClient(api_key="", ledger_path=tmp_path / "ledger.jsonl")
    resp = client.call([{"role": "user", "content": "test"}])
    assert not resp.success
    assert resp.error == "no_key"


def test_model_router_defensive_against_raising_custom_client():
    """A raising custom client is caught and converted to Unclear(reason=...) with failure increment."""
    class RaisingClient:
        def call(self, messages, task=""):
            raise RuntimeError("simulated client explosion")

    model = Model(client=RaisingClient())
    res_opener = model.opener("I need help with farming")
    assert isinstance(res_opener, Unclear)
    assert "client_exception" in res_opener.reason
    assert model.failures == 1

    res_turn = model.turn("farmer", box="occupation")
    assert isinstance(res_turn, Unclear)
    assert "client_exception" in res_turn.reason
    assert model.failures == 2
    assert model.keypad_only is True
