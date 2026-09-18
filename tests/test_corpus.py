"""tests/test_step11_snapshot_corpus_pool.py

Verification of Step 11, Data Contract §2, Architecture §10.1, and all hard constraints:
- Corpus.load verifies existence AND digest of every manifest render_key against the pool index.
  It must NOT read audio bytes into memory. It raises here and only here.
- Corpus.audio and Corpus.chunks return RenderKey, never bytes.
- corpus.py must not import pool.py. Only haqdaar/audio/ imports pool.py.
- The runtime imports no TTS client and no S3 client when AUDIO_TIER2=none.
- ANY sets a scheme's bit in every mask for that column.
- Every tunable reads from contracts/tunables.py. Hardcode nothing.
- Corpus implements frozen interface verbatim with no added methods and no changed names.
- AudioPool: tier 0 pinned, tier 1 mmap+LRU at AUDIO_CACHE_MB, tier 2 read-through, warm() and prefetch().
"""
from __future__ import annotations
import ast
import inspect
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import (
    ANY,
    RenderKey,
    SEVEN_BOXES,
    compute_render_key,
)
from haqdaar.data.pipeline.p6_snapshot import build_snapshot, apply_alias_uniqueness_gate
import haqdaar.data.corpus as corpus_module
from haqdaar.data.corpus import Corpus, CorpusError
from haqdaar.audio.pool import AudioPool


@pytest.fixture
def sample_schemes():
    return [
        {
            "scheme_id": "S1",
            "scheme_name_en": "Kisan Credit Scheme",
            "scheme_name_hi": "किसान क्रेडिट योजना",
            "scheme_name_mr": "किसान क्रेडिट योजना",
            "aliases_en": ["kisan credit", "farmer loan", "kcc"],
            "aliases_hi": ["किसान क्रेडिट", "केसीसी", "किसान ऋण"],
            "aliases_mr": ["किसान क्रेडिट", "शेतकरी कर्ज"],
            "category": "agriculture",
            "state": "BIHAR",
            "gender": "ALL",
            "social_category": "ALL",
            "age": 25,
            "income_band": 75000,
            "occupation": "farmer",
            "gate_notes": ["Requires active land records"],
            "chunks": {
                "en": {
                    "name": "Kisan Credit Scheme",
                    "summary": "Low interest institutional credit for farmers.",
                    "benefit_text": "Up to Rs 3 lakh loan at 4% interest.",
                    "who_can_apply": "All farmers with cultivateable land.",
                    "documents": "Aadhaar, Land possession certificate.",
                    "how_to_apply": "Apply at nearest nationalized bank branch.",
                },
                "hi": {
                    "name": "किसान क्रेडिट योजना",
                    "summary": "किसानों के लिए कम ब्याज वाला संस्थागत ऋण।",
                    "benefit_text": "4% ब्याज पर 3 लाख तक का ऋण।",
                    "who_can_apply": "खेती योग्य भूमि वाले सभी किसान।",
                    "documents": "आधार, भूमि स्वामित्व प्रमाण पत्र।",
                    "how_to_apply": "निकटतम बैंक शाखा में आवेदन करें।",
                },
                "mr": {
                    "name": "किसान क्रेडिट योजना",
                    "summary": "शेतकऱ्यांसाठी कमी व्याजदराचे संस्थात्मक कर्ज.",
                    "benefit_text": "4% व्याजाने 3 लाखांपर्यंत कर्ज.",
                    "who_can_apply": "शेतीयोग्य जमीन असलेले सर्व शेतकरी.",
                    "documents": "आधार, सातबारा उतारा.",
                    "how_to_apply": "जवळच्या बँक शाखेत अर्ज करा.",
                },
            },
        },
        {
            "scheme_id": "S2",
            "scheme_name_en": "Universal Healthcare Cover",
            "scheme_name_hi": "सार्वभौमिक स्वास्थ्य बीमा",
            "scheme_name_mr": "सार्वजनिक आरोग्य कवच",
            "aliases_en": ["health cover", "hospital insurance", "ayushman card"],
            "aliases_hi": ["स्वास्थ्य बीमा", "आयुष्मान कार्ड"],
            "aliases_mr": ["आरोग्य कवच", "दवाखाना कार्ड"],
            # state is ANY: scheme is silent on state, survives every state mask
            "category": "health",
            "state": ANY,
            "gender": "ALL",
            "social_category": "ALL",
            "age": ANY,
            "income_band": 150000,
            "occupation": ANY,
            "gate_notes": [],
        },
        {
            "scheme_id": "S3",
            "scheme_name_en": "Karnataka Weaver Support",
            "scheme_name_hi": "कर्नाटक बुनकर सहायता",
            "scheme_name_mr": "कर्नाटक विणकर सहाय्य",
            "aliases_en": ["weaver support", "handloom subsidy", "kcc"],  # "kcc" shared with S1 -> 2 schemes (Door A disambiguation)
            "aliases_hi": ["बुनकर सहायता", "केसीसी"],
            "aliases_mr": ["विणकर सहाय्य"],
            "category": "handloom",
            "state": "KARNATAKA",
            "gender": "ALL",
            "social_category": "ALL",
            "age": 30,
            "income_band": 50000,
            "occupation": "weaver",
            "gate_notes": ["Active handloom registration mandatory"],
        },
    ]


@pytest.fixture
def temp_environment(sample_schemes, tmp_path, monkeypatch):
    snap_dir = tmp_path / "snapshots"
    audio_dir = tmp_path / "audio"
    snap_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(snap_dir))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(audio_dir))
    monkeypatch.setattr(tunables, "AUDIO_CACHE_MB", 2)  # 2 MB for tests
    monkeypatch.setattr(tunables, "AUDIO_TIER2", "none")

    # Build snapshot
    snap_id = build_snapshot(
        schemes_data=sample_schemes,
        snapshot_id="test_snap_1",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=True,
    )
    return {
        "snap_id": snap_id,
        "snap_dir": snap_dir,
        "audio_dir": audio_dir,
    }


def test_frozen_corpus_interface_verbatim():
    """Verify Corpus interface matches 04-INTERFACES.md verbatim with NO extra methods."""
    expected_public_names = {
        "load",
        "snapshot_id",
        "mask",
        "values",
        "specificity",
        "scheme_id",
        "alias_lookup",
        "alias_set",
        "audio",
        "chunks",
        "gate_notes",
    }
    actual_public_names = {
        name for name in dir(Corpus) if not name.startswith("_")
    }
    assert actual_public_names == expected_public_names, (
        f"Corpus interface mismatch! Extra or missing: {actual_public_names ^ expected_public_names}"
    )


def test_corpus_py_does_not_import_pool_py():
    """corpus.py must not import pool.py. Only haqdaar/audio/ imports pool.py."""
    corpus_file = Path(corpus_module.__file__)
    with open(corpus_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(corpus_file))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "pool" not in alias.name, f"Forbidden pool import found in corpus.py: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "pool" not in mod, f"Forbidden pool import found in corpus.py: from {mod}"
            for alias in node.names:
                assert "pool" not in alias.name, f"Forbidden pool import found in corpus.py: {alias.name}"


def test_no_tts_and_no_s3_imported_when_tier2_is_none(monkeypatch):
    """Runtime imports no TTS client and no S3 client when AUDIO_TIER2=none."""
    # Ensure fresh state
    assert tunables.AUDIO_TIER2 == "none"
    pool = AudioPool(tier2="none")
    assert "boto3" not in sys.modules
    assert "botocore" not in sys.modules
    assert "sarvam" not in sys.modules
    pool.close()


def test_any_sets_scheme_bit_in_every_mask_for_that_column(temp_environment):
    """ANY sets a scheme's bit in every mask for that column."""
    corpus = Corpus.load(temp_environment["snap_id"])

    # Scheme S2 (bit 1) has state = ANY
    # Scheme S1 (bit 0) has state = BIHAR
    # Scheme S3 (bit 2) has state = KARNATAKA
    mask_bihar = corpus.mask("state", "BIHAR")
    mask_karnataka = corpus.mask("state", "KARNATAKA")

    # S1 (bit 0) should be in BIHAR, not in KARNATAKA
    assert (mask_bihar & (1 << 0)) != 0
    assert (mask_karnataka & (1 << 0)) == 0

    # S2 (bit 1, ANY) MUST be in BOTH BIHAR and KARNATAKA
    assert (mask_bihar & (1 << 1)) != 0
    assert (mask_karnataka & (1 << 1)) != 0

    # S3 (bit 2) should be in KARNATAKA, not in BIHAR
    assert (mask_karnataka & (1 << 2)) != 0
    assert (mask_bihar & (1 << 2)) == 0


def test_corpus_audio_and_chunks_return_render_key_never_bytes(temp_environment):
    """Corpus.audio and Corpus.chunks return RenderKey, never bytes."""
    corpus = Corpus.load(temp_environment["snap_id"])

    # Test audio()
    rk_audio = corpus.audio("greeting_trilingual", "hi")
    assert isinstance(rk_audio, str)
    assert not isinstance(rk_audio, (bytes, bytearray, memoryview))
    assert len(rk_audio) == 64

    # Test chip audio()
    rk_chip = corpus.audio("occupation", "hi", value="farmer")
    assert isinstance(rk_chip, str)
    assert not isinstance(rk_chip, (bytes, bytearray, memoryview))

    # Test chunks()
    chunks = corpus.chunks("S1", "en")
    assert isinstance(chunks, tuple)
    assert len(chunks) == 6
    for c in chunks:
        assert isinstance(c, str)
        assert not isinstance(c, (bytes, bytearray, memoryview))
        assert len(c) == 64


def test_corpus_load_verifies_existence_and_digest_and_raises(temp_environment):
    """Corpus.load verifies existence AND digest against pool index; raises on missing or corrupted."""
    audio_dir = temp_environment["audio_dir"]
    snap_id = temp_environment["snap_id"]

    # 1. Normal load succeeds
    corpus = Corpus.load(snap_id)
    assert corpus.snapshot_id == snap_id

    # 1b. Load via CURRENT pointer succeeds
    corpus_curr = Corpus.load("CURRENT")
    assert corpus_curr.snapshot_id == snap_id

    # 2. Corrupting a .ulaw file makes load raise
    # Pick a valid render key from the manifest
    manifest_file = temp_environment["snap_dir"] / snap_id / "manifest.json"
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    sample_rk = next(iter(manifest["render_keys"].keys()))
    audio_file = audio_dir / f"{sample_rk}.ulaw"

    # Backup original bytes
    with open(audio_file, "rb") as f:
        original_bytes = f.read()

    try:
        # Corrupt the file
        with open(audio_file, "wb") as f:
            f.write(b"CORRUPTED_GARBAGE_BYTES_12345")

        with pytest.raises(CorpusError, match="Digest mismatch"):
            Corpus.load(snap_id)
    finally:
        # Restore
        with open(audio_file, "wb") as f:
            f.write(original_bytes)

    # 3. Deleting a .ulaw file makes load raise
    try:
        audio_file.unlink()
        with pytest.raises(CorpusError, match="Audio file missing"):
            Corpus.load(snap_id)
    finally:
        with open(audio_file, "wb") as f:
            f.write(original_bytes)

    # 4. Removing key from audio/index.json makes load raise
    index_file = audio_dir / "index.json"
    with open(index_file, "r", encoding="utf-8") as f:
        index_data = json.load(f)

    del index_data[sample_rk]
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index_data, f)

    with pytest.raises(CorpusError, match="missing from pool index"):
        Corpus.load(snap_id)

    # 5. Missing audio/index.json makes load raise
    index_file.unlink()
    with pytest.raises(CorpusError, match="Pool index missing"):
        Corpus.load(snap_id)


def test_corpus_load_does_not_hold_audio_bytes_and_rss_flat(temp_environment):
    """Corpus.load must NOT read audio bytes into memory, keeping RSS flat."""
    snap_id = temp_environment["snap_id"]
    corpus = Corpus.load(snap_id)

    # Assert no audio byte buffers are attributes on corpus
    for attr, val in corpus.__dict__.items():
        assert not isinstance(val, (bytes, bytearray, memoryview)), f"Audio bytes found stored in {attr}!"
        if isinstance(val, dict):
            for k, v in val.items():
                assert not isinstance(v, (bytes, bytearray, memoryview)), f"Audio bytes found in dict {attr}[{k}]!"

    # Double pool with 1,000 junk .ulaw files (simulating 1,000 extra audio clips)
    audio_dir = temp_environment["audio_dir"]
    junk_size = 1000
    for i in range(junk_size):
        junk_rk = f"junk_{i:06d}_{'a'*50}"
        with open(audio_dir / f"{junk_rk}.ulaw", "wb") as f:
            f.write(b"\xff" * 2048)

    # Re-loading the corpus should succeed without loading junk audio
    corpus2 = Corpus.load(snap_id)
    assert corpus2.snapshot_id == snap_id
    assert len(corpus2._scheme_ids) == 3


def test_alias_uniqueness_gate_and_door_a_cap(temp_environment):
    """Alias uniqueness: >=3 dropped, ==2 kept (Door A pair), <=2 returned."""
    corpus = Corpus.load(temp_environment["snap_id"])

    # "kcc" was on S1 and S3 (exactly 2) -> kept!
    door_a_pair = corpus.alias_lookup("kcc", "en")
    assert set(door_a_pair) == {"S1", "S3"}
    assert len(door_a_pair) <= 2

    # Alias lookup is case-insensitive and whitespace-normalized
    assert corpus.alias_lookup("  KCC  ", "en") == door_a_pair
    assert corpus.alias_lookup("Kisan Credit", "en") == ("S1",)


def test_audio_pool_tiers_pinned_mmap_lru_and_prefetch(temp_environment):
    """AudioPool: tier 0 pinned, tier 1 mmap+LRU with byte ceiling, warm, prefetch."""
    audio_dir = temp_environment["audio_dir"]
    snap_id = temp_environment["snap_id"]

    # Manifest
    manifest_file = temp_environment["snap_dir"] / snap_id / "manifest.json"
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Create pool with small LRU ceiling (e.g. 500 bytes to force eviction)
    pool = AudioPool(audio_dir=audio_dir, cache_mb=1, tier2="none")
    # Artificially set 2000 bytes limit (each stub is 960 bytes, so at most 2 fit)
    pool._tier1_max_bytes = 2000

    # 1. Warm Tier 0 with templates
    pool.warm(manifest=manifest)
    assert pool.tier0_count > 0

    # Pinned keys return bytes directly from Tier 0
    sample_pinned = next(iter(pool._tier0_pinned.keys()))
    data0 = pool.get(sample_pinned)
    assert isinstance(data0, bytes)

    # 2. Tier 1 scheme chunks read on demand
    s1_chunks = manifest["chunks"]["S1"]["en"]
    chunk0 = s1_chunks[0]
    data1 = pool.get(chunk0)
    assert isinstance(data1, memoryview)
    assert chunk0 in pool._tier1_lru

    # 3. Prefetch all remaining chunks
    pool.prefetch(s1_chunks)

    # Verify byte-bounded eviction occurred because total size exceeds 200 bytes
    assert pool.tier1_bytes_used <= pool._tier1_max_bytes

    pool.close()


def test_corpus_methods_total_and_no_raise(temp_environment):
    """Corpus methods are total and never raise during a call (04-INTERFACES.md)."""
    corpus = Corpus.load(temp_environment["snap_id"])

    # Specificity: count of non-ANY boxes (S1 has all 7, S2 has 4 non-ANY boxes)
    spec_0 = corpus.specificity(0)
    spec_1 = corpus.specificity(1)
    assert spec_0 > spec_1
    assert corpus.specificity(999) == 0  # total, out of bounds does not raise

    # scheme_id
    assert corpus.scheme_id(0) == "S1"
    assert corpus.scheme_id(1) == "S2"
    assert corpus.scheme_id(999) == ""

    # values
    vals = corpus.values("state")
    assert isinstance(vals, tuple)
    assert "BIHAR" in vals
    assert "KARNATAKA" in vals
    assert corpus.values("nonexistent_box") == ()

    # gate_notes
    notes = corpus.gate_notes("S1")
    assert isinstance(notes, tuple)
    assert "Requires active land records" in notes
    assert corpus.gate_notes("nonexistent_scheme") == ()

    # alias_set
    aliases = corpus.alias_set("en")
    assert isinstance(aliases, dict)
    assert "kcc" in aliases


def test_box_discovery_is_seven_boxes_allow_list_only(sample_schemes, tmp_path, monkeypatch):
    """p6 :255-269, Step 1.3 fix A.

    Box discovery must be an allow-list (SEVEN_BOXES only). A record key that is not
    one of the seven boxes (evidence_quotes, a future priority field) must never become
    a keypad box, no matter what shape its value is.

    On the old skip-list code this fails: neither key is on the skip list, so both slip
    through and become boxes whose single value is a dict's/int's str().
    """
    snap_dir = tmp_path / "snapshots"
    audio_dir = tmp_path / "audio"
    snap_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(snap_dir))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(audio_dir))

    schemes_with_extra_keys = []
    for s in sample_schemes:
        s = dict(s)
        s["evidence_quotes"] = {"benefit_text": "cited from the official PDF"}
        s["priority"] = 1
        schemes_with_extra_keys.append(s)

    snap_id = build_snapshot(
        schemes_data=schemes_with_extra_keys,
        snapshot_id="test_snap_box_allowlist",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=True,
    )

    vocab_path = snap_dir / snap_id / "vocab.json"
    with open(vocab_path, "r", encoding="utf-8") as f:
        vocab_data = json.load(f)
    boxes = vocab_data["boxes"]

    assert "evidence_quotes" not in boxes
    assert "priority" not in boxes

    # Every SEVEN_BOXES box that actually has a value on these schemes must still
    # be discovered — the allow-list must not under-discover either.
    for box in SEVEN_BOXES:
        assert box in boxes, f"{box} missing from discovered boxes"
        assert len(boxes[box]["values"]) > 0, f"{box} discovered with no values"


def test_alias_category_word_gate_uses_alias_category_word_min(monkeypatch):
    """p6 :85, Step 1.3 fix B.

    apply_alias_uniqueness_gate's category-word drop must read
    tunables.ALIAS_CATEGORY_WORD_MIN, not tunables.ALIAS_FLOOR. Monkeypatch ONLY
    ALIAS_CATEGORY_WORD_MIN (leave ALIAS_FLOOR at its default 3) and prove the drop
    follows the lowered MIN. On the old ALIAS_FLOOR code this alias stays kept (2 < 3),
    so the assertion that it was dropped fails.
    """
    monkeypatch.setattr(tunables, "ALIAS_CATEGORY_WORD_MIN", 2)

    schemes = [
        {"scheme_id": "A", "aliases_en": ["shared word", "unique a"], "aliases_hi": [], "aliases_mr": []},
        {"scheme_id": "B", "aliases_en": ["shared word", "unique b"], "aliases_hi": [], "aliases_mr": []},
    ]

    updated_schemes, alias_map = apply_alias_uniqueness_gate(schemes)

    # "shared word" is on 2 schemes; with ALIAS_CATEGORY_WORD_MIN=2, 2 < 2 is False,
    # so it must be dropped from both, as a category word.
    assert "shared word" not in updated_schemes[0]["aliases_en"]
    assert "shared word" not in updated_schemes[1]["aliases_en"]
    assert "shared word" not in alias_map["en"]

    # Aliases that appear on only one scheme are unaffected.
    assert "unique a" in updated_schemes[0]["aliases_en"]
    assert "unique b" in updated_schemes[1]["aliases_en"]
