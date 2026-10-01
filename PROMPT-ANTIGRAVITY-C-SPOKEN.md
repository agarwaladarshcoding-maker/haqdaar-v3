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

## 1 · Scope (not started — zero confirm logic in `engine/call.py`, `sim.py`, `server.py` on 1 Oct)

- Implement spoken answers with the "if right press 1" confirmation turn: model
  understands the spoken answer, Mouth reads back what it heard, caller presses 1 to
  confirm (or corrects / the turn re-asks on mismatch — follow `PHASE-4-PLAN.md`).
- This touches the live call path, so prove it on the sim path: `make sim` must run end
  to end through a spoken-answer turn (fake STT/model at the seam, same as the bake-off
  does — no network).
- Offline tests for: confirm-accept, confirm-mismatch re-ask, and no-confirm-answer
  (silence/unclear) handling.

## 2 · Verify (all green before you reply)

```
cd ~/code/haqdaar-v2
.venv/bin/python -m pytest -q
make stress              # crashes 0, truth failures 0
make model-bakeoff       # still 30/30 offline
make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h"
```

## 3 · Reply with

Branch name; `git log <base>..HEAD`; pytest + stress + bake-off outputs; what the sim run
showed for the confirm turn; `PROJECT-UPDATE.md` entry (plain short words); updated
`.agent/TASK.md` + `.agent/NOTES.md`; anything left blocked and why. No merge, no tag —
the reviewer merges.
