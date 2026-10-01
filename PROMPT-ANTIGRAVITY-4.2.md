# PROMPT — Antigravity, step 4.2: model client + span guard + 30-utterance bake-off

You are writing code for HAQDAAR v2, Phase 4 (voice). Keypad (Phases 1–3) and
the ear (step 4.1, merged) are done. Your job is step TWO of Phase 4 only: the
model client that turns transcripts into facets. Later steps (Door A, spoken
answers, keypad fallback) come as separate prompts — do not start them.

## 0. Setup

- Work in `~/code/haqdaar-v2` (never the `~/Documents` copy, it hangs).
- Python is ALWAYS `.venv/bin/python` (3.11). System `python3` is 3.14 and broken here.
- Branch: `git switch -c step-4.2-model` from `main` (pushed, in sync).
- Read first: `HANDOFF.md`, `AGENTS.md`, `PLAN-V2.md` §2 (D1–D13, binding) and
  §3 step 4.2 (your scope; the plan's wording wins on detail).
- Keys in `.env` are never committed, never printed. Live speech must NEVER go
  to Muse (Contributor tier trains on it) — the model client is Groq only,
  and the bake-off runs on static checked-in fixtures, never live audio.

## 1. Warmup: fix-forward the 8 nits from the 4.1 review

1. `tests/test_ear.py:19`: unused imports (`END_FRAMES`, `END_RMS`,
   `MAX_UTTERANCE_FRAMES`, `PRE_ROLL_FRAMES`, `SAMPLE_RATE`, `START_FRAMES`,
   `START_RMS`, `speech_to_text`) — remove or use them.
2. `haqdaar/audio/ear.py:390`: `sarvam_ok` circuit breaker never resets (a live
   ear-check run stuck on Groq fallback after one transient Sarvam blip) — add a
   reset-per-`listen` or a failure counter.
3. `haqdaar/audio/ear.py:59`: `GROQ_LANG_MAP` returns ISO codes vs Sarvam `hi-IN`
   — normalize `res.lang`.
4. `haqdaar/audio/ear.py:387`: ledger Sarvam failures too, not just the final result.
5. `haqdaar/audio/ear.py:602`: `silence_count` not reset on the `Digit`
   early-returns — confirm and fix.
6. Document that plain `make ear-check` spends API budget (defaults live;
   `--offline` only checks loading).
7. Note Sarvam ignores `hint`; document the `STT_TIMEOUT_S` / `SARVAM_STT_MODEL` /
   `GROQ_STT_MODEL` env overrides.
8. Consider an autouse httpx guard in `tests/conftest.py` (it blocks only Muse today).

## 2. Build `haqdaar/model/` (does not exist yet)

- **Client:** Groq, JSON output, temperature 0, 2 s timeout, never raises.
  No SDK: raw `httpx`, copying the existing Groq pattern
  (`haqdaar/data/pipeline/p2_derive.py:68-124`). Key `GROQ_API_KEY` is in `.env`.
- **Failure accounting:** a 429 (or any failure/timeout) counts as a failure;
  2 failures → keypad-only for the rest of the call. Expose the counter so the
  engine (step 4.4) can read it; do not wire the engine yourself.
- **Span guard:** a value from the model is kept only if its words appear in the
  transcript. "Farmer" must never smuggle in "low income".
- One caller at a time. Nothing in this path may block the socket loop.

## 3. Utterances + `tests/test_model.py` + offline bake-off

- `fixtures/audio/speech/` holds 9 utterances today (`p1/p2/p3 × en/hi/mr`,
  see `manifest.json`). Author ~21 more (small static fixtures, checked in, keep
  them tiny) for a 30-utterance bake-off set; extend the manifest in the same shape.
- `tests/test_model.py`: mocked tests on transcripts only — span-guard cases
  ("farmer" must not add "low income"), timeout/429-as-failure, 2-failures →
  keypad-only. `tests/conftest.py` blocks paid APIs — tests must be offline,
  fake the HTTP layer, never touch the network.
- Bake-off (deferred to owner, but leave the command ready): add a
  `make model-bakeoff` target (or script + target) that runs the 30 transcripts
  through the client + span guard and prints accuracy with p50/p95 latency.
  You have no paid budget to burn, so do NOT block on the live run: verify it
  end-to-end against fixtures with the HTTP layer faked; the owner runs the
  live Groq pass and records p50/p95 in `.agent/NOTES.md`.

## 4. Rules

- Smallest correct change. No refactors, no renames, no "while I'm here".
- Do NOT touch `haqdaar/engine/`, `haqdaar/contracts/`, `snapshots/`,
  or any gate/threshold/tunable value.
- Build on the 4.1 surface, don't rework it: `SpeechToText`, `SttResult`,
  `transcribe`, `alisten`, the `push_*` keypress checkpoints, `speech_to_text()`.
- No Muse client anywhere near this step. No new dependencies without asking
  (httpx is already in).

## 5. Verify (all must pass)

```
.venv/bin/python -m pytest -q          # must stay green
make stress                            # 0 crashes, 0 truth failures
make model-bakeoff                     # runs against fixtures (faked HTTP), prints accuracy + p50/p95
```

## 6. Done-when

- New branch holds only: `haqdaar/model/`, `tests/test_model.py`,
  fixtures, nit fixes, `Makefile` target, `PROJECT-UPDATE.md` entry.
- pytest green, stress 0/0.
- Short entry appended to `PROJECT-UPDATE.md` (same style as previous entries).
- Reply with: branch name, `git log main..HEAD`, pytest + stress output.

## NOT yours

Steps 4.3–4.5 (separate prompts), the live Groq bake-off pass, p50/p95 NOTES
entry, server-location pick, owner audit (A2/A3), merge + tags.
