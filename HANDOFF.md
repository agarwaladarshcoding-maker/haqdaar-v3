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
  branch from here, for example `git switch -c step-4.3-door-a`.
- **Merged:** `main` holds Phase 2 + Phase 3, including the 3.7 audit tooling, plus
  step 4.1 (ear: Sarvam STT + Groq fallback, speech fixtures, `make ear-check`) and
  step 4.2 (model: Groq client + span guard + 30-utterance bake-off, pytest 353).
  Steps A–D prompts + owner end-file are on `main` (see §4).
  Tagging `v1-keypad` waits for the owner's audit verdicts and 3 real calls.
- **Python:** always `.venv/bin/python`, which is 3.11. The system `python3` is 3.14 and has no `audioop`.
- **Keys:** they live in `~/code/haqdaar-v2/.env` and are never committed. It holds MUSE_API_KEY,
  SARVAM_API_KEY, TWILIO_*, and HF_TOKEN. Never print a key or paste one into chat.

## 2 · How to check that nothing broke

```
cd ~/code/haqdaar-v2
.venv/bin/python -m pytest -q          # 353 pass on 1 Oct
make stress                            # 1,000 random callers: must say crashes 0, truth failures 0
make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h"   # one call in the terminal
```

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

## 4 · What is left, in order

Flow now: owner pastes ONE step prompt → Antigravity builds → reviewer checks + merges →
next step. Step prompts `PROMPT-ANTIGRAVITY-A/B/C/D` (+ dispatch index
`PROMPT-ANTIGRAVITY-3-4-COMBINED.md`). Owner physical work is parked in
`OWNER-END-TODO.md` (owner cannot run physical tests right now).

**Step A — Phase 3 code finish** (gates + fates + snapshot):
1. Fix the 7 gate failures (gates.json 21/28, 25% quarantined — fails the <15% bar).
2. Settle ab-pmjay (keep serving stale + flag), pm-sym, pmsby (see prompt for rules).
3. Rebuild snapshot from servable ∩ audio-ready (~12 schemes — new clips owner-blocked),
   `make render` missing: 0, `make backup`, `make stress` 0/0.

**Step B — 4.3 Door A** (say the scheme's name; new `haqdaar/engine/door_a.py` + offline
top-1 accuracy), with the 5 nits from the 4.2 review as warmup.

**Step C — 4.4 spoken answers** with "if right press 1" confirmation, proven on the sim path.

**Step D — 4.5 fallback wiring** (ear/model into the turn loop; today `server.py` passes
`model=None`), forced-STT-failure test, + live API passes if keys allow.

- **Muse must never hear live callers.** On the Contributor tier Meta may train on what it is
  sent. Live speech needs another provider: Groq Whisper, Sarvam STT, or similar.

**Phase 5: make it solid** (5.1–5.4)
- Covers "anything else" and prefetch, `tools/judge.py`, restart after a crash, and an Indian
  phone provider.

**Phase 6: the 10-call test**
- 10 outside callers, 8 or more PASS, then tag `v1`.

**Owner jobs (all parked in `OWNER-END-TODO.md` for the end)**
- Decisions: voice for new clips, menu length, server location.
- Ears: listen to clips (`make listen-cards L=mr N=10`), 3.7 read of 20 cards.
- Phone: 3 real keypad calls (Twilio trial → one verified number), 3 live voice calls,
  Door A live <20 s check.
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
