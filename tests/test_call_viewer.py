"""Step 5.5 — the call trace and the call page (`make calls-ui`).

The trace is the timed copy of a call; the page turns it into a back and forth. All offline.
"""
from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

from haqdaar.data.log import Log
from haqdaar.data.trace import Trace
from haqdaar.sim import run_sim
from tests.test_phone_call import _call, phone  # noqa: F401  (phone is a fixture)
from tools.call_viewer import Calls, Texts, build_call, make_app, read_calls


def _rows(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


# --- the trace -----------------------------------------------------------------------

def test_trace_rows_carry_seconds_since_the_call_started(tmp_path):
    now = [100.0]
    trace = Trace("c1", tmp_path, "snapX", clock=lambda: now[0])
    now[0] = 101.5
    trace("-> say greeting_trilingual (9.8 s)")
    now[0] = 112.25
    trace.record({"turn_n": 0, "class": "ANSWER", "transcript": "hi"})
    trace.close()
    trace("after close: dropped, not raised")

    rows = _rows(tmp_path / "trace" / "c1.jsonl")
    assert rows[0]["start"] == "c1" and rows[0]["snapshot"] == "snapX" and rows[0]["t"] == 0.0
    assert rows[1] == {"t": 1.5, "line": "-> say greeting_trilingual (9.8 s)"}
    assert rows[2] == {"t": 12.25, "log": {"turn_n": 0, "class": "ANSWER", "transcript": "hi"}}
    assert len(rows) == 3


def test_trace_never_raises_when_it_cannot_write(tmp_path):
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("x")
    trace = Trace("c1", blocker)  # the folder cannot be made
    trace("-> say x")
    trace.record({"a": 1})
    trace.close()


def test_the_log_hands_every_line_to_its_tap_and_stays_the_same(tmp_path):
    seen: list[dict] = []
    log = Log.open("c1", "snapX", logs_dir=tmp_path)
    log.tap = seen.append
    log.write({"mode": "keypad_only"})
    log.close("no_split")
    assert seen[0] == {"mode": "keypad_only"} and seen[1]["stop"] == "no_split"
    lines = _rows(tmp_path / "c1.jsonl")
    assert {"mode": "keypad_only"} in lines and not any("t" in row for row in lines[1:])


# --- trace -> the back and forth -------------------------------------------------------

TRACE = [
    {"t": 0.0, "start": "CA1", "at": "2026-10-02T23:50:01", "snapshot": "snapX"},
    {"t": 0.1, "line": "-> say greeting_trilingual (10.0 s)"},
    {"t": 4.0, "line": "<- key 2: language mr"},
    {"t": 4.0, "log": {"turn_n": 0, "class": "ANSWER", "transcript": "mr"}},
    {"t": 4.0, "log": {"lang": "mr", "lang_source": "keypad", "turn_n": 0}},
    {"t": 4.2, "line": "-> say consent_notice (5.0 s)"},
    {"t": 4.2, "line": "-> say opener_prompt (3.0 s)"},
    {"t": 15.2, "line": '<- speech "मला कृषी योजना हवी आहे" (mr, stt 0.42s)'},
    {"t": 15.3, "log": {"turn_n": 1, "class": "PROPOSAL", "box": "category", "value": "farming"}},
    {"t": 17.2, "line": "-> say confirm_yn_suffix (2.0 s)"},
    {"t": 21.0, "line": "<- key 1 (pre-queued)"},
    {"t": 21.0, "line": "<- key 1 (confirm)"},
    {"t": 21.0, "log": {"turn_n": 2, "class": "ANSWER", "box": "category", "value": "farming"}},
    {"t": 21.1, "line": "!! clip scheme:x:summary [mr] failed: KeyError('k')"},
    {"t": 21.2, "log": {"slug": "pm-kisan", "ending": "direct_match", "sections": ["summary"], "lang": "mr"}},
    {"t": 21.3, "line": "<- silence 1 (normal)"},
    {"t": 21.3, "log": {"turn_n": 2, "class": "SILENCE", "silence_n": 1}},
    {"t": 21.4, "log": {"mode": "keypad_only"}},
    {"t": 21.5, "log": {"stop": "survivors_le_4", "ladder_rung": 0, "mode": "keypad_only"}},
    {"t": 30.0, "line": "stop    caller hung up"},
    {"t": 30.1, "line": "call    CA1 finished"},
]


def _words(token, lang):
    return {"consent_notice": "हा कॉल रेकॉर्ड केला जात आहे.", "scheme:pm-kisan:name": "पीएम किसान"}.get(token, "")


def test_build_call_makes_a_back_and_forth_with_times():
    call = build_call(TRACE, _words)
    info, items = call["info"], call["items"]
    who = [i["who"] for i in items]
    assert who[:6] == ["ai", "caller", "ai", "caller", "ai", "caller"]

    greeting, pick, opener, speech, confirm, key = items[:6]
    assert greeting["dur"] == 10.0 and "reply_s" not in greeting
    # The caller pressed 2 six seconds before the greeting ended: a cut-in.
    assert pick["text"] == "pressed 2" and pick["lang"] == "mr" and pick["wait_s"] == -6.1
    assert pick["understood"] == "ANSWER" and pick["turn_n"] == 0
    # Two clips said in a row are one bubble; the words come from the lookup, in the new language.
    assert [p["token"] for p in opener["parts"]] == ["consent_notice", "opener_prompt"]
    assert opener["parts"][0]["text"] == "हा कॉल रेकॉर्ड केला जात आहे." and opener["dur"] == 8.0
    assert opener["reply_s"] == 0.2
    # The AI finished at 12.2 s; the speech was ready at 15.2 s.
    assert speech["kind"] == "speech" and speech["text"] == "मला कृषी योजना हवी आहे"
    assert speech["stt_s"] == 0.42 and speech["wait_s"] == 3.0
    assert speech["understood"] == "PROPOSAL · category = farming"
    assert confirm["reply_s"] == 2.0
    # The ear and the phone both noted the key: one bubble, not two.
    assert key["key"] == "1" and [i.get("key") for i in items].count("1") == 1

    texts = [i.get("text", "") for i in items]
    assert "read out: पीएम किसान · direct_match · summary" in texts
    assert any(i["who"] == "problem" and "clip scheme:x:summary" in i["text"] for i in items)
    assert any(i["who"] == "problem" and "keypad only" in i["text"] for i in items)
    assert info["lang"] == "mr" and info["turns"] == 2 and info["duration_s"] == 30.1
    assert info["problems"] == 2 and info["silences"] == 1 and info["unclear"] == 0
    assert info["stop"] == "survivors_le_4" and info["mode"] == "keypad_only"
    assert info["ended"] == "caller hung up" and info["finished"] is True
    assert info["ai_talk_s"] == 20.0 and info["slowest_reply_s"] == 2.0 and info["timed"] is True


def test_a_call_with_no_sound_shows_no_made_up_gaps():
    rows = [TRACE[0], {"t": 0.0, "line": "-> say greeting_trilingual"}, {"t": 0.0, "line": "-> say name:pm-kisan"},
            {"t": 0.0, "line": "<- key 1: language hi"}, {"t": 0.0, "line": "-> say opener_prompt"}]
    call = build_call(rows)
    assert call["info"]["timed"] is False and call["info"]["slowest_reply_s"] is None
    assert not any("wait_s" in i or "reply_s" in i for i in call["items"])
    assert [p["token"] for p in call["items"][0]["parts"]] == ["greeting_trilingual"]  # the mark is not speech
    assert call["info"]["finished"] is False


def test_read_calls_splits_a_reused_call_id_and_skips_a_half_written_line(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text('{"t": 0, "start": "x"}\n{"t": 1, "line": "a"}\n{"t": 0, "start": "x"}\n{"t": 2, "li', encoding="utf-8")
    calls = read_calls(path)
    assert [len(c) for c in calls] == [2, 1]


# --- a sim call and a phone call, end to end -------------------------------------------

def test_a_sim_call_shows_on_the_page(tmp_path, capsys):
    run_sim(canned_inputs=["2", "1", "0", "0", "0", "1", "1", "h"], call_id="sim_view", logs_dir=str(tmp_path))
    capsys.readouterr()
    client = TestClient(make_app([tmp_path], Texts(tmp_path / "no_snapshots")))

    assert "Haqdaar calls" in client.get("/").text
    listed = client.get("/api/calls").json()
    assert [c["key"] for c in listed] == ["sim_view"]
    assert listed[0]["source"] == "sim" and listed[0]["finished"] is True and listed[0]["live"] is False

    call = client.get("/api/calls/sim_view").json()
    first = call["items"][0]
    assert first["who"] == "ai" and first["parts"][0]["token"] == "greeting_trilingual"
    assert "हकदार" in first["parts"][0]["text"]  # fixed lines resolve with no snapshot on disk
    assert call["items"][1]["text"] == "pressed 2" and call["items"][1]["lang"] == "mr"
    # Every LOG record after the open line is in the trace, in order.
    log_rows = _rows(tmp_path / "sim_view.jsonl")[1:]
    traced = [r["log"] for r in _rows(tmp_path / "trace" / "sim_view.jsonl") if "log" in r]
    assert traced == log_rows

    assert client.get("/api/calls/nope").status_code == 404
    assert client.get("/api/calls/..%2F..%2Fsim_view").status_code == 404


def test_a_phone_call_is_traced_with_clip_lengths(phone):
    _call(["3", "1", "1"] + ["9"] * 8 + ["2", "2"])
    rows = _rows(phone / "calls" / "trace" / "CA42.jsonl")
    assert rows[0]["start"] == "CA42" and rows[0]["snapshot"] == "real"
    lines = [r["line"] for r in rows if "line" in r]
    # The test presses its keys at once, so the greeting is skipped; later clips carry a length.
    assert any(re.fullmatch(r"-> say \S+ \(\d+\.\d s\)", line) for line in lines)
    assert any(line.startswith("<- key 3: language en") for line in lines)
    assert lines[-2] == "call    CA42 finished"
    assert lines[-1].startswith("line    report: closed because we ended the call")   # step 1.0
    assert [r["t"] for r in rows] == sorted(r["t"] for r in rows)
    assert "9800000000" not in (phone / "calls" / "trace" / "CA42.jsonl").read_text()

    calls = Calls([phone / "calls"], Texts(phone / "snapshots")).all()
    info, items = calls["CA42"]["info"], calls["CA42"]["items"]
    assert info["source"] == "phone" and info["lang"] == "en" and info["finished"] and info["timed"]
    assert info["schemes"] and info["ai_talk_s"] > 0
    said = [p for i in items if i["who"] == "ai" for p in i["parts"]]
    assert all(p["text"] for p in said), [p["token"] for p in said if not p["text"]]
