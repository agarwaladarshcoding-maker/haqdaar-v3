# PROMPT — Antigravity, step 3.7 audit tooling (A1)

You are writing code for HAQDAAR v2, Phase 3 (30 schemes). The pipeline steps
3.4–3.5 are done and merged. Your job is the LAST codeable step of this phase:
the tooling the owner needs to audit 20 cards (step 3.7). The audit itself
(reading, listening, verdicts) is the owner's job, not yours.

## 0. Setup

- Work in `~/code/haqdaar-v2` (never the `~/Documents` copy, it hangs).
- Python is ALWAYS `.venv/bin/python` (3.11). System `python3` is 3.14 and broken here.
- Branch: `git switch -c step-3.7-audit` from `main` (already pushed, in sync).
- Read first: `HANDOFF.md`, `AGENTS.md`, `PLAN-V2.md` §2 (decisions D1–D13, binding).
- Keys in `.env` are never committed, never printed.

## 1. Build `tools/cards_sheet.py` (modeled on `tools/lines_sheet.py`)

Read `tools/lines_sheet.py` (103 lines) and copy its shape:
`build_sheet() -> str`, `main()` writes the file, prints `wrote ...` + count,
Markdown readable on a phone.

- Inputs: `data_cache/derived/schemes.jsonl` (28 records), `data_cache/reports/gates.json`.
- Sample (spec: "20 random", defaults fixed in `.agent/OPEN-QUESTIONS.md` OQ4):
  all 7 gate-failing schemes
  (`ignwps, mgnrega, nfbs, nps-tsep, pmjjby, pmmvy, rkvyshfshc`)
  + 13 seeded-random from the 21 passing. Fixed seed as a module constant.
- Write `data_cache/reports/audit_sample_3_7.json`: `{seed, sample_ids[20], failing_ids[7]}`.
- Write `data_cache/reports/cards_sheet.md`: one `### <scheme_id>` section per
  sampled card with `source_url`, `gate_notes` (failing cards only), then the
  card text in all 3 languages. Card fields per language live in
  `chunks.<lang>`: `name, summary, benefit_text, who_can_apply, documents,
  how_to_apply`, plus top-level `scheme_name_en/_hi/_mr`.
- Makefile target: `cards-sheet: $(PYTHON) -m tools.cards_sheet`.

## 2. Scaffold `data_cache/reports/audit_3_7.md` (template only)

Same run creates the verdict file ONLY if it does not exist (never overwrite):
20 sections, one per sampled id, each with `source_url`, per-language
read/listen checkboxes, and a `verdict:` line. Pass criteria (OQ3): 0 factual
errors across the 20; any error gets fixed at the pipeline stage that produced
it. You only scaffold — the owner fills verdicts.

## 3. Cards mode for `tools/listen.py`

- Add a `cards` source: `python -m tools.listen cards <L> <N>`,
  `L` in `{hi, mr}`, playing card-chunk clips for the 12 audio-ready schemes
  (ids from `snapshots/<id>/schemes.jsonl` where `<id>` is the content of
  `snapshots/CURRENT`; today: `ab-pmjay, pm-kisan, pmay-g, pmfby, apy,
  day-nrlm, kcc, pm-svanidhi, pmmy, naps, pmegp, smam`).
- Reuse the existing play path (μ-law→wav temp file, `afplay`); missing clips
  print `(missing: not rendered yet)` and skip. The 7 gate-failing schemes have
  no audio — they never appear here, that is expected.
- Makefile target: `listen-cards: $(PYTHON) -m tools.listen cards $(L) $(N)`.

## 4. Rules

- Smallest correct change. No refactors, no renames, no "while I'm here".
- Do NOT touch `haqdaar/engine/`, `haqdaar/audio/`, `haqdaar/contracts/`,
  `snapshots/`, or any gate/threshold.
- New tools must not call any paid API (no Muse/Sarvam in this step, no ledger
  entries). Tests must never reach the network or play audio (no `afplay` in tests).
- Tests: add `tests/test_cards_sheet.py` — same seed gives the same 20 ids;
  the sheet contains all 20 sampled ids; audit template is not overwritten on
  re-run. 2–4 tests, no more than needed.

## 5. Verify (all must pass)

```
.venv/bin/python -m pytest -q          # must stay green (311 passed on main)
make stress                            # 0 crashes, 0 truth failures
make cards-sheet                       # writes cards_sheet.md + audit_sample_3_7.json
make listen-cards L=hi N=2             # smoke only; owner does the real listening
```

## 6. Done-when

- New branch holds only: `tools/cards_sheet.py`, `tools/listen.py` cards mode,
  `tests/test_cards_sheet.py`, `Makefile` targets, generated reports.
- pytest green, stress 0/0, both `make` targets run.
- Short entry appended to `PROJECT-UPDATE.md` (same style as previous entries).
- Reply with: branch name, `git log main..HEAD`, pytest + stress output.

## NOT yours (owner keeps these)

Reading the 20 cards against source pages, listening (10 hi + 10 mr),
verdicts, voice choice for the 18 new schemes, menu-length decision, 3 real
calls, merge + tag `v1-keypad`.
