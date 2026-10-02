# STEP 5.1 — Anything-else voice turn + scheme-audio prefetch (Antigravity work order)

Close the two known end-of-call gaps. Owner work stays STOPPED: no new voice clips,
no Groq key, no real calls, no listening — if any item needs those, report it blocked.

## 0 · Setup

- Base: `main` @ `63e270a` (audit fixes merged, pytest 441). Check with
  `git log --oneline -1`. If the base is wrong: STOP, reply "wrong base".
- New branch: `git switch -c step-5.1-anything-else` from the base.
- Python: always `.venv/bin/python` (3.11). Keys in `.env`, never committed/printed.
- Read first: `HANDOFF.md`, `AGENTS.md`, `PLAN-V2.md` §2 (D1–D13, binding) + §3
  (Phase 5), `.agent/NOTES.md` tail (carried nits).
- Rules that stay: one caller; nothing blocks Mouth/socket loop; tests never touch a
  paid API (`tests/conftest.py` guards stay); Muse spend under hard ₹60 cap (₹12.97
  spent, expect ₹0.00 delta); **Muse must never hear live callers**; engine never
  imports audio pool (`call.py:7-12` layering); no merge, no tag — the reviewer merges.
- LANDMINE: `data_cache/derived/schemes.jsonl` does NOT reproduce from caches
  (hand-merged text + rendered audio). Do NOT run full `make pipeline-extract`.

## 1 · Build

1. **Anything-else hears voice** (`haqdaar/engine/call.py:977-1001`). Today it plays
   `anything_else` ("Press 1 for yes, 2 for no") and reads KEYPAD ONLY — a voice
   caller saying "yes" or naming a new topic is never heard and the call just ends.
   Fix: in voice mode, listen for speech first (same Ear/Model path as the question
   turns), accept yes/no via the Model confirm matcher (3 langs) plus keypad 1/2 as
   fallback; a "yes" re-opens the question loop for a new topic, a "no"/silence ends
   the call exactly as today. Keypad-only mode behavior UNCHANGED. Reuse the existing
   `anything_else` audio line — do NOT add or reword any line (new clips are owner-
   held). If the current wording makes a voice turn impossible, stop and report.
2. **Wire up prefetch.** `AudioPool.prefetch()` (`haqdaar/audio/pool.py:149-161`,
   gated by `AUDIO_PREFETCH_ON_STOP`, `tunables.py:50`) exists but has ZERO
   production callers, so the first scheme clip is a cold disk read. Call it from the
   terminal phase (`call.py:883-921`) using the ranked ids already computed
   (`call.py:946-948`). Engine cannot import the pool — go through the audio
   boundary: add a `PhoneAudio` method in `haqdaar/audio/phone.py` (cf. `_clip`
   `:162-170`) resolving keys via `Corpus.chunks()` (`corpus.py:339`). Prefetch must
   never block or crash the call: failures log and continue. Respect the tunable
   (off by default stays off; test both).
3. **Carried nit (small, adjacent):** add the missing direct test for
   `Turn.wait_input` (see NOTES step D review). Do NOT take the sim opener UNCLEAR
   asymmetry — that rides with 5.2 (judge/sim scope).

## 2 · Tests (mirror `tests/test_call_spoken.py`, `test_call.py`, `test_phone_call.py`)

- Voice "yes" at anything-else re-opens the loop; voice "no" ends; keypad 1/2 still
  work in both modes; silence ends (no hang, no extra turn).
- New-topic utterance after "yes" is heard (not just yes/no).
- Prefetch called once with ranked ids at terminal phase; prefetch failure still
  completes the call; tunable off = no prefetch call.
- `Turn.wait_input` direct test.
- Full suite green, no paid API (fakes only — the conftest guard must pass).

## 3 · Blocked — do not attempt, just report

- New/changed audio lines or clips (owner voice decision, Sarvam spend).
- Groq key / live model runs; real phone calls; listening checks; tags.
- 5.2 judge + sim asymmetry, 5.3 crash restart, 5.4 phone provider — later steps.

## 4 · Verify (all green)

```
cd ~/code/haqdaar-v2
.venv/bin/python -m pytest -q
make stress              # crashes 0, truth failures 0
make model-bakeoff       # 30/30 offline
make door-a-check        # >= 95% over 81 utterances
make render              # missing: 0
make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h"
```

## 5 · Reply with

Branch name; `git log <base>..HEAD`; pytest + stress + bake-off + door-a-check
outputs; Muse spend delta (expect ₹0.00); `PROJECT-UPDATE.md` entry (plain short
words); updated `.agent/NOTES.md`; anything left blocked and why. No merge, no tag.
