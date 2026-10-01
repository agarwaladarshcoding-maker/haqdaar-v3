# STEP B — 4.3 Door A + 4.2-nits warmup (Antigravity work order)

## 0 · Setup

- Base: `main`, and it MUST already contain the merged STEP A. Check with
  `git log --oneline -5`. If STEP A is not merged yet: STOP, reply
  "base missing step A merge", change nothing.
- New branch: `git switch -c step-4.3-door-a` from the base.
- Python: always `.venv/bin/python` (3.11). Keys in `.env`, never committed, never printed.
- Read first: `HANDOFF.md`, `AGENTS.md`, `PLAN-V2.md` §2 (D1–D13, binding) + §3,
  `PHASE-4-PLAN.md` (the 4.3 spec — follow it).
- Rules that stay: one caller at a time; nothing in Mouth/socket loop blocks; tests never
  touch a paid API (`tests/conftest.py` httpx guard stays); **Muse must never hear live
  callers** (Contributor tier may train on what it is sent — live speech goes to
  Groq/Sarvam only, never a Muse API).

## 1 · Warmup — fix-forward the 5 nits from the 4.2 review

1. `haqdaar/model/client.py:65` reads `MODEL_TIMEOUT_S` from `os.environ`; use
   `tunables.MODEL_TIMEOUT_S` so tests patching tunables take effect.
2. `tools/model_bakeoff.py:151-153,159`: `hallucinations_dropped` is asserted, not
   measured — a span-guard regression still prints 30/30 PASS. Fail the bake-off when
   produced ⊄ expected so it works as a regression gate.
3. `haqdaar/model/span_guard.py:164-166`: `income_band` accepts any non-empty string.
   Tighten only if bands are canonicalized; otherwise leave it and note why.
4. `haqdaar/model/router.py:80-84`: alias fast-path stamps skip SpanGuard. By design,
   but add a one-line comment noting the bypass.
5. `.agent/NOTES.md`: remove the stale "332 tests passed" line (the suite is at 353+).

Plus 3 nits from the Step A review:
6. `tests/test_cards_sheet.py:34`: `assert len(failing_ids) == len(gates.get("failures", []))`
   is near-tautological (the sample is built from gates) and would auto-pass a future
   regression. Assert `== 0` with a comment instead (gates are 28/28 now). Also fix the
   stale docstring at `:4` ("7 failing + 13 passing").
7. `Makefile:97`: `make render` without YES now checks only `snapshots/CURRENT`, but
   `make render YES=1` without SNAP still renders ALL schemes. Add a one-line comment
   noting the check/render scope mismatch so "missing: 0" is not misread as full-corpus
   coverage.
8. `haqdaar/audio/render.py:320-323`: bare-id branch re-checks `is_file()` on
   `snapshots/<id>` (always a dir) — harmless dead code. Remove it.

## 2 · Scope: 4.3 Door A (not started — no `haqdaar/engine/door_a.py` on 1 Oct)

- Build Door A per `PHASE-4-PLAN.md`: caller says the scheme's name at the opener and
  jumps straight to it.
- Include the OFFLINE top-1 accuracy check (3 forms × every scheme in
  `haqdaar/data/pipeline/schemes.yaml` — confirm the count from the file, 30-scheme scope).
- Offline tests only (fake the STT/model side). The live "<20 s" check needs a real call
  and is the owner's (see `OWNER-END-TODO.md`) — do not attempt it.

## 3 · Verify (all green before you reply)

```
cd ~/code/haqdaar-v2
.venv/bin/python -m pytest -q
make stress              # crashes 0, truth failures 0
make model-bakeoff       # still 30/30 offline
make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h"
```

## 4 · Reply with

Branch name; `git log <base>..HEAD`; pytest + stress + bake-off outputs; offline Door A
accuracy number; `PROJECT-UPDATE.md` entry (plain short words); updated `.agent/TASK.md`
+ `.agent/NOTES.md`; anything left blocked and why. No merge, no tag — the reviewer merges.
