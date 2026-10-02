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


# --- the day guard (owner, 2 Oct): ₹30 a day, and a block for the rest of the day ---

from datetime import datetime, timezone

from haqdaar.data.pipeline.muse import block_today, blocked_day, muse_day, spent_today_inr, unblock


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def test_the_spend_day_is_india_time_and_rolls_at_five_not_midnight():
    assert muse_day(_utc(2026, 10, 2, 17, 13)) == "2026-10-02"  # 22:43 IST
    assert muse_day(_utc(2026, 10, 2, 20, 0)) == "2026-10-02"   # 01:30 IST next date, same night
    assert muse_day(_utc(2026, 10, 2, 23, 29)) == "2026-10-02"  # 04:59 IST
    assert muse_day(_utc(2026, 10, 2, 23, 30)) == "2026-10-03"  # 05:00 IST: new day


def test_spent_today_counts_only_this_spend_day(tmp_path):
    ledger = tmp_path / "muse.jsonl"
    now = _utc(2026, 10, 2, 17, 0)
    rows = [
        {"ts": "2026-09-30T19:15:47.649549+00:00", "inr": 12.0},  # an older day
        {"ts": "2026-10-02T16:00:00+00:00", "inr": 4.0},           # today
        {"ts": "2026-10-02T02:00:00+00:00", "inr": 5.0},           # 07:30 IST, today
        {"inr": 1.5},                                               # no time: counts as today
    ]
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert spent_today_inr(ledger, now=now) == pytest.approx(10.5)
    assert spent_inr(ledger) == pytest.approx(22.5)


def test_the_daily_cap_stops_before_the_call(tmp_path):
    ledger = tmp_path / "muse.jsonl"
    ts = datetime.now(timezone.utc).isoformat()
    ledger.write_text(json.dumps({"ts": ts, "inr": tunables.MUSE_DAILY_CAP_INR}) + "\n")
    assert spent_inr(ledger) < tunables.MUSE_CAP_INR  # the all-time cap is not what trips
    c, sent = _client(tmp_path, [_reply({"ok": 1})])
    with pytest.raises(MuseBudgetError, match="daily cap"):
        c.call("sys", "user")
    assert sent == []


def test_old_spend_does_not_trip_the_daily_cap(tmp_path):
    ledger = tmp_path / "muse.jsonl"
    ledger.write_text(json.dumps({"ts": "2026-09-30T19:15:47+00:00", "inr": 45.0}) + "\n")
    c, sent = _client(tmp_path, [_reply({"ok": 1})])
    assert c.call("sys", "user") == {"ok": 1}


def test_a_block_shuts_muse_for_today_only(tmp_path):
    ledger = tmp_path / "muse.jsonl"
    c, sent = _client(tmp_path, [_reply({"ok": 1}), _reply({"ok": 2})])
    assert block_today(ledger, reason="quota done") == muse_day() == blocked_day(ledger)
    with pytest.raises(MuseBudgetError, match="blocked"):
        c.call("sys", "user")
    assert sent == []

    unblock(ledger)
    assert blocked_day(ledger) == ""
    assert c.call("sys", "user") == {"ok": 1}

    # A block written for an earlier day no longer holds.
    block_today(ledger, now=_utc(2026, 9, 30, 12))
    assert c.call("sys", "user") == {"ok": 2}


def test_the_translator_does_not_swallow_a_block(tmp_path):
    ledger = tmp_path / "muse.jsonl"
    block_today(ledger)
    c, sent = _client(tmp_path, [_reply({"text": "x"})])
    with pytest.raises(MuseBudgetError):
        MuseTranslator(client=c).translate("hello", "hi", slug="s", field="summary")
    assert sent == []
