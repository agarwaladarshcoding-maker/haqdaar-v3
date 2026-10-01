# STEP E — Audit remainder: engine correctness + hardening + reports (Antigravity work order)

The reviewer already fixed F1 (quarantine bypass + 11-scheme snapshot) and F2 (Door A
wiring + stamps + purity) on branch `audit-fixes`. This prompt covers the REST of
[AUDIT-PHASE1-4.md](/Users/adarshagarwala/code/haqdaar-v2/AUDIT-PHASE1-4.md): F3 engine
correctness, F4 server/audio/model hardening, F5 pipeline reports + hygiene. Do the
parts in order, verify green after EACH part, and commit per part (3 commits).

## 0 · Setup

- Base: `audit-fixes`, and it MUST contain the F1+F2 commit. Check with
  `git log --oneline -3` (you should see the audit-fixes work on top of `24c5176`).
  If the base is wrong: STOP, reply "wrong base", change nothing.
- New branch: `git switch -c step-audit-rest` from the base.
- Python: always `.venv/bin/python` (3.11). Keys in `.env`, never committed, never printed.
- Read first: `AUDIT-PHASE1-4.md` (the findings bible — every item below cites it),
  `HANDOFF.md`, `AGENTS.md`, `PLAN-V2.md` §2 (D1–D13, binding).
- Rules that stay: one caller at a time; nothing in Mouth/socket loop blocks; tests
  never touch a paid API (`tests/conftest.py` guards stay); Muse spend under the hard
  ₹60 cap (₹12.97 spent); **Muse must never hear live callers**.
- LANDMINE (read `.agent/NOTES.md` F1 entry): `data_cache/derived/schemes.jsonl` does
  NOT reproduce from caches (commit `0a0ba3a` hand-merged 6 schemes). Do NOT run a
  full `make pipeline-extract` — it flips blessed text and breaks 4 gates. If you
  believe a pipeline rerun is needed, stop and report instead.
- No merge, no tag — the reviewer merges.

## 1 · Part F3 — engine correctness (AUDIT TOP-10 #9, #10 + Track-1 Ms/Ls)

1. **#9 Widen/ladder agreement.** Planner tests RAW survivors (`planner.py`
   zero-survivor ladder) while `Terminals.classify_shape` tests speakable-filtered,
   so the predicted rung can disagree with the terminal. Recommended fix: give the
   planner the SAME predicate — import the speakable filter from `terminals.py`
   (engine sibling, allowed) and test speakable at each rung. Keep T17 frozen
   signatures (`next_action`/`survivors`/`tally`/`miss_set`, `Widen(box)` shape —
   do NOT add payload fields). Check LOG stop reasons stay sane; add/adjust tests.
2. **#10 yes/no word lists out of Engine** (`call.py` confirm: hardcoded Hindi/
   Marathi/English lists). T09: Model owns language. Move the lists + matcher to
   `haqdaar/model/` (e.g. `prompts/confirm.py` or `router.py` helper); Engine calls
   it. Tests must cover accept/reject in all 3 langs (existing confirm tests stay green).
3. **`READBACK_REPLAY_MAX`** (`call.py` top): move to `contracts/tunables.py` per T17
   (the "step file list" excuse no longer applies). Delete the excuse comment.
4. **Confirm-loop turn accounting** (`call.py` confirm loop): `#`/`*`/silence
   `continue`s consume cap turns; T14 says `#` costs no turn and SILENCE consumes
   none. Fix accounting WITHOUT reintroducing the unbounded loop the confirm-turns
   counter was added for (step D review N4): use a SEPARATE repeat counter for the
   bound, not `turn_n`. Test: repeat-mashing terminates; cap turns unaffected.
5. **NEAREST `ladder_rung`** (`call.py` near-end): reports `len(WIDENING_ORDER)` (3)
   with zero answered soft boxes; T18 (skipped rungs not counted) → 0. Fix + test.
6. **`contracts/types.py`**: comment says "46 fixed line IDs", tuple holds 50 — fix
   the count; remove dead `drop_category` (category never widened). Check nothing
   imports it first.
7. **Track-1 LOWs** (each with a test unless noted): `filter.py` speakable() ANY
   detection for dict corpora (over-strict gag); `_sort_survivors` ignoring priority
   (enforce D8 order or prove snapshot pre-order + document); planner `_inferred_
   questions` vs Engine live `question_count` divergence (unify or document why both);
   `box_strikes` consecutiveness (SILENCE should break the streak per T11 — or
   document the approximation); stale "The next round re-opens Door A" comment
   (verify true now, else fix); OR-bit_length scheme-count heuristic (document the
   assumption); CLARIFY/REPEAT/META never written by Engine (check the model side —
   if the model writes them, no action + note it).

## 2 · Part F4 — server/audio/model hardening (AUDIT #6, #7, #8 + Track-2 LOWs)

8. **#6 one-caller guard** (`server.py`): every websocket spawns an engine thread
   with no guard, contradicting the one-caller docstring. Add a guard: while a call
   is active, a second `/stream` connection is refused busy (clean close + log line,
   no engine spawn). Test with two fake connections (no real sockets needed if you
   factor the guard; else TestClient).
9. **#7 stale-media drain** (`ear.py listen()`): queued media packets from during
   STT are transcribed as ghost utterances on the next listen. Drain `_events` at
   listen start. Test: queued stale packet + fresh speech → only fresh transcribed.
10. **#8 STT worst-case ~10s barge-in delay** (`ear.py`: Sarvam + Groq sequential
    5s timeouts). Implement a SHARED deadline across both providers (second gets the
    remainder) so one utterance caps total STT time. If infeasible without threads
    (forbidden), do NOT hack it: document the bound + measured worst case in NOTES
    and report it as left-open.
11. **Small items**: `audioop` DeprecationWarning (`ear.py:36` — breaks on 3.13+;
    suppress with a version-guard comment, runtime stays 3.11); `_CALLER_HASH` leak
    in `server.py` (clear entries when `/stream` ends without `/answer`... verify
    the leak is real first); `Model.opener/turn` defensive try (a raising custom
    client currently kills the call — convert to a typed failure if cheap);
    `_clips` `"scheme:"` 3-part split (guard malformed tokens instead of ValueError).
    Parked (do NOT touch, note as verified): `mouth.py` lock-free `_cleared` read
    (GIL-atomic, harmless), `HANGUP_WAIT_S` 15s linger (bounded, fine).

## 3 · Part F5 — pipeline reports + repo hygiene (Track-3/4 Ms/Ls)

12. **Gate-report roster accounting**: `gates.json` (tracked) reports survivors-only
    counts, hiding quarantines. Add additive keys (roster size, quarantined count +
    slugs, kept count) so `30 - quarantined == kept` is checkable. Same for the
    untracked `cards.json`/`translate.json`/`derive.json` tallies. No reader breaks
    (additive keys only). Test the accounting reconciles.
13. **`print_cost` blind spot** (`run_all.py`): reads only groq/sarvam ledgers,
    hiding the ₹12.97 Muse spend against the binding ₹60 cap. Include the Muse
    ledger. Test with fake ledger rows.
14. **`run_all._run_snapshot` lies** (`run_all.py:69-79`): named/docstring'd "build
    a snapshot" but only counts texts. Either make it actually build via `p6.main`
    or rename to what it does + fix the docstring. No lying names either way.
15. **Stale words**: `tests/test_real_snapshot.py:1` "real 12 schemes" → 11.
    (The p2 "Reads 12 files" line is already fixed — verify, don't duplicate.)
16. **`.gitignore` confusion**: `.agent/` is ignored yet `.agent/NOTES.md` is
    tracked (works, but confusing). Add an explicit `!.agent/NOTES.md` + comment.
    Verify `git status` still shows NOTES.md correctly and TASK.md stays ignored.
17. **Twilio-boundary grep test** (TEST-PLAN §3 requires one every step; absent):
    add a test asserting twilio imports live only under `audio/telephony` (mirror
    the existing layering tests in `test_scrape.py` tail style).

## 4 · Blocked — do not attempt, just report

- Anything needing the owner: Groq key fix, voice/menu/server decisions, real phone
  calls, listening, tags. Live `--live` runs: only if keys allow, else report.
- Dead-branch deletion (`~30` merged branches, stale `demo-15sep`) — needs explicit
  owner ask. Historical plan staleness (superseded docs). p6 inline chunk keys +
  `--all-schemes` hatch (audited, documented, fine as-is).
- The schemes.jsonl non-reproducibility landmine (§0): report, don't rerun.

## 5 · Verify (after EACH part, all green before the next)

```
cd ~/code/haqdaar-v2
.venv/bin/python -m pytest -q
make stress              # crashes 0, truth failures 0
make model-bakeoff       # 30/30 offline
make door-a-check        # >= 95% over 81 utterances
make render              # missing: 0
make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h"
```

## 6 · Reply with

Branch name; `git log <base>..HEAD` (expect 3 part-commits); pytest + stress +
bake-off + door-a-check outputs per part; Muse spend delta (expect ₹0.00);
`PROJECT-UPDATE.md` entry (plain short words); updated `.agent/TASK.md` +
`.agent/NOTES.md`; anything left blocked and why. No merge, no tag.
