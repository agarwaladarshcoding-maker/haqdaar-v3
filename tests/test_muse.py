"""Plan 3.4 — the Muse client: a hard rupee cap, a ledger, and 0-9 digits. No network."""
from __future__ import annotations

import json

import pytest

from haqdaar.contracts import tunables
from haqdaar.data.pipeline.muse import (
    MuseBudgetError,
    MuseClient,
    MuseTranslator,
    cost_inr,
    spent_inr,
)


def _reply(content: dict, prompt: int = 1000, completion: int = 500, total: int = 0):
    usage = {"prompt_tokens": prompt, "completion_tokens": completion}
    if total:
        usage["total_tokens"] = total
    return 200, {"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}], "usage": usage}


def _client(tmp_path, replies):
    sent = []

    def post(payload):
        sent.append(payload)
        return replies.pop(0)

    c = MuseClient(api_key="fake", ledger_path=tmp_path / "muse.jsonl", post=post, sleep=lambda s: None)
    return c, sent


def test_call_sends_high_reasoning_and_writes_the_ledger(tmp_path):
    c, sent = _client(tmp_path, [_reply({"ok": 1}, prompt=1000, completion=100, total=2100)])
    assert c.call("sys", "user", task="facets", slug="pm-kisan") == {"ok": 1}
    assert sent[0]["reasoning_effort"] == tunables.MUSE_REASONING_EFFORT == "high"
    assert sent[0]["model"] == "muse-spark-1.3-contributor"
    row = json.loads((tmp_path / "muse.jsonl").read_text())
    assert row["completion_tokens"] == 1100  # reasoning counted as output, from total_tokens
    assert row["inr"] == pytest.approx(cost_inr(1000, 1100), abs=1e-4)


def test_the_cap_stops_before_the_call(tmp_path, monkeypatch):
    ledger = tmp_path / "muse.jsonl"
    ledger.write_text(json.dumps({"inr": 59.0}) + "\n" + json.dumps({"inr": 1.0}) + "\n")
    assert spent_inr(ledger) == pytest.approx(60.0)
    c, sent = _client(tmp_path, [_reply({"ok": 1})])
    with pytest.raises(MuseBudgetError):
        c.call("sys", "user")
    assert sent == []  # refused before anything was sent


def test_a_429_waits_and_retries(tmp_path):
    c, sent = _client(tmp_path, [(429, "slow down"), _reply({"ok": 2})])
    assert c.call("s", "u") == {"ok": 2}
    assert len(sent) == 2


def test_translate_forces_plain_digits(tmp_path):
    c, sent = _client(tmp_path, [_reply({"translation": "दरवर्षी ६,००० रुपये"})])
    out = MuseTranslator(client=c).translate("6,000 rupees every year", "mr", slug="pm-kisan", field="summary")
    assert out == "दरवर्षी 6,000 रुपये"
    assert "Marathi" in sent[0]["messages"][0]["content"]
    assert "0-9" in sent[0]["messages"][0]["content"]
