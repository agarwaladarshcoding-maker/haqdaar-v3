"""Step 7.9: cut-ins on the real engine and audio code, on a virtual clock (tools/barge_eval.py).

Each test is one caller doing one thing at one moment of a whole call. No real waiting, no
network. The same run every time.
"""
from __future__ import annotations

import pytest

from haqdaar.contracts import tunables
from tools import barge_eval as be


def _agent(res: be.Result) -> list[str]:
    """What the caller really heard, in order (clips cut before they began are left out)."""
    return [c["name"] for c in res.clips if (c["cut_at"] if c["cut_at"] is not None else c["end"]) > c["start"]]


def test_the_plain_call_runs_to_the_goodbye():
    for script in be.SCRIPTS:
        res = be.run_call(script, "voice_qa")
        assert res.error == "" and res.closed_at is not None, script
        assert _agent(res)[-1] == "closing_farewell", script
        assert sum(1 for r in res.log_rows if "stop" in r) == 1, script


def test_the_same_run_every_time():
    a, _ = be.run_case("question", "voice_qa", "scheme:S1:summary", 600, "voice_question")
    b, _ = be.run_case("question", "voice_qa", "scheme:S1:summary", 600, "voice_question")
    assert a == b


# --- a real cut-in ---------------------------------------------------------------------


def test_a_spoken_question_stops_the_summary_fast_and_is_answered():
    row, res = be.run_case("keys", "voice_qa", "scheme:S1:summary", 600, "voice_question")
    assert row["stopped"] and row["cut_clip"] == "scheme:S1:summary"
    assert row["stop_ms"] <= 300                      # good voice agents: 200-300 ms
    assert row["heard_texts"] == [be.QUESTION]        # whole, once
    assert row["questions"] == 1 and "answer" in _agent(res)
    assert row["heard_ms_err"] <= 60                  # the log knows how much was heard


def test_a_key_stops_the_agent_at_once():
    row, _ = be.run_case("keys", "keys_only", "scheme:S1:summary", 600, "key_valid")
    assert row["stopped"] and row["stop_ms"] <= 50


# --- things that are not an input ------------------------------------------------------


def test_a_short_cough_does_not_stop_the_agent():
    row, _ = be.run_case("keys", "voice_qa", "scheme:S1:summary", 500, "cough")
    assert not row["stopped"]


def test_two_short_coughs_do_not_add_up_to_a_cut():
    row, _ = be.run_case("keys", "voice_qa", "scheme:S1:name", 300, "two_coughs")
    assert not row["stopped"]


@pytest.mark.parametrize("kind", ["cough_long", "backchannel"])
def test_a_long_cough_or_hmm_over_the_summary_loses_nothing(kind):
    row, res = be.run_case("keys", "voice_qa", "scheme:S1:summary", 500, kind)
    assert row["stopped"] and row["said_again"]       # cut, then said again from the start of the clip
    assert row["false_cut"] == 1
    assert row["extra_noise"] == 0 and row["extra_unclear"] == 0 and row["extra_turns"] == 0
    plain = _agent(be.run_call("keys", "voice_qa"))
    assert _agent(res).count("unclear_prompt") == plain.count("unclear_prompt")   # not told off for a cough


def test_a_long_cough_at_a_question_costs_no_turn_and_asks_once():
    row, res = be.run_case("keys", "voice_qa", "state_q_maharashtra", 700, "cough_long")
    assert row["said_again"] and row["extra_noise"] == 0 and row["extra_turns"] == 0
    assert row["said_twice"] == ""
    assert _agent(res).count("state_q_maharashtra") == 2   # the cut one, then once more


def test_a_room_that_keeps_coughing_cannot_hold_the_call():
    """After CUT_IN_FALSE_MAX false cuts in one wait the sound is a noise; the line drops it."""
    be.KINDS["_coughs"] = dict(
        acts=[be._say("", 0.6), be._say("", 0.6, 3.0), be._say("", 0.6, 6.0), be._say("", 0.6, 9.0)],
        answers=True, voice=True)
    try:
        row, res = be.run_case("keys", "voice_qa", "state_q_maharashtra", 700, "_coughs")
    finally:
        del be.KINDS["_coughs"]
    assert res.error == "" and row["closed"] and row["n_stop"] == 1
    # two false cuts in the first wait, then the third cough is a noise: dropped, never a turn
    assert row["false_cut"] >= tunables.CUT_IN_FALSE_MAX and row["extra_noise"] == 0


def test_hmm_at_a_yes_no_is_said_again_but_a_word_is_an_answer():
    row, _ = be.run_case("keys", "voice_qa", "anything_else", 700, "backchannel")
    assert row["false_cut"] == 1 and row["said_again"]
    row, _ = be.run_case("keys", "voice_qa", "anything_else", 700, "voice_yes")
    assert row["false_cut"] == 0 and row["heard_texts"] == ["yes"]


# --- keys ------------------------------------------------------------------------------


def test_a_key_pressed_twice_fast_does_not_wipe_the_scheme():
    """The first press lands in the guard and is dropped; the second used to cut everything
    queued (name, summary, menu) and then be dropped too: 13 s of dead air."""
    row, res = be.run_case("spoken", "keys_only", "results_exact_preamble", 200, "key_twice")
    assert not row["stopped"]
    assert row["max_quiet_ms"] < be.DEAD_AIR_MS
    assert "scheme:S4:summary" in _agent(res)


def test_a_key_during_the_goodbye_does_not_chop_it():
    for kind in ("key_valid", "key_three_fast", "key_hash"):
        row, _ = be.run_case("keys", "keys_only", "closing_farewell", 800, kind)
        assert row["farewell"] == "whole", kind


@pytest.mark.parametrize("kind", ["key_hash", "key_star"])
def test_hash_and_star_say_the_question_once(kind):
    row, res = be.run_case("keys", "keys_only", "q_gender", 1200, kind)
    said = _agent(res)
    assert said.count("q_gender") == 2                # the cut one, then once more (not twice more)
    assert row["said_twice"] == ""


def test_a_key_beats_the_words_said_with_it():
    row, _ = be.run_case("keys", "voice_qa", "state_q_maharashtra", 700, "voice_then_key")
    assert row["first_got"][0] == "Digit"


# --- the sample matrix -----------------------------------------------------------------


def test_quick_matrix_every_call_ends_cleanly(tmp_path):
    rows, checks = be.run_eval(quick=True, workers=1, out_dir=tmp_path)
    assert len(rows) > 400
    bad = [r["id"] for r in rows if r["error"] or not r["closed"] or r["n_stop"] != 1]
    assert not bad, bad[:5]
    status = {c["id"]: c["status"] for c in checks}
    for cid in ("C1", "C2", "C3", "C5a", "C6a", "C6b", "C9", "C10", "C11", "C12", "C13"):
        assert status[cid] == "pass", (cid, status[cid])
    assert (tmp_path / "scorecard.md").exists() and (tmp_path / "results.jsonl").exists()


# --- T1: total quiet, with the real 30 s and 60 s ---------------------------------------


def _quiet_call(monkeypatch, script):
    monkeypatch.setitem(be.SCRIPTS, "gone", script)
    return be.run_call("gone", "keys_only", remind_s=30.0, hangup_s=60.0)


def _quiet_before_goodbye(res):
    """Seconds from the end of the last clip said before the goodbye (at the opener that is the
    key list, which runs on after opener_prompt) to the start of the goodbye."""
    bye = next(c for c in res.clips if c["name"] == "closing_farewell")
    return bye["start"] - max(c["end"] for c in res.clips if c["end"] <= bye["start"])


def _gap_after(res, before_name, after_name, nth=0):
    """Seconds from the end of the nth clip `before_name` to the start of the next `after_name`."""
    ends = [c["end"] for c in res.clips if c["name"] == before_name]
    start = next(c["start"] for c in res.clips if c["name"] == after_name and c["start"] >= ends[nth])
    return start - ends[nth]


@pytest.mark.parametrize("script,prompt,again", [
    # quiet at the opener: the second time round it is the long opener that brings the key list
    (["3", "s", "s"], "opener_short_prompt", "opener_prompt"),
    (["3", "1", "s", "s"], "state_q_maharashtra", "state_q_maharashtra"),   # quiet at the first question
])
def test_total_quiet_reminder_at_30_s_and_goodbye_at_60_s(monkeypatch, script, prompt, again):
    res = _quiet_call(monkeypatch, script)
    assert res.error == "" and res.closed_at is not None
    said = _agent(res)
    assert said.count("waiting_for_reply") == 1 and said[-1] == "closing_farewell"
    # the reminder comes 30 s after the prompt ends, then the prompt again (at the opener: the key
    # list), then 30 s more counted from the end of what was said last
    assert _gap_after(res, prompt, "waiting_for_reply") == pytest.approx(30.0, abs=1.0)
    assert _quiet_before_goodbye(res) == pytest.approx(30.0, abs=1.0)
    assert again in said[said.index("waiting_for_reply"):]


def test_total_quiet_at_the_language_pick_replays_the_greeting_then_says_goodbye(monkeypatch):
    def quiet_greeting(world, caller):
        caller.script[0] = "s"
    monkeypatch.setitem(be.SCRIPTS, "gone", ["s", "s"])
    res = be.run_call("gone", "keys_only", inject=quiet_greeting, remind_s=30.0, hangup_s=60.0)
    said = _agent(res)
    assert said.count("greeting_trilingual") == 2 and "waiting_for_reply" not in said
    assert said[-1] == "closing_farewell"
    assert _gap_after(res, "greeting_trilingual", "greeting_trilingual") == pytest.approx(30.0, abs=1.0)


def _cough_call(monkeypatch, script, cough_at, inject_kind="cough"):
    def cough(world, caller):
        for t in cough_at:
            world.at(be.T0 + t, lambda: caller.speak(world.now, 0.4, "", level=be.LOUD))
    monkeypatch.setitem(be.SCRIPTS, "gone", script)
    return be.run_call("gone", "keys_only", inject=cough, remind_s=30.0, hangup_s=60.0)


def test_a_noise_is_not_a_reply_the_wait_does_not_move(monkeypatch):
    """Quiet, with a cough (no words) in the first wait: the reminder still comes 30 s after the
    prompt ends and the call ends at about 60 s, as if it were fully quiet."""
    res = _cough_call(monkeypatch, ["3", "s", "s"], [10.0])
    said = _agent(res)
    assert res.error == "" and said[-1] == "closing_farewell"
    assert said.count("waiting_for_reply") == 1
    assert _gap_after(res, "opener_short_prompt", "waiting_for_reply") == pytest.approx(30.0, abs=1.5)
    # the second quiet runs from the end of the key list, which the opener says after the reminder
    assert "opener_prompt" in said
    assert _quiet_before_goodbye(res) == pytest.approx(30.0, abs=1.5)


def test_coughs_in_both_waits_do_not_stretch_the_call(monkeypatch):
    res = _cough_call(monkeypatch, ["3", "s", "s"], [10.0, 25.0, 45.0, 70.0])
    said = _agent(res)
    assert said.count("waiting_for_reply") == 1 and said[-1] == "closing_farewell"
    assert "opener_prompt" in said
    assert _quiet_before_goodbye(res) <= 45.0   # the second wait runs from the end of the key list


def test_a_cough_at_the_language_pick_is_not_a_reply(monkeypatch):
    def quiet_greeting(world, caller):
        caller.script[0] = "s"
        world.at(be.T0 + 12.0, lambda: caller.speak(world.now, 0.4, "", level=be.LOUD))
    monkeypatch.setitem(be.SCRIPTS, "gone", ["s", "s"])
    res = be.run_call("gone", "keys_only", inject=quiet_greeting, remind_s=30.0, hangup_s=60.0)
    said = _agent(res)
    assert said.count("greeting_trilingual") == 2 and said[-1] == "closing_farewell"
    assert _gap_after(res, "greeting_trilingual", "greeting_trilingual") == pytest.approx(30.0, abs=1.5)
    assert _gap_after(res, "greeting_trilingual", "closing_farewell", nth=1) == pytest.approx(30.0, abs=1.5)


def test_real_words_after_a_cough_still_start_the_count_again(monkeypatch):
    def cough_then_words(world, caller):
        world.at(be.T0 + 10.0, lambda: caller.speak(world.now, 0.4, "", level=be.LOUD))
        world.at(be.T0 + 40.0, lambda: caller.speak(world.now, 1.5, "hello", level=be.LOUD))
    monkeypatch.setitem(be.SCRIPTS, "gone", ["3", "s", "s", "s", "s"])
    res = be.run_call("gone", "voice_qa", inject=cough_then_words, remind_s=30.0, hangup_s=60.0)
    assert res.error == "" and res.closed_at is not None
    assert _agent(res).count("waiting_for_reply") == 2   # one before the words, one after
    assert res.closed_at - be.T0 > 100.0                  # the words at 40 s started the count again
