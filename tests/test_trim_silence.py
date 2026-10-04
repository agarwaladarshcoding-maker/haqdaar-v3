"""Step 7.6 — quiet at the start and end of a clip is cut to TRIM_EDGE_MS when the clip loads.

Fixtures are built here; real clips in audio/ are sampled only when that folder is present.
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from haqdaar.audio.pool import AudioPool, _quiet_bytes, trim_edges
from haqdaar.contracts import tunables

GAP = tunables.SAMPLE_RATE * tunables.TRIM_EDGE_MS // 1000
LOUD = b"\x10\x90\x20\xa0"
QUIET = b"\xff"


def _edges(data: bytes) -> tuple[int, int]:
    q = _quiet_bytes()
    lead = len(data) - len(data.lstrip(q))
    return lead, len(data) - len(data.rstrip(q))


def _fixture_clips() -> dict[str, bytes]:
    return {
        "both": QUIET * 3000 + LOUD * 500 + QUIET * 4000,
        "lead_only": QUIET * 2500 + LOUD * 500,
        "tail_only": LOUD * 500 + b"\x7f" * 2500,
        "middle": LOUD * 300 + QUIET * 5000 + LOUD * 300,
        "tight": QUIET * 40 + LOUD * 500 + QUIET * 40,
        "stub": QUIET * 8000,
        "tiny": QUIET * 5 + LOUD,
        "one_byte": b"\xff",
    }


def _pool(tmp_path: Path) -> tuple[AudioPool, dict[str, bytes]]:
    clips = {f"{i:064x}": d for i, d in enumerate(_fixture_clips().values())}
    for key, data in clips.items():
        (tmp_path / f"{key}.ulaw").write_bytes(data)
    return AudioPool(audio_dir=tmp_path, cache_mb=64, tier2="none"), clips


def test_trim_silence_at_load(tmp_path):
    pool, clips = _pool(tmp_path)
    for key, raw in clips.items():
        got = bytes(pool.get(key))
        assert got, key
        lead, tail = _edges(got)
        if got != raw:  # an untouched all-quiet or short clip is allowed to be quiet end to end
            assert lead <= GAP and tail <= GAP, key


def test_edges_cut_to_gap_and_middle_kept():
    data = QUIET * 3000 + LOUD * 500 + QUIET * 4000
    got = trim_edges(data)
    assert got == QUIET * GAP + LOUD * 500 + QUIET * GAP
    mid = LOUD * 300 + QUIET * 5000 + LOUD * 300
    assert trim_edges(QUIET * 3000 + mid + QUIET * 3000) == QUIET * GAP + mid + QUIET * GAP


def test_no_extra_quiet_is_unchanged():
    data = QUIET * 40 + LOUD * 500 + QUIET * GAP
    assert trim_edges(data) == data


def test_all_quiet_and_tiny_clips_survive():
    stub = QUIET * 8000
    assert trim_edges(stub) == stub
    tiny = QUIET * 5 + LOUD
    assert trim_edges(tiny) == tiny
    assert trim_edges(b"") == b""


def test_either_sign_of_zero_counts_as_quiet():
    got = trim_edges(b"\x7f" * 3000 + LOUD * 500 + b"\xfe" * 3000)
    assert got == b"\x7f" * GAP + LOUD * 500 + b"\xfe" * GAP


def test_get_and_pin_both_return_trimmed_bytes(tmp_path):
    pool, clips = _pool(tmp_path)
    keys = list(clips)
    got_get = {k: bytes(pool.get(k)) for k in keys[:4]}
    pool.pin(keys[4:])
    pool.pin(keys[:4])  # moves the first four from tier 1 to tier 0
    for key, raw in clips.items():
        assert bytes(pool.get(key)) == trim_edges(raw)
    for key in keys[:4]:
        assert got_get[key] == trim_edges(clips[key])
    assert len(bytes(pool.get(keys[0]))) < len(clips[keys[0]])
    assert pool.tier0_count == len(keys)


def test_trimmed_bytes_are_what_the_cache_holds(tmp_path):
    pool, clips = _pool(tmp_path)
    key = next(iter(clips))
    first = bytes(pool.get(key))
    assert pool.tier1_bytes_used == len(first) < len(clips[key])
    assert bytes(pool.get(key)) == first


def test_real_clips_sample_when_present():
    audio = Path(__file__).resolve().parent.parent / "audio"
    files = sorted(audio.glob("*.ulaw")) if audio.is_dir() else []
    if not files:
        pytest.skip("audio/ not present")
    random.Random(7).shuffle(files)
    pool = AudioPool(audio_dir=audio, cache_mb=64, tier2="none")
    for f in files[:100]:
        raw = f.read_bytes()
        got = bytes(pool.get(f.stem))
        assert got
        if got != raw:
            lead, tail = _edges(got)
            assert lead <= GAP and tail <= GAP, f.name
            assert got in raw
