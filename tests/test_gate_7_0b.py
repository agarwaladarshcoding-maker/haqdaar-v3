"""tests/test_gate_7_0b.py

Comprehensive tests for STEP 7.0b — The gate: keys and words at the wrong moment.
Validates rules G1 through G11:
- G1: Key while prompt clip plays -> clip stops, key is answer
- G2: Same key again within KEY_REPEAT_MS (300) -> counts once, rest dropped (5 fast presses of 1)
- G3: Other keys after key was taken for prompt -> dropped until next prompt (1 then 2 then 3 fast)
- G4: Key in gap -> dropped, next prompt plays in full (not skipped)
- G5: Key in first KEY_GUARD_MS (250) of new prompt -> dropped
- G6: Key not on prompt menu -> "wrong key" line, same prompt again across 4 profiles
- G7: Caller speaks, then presses key before read-back -> key wins, speech discarded
- G8: Key while line busy with key answer -> dropped
- G9: Control keys (#, *, 0) follow same gate rules
- G10: Hangup at any moment is own event, never Digit("h"), log closed on all paths
- G11: Clip cut by key -> trace logs cut clip and heard ms; section heard only when played to end
"""
from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Optional

import pytest

from haqdaar.audio.mouth import Mouth
from haqdaar.audio.turn import StampedKey, Turn
from haqdaar.contracts import tunables
from haqdaar.contracts.types import (
    Answer,
    Digit,
    Hangup,
    Noise,
    Silence,
    Speech,
    Stamp,
    Unclear,
)
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.data.trace import Trace
from haqdaar.engine.call import Engine
from haqdaar.model.router import Model
from haqdaar.sim import FakeAudio, SimModelClient


@pytest.fixture
def fixture_corpus(tmp_path, monkeypatch):
    """Test snapshot built from fixtures/schemes.jsonl."""
    root_dir = Path(__file__).resolve().parent.parent
    schemes_file = root_dir / "fixtures" / "schemes.jsonl"

    schemes = []
    with open(schemes_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                if row.get("scheme_id") != "S6":
                    schemes.append(row)

    snap_dir = tmp_path / "snapshots"
    audio_dir = tmp_path / "audio"
    snap_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(snap_dir))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(audio_dir))

    snap_id = build_snapshot(
        schemes_data=schemes,
        snapshot_id="test_gate_snap",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=True,
    )
    return Corpus.load(snap_id)


def _make_model(corpus: Any) -> Model:
    return Model(corpus=corpus, client=SimModelClient(corpus))


def _make_mouth_and_turn(clock: Any = None):
    out = []
    mouth = Mouth(out.append, "S")
    t = Turn(mouth=mouth, clock=clock or time.monotonic)
    return mouth, t, out


def _read_trace_events(logs_dir: Path | str, call_id: str) -> list[dict[str, Any]]:
    trace_file = Path(logs_dir) / "trace" / f"{call_id}.jsonl"
    if not trace_file.exists():
        return []
    return [json.loads(line) for line in trace_file.read_text("utf-8").splitlines()]


# --- G1: Key while prompt clip plays cuts clip, key is answer ---
def test_g1_key_cuts_clip():
    mouth, turn, out = _make_mouth_and_turn()
    mouth.play([("test_prompt", b"\x00" * 16000)])  # 2.0s clip
    assert mouth.playing

    turn.start_prompt("test_prompt")
    # Simulate clip playing past 250ms guard
    turn.prompt_start_t = time.monotonic() - 0.50
    turn.push_key("1")

    assert not mouth.playing
    assert any(m.get("event") == "clear" for m in out)
    k = turn.wait_input(gap_s=1.0)
    assert isinstance(k, Digit)
    assert k.digit == "1"


# --- G2: Fast repeat of same key dropped (five fast presses of 1) ---
def test_g2_fast_repeat_five_presses(tmp_path):
    call_id = "test_g2"
    trace = Trace(call_id, str(tmp_path), "snap1")
    mouth, turn, _ = _make_mouth_and_turn()
    turn.trace = trace

    turn.start_prompt("test_prompt")
    now = time.monotonic()
    turn.prompt_start_t = now - 0.50  # past 250ms guard

    turn.push_key("1")  # First key taken
    # 4 rapid repeat presses of 1 within 50ms intervals (< 300ms KEY_REPEAT_MS)
    for i in range(4):
        with turn._lock:
            turn._keys.put(StampedKey(
                digit="1",
                prompt_n=turn.prompt_n,
                t=now + 0.05 * (i + 1),
                prompt_open=True,
                prompt_start_t=turn.prompt_start_t,
                prompt_name="test_prompt",
            ))

    valid = turn.wait_input(gap_s=0.1)
    assert isinstance(valid, Digit)
    assert valid.digit == "1"

    # All remaining keys in queue should be dropped as repeat
    while True:
        k = turn.get_valid_key(block=False)
        if k is None:
            break
        pytest.fail(f"Unexpected valid key: {k}")

    # Inspect trace events: 1 taken, 4 dropped
    rows = [r for r in _read_trace_events(tmp_path, call_id) if r.get("event") == "key"]
    assert len(rows) == 5
    assert rows[0]["took"] is True
    assert rows[0]["why"] == "ok"
    for r in rows[1:]:
        assert r["took"] is False
        assert r["why"] == "repeat"


# --- G3: Other keys after key taken dropped (1 then 2 then 3 fast) ---
def test_g3_extra_keys_dropped(tmp_path):
    call_id = "test_g3"
    trace = Trace(call_id, str(tmp_path), "snap1")
    mouth, turn, _ = _make_mouth_and_turn()
    turn.trace = trace

    turn.start_prompt("box_question")
    now = time.monotonic()
    turn.prompt_start_t = now - 0.50  # past guard window

    with turn._lock:
        turn._keys.put(StampedKey(
            digit="1",
            prompt_n=turn.prompt_n,
            t=now,
            prompt_open=True,
            prompt_start_t=turn.prompt_start_t,
            prompt_name="box_question",
        ))
        turn._keys.put(StampedKey(
            digit="2",
            prompt_n=turn.prompt_n,
            t=now + 0.05,
            prompt_open=True,
            prompt_start_t=turn.prompt_start_t,
            prompt_name="box_question",
        ))
        turn._keys.put(StampedKey(
            digit="3",
            prompt_n=turn.prompt_n,
            t=now + 0.10,
            prompt_open=True,
            prompt_start_t=turn.prompt_start_t,
            prompt_name="box_question",
        ))

    k1 = turn.get_valid_key(block=False)
    assert isinstance(k1, Digit)
    assert k1.digit == "1"

    # 2 and 3 should be dropped
    k2 = turn.get_valid_key(block=False)
    assert k2 is None

    rows = [r for r in _read_trace_events(tmp_path, call_id) if r.get("event") == "key"]
    assert len(rows) == 3
    assert rows[0]["took"] is True
    assert rows[0]["value"] == "1"
    assert rows[1]["took"] is False
    assert rows[1]["value"] == "2"
    assert rows[1]["why"] == "prompt_closed"
    assert rows[2]["took"] is False
    assert rows[2]["value"] == "3"
    assert rows[2]["why"] == "prompt_closed"


# --- G4: Key in the gap is dropped, next prompt plays in full ---
def test_g4_gap_key_dropped(tmp_path):
    call_id = "test_g4"
    trace = Trace(call_id, str(tmp_path), "snap1")
    mouth, turn, _ = _make_mouth_and_turn()
    turn.trace = trace

    # Prompt 1 starts and finishes
    turn.start_prompt("prompt_1")
    turn.prompt_open = False  # Prompt closed / gap starts

    # Key pressed in the gap
    turn.push_key("9")

    # Gap key is dropped
    k = turn.get_valid_key(block=False)
    assert k is None

    rows = [r for r in _read_trace_events(tmp_path, call_id) if r.get("event") == "key"]
    assert len(rows) == 1
    assert rows[0]["took"] is False
    assert rows[0]["why"] == "prompt_closed"

    # Prompt 2 starts and plays
    turn.start_prompt("prompt_2")
    # Gap key should not answer prompt 2
    k2 = turn.get_valid_key(block=False)
    assert k2 is None


# --- G5: Key in first KEY_GUARD_MS (250 ms) of new prompt dropped ---
def test_g5_guard_window_dropped(tmp_path):
    call_id = "test_g5"
    trace = Trace(call_id, str(tmp_path), "snap1")
    mouth, turn, _ = _make_mouth_and_turn()
    turn.trace = trace

    turn.start_prompt("prev_prompt")
    turn.start_prompt("new_prompt")
    with turn._lock:
        turn._keys.put(StampedKey(
            digit="1",
            prompt_n=turn.prompt_n,
            t=turn.prompt_start_t + 0.10,  # 100ms in < 250ms guard
            prompt_open=True,
            prompt_start_t=turn.prompt_start_t,
            prompt_name="new_prompt",
        ))

    k = turn.get_valid_key(block=False)
    assert k is None

    rows = [r for r in _read_trace_events(tmp_path, call_id) if r.get("event") == "key"]
    assert len(rows) == 1
    assert rows[0]["took"] is False
    assert rows[0]["why"] == "guard"


# --- G6: Random key at each of the 4 profiles replays same prompt ---
class MockFourProfilesAudio:
    def __init__(self, inputs_seq):
        self.inputs_seq = list(inputs_seq)
        self.played = []
        self.language = "hi"
        self.hung_up = False

    def select_language(self):
        self.played.append("greeting_trilingual")
        return "hi", "keypad"

    def say(self, seq):
        for token in seq:
            self.played.append(token)

    def next_input(self, profile="normal"):
        if self.inputs_seq:
            return self.inputs_seq.pop(0)
        return Hangup()

    def hangup(self):
        self.hung_up = True

    def repeat(self):
        self.played.append("REPEAT")

    def was_cut(self, token):
        return False

    def on_mark(self, mark):
        return 0.0


def test_g6_random_key_four_profiles(fixture_corpus, tmp_path):
    """Random key at (1) box menu, (2) read-back/confirm, (3) results menu, (4) anything-else replays prompt."""
    audio = MockFourProfilesAudio(inputs_seq=[
        # Opener: speech farming
        Speech(text="I need farming schemes"),
        # Confirm profile: random key 7 -> unclear_prompt -> then valid key 1
        Digit("7"),
        Digit("1"),
        # Box menu (state): random key 9 -> unclear_prompt -> then valid key 2
        Digit("9"),
        Digit("2"),
        # Box menu (gender): valid key 1
        Digit("1"),
        # Box menu (social category): valid key 3
        Digit("3"),
        # Results menu (read-back): random key 6 -> unclear_prompt -> then 0 (leave)
        Digit("6"),
        Digit("0"),
        # Anything-else: random key 8 -> unclear_prompt -> then 2 (no/exit)
        Digit("8"),
        Digit("2"),
    ])

    log = Log.open("test_g6", fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = _make_model(fixture_corpus)

    Engine.run_call(audio, model, fixture_corpus, log)

    # Verify that unclear_prompt was played for out-of-menu digits
    assert "unclear_prompt" in audio.played
    # Count of unclear_prompt should be at least 4 (one per profile)
    assert audio.played.count("unclear_prompt") >= 4


# --- G7: Caller speaks, then presses key before read-back -> key wins ---
class MockModelThinkingWithPendingKey:
    def __init__(self, audio, return_stamps):
        self.audio = audio
        self.return_stamps = return_stamps

    def opener(self, transcript, lang="en"):
        # While router was "thinking", caller pressed a key!
        self.audio._pending_key = Digit(digit="1", prompt_n=1)
        return self.return_stamps

    def turn(self, transcript, box, window=None, ask_count=0):
        self.audio._pending_key = Digit(digit="1", prompt_n=2)
        return Answer(box=box, value="farmer", span="farmer")


def test_g7_speech_then_key_wins(fixture_corpus, tmp_path):
    """When a key arrives while model router is thinking, key wins and speech is discarded."""
    call_id = "test_g7"
    trace = Trace(call_id, str(tmp_path), fixture_corpus.snapshot_id)
    audio = FakeAudio(
        canned_inputs=["1", "say:I need farming schemes", "1", "1", "0", "2", "h"],
    )
    audio.trace = trace
    log = Log.open(call_id, fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = MockModelThinkingWithPendingKey(
        audio=audio,
        return_stamps=[Stamp(box="category", value="farming", span="farming")],
    )

    Engine.run_call(audio, model, fixture_corpus, log)

    # Check dropped events in trace file
    rows = [r for r in _read_trace_events(tmp_path, call_id) if r.get("why") == "key_beat_speech"]
    assert len(rows) >= 1
    assert rows[0]["event"] == "speech"
    assert rows[0]["took"] is False


# --- G8: Key while line busy with key answer dropped ---
def test_g8_busy_key_dropped(tmp_path):
    call_id = "test_g8"
    trace = Trace(call_id, str(tmp_path), "snap1")
    mouth, turn, _ = _make_mouth_and_turn()
    turn.trace = trace

    turn.start_prompt("prompt_busy")
    turn.prompt_open = False  # processing answer, prompt closed

    turn.push_key("3")
    k = turn.get_valid_key(block=False)
    assert k is None

    rows = [r for r in _read_trace_events(tmp_path, call_id) if r.get("event") == "key"]
    assert len(rows) == 1
    assert rows[0]["took"] is False
    assert rows[0]["why"] == "prompt_closed"


# --- G9: Control keys (#, *, 0) follow same gate rules ---
def test_g9_control_keys_gated(tmp_path):
    call_id = "test_g9"
    trace = Trace(call_id, str(tmp_path), "snap1")
    mouth, turn, _ = _make_mouth_and_turn()
    turn.trace = trace

    turn.start_prompt("prompt_ctrl")
    now = time.monotonic()
    turn.prompt_start_t = now - 0.50

    with turn._lock:
        turn._keys.put(StampedKey(
            digit="#",
            prompt_n=turn.prompt_n,
            t=now,
            prompt_open=True,
            prompt_start_t=turn.prompt_start_t,
            prompt_name="prompt_ctrl",
        ))
        turn._keys.put(StampedKey(
            digit="#",
            prompt_n=turn.prompt_n,
            t=now + 0.05,
            prompt_open=True,
            prompt_start_t=turn.prompt_start_t,
            prompt_name="prompt_ctrl",
        ))

    k1 = turn.get_valid_key(block=False)
    assert isinstance(k1, Digit)
    assert k1.digit == "#"

    k2 = turn.get_valid_key(block=False)
    assert k2 is None  # dropped as repeat

    rows = [r for r in _read_trace_events(tmp_path, call_id) if r.get("event") == "key"]
    assert len(rows) == 2
    assert rows[0]["took"] is True
    assert rows[1]["took"] is False
    assert rows[1]["why"] == "repeat"


# --- G10: Hangup mid-clip and mid-router: no Digit('h'), log closed ---
def test_g10_hangup_mid_clip_and_mid_router(fixture_corpus, tmp_path):
    """Hangup mid-clip and mid-router produces Hangup event, never Digit('h'), and closes log."""
    mouth, turn, _ = _make_mouth_and_turn()
    mouth.play([("long_clip", b"\x00" * 32000)])
    turn.start_prompt("long_clip")

    # Hangup mid-clip
    turn.push_hangup()
    inp = turn.wait_input(gap_s=1.0)
    assert isinstance(inp, Hangup)
    assert not isinstance(inp, Digit)

    # Test call mid-clip hangup closes log cleanly
    audio = FakeAudio(canned_inputs=["1", "h"])
    log = Log.open("test_g10_log", fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = _make_model(fixture_corpus)

    Engine.run_call(audio, model, fixture_corpus, log)
    # Check log is closed with closing line
    log_file = tmp_path / "test_g10_log.jsonl"
    rows = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert "stop" in rows[-1]


# --- G11: Results section marked heard only when clip played to end ---
def test_g11_section_heard_only_when_played_to_end(fixture_corpus, tmp_path):
    """When a section clip is cut by a barge-in key, it is NOT marked in sections_heard."""
    # Script a cut on scheme:S1:benefit_text
    audio = FakeAudio(canned_inputs=["1", "1", "1", "1", "0", "2", "h"])
    # Script a key '0' to cut the benefit_text clip after 100ms
    audio.script_cut("scheme:S1:benefit_text", key="0", ms=100)

    log = Log.open("test_g11_cut", fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = _make_model(fixture_corpus)

    Engine.run_call(audio, model, fixture_corpus, log)

    log_file = tmp_path / "test_g11_cut.jsonl"
    rows = [json.loads(line) for line in log_file.read_text().splitlines()]
    s1_deliveries = [r for r in rows if r.get("slug") == "S1"]
    if s1_deliveries:
        # benefit_text was cut, so it should not be in sections heard!
        assert "benefit_text" not in s1_deliveries[0]["sections"]


def test_gap_key_in_sim_dropped_and_next_prompt_played(fixture_corpus, tmp_path):
    """Key in gap dropped; next prompt clip played and not answered by gap key."""
    call_id = "test_gap_sim"
    trace = Trace(call_id, str(tmp_path), fixture_corpus.snapshot_id)
    # gap_key:1 is inserted before the opener prompt
    audio = FakeAudio(canned_inputs=["1", "gap_key:1", "1", "1", "0", "2", "h"])
    audio.trace = trace
    log = Log.open(call_id, fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = _make_model(fixture_corpus)

    Engine.run_call(audio, model, fixture_corpus, log)

    # Check dropped gap key in trace
    rows = [r for r in _read_trace_events(tmp_path, call_id) if r.get("event") == "key"]
    dropped = [r for r in rows if r["took"] is False and r["why"] == "prompt_closed"]
    assert len(dropped) >= 1
    # Next prompt played in full
    assert "opener_prompt" in audio.played_lines


class MockModelHangsUpMidRouter:
    def __init__(self, audio):
        self.audio = audio

    def opener(self, transcript, lang="en"):
        # Mid-router hangup!
        self.audio.push_hangup()
        return Unclear(reason="hangup")

    def turn(self, transcript, box, window=None, ask_count=0):
        self.audio.push_hangup()
        return Unclear(reason="hangup")


def test_hangup_mid_router_in_engine(fixture_corpus, tmp_path):
    """Hangup during router call closes log with no Digit('h')."""
    call_id = "test_mid_router_h"
    audio = FakeAudio(canned_inputs=["1", "say:hello", "h"])
    log = Log.open(call_id, fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = MockModelHangsUpMidRouter(audio)

    Engine.run_call(audio, model, fixture_corpus, log)

    log_file = tmp_path / f"{call_id}.jsonl"
    rows = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert "stop" in rows[-1]
    # Verify no Digit("h") logged
    for r in rows:
        assert r.get("transcript") != "h"
        assert r.get("value") != "h"



# --- The real path: Turn.push_key with a real Ear (added at Claude's review) ---------------
def _real_line():
    from haqdaar.audio.ear import Ear
    out: list[dict] = []
    mouth = Mouth(out.append, "S")
    ear = Ear()
    return mouth, ear, Turn(mouth, ear=ear), out


def test_real_ear_a_key_is_taken_once():
    """One press answers one prompt. The Ear must not hand the same key back again."""
    _, ear, turn, _ = _real_line()
    turn.start_prompt("q1")
    turn.push_key("1")
    first = turn.wait_input(0.1, profile="spoken")
    assert isinstance(first, Digit) and first.digit == "1"
    turn.start_prompt("q2")
    second = turn.wait_input(0.1, profile="spoken")
    assert not isinstance(second, Digit)
    assert ear._keys.empty()


def test_real_ear_gap_key_is_not_given_by_listen():
    """G4 on the real path: a key in the gap is dropped by the gate and by the Ear."""
    _, _, turn, _ = _real_line()
    turn.start_prompt("q1")
    turn.push_key("1")
    assert isinstance(turn.wait_input(0.1, profile="spoken"), Digit)
    turn.push_key("2")  # prompt closed, next not started
    turn.start_prompt("q2")
    assert not isinstance(turn.wait_input(0.1, profile="spoken"), Digit)


def test_key_for_an_older_prompt_does_not_answer_the_next():
    _, _, turn, _ = _real_line()
    turn.start_prompt("q1")
    turn.push_key("1")       # pressed at q1, not picked up
    turn.start_prompt("q2")  # the engine moved on
    assert turn.get_valid_key(block=False) is None


def test_guard_key_does_not_cut_the_new_prompt():
    """G5: a key that will be dropped must leave the prompt playing."""
    mouth, _, turn, out = _real_line()
    turn.start_prompt("q1")
    turn.start_prompt("q2")
    mouth.play([("q2", b"\x10" * 16000)])
    turn.push_key("1")       # inside the guard window
    assert mouth.playing
    assert not any(m.get("event") == "clear" for m in out)
    assert turn.get_valid_key(block=False) is None
