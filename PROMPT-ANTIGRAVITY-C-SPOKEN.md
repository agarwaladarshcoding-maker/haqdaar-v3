# STEP C — 4.4 Spoken answers + "if right press 1" (Antigravity work order)

## 0 · Setup

- Base: `main`, and it MUST already contain the merged STEP B. Check with
  `git log --oneline -5`. If STEP B is not merged yet: STOP, reply
  "base missing step B merge", change nothing.
- New branch: `git switch -c step-4.4-spoken` from the base.
- Python: always `.venv/bin/python` (3.11). Keys in `.env`, never committed, never printed.
- Read first: `HANDOFF.md`, `AGENTS.md`, `PLAN-V2.md` §2 (D1–D13, binding) + §3,
  `PHASE-4-PLAN.md` (the 4.4 spec — follow it).
- Rules that stay: one caller at a time; nothing in Mouth/socket loop blocks; tests never
  touch a paid API; **Muse must never hear live callers** (live speech to Groq/Sarvam only).

## 1 · Warmup — fix-forward the 7 nits from the Step B review

1. `haqdaar/model/router.py:43`: `timeout: float = 2.0` is still hardcoded and passed
   explicitly to `GroqModelClient`, so tunables-patching has no effect via the router
   path. Use `timeout: Optional[float] = None` passthrough to `tunables.MODEL_TIMEOUT_S`.
2. `haqdaar/engine/door_a.py:354,356,438,447`: magic policy numbers (1000/500 scores,
   30.0 floor, 0.90 tie band) live in code; repo convention puts them in
   `contracts/tunables.py` (cf. `NEAREST_CAP`). Move them.
3. `haqdaar/engine/door_a.py:212-216`: missing `schemes.yaml` yields a silently empty
   matcher (everything downgrades to B). Raise or log instead of going silent.
4. `haqdaar/engine/door_a.py:88-99`: `MANUAL_ALIASES` hardcodes data for 2 quarantined
   schemes (`pmsby`, `pm-sym`) in engine code. Remove them (quarantined schemes are not
   servable) or move them to a data source — do not leave data in engine code.
5. `haqdaar/engine/door_a.py:391`: corpus fast-path calls `alias_lookup` on the raw
   transcript without `normalize_text`, inconsistent with the token path. Normalize first.
6. `tools/door_a_check.py:52`, `tests/test_door_a.py:151`: the `shortlist[0]` fallback in
   the top-1 measure could mask future downgrades. Assert `action == "read"` for hits.
7. `PHASE-4-PLAN.md:15`: says "3 forms × 40 schemes" but `schemes.yaml` holds 30. Stale
   plan line — fix the plan, not the code.

(Parked, NOT this step: inject `scheme_entries` into Door A instead of engine reading
yaml at runtime — revisit when Door A gets a runtime caller in step D; and a hold-out /
STT-noised fixture set — owed before live, parked for the live phase.)

## 2 · Scope (not started — zero confirm logic in `engine/call.py`, `sim.py`, `server.py` on 1 Oct)

- Implement spoken answers with the "if right press 1" confirmation turn: model
  understands the spoken answer, Mouth reads back what it heard, caller presses 1 to
  confirm (or corrects / the turn re-asks on mismatch — follow `PHASE-4-PLAN.md`).
- This touches the live call path, so prove it on the sim path: `make sim` must run end
  to end through a spoken-answer turn (fake STT/model at the seam, same as the bake-off
  does — no network).
- Offline tests for: confirm-accept, confirm-mismatch re-ask, and no-confirm-answer
  (silence/unclear) handling.

## 3 · Verify (all green before you reply)

```
cd ~/code/haqdaar-v2
.venv/bin/python -m pytest -q
make stress              # crashes 0, truth failures 0
make model-bakeoff       # still 30/30 offline
make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h"
```

## 4 · Reply with

Branch name; `git log <base>..HEAD`; pytest + stress + bake-off outputs; what the sim run
showed for the confirm turn; `PROJECT-UPDATE.md` entry (plain short words); updated
`.agent/TASK.md` + `.agent/NOTES.md`; anything left blocked and why. No merge, no tag —
the reviewer merges.
