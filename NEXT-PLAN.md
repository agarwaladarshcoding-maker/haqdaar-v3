# NEXT-PLAN — how we finish HAQDAAR v1

> **Superseded on 18 Sep 2026 by [PLAN-V2.md](PLAN-V2.md)** (100+ schemes, 3 languages, one phase
> at a time). Kept for its audit notes and the cleanup list in §4.

Written 18 Sep 2026, after a full check of the repo, the brain, WORK.md, PROJECT-UPDATE.md,
the notes in `.agent/`, every git branch, and a real test run.
Plain words. Tick the boxes as we go.

---

## 1 · The short version

- **The goal:** a phone number anyone can call from a basic keypad phone. It asks a few
  questions in Hindi, Marathi or English, then reads out the government schemes that fit them.
  It must never lie, never say "you are eligible", and never hang up on the caller.
- **The test that says we are done:** 10 people from outside the team call it (at least 3 per
  language). A script reads each call's log and marks it pass or fail. **8 of 10 must pass.**
- **Where we are:** about **half the build is done.** The "brain" of the call (questions, filter,
  endings) is built and tested. The scheme data is scraped and cleaned. A phone line works.
  **What is missing is the real voice and the joining-up**: Hindi and Marathi text, the recorded
  voice lines, playing them on the phone, hearing speech, and the final test run.
- **The 15 Sep demo was a fixed script** (always the same path, Hindi and English only). It is on
  its own branch, `demo-15sep`. It proved the phone and the Sarvam voice work, but it is **not** the
  real product. The real product is on `main`.
- **Tests:** `pytest` → **109 passed** (run today in a clean setup).
- **One big problem found today:** iCloud has moved some repo files off the laptop (see §4, item A).
  That is why `make test`, `git log` and `grep` hang. The code itself is fine.

---

## 2 · What the project is, in simple words

A poor family in a village often misses government help they could get. To find a scheme today you
need a smartphone, you need to read English or Hindi, and you need to know the scheme's official
name. HAQDAAR removes all three: **you call a number and talk or press keys.**

How one call goes:

1. **Pick a language** — 1 Hindi, 2 Marathi, 3 English.
2. **Say what you want.** Either name a scheme ("PM Kisan") → it is read back at once.
   Or describe yourself ("I am a farmer") → a few short questions, then 2–4 schemes.
3. **Hear each scheme** — its name and a short summary. Then keys: 1 benefits, 2 how to apply,
   3 documents, 4 who can apply, 9 next scheme.
4. **Anything else?** — search again, or hang up.

Always there: `#` says it again, `*` changes language, `0` means "don't know".

Hard rules (each one is checked by code, not by hope):
- Never say "you are eligible" or "you will get".
- In a "no exact match" ending, say the bad news **before** any scheme name.
- Never name a scheme the caller is blocked from (wrong state, gender or caste group).
- Never make up a sentence during a call. Every line is recorded before the call.
- Never let the AI add a fact the caller did not say.
- Never keep the caller's voice or phone number.

---

## 3 · What is done, part by part

The build plan has **21 steps (0–20)**. Here is each one, checked against the code today.

| Step | What it is | State |
|---|---|---|
| 0 | Repo, Makefile, rules | ✅ done, on `main` |
| 1 | Phone line works (beep, keys, hang-up), Cloudflare tunnel | ✅ done, on `main` |
| 2 | Shapes of data, number settings, test data | ✅ done, on `main` |
| 3 | Filter — drops schemes that don't fit | ✅ done, on `main` |
| 4 | Planner — picks the best next question, widening ladder | ✅ done, on `main` |
| 5 | Endings — what to say at the end, bad news first | ✅ done, on `main` |
| 6 | Call loop + log + terminal call (`make sim`) | ✅ done, on `main` |
| 7 | Scraper — 12 real scheme pages from myscheme.gov.in | ✅ done, on `main` |
| 8 | Clean records — who each scheme is for, with quotes as proof | ✅ done, on `main` |
| 9 | **Translate to Hindi + Marathi, and the 5 safety gates** | ❌ not started. Hindi/Marathi have only name + summary; 4 of 6 sections are empty |
| 10 | **Record every line in the real voice** | ❌ not started (the demo made its own 125 clips, but not these) |
| 11 | Snapshot build + audio pool + corpus loader | 🟡 code written, **never run on real data**. No real snapshot exists. `make pipeline` is an empty stub |
| 12 | **Play lines on the phone, keypad call end to end** → tag `v1-keypad` | 🟡 half. `demo_server.py` did a keypad call with the Mac voice, but the real `mouth.py` / `turn.py` do not exist |
| 13 | Hear speech (Sarvam speech-to-text, live) | ❌ not started (the demo has a rough version) |
| 14 | AI model step (Groq) with the "no made-up facts" guard | ❌ not started. `haqdaar/model/` is empty |
| 15 | Door A — say a scheme name, hear it in < 20 s | ❌ not started |
| 16 | Spoken state + fall back to keys when voice fails → tag `v1-voice` | ❌ not started |
| 17 | "Anything else?" loop + read-back sections | 🟡 mostly in `call.py`; needs the real audio and the prefetch |
| 18 | Judge script — pass/fail from the log | ❌ not started |
| 19 | Hardening — restart on crash, drills, 30-min cold-start call | 🟡 tunnel restart done; the rest not |
| 20 | The 10-call acceptance run → tag `v1` | ❌ not done |

**Count:** 9 steps done, 4 half done, 8 not started.

### Each part, diagnosed

**Engine (`haqdaar/engine/`) — strong.** Filter, planner, endings and call loop are pure, tested
(61 tests), and already handle silence, `#`, `*`, keypad-only mode, widening and read-back menus.
Weak spot: it has only ever run against test data and on the terminal, never on the real snapshot.

**Data (`haqdaar/data/`) — good, but only English is complete.** 12 schemes, every fact backed by a
quote. Missing: the Hindi and Marathi sections (Step 9) and a built snapshot (Step 11).
**Risk:** `data_cache/` is in `.gitignore`, so the scraped and cleaned data exists **only on this
laptop**. One disk problem and it is gone (it costs Groq calls and time to rebuild).

**Audio (`haqdaar/audio/`) — the biggest gap.** The phone codec and the pool code exist. There is
no real recorded audio: `audio/` holds 401 silent test stubs. `mouth.py`, `turn.py` and `ear.py`
are not written.

**Model (`haqdaar/model/`) — empty.** Nothing yet. The Groq key works; notes say use
`reasoning_effort: "low"` and JSON mode, and the daily limit is 1,000 requests.

**Phone / server — works.** Real calls rang, keys arrive on time through the Cloudflare tunnel.
`make call-me` rings your phone with the real backend. The number is a US (+1) Twilio number, so
callers must be able to dial abroad.

**Demo branch (`demo-15sep`) — useful parts to keep.** 4 commits not on `main`. Worth bringing to
`main` later: the tunnel fixes in `tools/tunnel.py` (dead address check), `tools/run_demo.py`
(one command rings you), the slow-down code (voice at 90%), and the lessons on speech-to-text
(pad short words with 1 s of quiet; give Whisper a list of expected words; Sarvam STT can take 9 s).
**Do not copy** the demo's key choices into the real product (the demo used 9 = repeat and
3 = don't know; the product rules say `#` = repeat and `0` = don't know).

**Docs (`haqdaar-v2-brain/`, `source-docs/`) — complete but out of date on dates.** They still say
D-day is 14 Sep. That date has passed. A new date is needed (§6, decision 1).

---

## 4 · Cleanup — what should be removed, and why

I tried to remove these today, but the safety check blocked deleting files without your OK.
**Nothing was deleted.** Run the block below yourself (it moves things to the Trash, so it can be
undone), or tell me "go ahead" and I will do it.

| What | Why it can go |
|---|---|
| `_staging/` (15 files) | Old draft of the docs. Copied into `source-docs/` on 10 Sep. It still has the old ladder rule (category widened), so it can mislead an agent. Kept in git history. |
| 15 old voice clips in `haqdaar/voice_demo_clips/` | Lines from demo v1/v2 whose words changed. The demo uses 125 clips; these 15 are used by nothing. |
| `snapshots/fixtures/utterances.json/` | An empty **folder** with a file name. Made by mistake. |
| `.DS_Store`, `__pycache__/`, `.pytest_cache/` | Junk files the computer makes. Already ignored by git. |

```bash
cd /Users/adarshagarwala/Documents/haqdaar-v2
T=~/.Trash/haqdaar-cleanup-2026-09-18 && mkdir -p $T/clips
mv _staging $T/
mv snapshots/fixtures $T/snapshots-fixtures-stray
for k in 1a4a7b7fcb2a6014fb5f6b13 1c873f5cb5c9ea0f5a4a3a3a 1d5821ce727a29ecfcf04acb \
         54ebc75ac05a4a73dd8fcbde 551c4883322ebf8391e5dedb 5566280f6700e6dbb58ec5c6 \
         5e9c396972e65adb52da71eb 714cfd3c3fb4a4f086b46932 85f8ffd6d8e42a97a8e78625 \
         a6979a6b2e2874244fb3e492 beeb33b2232cf5fbcd4f108c df57f0dce1212f21a3527667 \
         e90815f0286654b5661c443b e92d443f40b46b86a635cf5b fe9e15b9b9ba2490ccb92f0d; do
  mv haqdaar/voice_demo_clips/$k.ulaw $T/clips/
done
git add -A _staging haqdaar/voice_demo_clips
# junk the computer makes (ignored by git, safe to lose)
find . \( -name .DS_Store -o -name __pycache__ -o -name .pytest_cache \) -not -path './.venv/*' -prune -exec rm -rf {} +
```

Or just tell me "go ahead with the cleanup" and I will run it.

**Keep** (they look like clutter but are used): `work-adarsh/` and `work-with-tools/` (WORK.md links
them), `audio/` (test stubs the sim needs), `logs/` (call logs I read after calls),
`haqdaar/demo_server.py` + `demo_voice.py` (the voice demo imports `demo_voice`), `sync_vault.py`.

### A · The iCloud problem (fix this first)

- The repo sits in `~/Documents`, which iCloud syncs. The disk is **90% full** (44 GB free), so
  macOS "Optimize Mac Storage" has pushed **507 files** off the laptop, leaving empty stand-ins.
- Hit: **457 files in `.venv`** (so `make test` hangs forever), **17 files inside `.git`** (so some
  git commands hang), plus junk.
- Your code files are all fine. I proved it: a fresh setup outside iCloud ran **109 tests, all pass**.
- **Fix (pick one):**
  1. **Best:** move the whole repo out of iCloud, e.g. to `~/code/haqdaar-v2`.
  2. Or turn off "Optimize Mac Storage" (System Settings → Apple ID → iCloud → iCloud Drive).
  3. Or at least rebuild the venv in a folder iCloud skips:
     ```bash
     rm -rf .venv && /opt/homebrew/bin/python3.11 -m venv .venv.nosync && ln -s .venv.nosync .venv
     .venv/bin/pip install -e .
     ```
- Also free some disk space. A full disk is a demo risk by itself.
- Stay on **Python 3.11**. The code uses `audioop`, which Python 3.13 removed.

---

## 5 · The plan — four phases

Each box is one thing. Do them in order. Each step still gets its own branch (`step-NN`), a review,
then a merge, as in WORK.md.

### Phase 0 · Fix the ground (about half a day)

- [ ] Fix iCloud (§4 A). Check: `make test` → 109 passed, in under a minute.
- [ ] Run the cleanup (§4).
- [ ] Commit the loose work on `demo-15sep`: `Makefile`, `tools/run_demo.py`, `PROJECT-UPDATE.md`,
      `REFERENCES-FOR-PPT.md`, and the **100 voice clips** not yet in git (without them the demo
      needs Sarvam credits again).
- [ ] Back up the data: commit `data_cache/derived/schemes.jsonl` (the build plan already says the
      snapshot's `schemes.jsonl` must be committed), or copy `data_cache/` somewhere safe.
- [ ] Bring the good demo pieces to `main` in one small branch: `tools/tunnel.py` dead-address fix
      and `tools/run_demo.py` (`make call-me`). Leave the rigged script on its branch.
- [ ] Pick the new dates (§6, decision 1) and write them into `source-docs/`, then
      `python3 sync_vault.py --sync`.
- [ ] Update WORK.md §1 and §6 so they match this file (they stopped on 14 Sep).

### Phase 1 · A real keypad call on the phone → `v1-keypad` (about 3 days)

This is the most important phase. **If time runs out, stop here: a keypad-only call is already a
full, honest product and can pass the test.**

- [ ] **Step 9 · Translate + safety gates.** Write `p3_translate.py` (Sarvam Translate, the 4 empty
      sections + summary into Hindi and Marathi) and `p4_gates.py` (the 5 gates: numbers, ₹ amounts
      and dates must stay the same; no "you are eligible" words; read-back complete).
      **Done when:** `make pipeline-gates` prints a table and at least 6 schemes pass every gate.
- [ ] **Step 10 · Record the lines.** `lines.yaml` with the 46 fixed lines (T23) in 3 languages,
      the answer "chips" (~600), and the scheme sections. Sarvam bulbul:v3 → 8 kHz μ-law. Reuse the
      demo's Sarvam code and its "save to disk, skip if already made" idea.
      **Done when:** `make pipeline-render` says 0 missing. **You listen** to 3 Hindi and 3 Marathi
      lines. Marathi at 8 kHz is the named risk: if a voice sounds bad, change the voice id and
      re-render.
- [ ] **Step 11 · Build the real snapshot.** Run `p6_snapshot.py` on the real data, make
      `make pipeline` run Steps 7–11 in one go.
      **Done when:** `make sim` runs a full call on the **real** 12 schemes, and a broken or missing
      audio file makes loading fail loudly.
- [ ] **Step 12 · Play it on the phone.** Write `audio/mouth.py` (say, repeat, clear, marks) and
      `audio/turn.py` (keys + silence timer). Wire them into `server.py`. Take what worked from
      `demo_server.py` (the fix for the 10-second freeze when a key is pressed mid-line).
      **Done when:** one real call per language, keypad only, reaches a scheme read-back and the
      goodbye line, and each log shows the closing line. **Tag `v1-keypad`.**

### Phase 2 · Voice (about 3 days)

- [ ] **Step 13 · Hear speech.** Live Sarvam speech-to-text with `stream_type="fast"`. A key pressed
      while talking wins. Tell NOISE from SILENCE.
      **First:** re-test running the server in the US (WORK.md §9 28). Live speech needs a fast link.
- [ ] **Step 14 · AI model step.** Groq, JSON only, temperature 0, 2 s time limit, never raises.
      **The span guard:** a value is kept only if its words are really in what the caller said
      ("I am a farmer" must **not** add "low income"). A 429 (rate limit) counts as a failure;
      2 failures → keypad-only. Pick the model with a 30-sentence test and record the speed.
- [ ] **Step 15 · Door A.** Say "PM Kisan" → name heard within 20 s. Match the name in code first,
      then ask the model. 2 matches → pick by key. 3 or more → ask questions instead.
- [ ] **Step 16 · Spoken state + fallbacks.** Ask the state by voice; 2 misses → "state unknown"
      (never a 36-item key menu). Voice broken → keypad-only for the rest of the call.
      **Tag `v1-voice`.**

### Phase 3 · Make it solid (about 2 days)

- [ ] **Step 17 · Finish "anything else?" and sections.** Two searches in one call keep every answer
      except the need. Read-back plays fast even from a cold start.
- [ ] **Step 18 · Judge script.** `python tools/judge.py logs/` → PASS or FAIL per call, with a
      reason, **from the log alone**.
- [ ] **Step 19 · Hardening.** `make run` restarts itself after a crash. Drills: Wi-Fi dies → phone
      hotspot; process dies → next call works. **Cold-start test:** laptop idle 30 min, then call.
      Measure how many callers can be on at once (expected: 1 — say so before judging).
- [ ] `make smoke` prints the checklist for the day (it is an empty stub now).

### Phase 4 · The test run → `v1` (1 day)

- [ ] Check every tester's phone can dial the +1 number (or get the Indian number, decision 3).
- [ ] 10 calls by people outside the team, at least 3 per language, no rehearsal. Make sure the
      7 hard cases each happen at least once: silence, wrong key, key mashing, a scheme we don't have,
      mixed languages, nothing clear, answering a different question.
- [ ] `tools/judge.py` → **8 or more PASS.** Tag `v1`. Copy 2–3 logs to `haqdaar-v2-brain/docs/evidence/`.

**Total:** about 9–10 working days if one step goes in at a time. Phase 1 alone gives a
product that can pass.

---

## 6 · Decisions only you can make

1. **New dates.** D-day (14 Sep) has passed. When is the new 10-call test? I suggest planning
   backward from it: Phase 1 must end at least 4 days before.
2. **Sarvam credits.** Step 9 (translate) and Step 10 (about 1,000 voice clips) need paid credits.
   Credits ran out once on 15 Sep. Top up before Phase 1.
3. **Indian phone number.** The +1 number means testers must dial abroad. Plivo India needs KYC.
   Start it now if you want it — it takes days.
4. **Where the server runs for voice.** Laptop + Cloudflare works for keys. For live speech, a US
   server near Twilio may be needed (WORK.md §9 28). Decide before Step 13.
5. **Repo location.** Move it out of iCloud (§4 A)? I recommend yes.

---

## 7 · Biggest risks, in one line each

- **iCloud + full disk** makes commands hang → fix first (§4 A).
- **Scheme data only on this laptop** → commit or back it up (Phase 0).
- **Sarvam credits run out mid-render** → top up first; the render skips files already made.
- **Marathi voice sounds bad at phone quality** → listen early (Step 10), swap the voice if needed.
- **Groq free limit (1,000 requests/day)** → the pipeline caches everything; the call uses at most
  2 model calls.
- **Speech-to-text is slow (up to 9 s seen)** → keys always work; voice failure drops to keypad.
- **One laptop, no spare** → a dead laptop is a dead demo. Keep it plugged in, lid open.
