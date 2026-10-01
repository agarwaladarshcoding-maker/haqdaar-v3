# PROMPT — Antigravity, step 4.1: ear.py (STT) + fixtures

You are writing code for HAQDAAR v2, Phase 4 (voice). Keypad (Phases 1–3) is
done and merged. Your job is step ONE of Phase 4 only: the ear (speech to
text). Later steps (model, Door A, spoken answers, keypad fallback) come as
separate prompts — do not start them.

## 0. Setup

- Work in `~/code/haqdaar-v2` (never the `~/Documents` copy, it hangs).
- Python is ALWAYS `.venv/bin/python` (3.11). System `python3` is 3.14 and broken here.
- Branch: `git switch -c step-4.1-ear` from `main` (pushed, in sync).
- Read first: `HANDOFF.md`, `AGENTS.md`, `PLAN-V2.md` §2 (D1–D13, binding) and
  §3 step 4.1 (your scope; the plan's wording wins on detail).
- Keys in `.env` are never committed, never printed. Live speech must NEVER go
  to Muse (Contributor tier trains on it) — this step uses Sarvam + Groq only.

## 1. Warmup: fix the 3 nits from the 3.7 review (5 minutes)

1. `tools/listen.py:58-59`: cards branch accepts count `all` but the docstring
   (`:1-9`) documents only `cards hi 10`. Document it (and guard the non-cards
   branch `:68-71`, where `int("all")` would crash).
2. `tools/cards_sheet.py:253`: `json.dump(...)` writes no trailing newline.
3. `tests/test_cards_sheet.py`: `import json` (`:10`), `AUDIT_PATH` (`:14`),
   `SAMPLE_PATH` (`:17`), `SHEET_PATH` (`:19`) are unused — remove or use them.

## 2. Build `haqdaar/audio/ear.py` (does not exist yet)

- **Providers:** Sarvam STT primary (re-check the model/endpoint at build time —
  the plan mandates this), Groq Whisper fallback. No SDKs: use raw `httpx`,
  copying the existing patterns (`haqdaar/audio/render.py:109-190` for Sarvam,
  `haqdaar/data/pipeline/p2_derive.py:68-124` for Groq). Keys `SARVAM_API_KEY`
  and `GROQ_API_KEY` are already in `.env`.
- **Behavior:** 1 s padding, hint words, energy VAD; distinguish NOISE from
  SILENCE; a keypress always wins over speech; an STT timeout is a failure
  signal, never an exception, never a retry loop.
- **Port-from reference:** `git show demo-15sep:haqdaar/voice_demo.py:340-385,476-524`
  (prior working shape; adapt, don't worship).
- One caller at a time. Nothing in the audio path may block the socket loop.

## 3. Speech fixtures + `tests/test_ear.py`

- `fixtures/audio/` today holds only 10 TTS `.ulaw` clips — no speech/STT
  fixtures exist. Add small static speech fixtures (checked in; keep them tiny).
- `tests/test_ear.py`: accuracy/shape tests on fixtures only.
  `tests/conftest.py` blocks paid APIs — tests must be offline, fake the
  HTTP layer, never touch the network.

## 4. Live-voice check (deferred to owner, but leave the command ready)

The plan wants 3 live sentences per language. You have no microphone, so do NOT
block on this: add a `make ear-check` target (or script + target) that takes
3 sentences × en/hi/mr and prints transcripts. Verify it runs end-to-end
against fixtures; the owner runs the live pass. The server-location RTT
pre-step is also the owner's and blocks nothing.

## 5. Rules

- Smallest correct change. No refactors, no renames, no "while I'm here".
- Do NOT touch `haqdaar/engine/`, `haqdaar/contracts/`, `snapshots/`,
  or any gate/threshold/tunable value.
- No Muse client anywhere near this step. No new dependencies without asking
  (httpx is already in).

## 6. Verify (all must pass)

```
.venv/bin/python -m pytest -q          # must stay green (314 passed on main)
make stress                            # 0 crashes, 0 truth failures
make ear-check                         # runs against fixtures, prints transcripts
```

## 7. Done-when

- New branch holds only: `haqdaar/audio/ear.py`, `tests/test_ear.py`,
  fixtures, nit fixes, `Makefile` target, `PROJECT-UPDATE.md` entry.
- pytest green, stress 0/0.
- Short entry appended to `PROJECT-UPDATE.md` (same style as previous entries).
- Reply with: branch name, `git log main..HEAD`, pytest + stress output.

## NOT yours

Steps 4.2–4.5 (separate prompts), live-voice pass, server-location pick,
owner audit (A2/A3), merge + tags.
