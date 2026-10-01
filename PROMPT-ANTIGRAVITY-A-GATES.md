# STEP A — Phase 3 code finish: gates + scheme fates + snapshot (Antigravity work order)

## 0 · Setup

- Base: `main`, and it MUST already contain the step-4.2 merge. Check with
  `git log --oneline -5` (you should see the 4.2 merge). If it is missing: STOP, reply
  "base missing 4.2 merge", change nothing.
- New branch: `git switch -c step-3x-gates-snapshot` from the base.
- Python: always `.venv/bin/python` (3.11). Keys in `.env`, never committed, never printed.
- Read first: `HANDOFF.md`, `AGENTS.md`, `PLAN-V2.md` §2 (D1–D13, binding) + §3.
- Rules that stay: tests never touch a paid API; Muse spend under the hard ₹60 cap
  (spent ₹12.97 so far, `data_cache/reports/muse_usage.jsonl` — pipeline reruns only pay
  for cache misses); `Corpus.load` refuses a snapshot with a missing clip (this rule stays,
  so build the snapshot ONLY from schemes that have audio); keypad menus ≤9 (0 = don't know).

## 1 · Scope (live state in brackets, verified 1 Oct)

1. **Fix the 7 gate failures** [`data_cache/reports/gates.json`: 21/28 pass, 25%
   quarantined — fails the <15% bar in PLAN-V2 3.4 verify]. Failing schemes: ignwps,
   mgnrega, nfbs, nps-tsep, pmjjby, pmmvy, rkvyshfshc (hi, some also mr: invented
   numbers, >1.6x source length, 0 Devanagari). Re-translate the 7 via the pipeline or
   hand-fix the hi/mr text, whichever costs less Muse spend. Re-run
   `make pipeline-gates` until quarantine is under 15%.
2. **Settle 3 scheme fates.** Document each choice in `.agent/NOTES.md` + `PROJECT-UPDATE.md`:
   - `ab-pmjay`: source page now 404s, but it passes derive+gates from cache and SERVES
     in the CURRENT 12-scheme snapshot. Default: keep serving, flag it stale in NOTES.
     Do not silently drop a live scheme.
   - `pm-sym`: bad `income_band` facet in `derive.json`. Fix from source if the page
     supports it, else quarantine.
   - `pmsby`: page has no documents block. Rescrape once; if still empty, quarantine.
3. **Rebuild the snapshot** from (servable ∩ audio-ready) schemes only. Voice clips for
   the 18 new schemes do NOT exist yet (owner decision pending) and `audio/` (882 clips)
   covers the CURRENT 12 only — so the rebuilt snapshot stays ~12 schemes, and that is
   correct per the Corpus.load rule. `make snapshot`, then `make render` must say
   missing: 0, then `make backup` (PLAN-V2 3.5 verify).
4. **Re-run `make stress`** on the new snapshot: must say crashes 0, truth failures 0.
5. Confirm `OCCUPATION` in `haqdaar/contracts/vocab.py` still has ≤9 values with hi/mr
   LABELS after the fixes (7 values on 1 Oct).

## 2 · Do NOT touch (owner's end-file, not this step)

Voice render for the 18 new schemes, 3.7 audit verdicts, menu-length decision, any merge
or tag, any real phone call. If you hit anything needing the owner: stop that item,
report it, finish the rest.

## 3 · Verify (all green before you reply)

```
cd ~/code/haqdaar-v2
.venv/bin/python -m pytest -q
make stress
make render          # missing: 0
make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h"
```

## 4 · Reply with

Branch name; `git log <base>..HEAD`; pytest + stress outputs; `gates.json` pass count;
new snapshot id + scheme count; Muse spend delta; `PROJECT-UPDATE.md` entry (plain short
words); updated `.agent/TASK.md` + `.agent/NOTES.md`; anything left blocked and why.
