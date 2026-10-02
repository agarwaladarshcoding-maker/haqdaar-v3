"""Tests for Part F5: pipeline reports roster accounting, print_cost with Muse, and repo hygiene."""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from haqdaar.data.pipeline.p1_scrape import compute_roster_accounting, load_scheme_slugs
from haqdaar.data.pipeline.run_all import _count_texts, _run_snapshot, print_cost


def test_tracked_gates_report_roster_accounting_reconciles():
    """gates.json (tracked) must report roster accounting where roster_size - quarantined_count == kept_count."""
    gates_path = Path("data_cache/reports/gates.json")
    assert gates_path.exists(), "data_cache/reports/gates.json must exist"

    data = json.loads(gates_path.read_text(encoding="utf-8"))
    assert "roster_size" in data
    assert "quarantined_count" in data
    assert "quarantined_slugs" in data
    assert "kept_count" in data

    assert data["roster_size"] == 30
    assert data["quarantined_count"] == 3
    assert data["kept_count"] == 27
    assert data["roster_size"] - data["quarantined_count"] == data["kept_count"]
    assert data["quarantined_slugs"] == ["ab-pmjay", "pm-sym", "pmsby"]
    # Existing keys must remain intact
    assert data["schemes"] == 27
    assert data["ok"] == 27
    assert "per_language" in data
    assert "failures" in data


def test_pipeline_reports_roster_accounting_all_reconcile():
    """All pipeline reports (cards.json, translate.json, derive.json) reconcile with 30 - quarantined == kept."""
    for report_name in ("cards.json", "translate.json", "derive.json"):
        report_path = Path("data_cache/reports") / report_name
        if not report_path.exists():
            continue
        data = json.loads(report_path.read_text(encoding="utf-8"))
        assert "roster_size" in data, f"{report_name} missing roster_size"
        assert "quarantined_count" in data, f"{report_name} missing quarantined_count"
        assert "quarantined_slugs" in data, f"{report_name} missing quarantined_slugs"
        assert "kept_count" in data, f"{report_name} missing kept_count"

        assert data["roster_size"] - data["quarantined_count"] == data["kept_count"]
        assert data["roster_size"] == 30
        assert data["quarantined_count"] == 3
        assert data["kept_count"] == 27
        assert data["quarantined_slugs"] == ["ab-pmjay", "pm-sym", "pmsby"]


def test_compute_roster_accounting_with_custom_yaml(tmp_path: Path):
    """compute_roster_accounting correctly computes roster and quarantined slugs against a custom yaml roster."""
    custom_yaml = tmp_path / "schemes.yaml"
    custom_yaml.write_text(
        "schemes:\n"
        "  - slug: scheme-a\n"
        "  - slug: scheme-b\n"
        "  - slug: scheme-c\n"
        "  - slug: scheme-d\n"
    )

    # 2 kept, 2 quarantined
    acc = compute_roster_accounting(["scheme-a", "scheme-c"], yaml_path=custom_yaml)
    assert acc["roster_size"] == 4
    assert acc["quarantined_count"] == 2
    assert acc["quarantined_slugs"] == ["scheme-b", "scheme-d"]
    assert acc["kept_count"] == 2
    assert acc["roster_size"] - acc["quarantined_count"] == acc["kept_count"]

    # All kept
    acc_all = compute_roster_accounting(["scheme-a", "scheme-b", "scheme-c", "scheme-d"], yaml_path=custom_yaml)
    assert acc_all["roster_size"] == 4
    assert acc_all["quarantined_count"] == 0
    assert acc_all["quarantined_slugs"] == []
    assert acc_all["kept_count"] == 4

    # None kept
    acc_none = compute_roster_accounting([], yaml_path=custom_yaml)
    assert acc_none["roster_size"] == 4
    assert acc_none["quarantined_count"] == 4
    assert acc_none["quarantined_slugs"] == ["scheme-a", "scheme-b", "scheme-c", "scheme-d"]
    assert acc_none["kept_count"] == 0


def test_print_cost_with_fake_ledger_rows_including_muse(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """print_cost prints Groq, Sarvam, TTS, and Muse ledger metrics accurately."""
    groq_ledger = tmp_path / "groq.jsonl"
    sarvam_ledger = tmp_path / "sarvam.jsonl"
    tts_ledger = tmp_path / "tts.jsonl"
    muse_ledger = tmp_path / "muse.jsonl"

    groq_ledger.write_text(
        json.dumps({"task": "cards", "prompt_tokens": 100, "completion_tokens": 50}) + "\n"
        + json.dumps({"task": "facets", "prompt_tokens": 200, "completion_tokens": 75}) + "\n"
    )
    sarvam_ledger.write_text(
        json.dumps({"lang": "hi", "chars": 1500}) + "\n"
        + json.dumps({"lang": "mr", "chars": 1200}) + "\n"
    )
    tts_ledger.write_text(
        json.dumps({"lang": "en", "chars": 800}) + "\n"
    )
    muse_ledger.write_text(
        json.dumps({"task": "cards", "prompt_tokens": 500, "completion_tokens": 1200, "inr": 2.50}) + "\n"
        + json.dumps({"task": "summary", "prompt_tokens": 300, "completion_tokens": 800, "inr": 1.75}) + "\n"
    )

    ret = print_cost(
        groq_ledger=groq_ledger,
        sarvam_ledger=sarvam_ledger,
        sarvam_tts_ledger=tts_ledger,
        muse_ledger=muse_ledger,
    )
    assert ret == 0
    captured = capsys.readouterr().out

    # Groq section
    assert "Groq (cards, facets, aliases, summary)" in captured
    assert "requests: 2" in captured
    assert "tokens total: 425" in captured

    # Sarvam section
    assert "Sarvam Translate" in captured
    assert "chars: 2700" in captured
    assert "hi: 1500 chars" in captured
    assert "mr: 1200 chars" in captured

    # TTS section
    assert "Sarvam TTS (make render)" in captured
    assert "chars: 800" in captured

    # Muse section
    assert "Muse (contributor tasks)" in captured
    assert "requests: 2" in captured
    assert "prompt tokens: 800" in captured
    assert "completion tokens: 2000" in captured
    assert "spent: ₹4.25 / ₹60 cap" in captured
    assert "cards: 1 requests" in captured
    assert "summary: 1 requests" in captured


def test_count_texts_and_run_snapshot_alias(capsys: pytest.CaptureFixture[str]):
    """_count_texts accurately counts speakable texts and _run_snapshot acts as backward compatibility alias."""
    ret1 = _count_texts()
    assert ret1 == 0
    out1 = capsys.readouterr().out
    assert "texts the call can say:" in out1
    assert "texts still missing:" in out1

    # Verify alias
    assert _run_snapshot is _count_texts
