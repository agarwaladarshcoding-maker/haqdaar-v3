"""Plan 2.3 — the call runs on a snapshot built from the real 11 schemes.

Built in a temp dir with silent stubs (the real clips live in audio/, which is not in git), so
this checks the wiring, not the voice. A deleted clip must stop the load, not the call.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from haqdaar import sim
from haqdaar.contracts import tunables
from haqdaar.data.corpus import Corpus, CorpusError
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.data.pipeline.texts import _load_schemes

DERIVED = Path(__file__).resolve().parent.parent / "data_cache" / "derived"


@pytest.fixture
def real_snap(tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(tmp_path / "snapshots"))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(tmp_path / "audio"))
    build_snapshot(
        _load_schemes(DERIVED),
        snapshot_id="real",
        snapshots_dir=tmp_path / "snapshots",
        audio_dir=tmp_path / "audio",
        render_stubs=True,
    )
    return tmp_path


@pytest.mark.parametrize("key,lang", [("1", "hi"), ("2", "mr"), ("3", "en")])
def test_a_full_call_in_each_language(real_snap, capsys, key, lang):
    keys = [key, "1", "1"] + ["9"] * 8 + ["2", "2", "h"]
    log_path = sim.run_sim(
        canned_inputs=keys, call_id=f"real_{lang}", logs_dir=str(real_snap / "logs"),
        snapshot="snapshots/CURRENT",
    )
    out = capsys.readouterr().out
    assert "[AUDIO SAY] closing_farewell" in out
    rows = [json.loads(line) for line in log_path.read_text("utf-8").splitlines()]
    assert rows[0]["snapshot_id"] == "real"
    assert {"lang": lang, "lang_source": "keypad", "turn_n": 0} in rows
    assert any("slug" in row for row in rows)  # at least one real scheme was read out


def test_a_deleted_clip_stops_the_load(real_snap):
    Corpus.load("CURRENT")  # loads while every clip is there
    manifest = json.loads((real_snap / "snapshots" / "real" / "manifest.json").read_text("utf-8"))
    victim = next(iter(manifest["render_keys"]))
    (real_snap / "audio" / f"{victim}.ulaw").unlink()
    with pytest.raises(CorpusError):
        Corpus.load("CURRENT")


def test_only_with_audio_skips_clipless_schemes(tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(tmp_path / "snapshots"))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(tmp_path / "audio"))

    all_schemes = _load_schemes(DERIVED)
    assert len(all_schemes) >= 2
    s1 = dict(all_schemes[0])
    s2 = dict(all_schemes[1])

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Render audio stubs for s1 (and templates)
    build_snapshot(
        [s1],
        snapshot_id="temp_stub",
        snapshots_dir=tmp_path / "snapshots",
        audio_dir=audio_dir,
        render_stubs=True,
    )

    # s2 has no clips in audio_dir. Monkeypatch _load_schemes to return [s1, s2]
    monkeypatch.setattr("haqdaar.data.pipeline.texts._load_schemes", lambda _: [s1, s2])

    from haqdaar.data.pipeline.p6_snapshot import main
    code = main(["--only-with-audio"])
    assert code == 0

    # Corpus.load on CURRENT must pass and hold only s1
    corpus = Corpus.load("CURRENT")
    assert len(corpus._scheme_ids) == 1
    assert corpus.scheme_id(0) == s1["scheme_id"]

