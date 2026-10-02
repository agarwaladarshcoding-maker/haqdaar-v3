"""tests/test_judge.py

Tests for tools/judge.py offline delivery log judge and sim opener UNCLEAR asymmetry fix.
- Evaluates 8 hand-made fixture logs in fixtures/judge_logs/ (PASS and FAIL conditions).
- Validates CLI runner and per-call exit codes.
- Tests T04 truth conditions (untrue claims, unprompted hangup, ended before terminal).
- Tests that PROPOSAL lines are ignored and only ANSWER lines count.
- Tests sim opener UNCLEAR-vs-empty-stamps symmetry (identical log + next-turn behavior).
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from haqdaar.audio.phone import Input
from haqdaar.contracts import tunables
from haqdaar.contracts.log_schema import (
    STOP_LE_4_SURVIVORS,
    STOP_MAX_QUESTIONS,
    STOP_MAX_TURNS,
    STOP_NO_SPLIT,
    STOP_ZERO_SURVIVORS,
)
from haqdaar.contracts.types import Digit, Speech, Unclear
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.engine.call import Engine
from haqdaar.model.client import ModelClientResponse
from haqdaar.model.router import Model
from haqdaar.sim import FakeAudio
from tools.judge import JudgeResult, judge_call_log, judge_logs_dir, run_judge

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "judge_logs"


def test_hand_made_pass_direct_match():
    """pass-direct-match.jsonl delivers true direct matches honestly."""
    res = judge_call_log(FIXTURES_DIR / "pass-direct-match.jsonl")
    assert res.passed is True
    assert "delivered 4 direct_match schemes honestly" in res.reason


def test_hand_made_pass_dead_end_with_ladder():
    """pass-dead-end-with-ladder.jsonl executes full widening ladder and labels nearest."""
    res = judge_call_log(FIXTURES_DIR / "pass-dead-end-with-ladder.jsonl")
    assert res.passed is True
    assert "dead-end through full ladder (rung 4)" in res.reason
    assert "labelled nearest" in res.reason


def test_hand_made_pass_keypad_only_terminal():
    """pass-keypad-only-terminal.jsonl reaches ordinary terminal in keypad-only mode."""
    res = judge_call_log(FIXTURES_DIR / "pass-keypad-only-terminal.jsonl")
    assert res.passed is True
    assert "delivered 1 direct_match schemes honestly" in res.reason


def test_hand_made_pass_proposal_ignored():
    """PROPOSAL-ignored.jsonl scores on confirmed ANSWER, ignoring preceding PROPOSAL."""
    res = judge_call_log(FIXTURES_DIR / "PROPOSAL-ignored.jsonl")
    assert res.passed is True
    assert "delivered 2 direct_match schemes honestly" in res.reason


def test_hand_made_fail_untrue_nearest_as_match():
    """fail-untrue-nearest-as-match.jsonl fails when nearest schemes read non-summary sections."""
    res = judge_call_log(FIXTURES_DIR / "fail-untrue-nearest-as-match.jsonl")
    assert res.passed is False
    assert "untrue: nearest read as matches" in res.reason


def test_hand_made_fail_dead_end_without_ladder():
    """fail-dead-end-without-ladder.jsonl fails when dead-end has answered soft boxes but rung 0."""
    res = judge_call_log(FIXTURES_DIR / "fail-dead-end-without-ladder.jsonl")
    assert res.passed is False
    assert "untrue: dead-end without the widening step" in res.reason


def test_hand_made_fail_ended_before_terminal():
    """fail-ended-before-terminal.jsonl fails when call terminates mid-air."""
    res = judge_call_log(FIXTURES_DIR / "fail-ended-before-terminal.jsonl")
    assert res.passed is False
    assert "ended before a terminal state" in res.reason


def test_hand_made_fail_unprompted_hangup():
    """fail-unprompted-hangup.jsonl fails when system-side close reason shows hangup before terminal."""
    res = judge_call_log(FIXTURES_DIR / "fail-unprompted-hangup.jsonl")
    assert res.passed is False
    assert "system hung up unprompted" in res.reason


def test_judge_cli_exit_codes():
    """run_judge returns exit 0 when all pass, exit 1 if any fail, exit 1 on invalid path."""
    assert run_judge(FIXTURES_DIR / "pass-direct-match.jsonl") == 0
    assert run_judge(FIXTURES_DIR / "fail-unprompted-hangup.jsonl") == 1
    assert run_judge(Path("non_existent_directory_or_file.jsonl")) == 1


def test_judge_in_memory_records():
    """In-memory record lists validate T04 truth and boundary conditions."""
    # 1. Untrue: scheme name outside corpus
    records_bad_scheme = [
        {"call_id": "test_bad_slug", "snapshot_id": "CURRENT"},
        {"turn_n": 1, "class": "ANSWER", "box": "category", "value": "farming"},
        {"slug": "non_existent_fake_scheme", "ending": "direct_match", "sections": ["summary"]},
        {"stop": "survivors_le_4", "ladder_rung": 0},
    ]
    res = judge_call_log(records_bad_scheme)
    assert res.passed is False
    assert "outside corpus" in res.reason

    # 2. Untrue: section claim outside allowed corpus sections
    records_bad_section = [
        {"call_id": "test_bad_section", "snapshot_id": "CURRENT"},
        {"turn_n": 1, "class": "ANSWER", "box": "category", "value": "farming"},
        {"slug": "pm-kisan", "ending": "direct_match", "sections": ["invalid_section_claim"]},
        {"stop": "survivors_le_4", "ladder_rung": 0},
    ]
    res = judge_call_log(records_bad_section)
    assert res.passed is False
    assert "benefit/document claim outside corpus" in res.reason

    # 3. Untrue: scheme not in survivors for answered box vector
    records_surv_mismatch = [
        {"call_id": "test_surv_mismatch", "snapshot_id": "CURRENT"},
        {"turn_n": 1, "class": "ANSWER", "box": "category", "value": "jobs_skills"},
        # pm-kisan is in category=farming, not jobs_skills
        {"slug": "pm-kisan", "ending": "direct_match", "sections": ["summary"]},
        {"stop": "survivors_le_4", "ladder_rung": 0},
    ]
    res = judge_call_log(records_surv_mismatch)
    assert res.passed is False
    assert "not in survivors for answered vector" in res.reason


def test_sim_opener_router_unclear_vs_empty_stamps_symmetry():
    """Router.opener returns Unclear(reason='unclear') for both UNCLEAR class and empty stamps."""
    class MockClient:
        def __init__(self, data):
            self.data = data

        def call(self, messages, task=None):
            return ModelClientResponse(success=True, data=self.data, latency_s=0.005)

    model_unclear = Model(client=MockClient({"class": "UNCLEAR", "stamps": []}))
    res_unclear = model_unclear.opener("xyz unknown opener words", lang="hi")

    model_empty_stamps = Model(client=MockClient({"stamps": []}))
    res_empty_stamps = model_empty_stamps.opener("xyz unknown opener words", lang="hi")

    model_unclear_only = Model(client=MockClient({"class": "UNCLEAR"}))
    res_unclear_only = model_unclear_only.opener("xyz unknown opener words", lang="hi")

    assert isinstance(res_unclear, Unclear)
    assert isinstance(res_empty_stamps, Unclear)
    assert isinstance(res_unclear_only, Unclear)

    assert res_unclear.reason == res_empty_stamps.reason == res_unclear_only.reason == "unclear"


def test_sim_opener_call_execution_symmetry(tmp_path, monkeypatch):
    """Unmatched opener speech produces identical log and next-turn behavior whether

    expressed as UNCLEAR class or empty stamps.
    """
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
        snapshot_id="test_judge_snap",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=True,
    )
    corpus = Corpus.load(snap_id)

    class CustomModelClient:
        def __init__(self, opener_payload):
            self.opener_payload = opener_payload

        def call(self, messages, task=None):
            if task == "model_opener":
                return ModelClientResponse(success=True, data=self.opener_payload, latency_s=0.005)
            # Default response
            return ModelClientResponse(success=True, data={}, latency_s=0.005)

    def run_sim_call(call_name: str, opener_payload: dict):
        # Caller inputs:
        # Turn 0: language selection (hi)
        # Turn 1: spoken opener (unmatched speech) -> triggers unclear_prompt and re-ask
        # Turn 2: keypad digit 1 (category=farming)
        # Turn 3: keypad digit 1 (state=OTHER)
        # Turn 4: keypad digit 1 (gender=female)
        # Turn 5: keypad digit 1 (social_category=SC)
        inputs: list[Input] = [
            Digit("1"),                             # hi
            Speech("unmatched speech content"),     # opener speech
            Digit("1"),                             # farming
            Digit("1"),
            Digit("1"),
            Digit("1"),
            Digit("1"),
            Digit("1"),
        ]
        audio = FakeAudio(inputs)
        model = Model(corpus=corpus, client=CustomModelClient(opener_payload))
        log = Log.open(call_name, corpus.snapshot_id, logs_dir=tmp_path)
        Engine.run_call(audio, model, corpus, log)

        # Read log lines (excluding call_id and timestamps)
        log_file = tmp_path / f"{call_name}.jsonl"
        lines = []
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line.strip())
                r.pop("call_id", None)
                r.pop("t0", None)
                lines.append(r)
        return lines, audio.played_lines

    # Run Call A with {"class": "UNCLEAR", "stamps": []}
    lines_a, played_a = run_sim_call("call_a", {"class": "UNCLEAR", "stamps": []})

    # Run Call B with {"stamps": []}
    lines_b, played_b = run_sim_call("call_b", {"stamps": []})

    # 1. Assert identical audio lines played
    assert played_a == played_b
    assert "unclear_prompt" in played_a

    # 2. Assert identical logged turn records and flow
    assert lines_a == lines_b

    # 3. Assert turn 1 was logged as UNCLEAR
    turn1_records = [r for r in lines_a if r.get("turn_n") == 1]
    assert len(turn1_records) == 1
    assert turn1_records[0].get("class") == "UNCLEAR" or turn1_records[0].get("turn_class") == "UNCLEAR"
