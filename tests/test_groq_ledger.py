"""tests/test_groq_ledger.py

Unit tests for the Groq usage ledger written by GroqClient.call (p2_derive.py).
"""
from datetime import datetime
import json
from pathlib import Path

import httpx
import pytest

from haqdaar.contracts import tunables
from haqdaar.data.pipeline.p2_derive import GroqClient


class _FakeResponse:
    """Stands in for the httpx.Response GroqClient.call reads."""

    def __init__(self, payload: dict):
        self.status_code = 200
        self.headers: dict = {}
        self.text = json.dumps(payload)
        self._payload = payload

    def json(self):
        return self._payload


class _FakeHttpxClient:
    """Stands in for httpx.Client(...) used as a context manager."""

    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def post(self, *args, **kwargs):
        return _FakeResponse(self._payload)


def _patch_groq_response(monkeypatch: pytest.MonkeyPatch, payload: dict) -> None:
    """Make httpx.Client(...) return a fake client whose post() answers with payload."""
    monkeypatch.setattr(httpx, "Client", lambda timeout=None: _FakeHttpxClient(payload))


def test_call_writes_ledger_line_and_updates_totals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    payload = {
        "choices": [{"message": {"content": json.dumps({"ok": True})}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30},
    }
    _patch_groq_response(monkeypatch, payload)

    ledger_path = tmp_path / "groq_usage.jsonl"
    client = GroqClient(api_key="fake-key", ledger_path=ledger_path)

    result = client.call("system", "user", task="facets", slug="test-scheme")

    assert result == {"ok": True}
    assert client.requests == 1
    assert client.prompt_tokens == 120
    assert client.completion_tokens == 30

    lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["task"] == "facets"
    assert entry["slug"] == "test-scheme"
    assert entry["model"] == tunables.GROQ_MODEL
    assert entry["prompt_tokens"] == 120
    assert entry["completion_tokens"] == 30
    # ts must be a valid ISO-8601 timestamp
    datetime.fromisoformat(entry["ts"])


def test_call_without_usage_block_defaults_tokens_to_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    payload = {
        "choices": [{"message": {"content": json.dumps({"ok": True})}}],
        # No "usage" key at all.
    }
    _patch_groq_response(monkeypatch, payload)

    ledger_path = tmp_path / "groq_usage.jsonl"
    client = GroqClient(api_key="fake-key", ledger_path=ledger_path)

    client.call("system", "user", task="summary", slug="other-scheme")

    assert client.requests == 1
    assert client.prompt_tokens == 0
    assert client.completion_tokens == 0

    lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["task"] == "summary"
    assert entry["slug"] == "other-scheme"
    assert entry["prompt_tokens"] == 0
    assert entry["completion_tokens"] == 0
