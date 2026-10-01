# STEP D — 4.5 Fallback wiring + live API passes (Antigravity work order)

## 0 · Setup

- Base: `main`, and it MUST already contain the merged STEP C. Check with
  `git log --oneline -5`. If STEP C is not merged yet: STOP, reply
  "base missing step C merge", change nothing.
- New branch: `git switch -c step-4.5-fallback` from the base.
- Python: always `.venv/bin/python` (3.11). Keys in `.env`, never committed, never printed.
- Read first: `HANDOFF.md`, `AGENTS.md`, `PLAN-V2.md` §2 (D1–D13, binding) + §3,
  `PHASE-4-PLAN.md` (the 4.5 spec — follow it).
- Rules that stay: one caller at a time; nothing in Mouth/socket loop blocks; tests never
  touch a paid API; **Muse must never hear live callers** (live speech to Groq/Sarvam only).

## 1 · Scope: wire ear + model into the turn loop (unwired on 1 Oct)

Warmup (from the Step C review) — do first:
1. `haqdaar/engine/door_a.py:265`: `_load_manual_aliases()` is called inside the
   per-scheme loop (re-reads + re-parses the JSON per scheme per init). Hoist to one
   load or a module-level cache.
2. `tools/door_a_check.py:52`: dead fallback `(res.scheme_ids[0] if res.scheme_ids
   else "")` retained. Simplify to match the test's clean form (line 53 already
   requires `action == "read"`).
3. `haqdaar/engine/call.py:473-480`: the proposed value is logged as ANSWER *before*
   the caller confirms, so a rejected value (press 2) leaves a phantom ANSWER record
   and accepted values log ANSWER twice. Log the proposal as a non-ANSWER class
   instead (no consumer reads this yet — `tools/judge.py` is step 5.2 — but define the
   shape now; update `tests/test_call_spoken.py` to match).
4. `haqdaar/engine/call.py:501,517,568,571`: `#`/`*`/silence-rung-1/2 `continue` the
   confirm loop without advancing turn_n or a MAX_TURNS check — unbounded on
   repeat-mashing. Bound it.
5. `haqdaar/sim.py:87-98`: SimModelClient's default opener stamp returns farming for
   ANY unrecognized speech, so sim can never exercise the model-UNCLEAR branch. Return
   UNCLEAR (or nothing) for unmatched text.
6. Reminder: prompt §reply asks for `.agent/TASK.md` AND `.agent/NOTES.md` — step C
   forgot TASK.md. Update both.

Main scope:

Today `server.py:181` passes `model=None` (keypad-only) and nothing imports ear/model in
server/sim/call/turn. The pieces exist in isolation — connect them:

- Ear failure signals (`haqdaar/audio/ear.py`) + model circuit breaker
  (`haqdaar/model/router.py`) → drive `Engine.run_call` off `model=None`: voice breaks
  twice / STT fails → the call falls back to keypad (the `model=None` keypad path in
  `engine/call.py:125-128` already exists — reuse it, do not fork the call path).
- Add the forced-STT-failure test IN the turn loop (fail the ear on purpose, assert the
  call continues on keypad and the LOG shows the fallback line).
- Keep the non-blocking + one-caller rules: no new threads/queues/pools anywhere.

## 2 · Live API passes (cheap, no phone needed — do them if keys/network allow)

- `make model-bakeoff ARGS=--live` (PLAN-V2 4.2 verify wants live p50/p95 — record in NOTES).
- Live ear-check (`make ear-check`, default live target).
- If either is blocked (no key, no network): leave for the owner, report exactly what
  blocked it. Do not fake numbers.

## 3 · Do NOT touch (owner's end-file)

Any real phone call, any merge or tag (`v1-voice` is the owner's). Server-location pick
is the owner's — but record the ear-check latency you measured in NOTES so the owner can
decide (0.43s avg measured 1 Oct).

## 4 · Verify (all green before you reply)

```
cd ~/code/haqdaar-v2
.venv/bin/python -m pytest -q
make stress              # crashes 0, truth failures 0
make model-bakeoff       # 30/30 offline (+ live numbers if §2 ran)
make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h"
```

## 5 · Reply with

Branch name; `git log <base>..HEAD`; pytest + stress + bake-off (offline + live if ran)
outputs; forced-failure test result; `PROJECT-UPDATE.md` entry (plain short words);
updated `.agent/TASK.md` + `.agent/NOTES.md`; anything left blocked and why. No merge,
no tag — the reviewer merges.
