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
    DeliveryRecord,
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
    DELIVERY_DIRECT_MATCH,
    DELIVERY_NEAREST,
    DELIVERY_WIDENED_MATCH,
    RESULTS_EXACT_PREAMBLE,
    RESULTS_MORE_PROMPT,
    RESULTS_WIDENED_LEAD,
    SECTION_MENU,
    STATE_UNKNOWN_DISCLAIMER,
    TERMINAL_EMPTY,
    TERMINAL_NEAREST_PREAMBLE,
    TERMINAL_WIDENED_PREAMBLE,
    Terminals,
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
    # category (the opener, asked first) now has all 9 vocab.CATEGORY values as
    # valid keys 1-9 (D6, step 1.5a), so every digit 1-9 is a real pick there,
    # and "0" is reserved for "don't know" (D7/F8, step 1.6), not a strike. So
    # this test strikes the box after it: state has only 2 vocab values
    # (MAHARASHTRA, OTHER), so "5" is genuinely out-of-menu there.
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0
        Digit("1"),    # opener: category -> farming
        Digit("5"),    # state: out of menu strike 1 (re-ask)
        Digit("5"),    # state: out of menu strike 2 (drop to UNKNOWN)
        Digit("1"),    # Next box
        Digit("3"),    # Next box
        Digit("9"), Digit("9"), Digit("9"),   # read-back: walk the schemes
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
    assert dropped[0]["box"] == "state"


# ---------------------------------------------------------------------------
# 3. Personas End-to-End Tests (P1 and P2)
# ---------------------------------------------------------------------------

def test_persona_p1_happy_path_end_to_end(corpus, tmp_path):
    """P1 (Sunita Devi) narrows cleanly to a direct match (survivors_le_4)."""
    # Door A: category=1 (farming), then state=2 (OTHER — P1 is from outside
    # Maharashtra; S1 is state=ANY/central so it still matches), gender=1
    # (female), social_category=3 (SC). Digits are keypad positions in
    # vocab.py order (D6, step 1.5a), not the old alphabetical-over-
    # discovered-values order.
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> farming
        Digit("2"),    # state -> OTHER
        Digit("1"),    # gender -> female
        Digit("3"),    # social_category -> SC
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
    assert opener and opener[0]["value"] == "farming"
    assert lines[-1]["stop"] == STOP_LE_4_SURVIVORS
    assert lines[-1]["ladder_rung"] == 0


def test_delivery_record_one_per_scheme_with_sections(corpus, tmp_path):
    """D9: a direct-match call writes one DeliveryRecord per named scheme,
    carrying the scheme's slug and the sections actually spoken, and the log
    has zero invalid lines.

    Same P1 keypad path as test_persona_p1_happy_path_end_to_end (2 named
    schemes -- see that test's fixture, S1/S2), except the first read-back
    reads back a section (key 1 = benefit_text) before moving on, so its
    record's sections grow past the baseline "summary".
    """
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> farming
        Digit("2"),    # state -> OTHER
        Digit("1"),    # gender -> female
        Digit("3"),    # social_category -> SC
        Digit("1"),    # read-back scheme 1: hear benefit_text
        Digit("9"), Digit("9"),   # read-back: walk the schemes
        Digit("2"),    # anything else -> no
    ])
    log = Log.open("test_p1_delivery", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    lines = [json.loads(l) for l in open(tmp_path / "test_p1_delivery.jsonl")]
    assert not [l for l in lines if l.get("invalid")]

    named = [t.split(":", 1)[1] for t in audio.played if t.startswith("name:")]
    deliveries = [l for l in lines if "slug" in l]
    assert len(deliveries) == len(named) == 2

    for rec, slug in zip(deliveries, named):
        assert rec["slug"] == slug
        assert rec["ending"] == DELIVERY_DIRECT_MATCH
        assert rec["lang"] == "hi"
        assert rec["sections"][0] == "summary"

    # Only the first scheme's read-back key was pressed.
    assert deliveries[0]["sections"] == ["summary", "benefit_text"]
    assert deliveries[1]["sections"] == ["summary"]


def test_delivery_record_nearest_summary_only(corpus, tmp_path):
    """D9: a Nearest terminal has no section_menu / read-back, but its named
    schemes were still spoken, so each still gets a DeliveryRecord (sections
    == ["summary"] only) and no invalid lines are written."""
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("2"),    # opener: category -> business_loans
        Digit("2"),    # state -> OTHER
        Digit("1"),    # gender -> female
        Digit("3"),    # social_category -> SC
        Digit("2"),    # anything else -> no
    ])
    log = Log.open("test_p2_delivery", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    lines = [json.loads(l) for l in open(tmp_path / "test_p2_delivery.jsonl")]
    assert not [l for l in lines if l.get("invalid")]

    named = [t.split(":", 1)[1] for t in audio.played if t.startswith("name:")]
    deliveries = [l for l in lines if "slug" in l]
    assert len(deliveries) == len(named) == 2
    for rec, slug in zip(deliveries, named):
        assert rec["slug"] == slug
        assert rec["ending"] == DELIVERY_NEAREST
        assert rec["sections"] == ["summary"]


def test_persona_p2_nearest_two_end_to_end(corpus, tmp_path):
    """P2 dead end: nothing matches, the ladder is exhausted, two nearest are named.

    The caller asks about handloom (business_loans) from outside Maharashtra.
    S5 (the sole business_loans scheme) is state=MAHARASHTRA-only (D6 fixture
    migration: KARNATAKA -> MAHARASHTRA), so it hard-misses this caller, and
    `category` is never widened (T10 D6 as amended), so the ladder runs out
    and the terminal is Nearest: preamble first, cap 2, summary only, no
    section_menu, auto-advance (T18 §2).
    """
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("2"),    # opener: category -> business_loans
        Digit("2"),    # state -> OTHER
        Digit("1"),    # gender -> female
        Digit("3"),    # social_category -> SC
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

    Round 2 asks category -> business_loans again; with state=OTHER carried
    over from round 1 (Door B clears only `category`), S5 hard-misses on
    state again, so round 2 also ends as a Nearest (see
    test_persona_p2_nearest_two_end_to_end).
    """
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> farming
        Digit("2"),    # state -> OTHER
        Digit("1"),    # gender -> female
        Digit("3"),    # social_category -> SC
        Digit("0"),    # read-back: none of these, leave the menu
        Digit("1"),    # anything else -> yes, Door B
        Digit("2"),    # opener again: category -> business_loans
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

    A caller who cannot name their subject declines it, so Door A drops to
    UNKNOWN and the Planner falls back to facts. income_band then contradicts
    a scheme, and dropping that one rung recovers it. T18 order: preamble ->
    drop_* -> lead -> names.

    category now has all 9 vocab.CATEGORY values as valid keys (D6, step
    1.5a), so "3" is a valid pick, not an out-of-menu strike. Step 1.6 (D7/F8)
    makes "0" mean "don't know" on every box, a one-key decline rather than a
    two-strike drop, so the opener input changed from "0","0" (strike, strike)
    to a single "0" (declined). S4's D6 fixture migration gives it back a real
    `state` constraint (MAHARASHTRA-only, like S3/S5), so state=OTHER excludes
    it here too. income_band is now a band box (step 1.5b): the fixture
    corpus's bands are ("0-29999", "30000-30000", "30001-49999",
    "50000-50000", "50001-74999", "75000-75000", "75001+"); key 4 =
    "50000-50000", which misses both S1 and S2 (their own bands are
    "75000-75000" and "30000-30000").
    """
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("0"),    # opener declined -> category = UNKNOWN
        Digit("4"),    # income_band -> "50000-50000" band
        Digit("2"),    # state -> OTHER
        Digit("1"),    # gender -> female
        Digit("3"),    # social_category -> SC
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
    # Door A was declined, and that is logged (D7/F8: "0" -> declined, not a strike)
    assert [
        l for l in lines
        if l.get("box") == "category" and l.get("unknown_source") == "declined"
    ]


def test_widened_match_with_door_a_answered(tmp_path, monkeypatch):
    """Shape 3 on the normal road: the caller names their subject, answers two
    soft boxes, and the second answer leaves nothing. One rung recovers it.

    fixtures/ is too small for this (five schemes narrow to <=4 or 0 before a
    second soft box is ever asked), so this builds a corpus where it is not:
    income_band 30000 holds farmers and weavers, only 75000 holds artisans, and
    every hard box is ANY. Planner asks income_band, then occupation; the caller
    says 30000 and artisan; dropping income_band brings the artisans back.
    """
    schemes = []
    for inc, occ, copies in (("30000", "farmer", 3), ("30000", "weaver", 3), ("75000", "artisan", 6)):
        for _ in range(copies):
            schemes.append({
                "scheme_id": f"G{len(schemes)}", "state": "ANY", "category": "farming",
                "gender": "ANY", "social_category": "ANY", "age": "ANY",
                "income_band": inc, "occupation": occ,
            })
    schemes.append({
        "scheme_id": "H0", "state": "ANY", "category": "business_loans",
        "gender": "ANY", "social_category": "ANY", "age": "ANY",
        "income_band": "ANY", "occupation": "ANY",
    })
    snap_dir = tmp_path / "gsnap"
    audio_dir = tmp_path / "gaudio"
    snap_dir.mkdir()
    audio_dir.mkdir()
    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(snap_dir))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(audio_dir))
    snap_id = build_snapshot(
        schemes_data=schemes, snapshot_id="test_widened_door_a",
        snapshots_dir=snap_dir, audio_dir=audio_dir, render_stubs=True,
    )
    c = Corpus.load(snap_id)
    # income_band is a band box (step 1.5b): bare-number 30000/75000 facets
    # become point bands, plus the open "0-29999" floor and "75001+" ceiling
    # that no scheme here constrains.
    assert c.values("income_band") == ("0-29999", "30000-30000", "30001-74999", "75000-75000", "75001+")
    # occupation is a vocab.py keypad box (D6, step 1.5a): values() is always
    # the full vocab.OCCUPATION list, in vocab order, not just what schemes use.
    assert c.values("occupation") == (
        "farmer", "street_vendor", "apprentice", "entrepreneur", "artisan", "weaver", "worker",
    )

    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> farming (answered, not struck out)
        Digit("2"),    # income_band -> "30000-30000" band
        Digit("5"),    # occupation -> artisan
        Digit("9"), Digit("9"), Digit("9"), Digit("9"),   # read-back
        Digit("2"),    # anything else -> no
    ])
    log = Log.open("test_widened_door_a", snap_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, c, log)

    played = audio.played
    assert "opener_prompt" in played
    assert TERMINAL_WIDENED_PREAMBLE in played
    drops = [t for t in played if t.startswith("drop_")]
    assert drops == ["drop_income_band"]
    names = [t for t in played if t.startswith("name:")]
    assert names and all(c.scheme_id(int(n.split(":")[1][1:])) for n in names)
    assert played.index(TERMINAL_WIDENED_PREAMBLE) < played.index(RESULTS_WIDENED_LEAD) < played.index(names[0])

    lines = [json.loads(l) for l in open(tmp_path / "test_widened_door_a.jsonl")]
    assert not [l for l in lines if l.get("class") == "UNCLEAR"]
    assert [l for l in lines if l.get("box") == "category" and l.get("value") == "farming"]
    assert lines[-1]["stop"] == STOP_ZERO_SURVIVORS
    assert lines[-1]["ladder_rung"] == 1


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


class _CardinalityOverrideCorpus:
    """Wraps a real Corpus, overriding values() for one box only, so a test can
    force it over KEYPAD_CARDINALITY_MAX without needing p6 to ever build such
    a snapshot (which it can no longer do, D6 step 1.5a — see
    test_box_drops_to_unknown_only_when_it_will_not_fit_a_keypad). Every other
    method (mask, scheme_id, chunks, audio, gate_notes, specificity, ...)
    delegates straight through to the real corpus.
    """

    def __init__(self, inner, box, fake_values):
        self._inner = inner
        self._box = box
        self._fake_values = fake_values

    def values(self, box):
        if box == self._box:
            return self._fake_values
        return self._inner.values(box)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_box_drops_to_unknown_only_when_it_will_not_fit_a_keypad(corpus, tmp_path):
    """T18 §3 is a cardinality test, not a hard-coded box: call.py's safety net
    (a box with > KEYPAD_CARDINALITY_MAX values drops to UNKNOWN,
    unknown_source="keypad_dropped", and is never prompted) has to fire for
    whatever box the planner would otherwise ask, not just `state`.

    p6 can no longer itself produce a box with > 9 values (D6, step 1.5a: the
    5 vocab.KEYPAD_LISTS boxes are always the full, <=9-item vocab list, and
    age/income_band bands are always capped at KEYPAD_CARDINALITY_MAX too), so
    build_snapshot() can no longer construct the corpus this test used to
    build. The engine's safety net in call.py is untouched and still has to
    hold, so this tests it directly: take the real fixture corpus and wrap it
    so `values("state")` returns 10 entries, without needing p6 involved at
    all.
    """
    over_cap = tuple(f"STATE_{i}" for i in range(tunables.KEYPAD_CARDINALITY_MAX + 1))
    wide_corpus = _CardinalityOverrideCorpus(corpus, "state", over_cap)
    assert len(wide_corpus.values("state")) > tunables.KEYPAD_CARDINALITY_MAX

    audio = MockAudio(inputs=[Digit("1"), Digit("1"), Digit("1"), Digit("2")])
    log = Log.open("test_wide", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, wide_corpus, log)

    assert "state_q_maharashtra" not in audio.played, "an over-cardinality box must never be prompted"

    lines = [json.loads(l) for l in open(tmp_path / "test_wide.jsonl")]
    dropped = [
        l for l in lines
        if l.get("box") == "state" and l.get("unknown_source") == "keypad_dropped"
    ]
    assert dropped, "the keypad drop was not logged"
    assert dropped[0]["value"] == UNKNOWN

    # Contrast: with <= 9 values (the real fixture corpus, 2 states) `state`
    # is asked like any other box — the safety net does not fire when it
    # shouldn't.
    assert len(corpus.values("state")) <= tunables.KEYPAD_CARDINALITY_MAX
    audio_normal = MockAudio(inputs=[Digit("1"), Digit("1"), Digit("1"), Digit("1"), Digit("2")])
    log_normal = Log.open("test_normal_state", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio_normal, None, corpus, log_normal)
    assert "state_q_maharashtra" in audio_normal.played


# ---------------------------------------------------------------------------
# 3b. Step 1.6: state question + key 0 = "don't know" (D7, F8)
# ---------------------------------------------------------------------------

def test_state_yes_names_a_maharashtra_only_scheme(corpus, tmp_path):
    """Pressing 1 on state_q_maharashtra means "yes" (MAHARASHTRA): a
    Maharashtra-only fixture scheme (S3) is named, alongside the nationwide
    ones (S1, S2)."""
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> farming
        Digit("1"),    # state -> MAHARASHTRA (yes)
        Digit("1"),    # gender -> female
        Digit("3"),    # social_category -> SC
        Digit("9"), Digit("9"), Digit("9"),   # read-back: walk the schemes
        Digit("2"),    # anything else -> no
    ])
    log = Log.open("test_state_yes", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    names = {t.split(":", 1)[1] for t in audio.played if t.startswith("name:")}
    assert "S3" in names, "the Maharashtra-only scheme must be named after state=1"


def test_state_no_keeps_only_central_schemes(corpus, tmp_path):
    """Pressing 2 on state_q_maharashtra means "no" (OTHER): only nationwide
    schemes (S1, S2) are named, never a Maharashtra-only one (S3, S4, S5)."""
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> farming
        Digit("2"),    # state -> OTHER (no)
        Digit("1"),    # gender -> female
        Digit("3"),    # social_category -> SC
        Digit("9"), Digit("9"), Digit("9"),   # read-back: walk the schemes
        Digit("2"),    # anything else -> no
    ])
    log = Log.open("test_state_no", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    names = {t.split(":", 1)[1] for t in audio.played if t.startswith("name:")}
    assert names, "expected at least the nationwide schemes to be named"
    assert not (names & {"S3", "S4", "S5"}), "a Maharashtra-only scheme must never be named after state=2"


def test_state_zero_declines_with_no_strike_and_disclaimer(corpus, tmp_path):
    """Pressing 0 on state_q_maharashtra is a real answer (UNKNOWN, declined):
    no strike, no UNCLEAR record, state_unknown_disclaimer plays, the
    nationwide schemes are named, and no Maharashtra-only scheme is named."""
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> farming
        Digit("0"),    # state -> UNKNOWN (don't know)
        Digit("1"),    # gender -> female
        Digit("3"),    # social_category -> SC
        Digit("9"), Digit("9"), Digit("9"),   # read-back: walk the schemes
        Digit("2"),    # anything else -> no
    ])
    log = Log.open("test_state_zero", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    assert STATE_UNKNOWN_DISCLAIMER in audio.played
    names = {t.split(":", 1)[1] for t in audio.played if t.startswith("name:")}
    assert names, "expected the nationwide schemes to be named"
    assert not (names & {"S3", "S4", "S5"}), "a Maharashtra-only scheme must never be named when state is unknown"

    lines = [json.loads(l) for l in open(tmp_path / "test_state_zero.jsonl")]
    state_answers = [l for l in lines if l.get("class") == "ANSWER" and l.get("box") == "state"]
    assert len(state_answers) == 1
    assert state_answers[0]["value"] == UNKNOWN
    assert state_answers[0]["unknown_source"] == "declined"
    assert not [l for l in lines if l.get("class") == "UNCLEAR" and l.get("transcript") == "0"]


def test_zero_declines_any_box_with_no_strike(corpus, tmp_path):
    """Key 0 means "don't know" on any box, not only state: it is logged as a
    real ANSWER (UNKNOWN, declined), never as a strike."""
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> farming
        Digit("2"),    # state -> OTHER
        Digit("0"),    # gender -> UNKNOWN (don't know)
        Digit("3"),    # social_category -> SC
        Digit("2"),    # anything else -> no (whatever the outcome)
    ])
    log = Log.open("test_zero_any_box", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    lines = [json.loads(l) for l in open(tmp_path / "test_zero_any_box.jsonl")]
    gender_answers = [l for l in lines if l.get("class") == "ANSWER" and l.get("box") == "gender"]
    assert len(gender_answers) == 1
    assert gender_answers[0]["value"] == UNKNOWN
    assert gender_answers[0]["unknown_source"] == "declined"
    assert not [l for l in lines if l.get("class") == "UNCLEAR" and l.get("transcript") == "0"]


def test_state_prompt_id_is_state_q_maharashtra(corpus, tmp_path):
    """The state box plays state_q_maharashtra, never a generic keypad_state
    prompt (step 1.6, D7/F8)."""
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> farming
        Digit("1"),    # state -> MAHARASHTRA
        Digit("1"),    # gender -> female
        Digit("3"),    # social_category -> SC
        Digit("9"), Digit("9"), Digit("9"),
        Digit("2"),
    ])
    log = Log.open("test_state_prompt_id", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    assert "state_q_maharashtra" in audio.played
    assert "keypad_state" not in audio.played


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


# ---------------------------------------------------------------------------
# 5. Step 1.8: Ranking & Paging (D8) Tests
# ---------------------------------------------------------------------------

def test_star_in_read_back_switches_language_and_logs_switch(corpus, tmp_path):
    """D13's `*` cycle also works on the read-back menu (step 1.8, shared with
    the question phase via _next_lang): it rotates the language, logs a
    LangSwitchRecord, and replays the current scheme's block without advancing."""
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> farming
        Digit("2"),    # state -> OTHER
        Digit("1"),    # gender -> female
        Digit("3"),    # social_category -> SC
        Digit("*"),    # read-back: switch language, replay scheme 1
        Digit("9"), Digit("9"),   # read-back: walk the schemes to the end
        Digit("2"),    # anything else -> no
    ])
    log = Log.open("test_readback_star", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    assert audio.language == "mr"
    # name:S1's block was said twice: once by the initial terminal play, once
    # again by the `*` replay.
    assert audio.played.count("name:S1") == 2

    lines = [json.loads(l) for l in open(tmp_path / "test_readback_star.jsonl")]
    switches = [l for l in lines if l.get("lang") == "mr" and l.get("lang_source") == "keypad"]
    assert len(switches) == 1


def test_unmapped_digit_replays_section_menu_and_does_not_leave(corpus, tmp_path):
    """Step 1.8: an unmapped read-back digit (5-8) replays section_menu on the
    same scheme instead of leaving the menu."""
    audio = MockAudio(inputs=[
        Digit("1"),    # Turn 0 (hi)
        Digit("1"),    # opener: category -> farming
        Digit("2"),    # state -> OTHER
        Digit("1"),    # gender -> female
        Digit("3"),    # social_category -> SC
        Digit("5"),    # read-back: unmapped digit -> replay section_menu
        Digit("9"), Digit("9"),   # read-back: walk the schemes to the end
        Digit("2"),    # anything else -> no
    ])
    log = Log.open("test_readback_replay", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)

    assert audio.hung_up
    assert "no_more_schemes" in audio.played
    # 2 named schemes each get one section_menu from the initial terminal
    # play, plus one extra from the "5" replay.
    assert audio.played.count(SECTION_MENU) == 3


def test_read_back_pages_10_survivors_3_3_3_1_in_priority_slug_order(tmp_path, monkeypatch):
    """Step 1.8 (D8): with more speakable candidates than were named, the
    read-back menu pages through the rest as 3 + 3 + 1 (on top of the 3 already
    named), each page led by results_more_prompt, in the same specificity ->
    priority -> slug order p6's (priority, slug) bit assignment already gives
    (all 10 schemes here tie on specificity, so this exercises the priority ->
    slug tie-break end to end)."""
    snap_dir = tmp_path / "snap_page"
    audio_dir = tmp_path / "audio_page"
    snap_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(snap_dir))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(audio_dir))

    base = {"state": "ANY", "category": "farming", "gender": "ANY",
            "social_category": "ANY", "age": "ANY", "income_band": "ANY",
            "occupation": "ANY"}
    priorities = [1, 1, 1, 2, 2, 2, 2, 3, 3, 3]
    schemes = [
        {"scheme_id": f"s{i + 1:02d}", "priority": p, **base}
        for i, p in enumerate(priorities)
    ]
    snap_id = build_snapshot(
        schemes_data=schemes, snapshot_id="test_page10",
        snapshots_dir=snap_dir, audio_dir=audio_dir, render_stubs=True,
    )
    c = Corpus.load(snap_id)

    ranked_ids = [c.scheme_id(i) for i in Terminals.ranked(list(range(10)), c)]
    assert ranked_ids == [f"s{i:02d}" for i in range(1, 11)]

    named = ranked_ids[:3]
    rest = ranked_ids[3:]
    sections_heard = {n: ["summary"] for n in named}

    audio = MockAudio(inputs=[Digit("9")] * 10)
    log = Log.open("test_page10", snap_id, logs_dir=tmp_path)
    kept_going = Engine._read_back(audio, named, sections_heard, rest, c, log, turn_n=4)
    log.close(reason=STOP_LE_4_SURVIVORS)

    assert kept_going
    assert named == ranked_ids
    assert rest == []

    more_prompt_indices = [i for i, t in enumerate(audio.played) if t == RESULTS_MORE_PROMPT]
    assert len(more_prompt_indices) == 3

    idx_s04 = audio.played.index("name:s04")
    idx_s07 = audio.played.index("name:s07")
    idx_s10 = audio.played.index("name:s10")
    assert audio.played[idx_s04 - 1] == RESULTS_MORE_PROMPT
    assert audio.played[idx_s07 - 1] == RESULTS_MORE_PROMPT
    assert audio.played[idx_s10 - 1] == RESULTS_MORE_PROMPT

    def _names_between(start: int, end: Optional[int]) -> list[str]:
        segment = audio.played[start:end]
        return [t for t in segment if t.startswith("name:")]

    assert _names_between(idx_s04 - 1, idx_s07 - 1) == ["name:s04", "name:s05", "name:s06"]
    assert _names_between(idx_s07 - 1, idx_s10 - 1) == ["name:s07", "name:s08", "name:s09"]
    assert _names_between(idx_s10 - 1, None) == ["name:s10"]


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
