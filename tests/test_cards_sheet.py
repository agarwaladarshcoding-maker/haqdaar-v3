"""tests/test_cards_sheet.py

Tests for tools/cards_sheet.py:
1. Seeded sample gives identical 20 ids (7 failing + 13 passing).
2. Rendered cards sheet contains all 20 sampled ids and their 3-language sections.
3. Scaffolded audit_3_7.md is preserved on re-run and never overwritten.
"""
from __future__ import annotations

from pathlib import Path

from tools.cards_sheet import (
    DERIVED_SCHEMES_PATH,
    GATES_REPORT_PATH,
    SEED,
    build_sheet,
    load_gates,
    load_schemes,
    run_cards_sheet,
    select_audit_sample,
)


def test_seeded_sample_reproducibility():
    schemes = load_schemes(DERIVED_SCHEMES_PATH)
    gates = load_gates(GATES_REPORT_PATH)

    sample1 = select_audit_sample(schemes, gates, seed=SEED, sample_size=20)
    sample2 = select_audit_sample(schemes, gates, seed=SEED, sample_size=20)

    assert sample1["sample_ids"] == sample2["sample_ids"]
    assert sample1["failing_ids"] == sample2["failing_ids"]
    assert len(sample1["sample_ids"]) == 20
    assert len(sample1["failing_ids"]) == len(gates.get("failures", []))

    # All failing ids are in sample_ids
    for fid in sample1["failing_ids"]:
        assert fid in sample1["sample_ids"]

    # Different seed yields different passing sample
    sample_diff = select_audit_sample(schemes, gates, seed=999, sample_size=20)
    assert sample_diff["failing_ids"] == sample1["failing_ids"]
    assert sample_diff["sample_ids"] != sample1["sample_ids"]


def test_cards_sheet_contains_all_sampled_ids():
    schemes = load_schemes(DERIVED_SCHEMES_PATH)
    gates = load_gates(GATES_REPORT_PATH)
    sample_info = select_audit_sample(schemes, gates, seed=SEED, sample_size=20)

    sheet = build_sheet(schemes, gates, sample_info, seed=SEED)

    for sid in sample_info["sample_ids"]:
        assert f"### {sid}" in sheet
        assert "Source URL:" in sheet

    # All 3 languages present
    assert "English (en)" in sheet
    assert "Hindi (hi)" in sheet
    assert "Marathi (mr)" in sheet

    # Failing schemes include gate notes / failure details
    for fid in sample_info["failing_ids"]:
        pos = sheet.find(f"### {fid}")
        next_pos = sheet.find("### ", pos + 4)
        section = sheet[pos:next_pos] if next_pos != -1 else sheet[pos:]
        assert "Gate notes:" in section or "Gate failure reasons:" in section


def test_audit_template_not_overwritten_on_rerun(tmp_path: Path):
    schemes_path = DERIVED_SCHEMES_PATH
    gates_path = GATES_REPORT_PATH
    sample_path = tmp_path / "sample.json"
    sheet_path = tmp_path / "sheet.md"
    audit_path = tmp_path / "audit_3_7.md"

    # First run creates the audit scaffold
    rc1 = run_cards_sheet(
        schemes_path=schemes_path,
        gates_path=gates_path,
        sample_path=sample_path,
        sheet_path=sheet_path,
        audit_path=audit_path,
        seed=SEED,
    )
    assert rc1 == 0
    assert audit_path.exists()
    initial_text = audit_path.read_text(encoding="utf-8")
    assert "verdict: PENDING" in initial_text

    # Owner audits and records verdicts
    customized_text = initial_text.replace("verdict: PENDING", "verdict: PASS", 1)
    customized_text += "\nowner_note: verified against myscheme\n"
    audit_path.write_text(customized_text, encoding="utf-8")

    # Second run must preserve the owner's edits
    rc2 = run_cards_sheet(
        schemes_path=schemes_path,
        gates_path=gates_path,
        sample_path=sample_path,
        sheet_path=sheet_path,
        audit_path=audit_path,
        seed=SEED,
    )
    assert rc2 == 0
    preserved_text = audit_path.read_text(encoding="utf-8")
    assert "verdict: PASS" in preserved_text
    assert "owner_note: verified against myscheme" in preserved_text
