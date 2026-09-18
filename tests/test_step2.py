"""tests/test_step2.py

Tests for Step 2 of Haqdaar v2:
- Root shim package `contracts/` deleted; `import contracts` fails
- `haqdaar.contracts.log_schema` types, turn accounting, and stop reasons
- `fixtures/` loading: 5 valid schemes (S1-S5) + S6 gate rejection test
- 3 personas, 9 utterances, and ~10 audio stubs with valid index.json digests
"""

import hashlib
import json
from pathlib import Path
import pytest

from haqdaar.contracts import log_schema, tunables, types
from haqdaar.contracts.log_schema import (
    CallCloseRecord,
    CallOpenRecord,
    LangSwitchRecord,
    TurnLogRecord,
    TURN_CLASSES,
    STOP_REASONS,
    STOP_LE_4_SURVIVORS,
    STOP_MAX_TURNS,
    STOP_MAX_QUESTIONS,
    STOP_NO_SPLIT,
    STOP_ZERO_SURVIVORS,
)
from haqdaar.contracts.types import (
    ANY,
    HARD_BOXES,
    SCHEME_CHUNKS,
    SEVEN_BOXES,
    compute_render_key,
)
from haqdaar.data.pipeline.p6_snapshot import (
    BuildGateError,
    apply_readback_completeness_gate,
    validate_readback_completeness,
    build_snapshot,
)
from haqdaar.audio.pool import AudioPool

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"


# ---------------------------------------------------------------------------
# 1. Package & Shim Tests
# ---------------------------------------------------------------------------

def test_root_contracts_shim_is_deleted():
    """Verify top-level 'contracts' package is deleted and raises ModuleNotFoundError."""
    with pytest.raises(ModuleNotFoundError):
        import contracts  # type: ignore # noqa: F401


def test_contracts_exports_and_tunables():
    """Verify canonical haqdaar.contracts exports types, tunables, and log_schema."""
    assert tunables.MAX_TURNS == 8
    assert tunables.MAX_QUESTIONS == 6
    assert tunables.ENDPOINT_MS == 700
    assert tunables.STOP_SURVIVORS == 4
    assert tunables.NEAREST_CAP == 2
    assert tunables.AUDIO_TIER2 == "none"

    assert len(SEVEN_BOXES) == 7
    assert "state" in HARD_BOXES
    assert len(SCHEME_CHUNKS) == 6


# ---------------------------------------------------------------------------
# 2. Log Schema Tests
# ---------------------------------------------------------------------------

def test_log_schema_records():
    """Verify all log record dataclasses instantiate and hold correct values."""
    open_rec = CallOpenRecord(
        call_id="call_123",
        snapshot_id="snap_001",
        caller_hash="hash_abc",
        lang="hi",
        lang_source="keypad",
        t0=1000.0,
    )
    assert open_rec.call_id == "call_123"
    assert open_rec.lang == "hi"
    assert open_rec.lang_source == "keypad"

    # ANSWER turn
    turn_answer = TurnLogRecord(
        turn_n=1,
        turn_class="ANSWER",
        transcript="I am a farmer",
        box="occupation",
        value="farmer",
        span="farmer",
    )
    assert turn_answer.turn_class == "ANSWER"
    assert turn_answer.box == "occupation"
    assert turn_answer.value == "farmer"

    # NOISE turn (thin record consuming cap turn)
    turn_noise = TurnLogRecord(
        turn_n=2,
        turn_class="NOISE",
    )
    assert turn_noise.turn_class == "NOISE"
    assert turn_noise.transcript is None

    # SILENCE turn (carries silence_n and unchanged turn_n)
    turn_silence = TurnLogRecord(
        turn_n=2,
        turn_class="SILENCE",
        silence_n=1,
    )
    assert turn_silence.turn_class == "SILENCE"
    assert turn_silence.silence_n == 1

    # Language switch
    switch_rec = LangSwitchRecord(lang="mr", lang_source="keypad", turn_n=3)
    assert switch_rec.lang == "mr"
    assert switch_rec.turn_n == 3

    # Close records for key stop reasons
    close_rec = CallCloseRecord(
        stop=STOP_LE_4_SURVIVORS,
        ladder_rung=0,
        mode="voice",
    )
    assert close_rec.stop == "survivors_le_4"
    assert close_rec.ladder_rung == 0

    # Ensure all stop reasons are recognized
    for stop_reason in (
        STOP_LE_4_SURVIVORS,
        STOP_MAX_TURNS,
        STOP_MAX_QUESTIONS,
        STOP_NO_SPLIT,
        STOP_ZERO_SURVIVORS,
    ):
        assert stop_reason in STOP_REASONS

    # Ensure all turn classes are recognized
    for tc in ("ANSWER", "CLARIFY", "REPEAT", "META", "UNCLEAR", "NOISE", "SILENCE"):
        assert tc in TURN_CLASSES


# ---------------------------------------------------------------------------
# 3. Fixtures Schemes Loading and S6 Build Gate Rejection
# ---------------------------------------------------------------------------

def test_fixtures_schemes_load_and_validate():
    """Load fixtures/schemes.jsonl, verify all 6 rows load with no validation error."""
    schemes_file = FIXTURES_DIR / "schemes.jsonl"
    assert schemes_file.exists(), f"Missing {schemes_file}"

    schemes = []
    with open(schemes_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            schemes.append(row)

    assert len(schemes) == 6, f"Expected 6 schemes, got {len(schemes)}"
    scheme_ids = [s["scheme_id"] for s in schemes]
    assert scheme_ids == ["S1", "S2", "S3", "S4", "S5", "S6"]

    # Verify S1–S5 valid roles
    s1, s2, s3, s4, s5, s6 = schemes

    # S1: Happy path match (state is ANY/central, D6 fixture migration: BIHAR -> ANY)
    assert s1["state"] == "ANY"
    assert s1["category"] == "farming"
    assert s1["occupation"] == "farmer"
    assert "kcc" in s1["aliases_en"]

    # S2: Soft-miss on income_band only (30,000 cutoff)
    assert s2["income_band"] == 30000
    assert s2["state"] == "ANY"

    # S3: Hard-miss on state (D6 fixture migration: KARNATAKA -> MAHARASHTRA)
    assert s3["state"] == "MAHARASHTRA"

    # S4: Near-ANY generic (specificity 2, holds ANY on 5 boxes)
    any_boxes = [box for box in ("gender", "social_category", "age", "income_band", "occupation") if s4[box] == ANY]
    assert len(any_boxes) == 5

    # S5: Door A alias clash with S1 (shares 'kcc')
    assert "kcc" in s5["aliases_en"]
    assert "केसीसी" in s5["aliases_hi"]

    # Check that S1–S5 have all 6 chunks across all 3 languages
    for s in (s1, s2, s3, s4, s5):
        ok, reason = validate_readback_completeness(s)
        assert ok is True, f"Scheme {s['scheme_id']} unexpectedly failed Gate 3: {reason}"


def test_fixtures_s6_rejected_at_build_gate():
    """Verify S6 is missing Marathi summary and is strictly rejected by the build gate."""
    schemes_file = FIXTURES_DIR / "schemes.jsonl"
    schemes = []
    with open(schemes_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                schemes.append(json.loads(line.strip()))

    s6 = next(s for s in schemes if s["scheme_id"] == "S6")

    # 1. Direct check: Marathi summary must be missing
    assert "summary" not in s6["chunks"]["mr"], "S6 must be missing its Marathi summary chunk"

    # 2. Gate 3 validator rejects S6
    ok, reason = validate_readback_completeness(s6)
    assert ok is False
    assert "summary" in reason
    assert "mr" in reason

    # 3. apply_readback_completeness_gate filters S6 into rejected
    accepted, rejected = apply_readback_completeness_gate(schemes)
    assert len(accepted) == 5
    assert [s["scheme_id"] for s in accepted] == ["S1", "S2", "S3", "S4", "S5"]
    assert len(rejected) == 1
    rejected_scheme, rej_reason = rejected[0]
    assert rejected_scheme["scheme_id"] == "S6"
    assert "summary" in rej_reason

    # 4. Strict mode raises BuildGateError
    with pytest.raises(BuildGateError, match="Gate 3 rejection"):
        apply_readback_completeness_gate([s6], strict=True)


def test_build_snapshot_enforces_readback_gate(tmp_path):
    """Verify build_snapshot rejects S6 when enforce_readback_gate=True."""
    schemes_file = FIXTURES_DIR / "schemes.jsonl"
    schemes = [json.loads(line) for line in open(schemes_file) if line.strip()]
    s6 = [s for s in schemes if s["scheme_id"] == "S6"]

    with pytest.raises(BuildGateError, match="Gate 3 rejected scheme S6"):
        build_snapshot(
            schemes_data=s6,
            snapshots_dir=tmp_path / "snaps",
            audio_dir=tmp_path / "audio",
            enforce_readback_gate=True,
        )


# ---------------------------------------------------------------------------
# 4. Personas & Utterances Tests
# ---------------------------------------------------------------------------

def test_fixtures_personas_load():
    """Verify fixtures/personas.json loads cleanly with all 3 required personas."""
    personas_file = FIXTURES_DIR / "personas.json"
    assert personas_file.exists()

    with open(personas_file, "r", encoding="utf-8") as f:
        personas = json.load(f)

    assert len(personas) == 3
    p1, p2, p3 = personas

    assert p1["persona_id"] == "P1"
    assert p1["target_scheme"] == "S1"
    assert p1["expected_stop"] == "survivors_le_4"

    assert p2["persona_id"] == "P2"
    assert p2["target_scheme"] is None
    assert p2["expected_stop"] == "zero_survivors"
    assert "S1" in p2["expected_nearest"]

    assert p3["persona_id"] == "P3"
    assert p3["door_a_alias"] == "kcc"
    assert p3["expected_candidates"] == ["S1", "S5"]


def test_fixtures_utterances_load():
    """Verify fixtures/utterances.json loads cleanly with 9 utterances (3 per persona)."""
    utterances_file = FIXTURES_DIR / "utterances.json"
    assert utterances_file.exists()

    with open(utterances_file, "r", encoding="utf-8") as f:
        utterances = json.load(f)

    assert len(utterances) == 9

    personas_seen = set()
    langs_seen = set()
    for u in utterances:
        personas_seen.add(u["persona_id"])
        langs_seen.add(u["lang"])
        assert len(u["transcript"]) > 0
        assert len(u["expected_stamps"]) > 0
        for stamp in u["expected_stamps"]:
            assert "box" in stamp
            assert "value" in stamp
            assert "span" in stamp
            # Verify the extracted span exists in the transcript
            assert stamp["span"] in u["transcript"]

    assert personas_seen == {"P1", "P2", "P3"}
    assert langs_seen == {"en", "hi", "mr"}


# ---------------------------------------------------------------------------
# 5. Audio Stubs & Index Tests
# ---------------------------------------------------------------------------

def test_fixtures_audio_stubs_integrity():
    """Verify audio stubs exist, have correct size, match SHA256 in index.json."""
    audio_dir = FIXTURES_DIR / "audio"
    index_file = audio_dir / "index.json"
    assert index_file.exists()

    with open(index_file, "r", encoding="utf-8") as f:
        index = json.load(f)

    assert len(index) >= 10, f"Expected at least 10 audio stubs, found {len(index)}"

    for rk, meta in index.items():
        ulaw_file = audio_dir / f"{rk}.ulaw"
        assert ulaw_file.exists(), f"Missing audio stub: {ulaw_file}"

        data = ulaw_file.read_bytes()
        assert len(data) == meta["size"]

        computed_sha = hashlib.sha256(data).hexdigest()
        assert computed_sha == meta["digest"]

        # Verify all bytes are 0xFF (standard silence in μ-law)
        assert data == b"\xff" * len(data)

    # Verify AudioPool can initialize with fixtures/audio/ without errors
    pool = AudioPool(audio_dir=str(audio_dir))
    first_rk = next(iter(index.keys()))
    audio_bytes = pool.get(first_rk)
    assert audio_bytes is not None
    assert len(audio_bytes) == index[first_rk]["size"]
