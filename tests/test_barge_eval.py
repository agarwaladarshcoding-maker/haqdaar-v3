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
    """After CUT_IN_FALSE_MAX false cuts in one wait the sound goes to the engine as before."""
    be.KINDS["_coughs"] = dict(
        acts=[be._say("", 0.6), be._say("", 0.6, 3.0), be._say("", 0.6, 6.0), be._say("", 0.6, 9.0)],
        answers=True, voice=True)
    try:
        row, res = be.run_case("keys", "voice_qa", "state_q_maharashtra", 700, "_coughs")
    finally:
        del be.KINDS["_coughs"]
    assert res.error == "" and row["closed"] and row["n_stop"] == 1
    # two false cuts in the first wait, then the third cough reaches the engine as noise
    assert row["false_cut"] >= tunables.CUT_IN_FALSE_MAX and row["extra_noise"] >= 1


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
    assert row["max_quiet_ms"] < 9000
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
