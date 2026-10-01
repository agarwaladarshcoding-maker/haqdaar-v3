# HANDOFF — start here (1 Oct 2026)

From now on the owner works like this:
- **Muse Spark 1.3 Contributor** plans each step.
- **Antigravity** writes the code.
- **Claude** checks everything at the end.

This file is the shared base for all three. Read it first, then `AGENTS.md` (the rules), then
`PLAN-V2.md` §2 (design decisions D1–D13, binding) and §3 (the phases).

---

## 1 · Where the code is

- **Folder:** `~/code/haqdaar-v2`. Always work here. The `~/Documents/haqdaar-v2` copy sits in
  iCloud and hangs on big reads. Both copies are on the same branch, but only `~/code` is safe to run.
- **Branch:** `main` (pushed to GitHub, `haqdaar-v3`, in sync). Start every new step on a new
  branch from here, for example `git switch -c step-4.1-ear`.
- **Merged:** `main` holds Phase 2 + Phase 3, including the 3.7 audit tooling.
  Tagging `v1-keypad` waits for the owner's audit verdicts and 3 real calls.
- **Python:** always `.venv/bin/python`, which is 3.11. The system `python3` is 3.14 and has no `audioop`.
- **Keys:** they live in `~/code/haqdaar-v2/.env` and are never committed. It holds MUSE_API_KEY,
  SARVAM_API_KEY, TWILIO_*, and HF_TOKEN. Never print a key or paste one into chat.

## 2 · How to check that nothing broke

```
cd ~/code/haqdaar-v2
.venv/bin/python -m pytest -q          # 314 pass on 1 Oct
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
    - It has a **hard ₹60 cap**; spent so far is ₹3.93, logged in `data_cache/reports/muse_usage.jsonl`.
    - The facet step (`make pipeline-extract`) was stopped on purpose near the end.
    - Everything already answered is cached, so a re-run only pays for what is left.
  - **3.8** The server pins only the fixed lines (6.7 MB), and scheme audio loads when it is read.
  - **3.6** `make stress` runs 1,000 callers: 0 crashes, 0 truth failures.
- **3.7 tooling** `tools/cards_sheet.py` (seeded 20-sample), `audit_3_7.md`
  template, `listen.py` cards mode. Reading, listening and verdicts are the owner's.

## 4 · What is left, in order

**Phase 3 (30 schemes)**
1. **3.4 finish.**
   - Run `make pipeline-extract`, then `make pipeline-cards`, both on Muse.
   - Check that the quarantine is under 15%.
   - Check that the occupation list has **at most 9** values; a keypad box with more than 9 is dropped.
   - Add Hindi and Marathi labels in `vocab.LABELS` for every new occupation.
2. **3.5 translate and check.**
   - `make pipeline-translate` (Muse; it must use digits 0–9), then `make pipeline-gates`.
   - Then `make snapshot`.
   - **Not yet:** voice clips for the 18 new schemes. The owner is choosing the voice:
     - the free local model AI4Bharat Indic Parler-TTS (samples in `logs/voice-trial/`);
     - or Bhashini (government, free).
   - Until then, the snapshot must be built from the schemes that have audio. `Corpus.load`
     refuses a snapshot with a missing clip, and that rule stays.
3. **3.7 check (tooling done, owner pending).** Read 20 cards against their source pages, and the owner listens.
4. **Open owner decision:** the keypad menus are long.
   - Topic: 44 s in Hindi.
   - Age and occupation: about 30 s each.
   - Choices: say fewer options, speak faster, or leave them as they are.

**Phase 4, voice (`PLAN-V2.md` §3, steps 4.1–4.5)**
- Build speech-to-text, the model that understands answers, "Door A" (say the scheme's name),
  spoken answers with a confirmation, and a fall back to keypad if voice breaks.
- **Muse must never hear live callers.** On the Contributor tier Meta may train on what it is
  sent. Live speech needs another provider: Groq Whisper, Sarvam STT, or similar.

**Phase 5: make it solid** (5.1–5.4)
- Covers "anything else" and prefetch, `tools/judge.py`, restart after a crash, and an Indian
  phone provider.

**Phase 6: the 10-call test**
- 10 outside callers, 8 or more PASS, then tag `v1`.

**Owner jobs still open**
- 3 real keypad calls. Twilio is a trial account, so it can call only the one verified number.
- Listen to the clips (`make listen-cards L=mr N=10`).
- Choose the voice for new clips.
- Decide the menu length.
- OK to tag `v1-keypad` (merges done 1 Oct).

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
