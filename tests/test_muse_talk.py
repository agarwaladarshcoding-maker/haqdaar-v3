"""Muse as a talk-chain model: one try, the money guard kept, a failure moves the chain on."""
import json

from haqdaar.contracts import tunables
from haqdaar.data.pipeline import muse
from haqdaar.model import muse_talk
from haqdaar.model.client import GroqModelClient

MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def _ok(payload, key, timeout):
    _ok.seen = payload
    return 200, {"choices": [{"message": {"content": '```json\n{"action": "goodbye"}\n```'}}],
                 "usage": {"prompt_tokens": 3000, "completion_tokens": 100}}


def test_a_muse_reply_is_parsed_and_its_cost_goes_to_the_ledger(tmp_path):
    ledger = tmp_path / "muse_usage.jsonl"
    resp = muse_talk.call(MESSAGES, model="muse:small-one", post=_ok, ledger=ledger, api_key="k")
    assert resp.success and resp.data == {"action": "goodbye"}
    assert _ok.seen["model"] == "small-one" and _ok.seen["reasoning_effort"] == tunables.TALK_MUSE_EFFORT
    row = json.loads(ledger.read_text())
    assert row["model"] == "small-one" and row["inr"] > 0 and muse.spent_today_inr(ledger) == row["inr"]


def test_the_money_guard_and_every_failure_move_the_chain_on(tmp_path, monkeypatch):
    ledger = tmp_path / "muse_usage.jsonl"
    calls = []

    def post(payload, key, timeout):
        calls.append(1)
        return 500, "down"

    assert muse_talk.call(MESSAGES, model="muse:m", post=post, ledger=ledger, api_key="k").is_429
    muse.block_today(ledger)
    resp = muse_talk.call(MESSAGES, model="muse:m", post=post, ledger=ledger, api_key="k")
    assert resp.is_429 and resp.error == "muse_blocked" and len(calls) == 1    # blocked: nothing is sent
    muse.unblock(ledger)
    monkeypatch.setattr(tunables, "MUSE_DAILY_CAP_INR", 0.0)
    assert muse_talk.call(MESSAGES, model="muse:m", post=post, ledger=ledger, api_key="k").error == "muse_day_cap"
    assert muse_talk.call(MESSAGES, model="muse:m", post=post, ledger=ledger, api_key="").error == "no_key"


def test_a_muse_entry_of_the_chain_goes_to_muse(monkeypatch):
    seen = {}
    monkeypatch.setattr(muse_talk, "call", lambda messages, **k: seen.update(k) or "from muse")
    assert GroqModelClient(api_key="g").call(MESSAGES, task="talk", model="muse:m") == "from muse"
    assert seen["model"] == "muse:m"
