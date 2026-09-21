"""tests/test_texts.py

Step 1.14 (plan 1.12) — one text list for the render and the snapshot.

The load-bearing test is `test_p6_line_keys_match_all_texts`: if the snapshot and the text
list ever disagree about what audio must exist, the call plays the wrong file or none at all.
"""
import json
from pathlib import Path

import pytest

from haqdaar.contracts.types import FIXED_LINE_IDS, SCHEME_CHUNKS, compute_render_key
from haqdaar.data.pipeline import texts as texts_mod
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.data.pipeline.texts import (
    Text,
    all_texts,
    band_texts,
    chip_texts,
    fixed_line_texts,
    missing,
    scheme_chunk_texts,
)

SCHEME = {
    "scheme_id": "demo-scheme",
    "chunks": {
        lang: {chunk: f"{chunk} text in {lang}" for chunk in SCHEME_CHUNKS}
        for lang in ("en", "hi", "mr")
    },
}


def test_a_texts_key_is_the_key_of_its_own_words():
    """The whole point: the key names the text, so the pool cannot hold different words."""
    for item in all_texts([SCHEME]):
        assert item.key == compute_render_key(item.text, item.lang)


def test_every_scheme_chunk_in_every_language_is_listed():
    items = list(scheme_chunk_texts([SCHEME]))
    assert len(items) == len(SCHEME_CHUNKS) * 3
    assert {i.ref for i in items} == {f"demo-scheme/{c}" for c in SCHEME_CHUNKS}


def test_an_empty_chunk_is_not_given_a_placeholder():
    """p6 used to invent f"{sid} {chunk} in {lang}" and stub it. Silence beats a fake key."""
    scheme = {
        "scheme_id": "half-done",
        "chunks": {"en": {c: f"{c} text" for c in SCHEME_CHUNKS}, "hi": {}, "mr": {}},
    }
    items = list(scheme_chunk_texts([scheme]))
    assert {i.lang for i in items} == {"en"}
    assert not any("half-done benefit_text in hi" in i.text for i in items)


def test_missing_names_every_gap():
    scheme = {
        "scheme_id": "half-done",
        "chunks": {"en": {c: f"{c} text" for c in SCHEME_CHUNKS}, "hi": {}, "mr": {}},
    }
    gaps = missing([scheme])
    assert any("half-done has no hi benefit_text" in g for g in gaps)
    assert not any("half-done has no en" in g for g in gaps)


def test_the_trilingual_greeting_is_one_recording():
    items = [i for i in fixed_line_texts() if i.ref == "greeting_trilingual"]
    assert len(items) == 1
    assert items[0].lang == "all"


def test_identical_words_are_one_recording():
    """"Let us use the keypad." is written for several boxes and rendered once."""
    keys = {(i.key, i.lang) for i in all_texts([SCHEME])}
    assert len(keys) == len(all_texts([SCHEME]))


def test_chips_come_from_vocab_not_from_a_second_list():
    refs = {i.ref for i in chip_texts()}
    assert "chip_gender_female" in refs
    assert "chip_social_category_SC" in refs


def test_bands_are_built_from_what_the_snapshot_made():
    bands = {"age": [{"code": "age_0", "lo": 18, "hi": 40}, {"code": "age_1", "lo": 41, "hi": None}]}
    items = list(band_texts(bands))
    en = {i.text for i in items if i.lang == "en"}
    assert "18 to 40 years" in en
    assert "41 years and above" in en


def test_p6_line_keys_match_all_texts(tmp_path: Path):
    """The snapshot's fixed-line keys must be exactly the text list's keys.

    This is the drift this whole module exists to prevent.
    """
    snap_dir = tmp_path / "snapshots"
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    build_snapshot(
        [SCHEME],
        snapshot_id="test-snap",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=False,
    )
    templates = json.loads(
        (snap_dir / "test-snap" / "templates.json").read_text(encoding="utf-8")
    )

    expected: dict[str, dict[str, str]] = {}
    for item in fixed_line_texts():
        expected.setdefault(item.ref, {})[item.lang] = item.key

    for line_id, by_lang in expected.items():
        for lang, key in by_lang.items():
            assert templates[line_id][lang] == key, f"{line_id}/{lang} drifted"


def test_p6_does_not_write_stubs_by_default(tmp_path: Path):
    """render_stubs is False now: a silent file must not stand in for missing audio."""
    snap_dir = tmp_path / "snapshots"
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    build_snapshot(
        [SCHEME],
        snapshot_id="test-snap",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
    )
    assert list(audio_dir.glob("*.ulaw")) == []
