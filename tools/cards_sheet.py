"""tools/cards_sheet.py

Step 3.7 — write sampled scheme cards out as a review sheet for the owner to audit.

    python -m tools.cards_sheet

Outputs:
    data_cache/reports/audit_sample_3_7.json  (seed, 20 sample ids, 7 failing ids)
    data_cache/reports/cards_sheet.md         (Markdown review sheet for phone/laptop)
    data_cache/reports/audit_3_7.md           (verdict template, created only if not exists)
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

SEED = 42

DERIVED_SCHEMES_PATH = Path("data_cache/derived/schemes.jsonl")
GATES_REPORT_PATH = Path("data_cache/reports/gates.json")
SAMPLE_PATH = Path("data_cache/reports/audit_sample_3_7.json")
SHEET_PATH = Path("data_cache/reports/cards_sheet.md")
AUDIT_PATH = Path("data_cache/reports/audit_3_7.md")

LANGS = ("en", "hi", "mr")
LANG_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}
CARD_FIELDS = (
    ("name", "Card name"),
    ("summary", "Summary"),
    ("benefit_text", "Benefit"),
    ("who_can_apply", "Who can apply"),
    ("documents", "Documents"),
    ("how_to_apply", "How to apply"),
)


def load_gates(path: Path = GATES_REPORT_PATH) -> dict:
    if not path.exists():
        return {"schemes": 0, "ok": 0, "failures": []}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_schemes(path: Path = DERIVED_SCHEMES_PATH) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def select_audit_sample(
    schemes: list[dict],
    gates_report: dict,
    seed: int = SEED,
    sample_size: int = 20,
) -> dict:
    """Select stratified sample: all failing schemes + seeded random passing schemes."""
    failures = gates_report.get("failures", [])
    failing_ids = sorted(f["scheme_id"] for f in failures if "scheme_id" in f)
    failing_set = set(failing_ids)

    passing_ids = sorted(
        s["scheme_id"]
        for s in schemes
        if s.get("scheme_id") and s["scheme_id"] not in failing_set
    )

    needed_passing = max(0, sample_size - len(failing_ids))
    rng = random.Random(seed)
    sampled_passing = sorted(rng.sample(passing_ids, min(needed_passing, len(passing_ids))))
    sample_ids = sorted(failing_ids + sampled_passing)

    return {
        "seed": seed,
        "sample_ids": sample_ids,
        "failing_ids": failing_ids,
    }


def _format_failing_notes(scheme: dict, gates_report: dict) -> list[str]:
    """Format gate failure reasons and scheme gate_notes for a failing scheme."""
    sid = scheme.get("scheme_id", "")
    out: list[str] = []

    # Scheme eligibility gate_notes from schemes.jsonl
    scheme_notes = scheme.get("gate_notes", [])
    if scheme_notes:
        out.append(f"- **Gate notes:** {'; '.join(scheme_notes)}")

    # Specific pipeline gate failure reasons from gates.json
    failures = gates_report.get("failures", [])
    for f in failures:
        if f.get("scheme_id") == sid:
            reasons = []
            for lang, fields in f.get("languages", {}).items():
                for field, field_reasons in fields.items():
                    for r in field_reasons:
                        reasons.append(f"[{lang}] {field}: {r}")
            for comp in f.get("complete", []):
                reasons.append(f"incomplete: {comp}")
            if reasons:
                out.append(f"- **Gate failure reasons:** {'; '.join(reasons)}")
            break

    if not out:
        out.append("- **Gate notes:** (failed pipeline gates)")

    return out


def build_sheet(
    schemes: list[dict] | None = None,
    gates_report: dict | None = None,
    sample_info: dict | None = None,
    seed: int = SEED,
) -> str:
    """Build cards_sheet.md content for sampled cards."""
    if schemes is None:
        schemes = load_schemes()
    if gates_report is None:
        gates_report = load_gates()
    if sample_info is None:
        sample_info = select_audit_sample(schemes, gates_report, seed=seed)

    schemes_by_id = {s["scheme_id"]: s for s in schemes if "scheme_id" in s}
    failing_set = set(sample_info.get("failing_ids", []))
    sample_ids = sample_info.get("sample_ids", [])

    out: list[str] = [
        "# Spoken cards — audit review sheet",
        "",
        "Fact-check 20 cards against source pages (step 3.7).",
        "Readable on mobile. Card text in all 3 languages (English, Hindi, Marathi).",
        "",
        f"Sample size: {len(sample_ids)} schemes (7 gate-failing + {len(sample_ids) - len(failing_set)} passing, seed={sample_info.get('seed')}).",
        "",
        "---",
        "",
    ]

    for sid in sample_ids:
        s = schemes_by_id.get(sid)
        if not s:
            out.append(f"### {sid}\n\n_(scheme record not found)_\n")
            continue

        source_url = s.get("source_url", "")
        out.append(f"### {sid}")
        out.append("")
        out.append(f"- **Source URL:** {source_url}")

        if sid in failing_set:
            out.extend(_format_failing_notes(s, gates_report))

        out.append("")

        chunks = s.get("chunks", {})
        for lang in LANGS:
            lang_name = LANG_NAMES[lang]
            scheme_name = s.get(f"scheme_name_{lang}", "")
            out.append(f"#### {lang_name} ({lang})")
            if scheme_name:
                out.append(f"- **Official name:** {scheme_name}")

            lang_chunk = chunks.get(lang, {})
            for field_key, field_label in CARD_FIELDS:
                val = lang_chunk.get(field_key, "")
                mark = "" if val else " _(missing)_"
                out.append(f"- **{field_label}:** {val}{mark}")
            out.append("")

        out.append("---")
        out.append("")

    return "\n".join(out)


def build_audit_template(
    sample_ids: list[str],
    schemes_by_id: dict[str, dict],
    seed: int = SEED,
    failing_ids: list[str] | None = None,
) -> str:
    """Build scaffold template for data_cache/reports/audit_3_7.md."""
    failing_set = set(failing_ids or [])
    out: list[str] = [
        "# 3.7 Card Audit Verdicts (20 Sampled Cards)",
        "",
        "Pass criteria (OQ3): 0 factual errors across the 20 sampled cards.",
        "Any error gets fixed at the pipeline stage that produced it.",
        "",
        f"- Sample seed: {seed}",
        f"- Total sampled: {len(sample_ids)} (all {len(failing_set)} gate-failing + {len(sample_ids) - len(failing_set)} passing)",
        "",
        "Status legend: PENDING, PASS, FAIL",
        "",
        "---",
        "",
    ]

    for sid in sample_ids:
        s = schemes_by_id.get(sid, {})
        source_url = s.get("source_url", "")
        is_failing = sid in failing_set
        gate_status = "gate-failing (unshipped, no audio)" if is_failing else "gate-passing"

        out.append(f"### {sid}")
        out.append(f"- source_url: {source_url}")
        out.append(f"- status: {gate_status}")
        out.append("- [ ] read en")
        out.append("- [ ] read hi")
        out.append("- [ ] read mr")
        if is_failing:
            out.append("- [ ] listen hi (no audio — skipped)")
            out.append("- [ ] listen mr (no audio — skipped)")
        else:
            out.append("- [ ] listen hi")
            out.append("- [ ] listen mr")
        out.append("verdict: PENDING")
        out.append("notes: ")
        out.append("")

    return "\n".join(out)


def run_cards_sheet(
    schemes_path: Path = DERIVED_SCHEMES_PATH,
    gates_path: Path = GATES_REPORT_PATH,
    sample_path: Path = SAMPLE_PATH,
    sheet_path: Path = SHEET_PATH,
    audit_path: Path = AUDIT_PATH,
    seed: int = SEED,
) -> int:
    schemes = load_schemes(schemes_path)
    if not schemes:
        print(f"no schemes found at {schemes_path}; run derive step first")
        return 1

    gates = load_gates(gates_path)
    sample_info = select_audit_sample(schemes, gates, seed=seed)
    schemes_by_id = {s["scheme_id"]: s for s in schemes if "scheme_id" in s}

    # 1. Write sample JSON
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    with sample_path.open("w", encoding="utf-8") as f:
        json.dump(sample_info, f, indent=2)
    print(f"wrote {sample_path}")

    # 2. Write cards sheet
    sheet = build_sheet(schemes, gates, sample_info, seed=seed)
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_path.write_text(sheet, encoding="utf-8")
    print(f"wrote {sheet_path}")
    print(f"cards: {len(sample_info['sample_ids'])}")

    # 3. Scaffold audit verdicts file ONLY if it does not already exist
    if not audit_path.exists():
        audit_content = build_audit_template(
            sample_info["sample_ids"],
            schemes_by_id,
            seed=seed,
            failing_ids=sample_info["failing_ids"],
        )
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(audit_content, encoding="utf-8")
        print(f"scaffolded {audit_path}")
    else:
        print(f"preserved existing {audit_path} (not overwritten)")

    return 0


def main() -> int:
    return run_cards_sheet()


if __name__ == "__main__":
    sys.exit(main())
