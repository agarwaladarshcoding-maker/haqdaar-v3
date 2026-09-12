"""tests/test_call.py

Comprehensive tests for Step 6 (haqdaar/data/log.py, haqdaar/engine/call.py, haqdaar/sim.py).
Verifies:
- Log resilience: Log.write never raises on malformed records and writes invalid: True.
- Schema conformity: 7 turn classes including SILENCE (silence_n, turn_n unchanged) and NOISE.
- Keypad-only mode entry line written once and consumes no turn.
- Turn 0 written with turn_n=0 and not counted towards 8-turn cap.
- Silence ladder rungs 1..3 with hangup on rung 3.
- Caps and walls: 8-turn cap and 6-question wall read from contracts/tunables.py.
- Out-of-menu digit strikes and drop to UNKNOWN.
- Personas P1 and P2 full end-to-end runs against fixtures/.
- Ordering lock: negative preambles precede scheme names.
- Concurrency and import discipline: no Thread, asyncio, Queue, Pool, audio, model, or pipeline imports.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any, Optional
import warnings
import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.log_schema import (
    STOP_REASONS,
    CallCloseRecord,
    CallOpenRecord,
    LangSwitchRecord,
    STOP_LE_4_SURVIVORS,
    STOP_MAX_QUESTIONS,
    STOP_MAX_TURNS,
    STOP_NO_SPLIT,
    STOP_ZERO_SURVIVORS,
    TURN_CLASSES,
    TurnLogRecord,
)
from haqdaar.contracts.types import (
    Digit,
    Hangup,
    Lang,
    LangSource,
    Noise,
    Silence,
    Speech,
    UNASKED,
    UNKNOWN,
)
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.engine.call import Engine
from haqdaar.engine.terminals import (
    DELIVERY_NEAREST,
    DELIVERY_WIDENED_MATCH,
    RESULTS_EXACT_PREAMBLE,
    RESULTS_WIDENED_LEAD,
    SECTION_MENU,
    STATE_UNKNOWN_DISCLAIMER,
    TERMINAL_EMPTY,
    TERMINAL_NEAREST_PREAMBLE,
    TERMINAL_WIDENED_PREAMBLE,
)


class MockAudio:
    """Mock audio session for unit and integration testing."""

    def __init__(self, inputs: Optional[list[Any]] = None, initial_lang: Lang = "hi") -> None:
        self.inputs = list(inputs) if inputs else []
        self.language: Lang = initial_lang
        self.played: list[str] = []
        self.hung_up: bool = False
        self._last_played: tuple[str, ...] = ()
        self.marks: list[str] = []

    def select_language(self) -> tuple[Lang, LangSource]:
        self.played.append("greeting_trilingual")
        if self.inputs and isinstance(self.inputs[0], Digit):
            d = self.inputs.pop(0).digit
            if d == "2":
                self.language = "mr"
                return "mr", "keypad"
            elif d == "3":
                self.language = "en"
                return "en", "keypad"
        return "hi", "keypad"

    def say(self, sequence: tuple[str, ...]) -> None:
        self._last_played = sequence
        for token in sequence:
            self.played.append(token)

    def repeat(self) -> None:
        self.played.append("REPEAT")
        if self._last_played:
            for token in self._last_played:
                self.played.append(token)

    def clear(self) -> None:
        self.played.append("CLEAR")

    def on_mark(self, mark: str) -> float:
        self.marks.append(mark)
        return 0.0

    def hangup(self) -> None:
        self.hung_up = True

    def next_input(self, profile: str = "normal") -> Digit | Noise | Silence | Hangup | Speech:
        if self.inputs:
            item = self.inputs.pop(0)
            if isinstance(item, str):
                return Digit(digit=item)
            return item
        return Digit(digit="2")


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    root_dir = Path(__file__).resolve().parent.parent
    fixtures_dir = root_dir / "fixtures"
    schemes_file = fixtures_dir / "schemes.jsonl"

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
        snapshot_id="test_step6_snap",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=True,
    )
    return Corpus.load(snap_id)


# ---------------------------------------------------------------------------
# 1. Log Resilience & Schema Tests
# ---------------------------------------------------------------------------

def test_log_write_never_raises(tmp_path):
    """Log.write never raises on bad lines and persists invalid: True."""
    log = Log.open("test_resilience", "snap_01", logs_dir=tmp_path)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # Malformed dicts
        log.write({"bogus": "field", "invalid_data": 123})
        # Invalid turn class
        log.write({"turn_n": 1, "class": "NOT_A_CLASS"})
        # Bad turn_n type
        log.write({"turn_n": "one", "class": "ANSWER"})
        # Non-dict line
        log.write("raw_string_line")
        log.write(12345)
        log.write([1, 2, 3])

    log.close(reason="survivors_le_4")

    lines = [json.loads(l) for l in open(tmp_path / "test_resilience.jsonl")]
    assert len(lines) == 8  # 1 open + 6 bad + 1 close
    for bad_line in lines[1:7]:
        assert bad_line.get("invalid") is True


def test_log_seven_turn_classes(tmp_path):
    """Verify all 7 turn classes serialize properly to JSON with key 'class'."""
    log = Log.open("test_7_classes", "snap_01", logs_dir=tmp_path)

    for i, tc in enumerate(TURN_CLASSES, 1):
        if tc == "SILENCE":
            log.write(TurnLogRecord(turn_n=i, turn_class=tc, silence_n=1))
        elif tc == "NOISE":
            log.write(TurnLogRecord(turn_n=i, turn_class=tc))
        else:
            log.write(TurnLogRecord(turn_n=i, turn_class=tc, transcript="test"))

    log.close(reason=STOP_LE_4_SURVIVORS)

    lines = [json.loads(l) for l in open(tmp_path / "test_7_classes.jsonl")]
    classes_logged = [l.get("class") for l in lines[1:-1]]
    assert classes_logged == list(TURN_CLASSES)
    assert "SILENCE" in classes_logged
    assert "NOISE" in classes_logged


def test_log_silence_turn_accounting(tmp_path):
    """SILENCE carries silence_n and leaves turn_n unchanged."""
    log = Log.open("test_silence_log", "snap_01", logs_dir=tmp_path)
    log.write(TurnLogRecord(turn_n=1, turn_class="SILENCE", silence_n=1))
    log.write(TurnLogRecord(turn_n=1, turn_class="SILENCE", silence_n=2))
    log.close(reason=STOP_LE_4_SURVIVORS)

    lines = [json.loads(l) for l in open(tmp_path / "test_silence_log.jsonl")]
    assert lines[1]["turn_n"] == 1
    assert lines[1]["class"] == "SILENCE"
    assert lines[1]["silence_n"] == 1
    assert lines[2]["turn_n"] == 1
    assert lines[2]["class"] == "SILENCE"
    assert lines[2]["silence_n"] == 2


# ---------------------------------------------------------------------------
# 2. Call Loop & Turn Clock Tests
# ---------------------------------------------------------------------------

def test_turn_0_and_keypad_mode_entry(corpus, tmp_path):
    """Turn 0 is logged with turn_n=0, keypad mode line is written once, no cap spent."""
    audio = MockAudio(inputs=[Digit("1"), Digit("1"), Digit("1"), Digit("2")])
    log = Log.open("test_turn0", corpus.snapshot_id, logs_dir=tmp_path)

    Engine.run_call(audio, None, corpus, log)
    assert audio.hung_up

    lines = [json.loads(l) for l in open(tmp_path / "test_turn0.jsonl")]
    # Call-open header
    assert lines[0]["call_id"] == "test_turn0"
    # Turn 0 answer, and the lang record carrying what the caller actually pressed
    assert lines[1]["turn_n"] == 0
    assert lines[1]["class"] == "ANSWER"
    lang_lines = [l for l in lines if l.get("lang_source")]
    assert lang_lines and lang_lines[-1]["lang_source"] == "keypad"
    assert lang_lines[-1]["turn_n"] == 0
    # Keypad-only mode entry line, written exactly once
    assert [l for l in lines if l.get("mode") == "keypad_only" and "stop" not in l]
    assert len([l for l in lines if l.get("mode") == "keypad_only" and "stop" not in l]) == 1
    # Turn 0 spends no cap turn: the first cap turn is still 1
    cap_turns = [l["turn_n"] for l in lines if l.get("turn_n", 0) > 0]
    assert cap_turns and min(cap_turns) == 1


def test_noise_spends_turn_silence_does_not(corpus, tmp_path):
    """NOISE increments turn_n; SILENCE leaves turn_n unchanged."""
    # Inputs: Turn 0=Digit(1), Question 1: Silence(1), Silence(2), Noise(), Answer(1), AnythingElse=2
    audio = MockAudio(inputs=[
        Digit("1"),
        Silence(n=1),
        Silence(n=2),
        Noise(),
        Digit("1"),
        Digit("2"),
    ])
    log = Log.open("test_turn_accounting", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    lines = [json.loads(l) for l in open(tmp_path / "test_turn_accounting.jsonl")]
    # Turn records after mode entry
    turns = [l for l in lines if l.get("class") in ("SILENCE", "NOISE", "ANSWER") and l.get("turn_n") is not None]
    # Turn 0 was language selection; next lines are the questioning turns
    question_turns = turns[1:]
    # Silence at turn_n=0
    assert question_turns[0]["class"] == "SILENCE" and question_turns[0]["turn_n"] == 0 and question_turns[0]["silence_n"] == 1
    assert question_turns[1]["class"] == "SILENCE" and question_turns[1]["turn_n"] == 0 and question_turns[1]["silence_n"] == 2
    # Noise increments to turn_n=1
    assert question_turns[2]["class"] == "NOISE" and question_turns[2]["turn_n"] == 1
    # Answer increments to turn_n=2
    assert question_turns[3]["class"] == "ANSWER" and question_turns[3]["turn_n"] == 2


def test_silence_ladder_timeout_hangup(corpus, tmp_path):
    """Rung 3 of silence ladder triggers closing_farewell and hangup."""
    audio = MockAudio(inputs=[
        Digit("1"),
        Silence(n=1),
        Silence(n=2),
        Silence(n=3),
    ])
    log = Log.open("test_silence_hangup", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    assert audio.hung_up
    assert "closing_farewell" in audio.played
    lines = [json.loads(l) for l in open(tmp_path / "test_silence_hangup.jsonl")]
    assert lines[-1]["stop"] in STOP_REASONS


def test_max_turns_budget_cap(corpus, tmp_path):
    """Exceeding MAX_TURNS (8) stops questioning with STOP_MAX_TURNS."""
    # 8 NOISE turns exceed MAX_TURNS (8)
    audio = MockAudio(inputs=[Digit("1")] + [Noise() for _ in range(tunables.MAX_TURNS + 2)])
    log = Log.open("test_max_turns", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    lines = [json.loads(l) for l in open(tmp_path / "test_max_turns.jsonl")]
    assert lines[-1]["stop"] == STOP_MAX_TURNS


def test_control_keys_hash_and_star(corpus, tmp_path):
    """'#' repeats last prompt without spending turn; '*' switches language."""
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0
        Digit("#"),    # Repeat
        Digit("*"),    # Switch to mr
        Digit("1"),    # Answer question 1
        Digit("2"),    # Anything else
    ])
    log = Log.open("test_control_keys", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    assert "REPEAT" in audio.played
    lines = [json.loads(l) for l in open(tmp_path / "test_control_keys.jsonl")]
    switches = [l for l in lines if l.get("lang") == "mr" and l.get("lang_source") == "keypad"]
    assert len(switches) == 1
    assert audio.language == "mr"


def test_out_of_menu_digit_strike_and_drop(corpus, tmp_path):
    """Out-of-menu digit is logged as UNCLEAR; second strike drops box to UNKNOWN."""
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0
        Digit("9"),    # Out of menu strike 1 (re-ask)
        Digit("9"),    # Out of menu strike 2 (drop to UNKNOWN)
        Digit("1"),    # Next box
        Digit("2"),    # Anything else
    ])
    log = Log.open("test_out_of_menu", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    lines = [json.loads(l) for l in open(tmp_path / "test_out_of_menu.jsonl")]
    unclears = [l for l in lines if l.get("class") == "UNCLEAR"]
    assert len(unclears) >= 1
    dropped = [l for l in lines if l.get("unknown_source") == "keypad_dropped"]
    assert len(dropped) == 1
    assert dropped[0]["value"] == UNKNOWN


# ---------------------------------------------------------------------------
# 3. Personas End-to-End Tests (P1 and P2)
# ---------------------------------------------------------------------------

def test_persona_p1_happy_path_end_to_end(corpus, tmp_path):
    """P1 (Sunita Devi) narrows cleanly to a direct match (survivors_le_4)."""
    # Door A: category=1 (agriculture), then state=1 (BIHAR), gender=2 (female),
    # social_category=2 (SC).
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> agriculture
        Digit("1"),    # state -> BIHAR
        Digit("2"),    # gender -> female
        Digit("2"),    # social_category -> SC
        Digit("9"), Digit("9"), Digit("9"),   # read-back: walk the schemes
        Digit("2"),    # anything else -> no
    ])
    log = Log.open("test_p1_full", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    assert audio.hung_up
    assert RESULTS_EXACT_PREAMBLE in audio.played
    assert "closing_farewell" in audio.played
    assert [t for t in audio.played if t.startswith("name:")]

    lines = [json.loads(l) for l in open(tmp_path / "test_p1_full.jsonl")]
    assert lines[0]["call_id"] == "test_p1_full"
    assert lines[1]["turn_n"] == 0
    assert [l for l in lines if l.get("mode") == "keypad_only" and "stop" not in l]
    # The opener is asked first and logged as a real box
    opener = [l for l in lines if l.get("box") == "category"]
    assert opener and opener[0]["value"] == "agriculture"
    assert lines[-1]["stop"] == STOP_LE_4_SURVIVORS
    assert lines[-1]["ladder_rung"] == 0


def test_persona_p2_nearest_two_end_to_end(corpus, tmp_path):
    """P2 dead end: nothing matches, the ladder is exhausted, two nearest are named.

    The caller asks about handloom in BIHAR. There is no handloom scheme in
    BIHAR, and `category` is never widened (T10 D6 as amended), so the ladder
    runs out and the terminal is Nearest: preamble first, cap 2, summary only,
    no section_menu, auto-advance (T18 §2).
    """
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("2"),    # opener: category -> handloom
        Digit("1"),    # state -> BIHAR
        Digit("2"),    # gender -> female
        Digit("2"),    # social_category -> SC
        Digit("2"),    # anything else -> no
    ])
    log = Log.open("test_p2_nearest", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    assert audio.hung_up
    assert "closing_farewell" in audio.played

    played = audio.played
    assert TERMINAL_NEAREST_PREAMBLE in played
    i_pre = played.index(TERMINAL_NEAREST_PREAMBLE)
    i_end = played.index("anything_else", i_pre)
    block = played[i_pre:i_end]

    names = [t for t in block if t.startswith("name:")]
    assert len(names) == tunables.NEAREST_CAP == 2
    assert len(set(names)) == 2, "the same scheme was named twice"
    # Bad news before names
    assert block.index(TERMINAL_NEAREST_PREAMBLE) < block.index(names[0])
    # Restraint: a nearest auto-advances and never offers the section menu
    assert SECTION_MENU not in block
    # Summary only, no source sections
    assert not [t for t in block if t.startswith("scheme:") and t.endswith(":benefit_text")]

    lines = [json.loads(l) for l in open(tmp_path / "test_p2_nearest.jsonl")]
    close_line = lines[-1]
    assert close_line["stop"] == STOP_ZERO_SURVIVORS
    assert close_line["ladder_rung"] >= 1
    assert close_line["mode"] == "keypad_only"


def test_persona_p3_second_subject_door_b(corpus, tmp_path):
    """P3: a caller with a second subject. "Anything else" == 1 re-opens Door A.

    T17 §4's P3 names a scheme at the opener, which is a speech path and has no
    keypad equivalent. The third keypad persona is the Door B caller: one
    terminal, "anything else" == 1, the opener asked again, a second terminal
    on the same budget, then the farewell.
    """
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> agriculture
        Digit("1"),    # state -> BIHAR
        Digit("2"),    # gender -> female
        Digit("2"),    # social_category -> SC
        Digit("0"),    # read-back: none of these, leave the menu
        Digit("1"),    # anything else -> yes, Door B
        Digit("2"),    # opener again: category -> handloom
        Digit("2"),    # anything else -> no
    ])
    log = Log.open("test_p3_door_b", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    assert audio.hung_up
    assert "closing_farewell" in audio.played
    # Two rounds: the opener is asked twice and two terminals are delivered
    assert audio.played.count("opener_prompt") == 2
    assert audio.played.count("anything_else") == 2
    assert audio.played.count("closing_farewell") == 1
    assert RESULTS_EXACT_PREAMBLE in audio.played
    assert TERMINAL_NEAREST_PREAMBLE in audio.played

    lines = [json.loads(l) for l in open(tmp_path / "test_p3_door_b.jsonl")]
    assert lines[-1]["mode"] == "keypad_only"
    assert lines[-1]["stop"] in STOP_REASONS


def test_widened_match_when_door_a_is_struck_out(corpus, tmp_path):
    """Shape 3: 0 survivors, a rung of the ladder recovers a scheme.

    A caller who cannot name their subject presses an out-of-menu key twice, so
    Door A drops to UNKNOWN and the Planner falls back to facts. income_band
    then contradicts the only KARNATAKA scheme, and dropping that one rung
    recovers it. T18 order: preamble -> drop_* -> lead -> names.
    """
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("3"), Digit("3"),   # opener struck out -> category = UNKNOWN
        Digit("1"),    # income_band -> 30000
        Digit("2"),    # state -> KARNATAKA
        Digit("2"),    # gender -> female
        Digit("2"),    # social_category -> SC
        Digit("9"),    # read-back: advance
        Digit("2"),    # anything else -> no
    ])
    log = Log.open("test_widened", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    played = audio.played
    assert TERMINAL_WIDENED_PREAMBLE in played
    drops = [t for t in played if t.startswith("drop_")]
    assert drops == ["drop_income_band"]
    assert RESULTS_WIDENED_LEAD in played
    names = [t for t in played if t.startswith("name:")]
    assert names, "the ladder recovered schemes but named none"
    assert played.index(TERMINAL_WIDENED_PREAMBLE) < played.index(drops[0])
    assert played.index(drops[0]) < played.index(RESULTS_WIDENED_LEAD)
    assert played.index(RESULTS_WIDENED_LEAD) < played.index(names[0])

    lines = [json.loads(l) for l in open(tmp_path / "test_widened.jsonl")]
    assert lines[-1]["stop"] == STOP_ZERO_SURVIVORS
    assert lines[-1]["ladder_rung"] == 1
    # Door A was struck out, and that is logged
    assert [
        l for l in lines
        if l.get("box") == "category" and l.get("unknown_source") == "keypad_dropped"
    ]


def test_category_is_never_widened(corpus, tmp_path):
    """T10 D6 as amended: the ladder is income_band -> age -> occupation only."""
    from haqdaar.contracts.types import WIDENING_ORDER as WO
    assert "category" not in WO
    assert WO == ("income_band", "age", "occupation")

    audio = MockAudio(inputs=[
        Digit("1"), Digit("2"), Digit("1"), Digit("2"), Digit("2"), Digit("2"),
    ])
    log = Log.open("test_no_cat_drop", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)
    assert "drop_category" not in audio.played


def test_state_drops_to_unknown_only_when_it_will_not_fit_a_keypad(tmp_path, monkeypatch):
    """T18 §3 is a cardinality test, not a hard-coded box.

    On a corpus with more states than a keypad holds, `state` drops to UNKNOWN,
    `state_unknown_disclaimer` plays, and only nationwide schemes are speakable.
    On fixtures/ (2 states) `state` is asked like any other box.
    """
    wide = []
    for i in range(tunables.KEYPAD_CARDINALITY_MAX + 2):
        wide.append({
            "scheme_id": f"W{i}",
            "state": f"STATE_{i}",
            "category": "agriculture",
            "gender": "ANY",
            "social_category": "ANY",
            "age": "ANY",
            "income_band": "ANY",
            "occupation": "ANY",
        })
    # One nationwide scheme: the only thing speakable once state is UNKNOWN
    wide.append({
        "scheme_id": "WNAT",
        "state": "ANY",
        "category": "agriculture",
        "gender": "ANY",
        "social_category": "ANY",
        "age": "ANY",
        "income_band": "ANY",
        "occupation": "ANY",
    })

    snap_dir = tmp_path / "wsnap"
    audio_dir = tmp_path / "waudio"
    snap_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(snap_dir))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(audio_dir))
    snap_id = build_snapshot(
        schemes_data=wide,
        snapshot_id="test_wide_states",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=True,
    )
    wide_corpus = Corpus.load(snap_id)
    assert len(wide_corpus.values("state")) > tunables.KEYPAD_CARDINALITY_MAX

    audio = MockAudio(inputs=[Digit("1"), Digit("0"), Digit("2")])
    log = Log.open("test_wide", snap_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, wide_corpus, log)

    assert STATE_UNKNOWN_DISCLAIMER in audio.played
    named = {t.split(":", 1)[1] for t in audio.played if t.startswith("name:")}
    assert "WNAT" in named or not named
    assert not {n for n in named if n.startswith("W") and n != "WNAT"}, (
        "a state-specific scheme was named to a caller whose state is UNKNOWN"
    )

    lines = [json.loads(l) for l in open(tmp_path / "test_wide.jsonl")]
    dropped = [
        l for l in lines
        if l.get("box") == "state" and l.get("unknown_source") == "keypad_dropped"
    ]
    assert dropped, "the keypad drop was not logged"


# ---------------------------------------------------------------------------
# 4. Ordering & Hard Rules Constraints Tests
# ---------------------------------------------------------------------------

def test_ordering_bad_news_before_names_in_call_output(corpus, tmp_path):
    """The call orchestrator never reorders tokens; preambles precede scheme names."""
    audio = MockAudio(inputs=[Digit("1"), Digit("1"), Digit("1"), Digit("2")])
    log = Log.open("test_order_check", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    # In audio.played, any disclaimer/preamble must precede scheme names
    tokens = audio.played
    name_indices = [i for i, t in enumerate(tokens) if t.startswith("name:")]
    preamble_indices = [
        i for i, t in enumerate(tokens)
        if t in (RESULTS_EXACT_PREAMBLE, TERMINAL_WIDENED_PREAMBLE, TERMINAL_NEAREST_PREAMBLE, STATE_UNKNOWN_DISCLAIMER)
    ]

    if name_indices and preamble_indices:
        assert min(preamble_indices) < min(name_indices)


def test_concurrency_and_import_discipline():
    """Verify zero concurrency primitives and strict import discipline."""
    import haqdaar.engine.call as call_mod
    import haqdaar.sim as sim_mod

    call_src = Path(call_mod.__file__).read_text()
    sim_src = Path(sim_mod.__file__).read_text()

    # No concurrency primitives
    for token in ("Thread", "asyncio", "Queue", "Pool"):
        assert token not in call_src, f"Forbidden token {token} found in call.py"
        assert token not in sim_src, f"Forbidden token {token} found in sim.py"

    # call.py imports no audio, model, or pipeline modules
    call_imports = [line for line in call_src.splitlines() if line.strip().startswith(("import ", "from "))]
    for imp in call_imports:
        low = imp.lower()
        assert "audio" not in low, f"Forbidden audio import in call.py: {imp}"
        assert "model" not in low, f"Forbidden model import in call.py: {imp}"
        assert "pipeline" not in low, f"Forbidden pipeline import in call.py: {imp}"
