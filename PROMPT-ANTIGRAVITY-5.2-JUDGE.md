# STEP 5.2 — tools/judge.py + sim opener UNCLEAR fix (Antigravity work order)

Offline delivery log judge + sim opener UNCLEAR-vs-empty-stamps unification.
Owner work stays STOPPED: no new voice clips, no Groq key, no real calls,
no listening — if any item needs those, report it blocked.

## 0 · Setup

- Base: `main` @ `6cb7648` (5.1 merged, pytest 456). Check with
  `git log --oneline -1`. If the base is wrong: STOP, reply "wrong base".
- New branch: `git switch -c step-5.2-judge` from the base.
- Python: always `.venv/bin/python` (3.11). Keys in `.env`, never committed/printed.
- Read first: `HANDOFF.md`, `AGENTS.md`, `PLAN-V2.md` §2 (D1–D13, binding) + §3
  (Phase 5.2), `source-docs/T04.md`, `source-docs/T16.md`, `source-docs/T18.md`, `.agent/NOTES.md` tail.
- Maintain `.agent/TASK.md` (one `in_progress` at a time) and append findings to
  `.agent/NOTES.md` as you learn them.
- Rules that stay: one caller; nothing blocks Mouth/socket loop; tests never touch a
  paid API (`tests/conftest.py` guards stay); Muse spend under hard ₹60 cap (₹12.97
  spent, expect ₹0.00 delta); **Muse must never hear live callers**; no merge, no tag — the reviewer merges.

## 1 · Build

1. **tools/judge.py logs/ → PASS/FAIL from the delivery log alone** (PLAN-V2 5.2, T04, T16).
   • Input: a logs dir (or single log file). Output: per-call PASS/FAIL + one-line reason; summary counts; exit 1 if any FAIL.
   • Read ONLY log artifacts: the D9 delivery record (slug, ending type, sections played) + turn lines. No audio, no re-running the engine.
   • FAIL iff any of T04's three conditions (source-docs/T04.md branch 2):
     (1) untrue — named scheme not in survivors, nearest read as matches, dead-end without the widening step, benefit/document claim outside the corpus;
     (2) system hung up unprompted (close reason shows system-side close before terminal);
     (3) ended before a terminal state (read-back started / honest dead-end / keypad-only-then-terminal).
   • PASS rules: dead-end through the full ladder with nearest labelled nearest = pass (T04 branch 3); exactly-one-survivor named honestly = pass; call ending in keypad-only at an ordinary terminal = pass (T18).
   • Which ANSWER counts: only confirmed turn_class="ANSWER" lines. PROPOSAL lines (call.py proposal logging) are ignored for scoring. An ANSWER with no preceding PROPOSAL still counts (keypad path has no proposals).
   • Offline, stdlib-only, mirrors tools/door_a_check.py structure. No new deps.

2. **Carried nit (small, adjacent): sim opener UNCLEAR-vs-empty-stamps asymmetry.**
   • SimModelClient returns `{"class": "UNCLEAR", "stamps": []}` for unmatched opener speech (NOTES step D item 5), but downstream the UNCLEAR class and the empty-stamps list take different paths. Unify: both flow through the same specific-re-ask path with identical logging. One behaviour, one test.

## 2 · Tests (mirror `tests/test_door_a_check.py`-style + hand-made logs)

• Hand-made fixture logs: pass-direct-match, pass-dead-end-with-ladder, pass-keypad-only-terminal, fail-untrue-nearest-as-match, fail-dead-end-without-ladder, fail-ended-before-terminal, fail-unprompted-hangup, PROPOSAL-ignored (PROPOSAL-only call for a box scores on its ANSWER, not the proposal).
• Sim test: unmatched opener speech produces identical log + next-turn behaviour whether expressed as UNCLEAR class or empty stamps.

## 3 · Non-goals / Blocked

• New/changed audio lines or clips (owner voice hold, Sarvam cap).
• Groq key / live model runs / real phone calls / listening checks / tags.
• 5.3 crash restart, 5.4 provider adapter, Phase 6 10-call test.
• No changes to engine scoring semantics — the judge reads the log; it does not redefine truth (filter/planner/terminals untouched).

## 4 · Verify (all green)

```
cd ~/code/haqdaar-v2
.venv/bin/python -m pytest -q
.venv/bin/python tools/judge.py <hand-made-pass-log> # expect PASS
.venv/bin/python tools/judge.py <hand-made-fail-log> # expect FAIL + reason, exit 1
make stress && make model-bakeoff && make door-a-check && make render
make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h"
Record Muse spend delta from data_cache/reports/muse_usage.jsonl (expect ₹0.00).
Update PROJECT-UPDATE.md + .agent/NOTES.md. No merge, no tag — reviewer merges.
```

## 5 · Reply with

Branch name; `git log <base>..HEAD`; pytest + judge + stress + bake-off + door-a-check outputs; Muse spend delta (expect ₹0.00); `PROJECT-UPDATE.md` entry (plain short words); updated `.agent/NOTES.md`; anything left blocked and why. No merge, no tag.
