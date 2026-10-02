# HANDOFF — start here (1 Oct 2026)

From now on the owner works like this:
- **Muse Spark 1.3 Contributor** plans each step.
- **Antigravity** writes the code.
- **Muse (reviewer)** checks each Antigravity step and merges it.
- **Claude** checks everything at the end.

This file is the shared base for all four. Read it first, then `AGENTS.md` (the rules), then
`PLAN-V2.md` §2 (design decisions D1–D13, binding) and §3 (the phases).

---

## 1 · Where the code is

- **Folder:** `~/code/haqdaar-v2`. Always work here. The `~/Documents/haqdaar-v2` copy sits in
  iCloud and hangs on big reads. Both copies are on the same branch, but only `~/code` is safe to run.
- **Branch:** `main` (pushed to GitHub, `haqdaar-v3`, in sync). Start every new step on a new
  branch from here, for example `git switch -c step-5.1-attr`.
- **Merged:** `main` holds Phase 2 + Phase 3 + Phase 4 code plus the audit fixes
  (F1+F2+E, all 36 findings): the 3.7 audit tooling, step 4.1 (ear), step 4.2 (model +
  bake-off), steps A–D (gates 27/27 + 11-scheme snapshot, Door A 79/81 wired with stamps,
  spoken+confirm turn, fallback wiring + live ear-check 9/9), one-caller guard, ghost
  drain, shared STT deadline, roster accounting. Step 5.1 is merged too (pytest 456, stress 0/0).
- **Merged 2 Oct (night), on the owner's word, and pushed:** `step-5.2-judge` (the judge),
  `step-5.3-hardening` (restart after a crash, smoke checklist, Muse day guard, two opener
  fixes) and `step-5.5-call-viewer` (the call page, see §2). Nothing is waiting to be merged.
  Tagging `v1-keypad` waits for the owner's audit verdicts and 3 real calls.
- **Python:** always `.venv/bin/python`, which is 3.11. The system `python3` is 3.14 and has no `audioop`.
- **Keys:** they live in `~/code/haqdaar-v2/.env` and are never committed. It holds MUSE_API_KEY,
  SARVAM_API_KEY, TWILIO_*, and HF_TOKEN. Never print a key or paste one into chat.

## 2 · How to check that nothing broke

```
cd ~/code/haqdaar-v2
.venv/bin/python -m pytest -q          # 491 on main (2 Oct)
make stress                            # 1,000 random callers: must say crashes 0, truth failures 0
make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h"   # one call in the terminal
```

**To look at a call:** `make calls-ui` opens the call page (http://127.0.0.1:8001, this computer
only). Each call shows as a back and forth: what the AI said, what the caller pressed or said,
what the engine made of it, and how long each part took. A call in progress updates by itself.
It reads `<logs>/trace/<call_id>.jsonl`, which every phone call and every sim now writes
(`haqdaar/data/trace.py`). Sims play no sound, so only real calls show times.

Every step must end with pytest green and `make stress` at 0 / 0. Tests must never call a paid
API: `tests/conftest.py` blocks Muse, and each test fakes its client.

## 3 · What is done

- **Phase 0 and Phase 1:** done and merged. The pipeline turns myscheme pages into cards, and the
  engine is keypad-only.
- **Phase 2:** done in code on the 12 schemes. This covers the real voice clips (Sarvam),
  snapshot, pool, telephony, Mouth, Turn and the `/stream` server. It is waiting on the owner:
  3 real calls, listening, then merge + tag `v1-keypad`.
- **Phase 3 so far** (owner, 30 Sep: **30 schemes for now, not 110–130**; the big voice render
  comes later):
  - **3.1** `p0_discover.py` → `data_cache/derived/candidates.csv` has all 746 central schemes.
  - **3.2** `haqdaar/data/pipeline/schemes.yaml` has 30 schemes: the 12 plus 18 new ones.
  - **3.3** The scraper adds each scheme's level and ministry, and uses the system Chrome.
    - 28 of 30 scraped.
    - `ab-pmjay`: the site now says "Page not found".
    - `pmsby`: the page has no documents section.
  - **3.4** `haqdaar/data/pipeline/muse.py` is the Muse client for cards and translation.
    - It has a **hard ₹60 cap**; spent so far is ₹12.97, logged in `data_cache/reports/muse_usage.jsonl`.
    - It also has a **₹30 a day cap** and a day block (2 Oct, on `step-5.3-hardening`):
      `make muse-status`, `make muse-block`, `make muse-unblock`. The day rolls at 05:00 India time.
    - The facet step (`make pipeline-extract`) was stopped on purpose near the end.
    - Everything already answered is cached, so a re-run only pays for what is left.
  - **3.8** The server pins only the fixed lines (6.7 MB), and scheme audio loads when it is read.
  - **3.6** `make stress` runs 1,000 callers: 0 crashes, 0 truth failures.
- **3.7 tooling** `tools/cards_sheet.py` (seeded 20-sample), `audit_3_7.md`
  template, `listen.py` cards mode. Reading, listening and verdicts are the owner's.
- **4.1 ear** `haqdaar/audio/ear.py` (Sarvam STT primary, Groq Whisper fallback,
  energy VAD, NOISE vs SILENCE, keypress wins, timeout = failure signal), 9 speech
  fixtures, `tests/test_ear.py` (17 tests, offline), `make ear-check` (defaults live;
  `--offline` only checks loading). Merged 1 Oct, pytest 331.
- **4.2 model** `haqdaar/model/` (Groq client: raw httpx, JSON, T0, 2 s timeout, never
  raises; router with 2-failures → keypad-only; span guard), 30 speech fixtures,
  `tests/test_model.py` (21 tests, offline), `make model-bakeoff` (30/30 offline).
  Merged 1 Oct, pytest 353.
- **Steps A–D** (Phase 3 code finish + 4.3–4.5), merged 1 Oct, pytest 372:
  - **A:** fixed the 7 gate failures (28/28, ₹0 new spend), settled 3 scheme fates
    (ab-pmjay kept serving + flagged stale; pm-sym, pmsby quarantined), rebuilt the
    12-scheme audio-ready snapshot (`snap_20261001_084303`).
  - **B:** `haqdaar/engine/door_a.py` — say the scheme's name to jump to it (90/90
    offline, 0.55 ms mean). 8 warmup nits fixed.
  - **C:** spoken answers + "if right press 1" confirmation turn, proven on the sim
    path (live keypad path untouched). 7 warmup nits fixed.
  - **D:** ear/model wired into the turn loop — voice breaks → keypad fallback (no
    forked call path), forced-STT-failure test, live ear-check 9/9 @0.61 s avg.
    6 warmup items fixed. Bake-off `--live` blocked: Groq key lacks
    `llama-3.3-70b-versatile` (404, 0 tokens) — owner key fix + rerun.

## 4 · What is left, in order

Phase 3 + Phase 4 code is DONE and merged (steps A–D). What remains:

1. **Owner end-file** `OWNER-END-TODO.md` (owner cannot run physical tests right now):
   decisions (voice for 18 new clips, menu length, server location), ears (listen to
   clips, 3.7 read of 20 cards), phone (3 real keypad calls, 3 live voice calls, Door A
   live <20 s check), tags (`v1-keypad`, `v1-voice`). Plus the Groq key fix +
   live bake-off rerun (blocked in step D, 0 tokens spent).
2. **Phase 5: make it solid.** The code for 5.1, 5.2 and 5.3 is written (5.1 merged; 5.2 and 5.3
   on their branches, see §1). The carried nits are closed. Still open:
   - **5.3 drills (owner, real phone):** Wi-Fi dies, the process is killed, a call after
     30 min idle. `make smoke` prints the list.
   - **5.4 Indian phone provider: dropped for now** (owner, 2 Oct). Do not start it. If it comes
     back, it is one new file in `haqdaar/audio/telephony/` that passes the conformance test.
3. **Phase 6: the 10-call test** — 10 outside callers, 8 or more PASS, then tag `v1`.

- **Muse must never hear live callers.** On the Contributor tier Meta may train on what it is
  sent. Live speech needs another provider: Groq Whisper, Sarvam STT, or similar.

**Owner jobs (all parked in `OWNER-END-TODO.md` for the end)**
- Decisions: voice for new clips, menu length, server location.
- Ears: listen to clips (`make listen-cards L=mr N=10`), 3.7 read of 20 cards.
- Phone: 3 real keypad calls (Twilio trial → one verified number), 3 live voice calls,
  Door A live <20 s check.
- Keys: Groq key needs `llama-3.3-70b-versatile` (or new model name), then live bake-off rerun.
- Tags: `v1-keypad`, then `v1-voice`.

## 5 · Rules that caught real bugs (keep them)

- **One caller at a time.** Never build for concurrency.
- **Nothing in Mouth or the socket loop may block.** The 15 Sep demo froze for 10 s this way.
- **Every clip the snapshot names must exist.** `make render` and `p6_snapshot` share one text
  list (`texts.py`), and a test checks that they match.
- **Keypad menus have at most 9 choices.** 0 means "don't know".
- **Paid APIs sit behind a ledger and a cap.** A test must never reach one.
- **Write in plain, short words.** After each step, add an entry to `PROJECT-UPDATE.md`.
- **Keep `.agent/TASK.md` (checklist) and `.agent/NOTES.md` (findings) up to date.** They are
  how the next tool knows what happened.

## 6 · When the work is done, for Claude's check

Leave these ready, and Claude will review them:
- the branch name;
- `git log main..HEAD`;
- the pytest and `make stress` output;
- any Muse spend (`muse_usage.jsonl`);
- a short list of what changed, per step, in `PROJECT-UPDATE.md`.
