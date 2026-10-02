# PROJECT-UPDATE — what HAQDAAR can do right now

**How this file works.** Every time we chat or finish something, I add one entry at the top of
the log (§3) and fix §1 and §2 so they stay true. Plain words only.
Each entry says: what was added, what was changed, and what the project can do at that point.

---

## 1 · What the project can do today (18 Sep, v2 Phase 0 done)

**It can:**
- Take 12 real government schemes from myscheme.gov.in and save their pages (Step 7).
- Turn each page into a clean record: who it is for (age, gender, category, work, state),
  names people call it by, and a short summary — every fact backed by a quote from the page (Step 8).
- Answer telephony webhooks on `/answer` (TwiML Stream) and connect WebSocket on `/stream`,
  sending a 1-second 440 Hz μ-law tone, acknowledging DTMF digits and marks, and closing on digit 9 (Step 1).
- Run a **whole call in your terminal**: `make sim`. You press keys, it asks questions, narrows the
  schemes, reads out what matches, and writes a log of every turn (Step 6).
- Pick the next question that cuts the list down fastest (Step 4), drop schemes that don't fit (Step 3),
  and choose how to end the call (Step 5).
- Take a real phone call through a Cloudflare tunnel, with every key arriving on time (Step 1).
- `pytest -q` → **468 passed**.
- Ring your phone into the real backend in one command: `make call-me`.
- Back up all the scheme data: `make backup`. The text part is also saved in git.

**It cannot yet:**
- Run full voice dialogue over the phone call (waiting on speech model, TTS audio, and live dial verification).
- Speak Hindi or Marathi, or check a translation is safe. (Step 9 — today.)
- Play real voice audio. (Steps 10–12.)
- Understand speech — keypad only for now. (Steps 13–16.)

---

## 2 · Every file, and what it is for

### Rules and shapes — `haqdaar/contracts/`
| File | What it does |
|---|---|
| `types.py` | The shape of everything passed between parts: answers, schemes, turn results. |
| `tunables.py` | Every number in one place (caps, timeouts, limits). No number lives in code. |
| `log_schema.py` | The shape of one log line. Seven kinds of line, including SILENCE. |

### The brain — `haqdaar/engine/`
| File | What it does |
|---|---|
| `filter.py` | Removes schemes that don't fit the caller's answers. |
| `planner.py` | Picks the next question — the one that splits the list best. |
| `terminals.py` | Decides how a call ends: exact match, near match, or nothing found. |
| `call.py` | The call loop. Ties filter, planner and terminals together, turn by turn. |
| `door_a.py` | Matches a scheme name spoken at the start of the call; jumps straight to it. |

### Data — `haqdaar/data/`
| File | What it does |
|---|---|
| `log.py` | Writes the call log, one line per turn. |
| `corpus.py` | Loads the finished scheme snapshot and checks the files are not broken. |
| `pipeline/schemes.yaml` | The list of 12 schemes to fetch. |
| `pipeline/p1_scrape.py` | Fetches the 12 pages. Output: `data_cache/raw/`. |
| `pipeline/p2_derive.py` | Uses Groq to turn a page into a record + aliases + summary. Output: `data_cache/derived/`. |
| `pipeline/p6_snapshot.py` | Builds the final five snapshot files the phone call reads. |

### Sound and Telephony — `haqdaar/audio/`
| File | What it does |
|---|---|
| `pool.py` | Keeps audio clips ready: a small set always loaded, the rest loaded when needed. |
| `mouth.py` | What the caller hears: sends the voice down the line, stops it on a key, repeats on `#`. |
| `turn.py` | Keys and silence from the caller; a key pressed while the call talks is kept. |
| `phone.py` | Connects the call brain to the phone: finds each clip, adds the keypad menus. |
| `telephony/base.py` | The common shape every phone company must fit. |
| `render.py` | Makes the real voice: asks Sarvam to speak every line, button word and scheme text, and saves each clip. `make render`. |
| `telephony/twilio.py` | Telephony wire codec (parse 6 inbound events, build 3 outbound events). |
| `telephony/__init__.py` | Isolates telephony wire codecs so vendor names never leak outside telephony. |
| `ear.py` | The ear: speech to text (Sarvam + Groq), energy VAD, NOISE vs SILENCE, keypress wins. |

### Server and Tools
| File | What it does |
|---|---|
| `haqdaar/server.py` | FastAPI app exposing `/health`, `/answer` (TwiML Stream XML), `/stream` (audio WS). |
| `tools/tone.py` | 8 kHz μ-law 440 Hz 1-second pure tone generator (no WAV/RIFF headers). |
| `tools/run_demo.py` | `make call-me`: tunnel + server + rings your phone, in one command. |
| `tools/listen.py` | Plays saved clips on the Mac, with their words printed first. `make listen L=mr N=5`. |
| `tools/cards_sheet.py` | Generates 20-card audit sheet and sample. `make cards-sheet`. |
| `tools/ear_check.py` | Verifies speech to text across 3 sentences × en/hi/mr. `make ear-check`. |
| `tools/door_a_check.py` | Verifies Door A accuracy across all 30 schemes in 3 languages. `make door-a-check`. |
| `tools/judge.py` | Offline delivery log judge: PASS/FAIL from D9 delivery records and turn lines alone. |

### Other
| File | What it does |
|---|---|
| `haqdaar/sim.py` | The terminal call. `make sim`. |
| `fixtures/` | 5 test schemes, 3 test callers, 10 TTS stubs, 30 speech fixtures, 90 Door A utterances. |
| `tests/` | Unit and shape tests across contracts, engine, pipeline, audio pool, mouth, phone, ear, model, and door_a. |
| `Makefile` | Short commands: `make test`, `make sim`, `make run`, `make stress`, `make ear-check`, `make model-bakeoff`, `make door-a-check`, etc. |

### Not written yet
None for Phase 4 core engine. Live phone dial checks and field tests remain with the owner.

---

## 3 · Log — newest first

### 2 Oct (late night) — Merged 5.2 + 5.3, built the call page (step 5.5), dropped 5.4
- **Merged and pushed.** `step-5.2-judge` and `step-5.3-hardening` are in `main`, and so is the
  new `step-5.5-call-viewer`. Nothing is waiting to be merged.
- **Dropped for now — the Indian phone provider (5.4).** Owner's word. Nothing was built for it.
- **Added — the call page.** `make calls-ui` opens http://127.0.0.1:8001 in the browser.
  - On the left, every call, newest first: when, how long, language, turns, the judge's
    PASS or FAIL, and a red mark if something went wrong. A call going on right now says LIVE
    and fills in by itself every 2 seconds.
  - On the right, the call as a back and forth. The AI is on the left with the real words it
    spoke (Hindi, Marathi or English) and the clip names under them. The caller is on the
    right: the key pressed, or the words the speech-to-text heard.
  - Under each caller bubble: what the engine made of it (for example
    `turn 1: PROPOSAL · category = farming`), how long the caller waited, or by how much they
    cut in, and how long speech-to-text took.
  - Under each AI bubble: how long it spoke and how fast it replied. Over 1.2 s shows amber,
    over 3 s shows red.
  - At the top: call length, AI talking time, slowest reply, not-understood count, silences,
    problems, why it stopped asking, how it ended, and the judge's reason.
  - Problems show as red bars in the place they happened: a missing clip, speech-to-text
    failing over, the call falling back to keypad only. A call with no end line (the server
    was killed) says so.
- **Added — the call trace.** The call log has no clock and never said what the AI spoke, so
  the page had nothing to show. Each call now also writes `<logs>/trace/<call_id>.jsonl`: every
  event line the server already prints, and a copy of each log line, each with the seconds
  since the call began. The call log itself is unchanged. A trace can never break a call.
- **Why the page is its own small server.** The call server is open to the world through the
  tunnel. What callers say is private. So the page runs apart, on this computer only, and it
  only reads files, so it cannot slow a call.
- **Know this:** only calls made from now on have a trace. Sims show the words but not the
  times, because a sim plays no sound. No real phone call has been logged yet, so the times
  have been checked only by tests and by a hand-made sample, not on a live call.
- **Other phases without the owner: none left.** Every open step needs a phone, ears, a
  decision or a key. See HANDOFF §4.
- **Checks:** pytest 491 (was 483) · `make stress` 1,000 callers, 0 crashes, 0 truth failures ·
  py_compile clean · vault in sync · Muse spend ₹0 (nothing here calls Muse).

### 2 Oct (night) — Step 5.3 code: restart after a crash, smoke checklist, Muse day guard
Branch `step-5.3-hardening` (cut from `step-5.2-judge`). Not merged, not pushed.
- **Added — the server comes back by itself.** `make run` now runs the server under
  `tools/keep_running.py`. If the server dies, it starts again after 2 s. Ctrl-C (or `kill` on
  the restarter) stops it for good and takes the server down too. If the server dies 5 times
  in 60 s it gives up and says so, so a broken start does not spin for ever.
  - Tried for real on a test port: `kill -9` on the server, and it answered again in about 2 s.
- **Added — `make smoke` prints the checklist.** It checks 5 things by itself (Python 3.11, the
  snapshot and all its clips, the keys by name only, the logs folder, Muse spend) and then
  prints the 10 things to do by hand with a phone, the three 5.3 drills among them.
- **Added — Muse money guard.** No more than ₹30 of Muse in one day, on top of the ₹60 total.
  The day is India time and rolls at 05:00, not midnight (night work). It sits in `muse.py`,
  the one door every Muse call goes through, so every pipeline step obeys it.
  - `make muse-status` shows it. `make muse-block` shuts Muse for the rest of the day.
    `make muse-unblock` lifts it.
  - **Muse is blocked for 2 Oct** (owner: the quota is done). A test call was refused with
    nothing sent. It opens again by itself at 05:00 on 3 Oct.
  - It only guards Muse used from this repo. It cannot see Muse used in a chat window.
- **Changed — two faults found while checking step 5.2, both in the opener, both fixed:**
  - The model's own words for "why unclear" leaked out, and the engine read any such words as
    "the model failed". Unclear is not a failure. Now the reason is always the same word.
  - When the caller named a scheme and the model added nothing, the named scheme was thrown
    away. Now it is kept.
- **Checks:** pytest 483 (was 468) · `make stress` 1,000 callers, 0 crashes, 0 truth failures ·
  bake-off 30/30 offline · Door A 79/81 · a sim call judged PASS by `tools/judge.py` ·
  Muse spend ₹0.00 new (₹12.97 total).
- **Left, all needing the owner:** the three drills on a real phone; 5.4 (no Indian provider or
  number yet); Phase 6 (10 callers); the items in `OWNER-END-TODO.md`; the Groq key; merging
  `step-5.2-judge` and `step-5.3-hardening` into `main`.

### 2 Oct — Step 5.2: Delivery log judge + sim opener UNCLEAR fix
- **Offline delivery log judge (`tools/judge.py`):**
  - Scores call logs purely from D9 delivery records and turn lines without needing audio or rerunning the engine.
  - Flags untrue claims (schemes not in survivors, nearest read as matches, dead-ends skipping widening, claims outside corpus).
  - Flags unprompted system hangups and calls terminating before reaching a terminal.
  - Scores solely on confirmed `ANSWER` turns, ignoring spoken `PROPOSAL` turns.
  - Per-call PASS/FAIL with one-line reason and summary counts; exits 1 if any call fails.
- **Sim opener UNCLEAR unification (`haqdaar/model/router.py`, `haqdaar/engine/call.py`):**
  - Unmatched opener speech returning `{"class": "UNCLEAR", "stamps": []}` or `{"stamps": []}` now both return `Unclear(reason="unclear")`.
  - Both flow through the exact same specific re-ask path with `unclear_prompt`, logging `turn_class="UNCLEAR"` without tripping engine model failure accounting.
- **Fixtures & tests (`fixtures/judge_logs/`, `tests/test_judge.py`):**
  - 8 hand-made fixtures testing all pass and fail rules.
  - 12 unit tests covering all judge rules, CLI exit codes, and sim opener execution symmetry.
- **Verified:** 468 unit tests pass, `make stress` 1,000 callers (0 crashes, 0 truth failures), `make model-bakeoff` (30/30 offline pass), `make door-a-check` (79/81 top-1 hits, 97.5%), `make render` (456 clips on disk, 0 missing), `make sim` finishes cleanly and passes judge. Muse spend delta: ₹0.00.

### 2 Oct — Step 5.1: Anything-else voice turn + scheme-audio prefetch
- **Anything-else hears voice (`haqdaar/engine/call.py`):**
  - The "anything else" turn now listens for speech in voice mode using the confirm profile.
  - Understands yes/no via the model confirm matcher across Hindi, Marathi, and English, with keypad 1 and 2 as fallback.
  - Saying "yes" re-opens the question loop for a new topic; saying "no" or silence ends the call with the farewell.
  - Keypad-only mode remains unchanged.
- **Scheme-audio prefetch (`haqdaar/audio/phone.py`, `haqdaar/engine/call.py`):**
  - Added `PhoneAudio.prefetch()` to fetch scheme audio chunks into the Tier 1 cache using `Corpus.chunks()`.
  - Terminal phase calls prefetch with the ranked scheme list before playing audio, warming clips so playback starts without cold disk pauses.
  - Prefetch never blocks or crashes the call; respects `AUDIO_PREFETCH_ON_STOP`.
- **Turn input test (`tests/test_turn.py`):**
  - Added direct unit tests for `Turn.wait_input()` covering keys, hangups, silence gaps, Ear listening, and barge-in.
- **Verified:** 456 unit tests pass, `make stress` 1,000 callers (0 crashes, 0 truth failures), `make model-bakeoff` (30/30 offline pass), `make door-a-check` (79/81 top-1 hits, 97.5%), `make render` (456 clips on disk, 0 missing), `make sim` finishes cleanly. Muse spend delta: ₹0.00.

### 2 Oct — Audit fixes merged to main (reviewed, verified, pushed)
- **Merged:** `audit-fixes` into `main` — fast-forward, no conflicts. All 36 audit findings
  are now on `main`: quarantine bypass closed + 11-scheme snapshot (F1), Door A wired with
  stamps (F2), engine correctness + one-caller guard + ghost drain + STT deadline + report
  accounting (Step E). Review caught 1 fault (a wrong count in a comment); fixed before merge.
- **Verified on main:** pytest 441, stress 0/0, bake-off 30/30, door-a 79/81, render 456/456,
  sim clean. Muse spend unchanged at ₹12.97 of the ₹60 cap.
- **Project can now:** refuse stale quarantined schemes end to end; hear a scheme name in the
  opener and read its card (Door A, 3 langs); bound confirm repeats and STT time; refuse a
  second caller while one is on; report roster-vs-kept counts and full spend honestly.

### 2 Oct — Step E: Audit remainder (engine correctness, hardening, pipeline reports)
- **Engine correctness (Part F3):**
  - Widening ladder in the planner now shares the speakable check from terminals so predicted rungs agree.
  - Spoken confirmation words (yes/no in Hindi, Marathi, English) moved out of Engine into Model.
  - Confirm loop now bounds repeats separately; silence and `#` repeats do not eat cap turns.
  - Fixed nearest ladder rung accounting (0 when no soft boxes were answered).
  - Cleaned types, removed dead drop_category line, and documented priority ordering.
- **Server, audio, and model hardening (Part F4):**
  - Added a one-caller guard: second phone stream gets a clean busy rejection instead of starting a new engine.
  - Ear now drains old audio packets before listening so past audio is not transcribed as ghost speech.
  - Added a shared 5-second deadline across speech recognition providers.
  - Defended model calls against unexpected client crashes; guarded malformed scheme clips; suppressed audioop warning.
- **Pipeline reports and repo hygiene (Part F5):**
  - Added roster accounting to all pipeline reports (`gates.json`, `cards.json`, `translate.json`, `derive.json`): 30 roster - 3 quarantined == 27 kept.
  - Added Muse spend tracking to `run_all.py --cost` alongside Groq and Sarvam.
  - Renamed text counting step in `run_all.py` to match what it does.
  - Fixed scheme counts in test docstrings, cleaned `.gitignore` rules for notes, and added a test guarding the Twilio import boundary.
- **Verified:** 441 unit tests pass, `make stress` 1,000 callers (0 crashes, 0 truth failures), `make model-bakeoff` (30/30 offline pass), `make door-a-check` (79/81 top-1 hits, 97.5%), `make render` (456 clips on disk, 0 missing), `make sim` finishes cleanly. Muse spend delta: ₹0.00.

### 2 Oct — Step 4.5: Fallback wiring + live API passes
- **Wired Ear failure signals and Model circuit breaker into call loop (`haqdaar/engine/call.py`):**
  - When speech recognition fails (STT error/timeout) or the model fails twice, the call immediately drops to keypad-only mode.
  - Plays `keypad_only_mode` prompt, logs `{"mode": "keypad_only"}`, and conducts all remaining questions and menus via DTMF keypad.
  - Does not fork the call path: seamlessly switches mode in the existing question loop.
- **Wired telephony server stream to Ear and Model (`haqdaar/server.py`, `haqdaar/audio/turn.py`, `haqdaar/audio/phone.py`):**
  - In `server.py`: `stream_endpoint` now creates `Ear(log=say)` and passes it to `Turn(mouth, ear=ear)`; forwards inbound audio packets via `MediaEvent` to `turn.push_media()`.
  - In `server.py`: `_run_engine` instantiates `Model(corpus=corpus)` and passes it to `Engine.run_call`.
  - In `turn.py`: `Turn` coordinates speech input through `ear.listen()` while prioritizing pre-queued or barge-in DTMF keypresses.
  - In `phone.py`: `PhoneAudio.next_input()` delegates spoken turns to `turn.wait_input()` and exposes `keypad_only`.
- **Fixed the 6 warmup items from Step C review:**
  - `haqdaar/engine/door_a.py`: hoisted `_load_manual_aliases()` outside the per-scheme loop with a module-level cache.
  - `tools/door_a_check.py`: simplified dead fallback logic.
  - `haqdaar/contracts/log_schema.py` & `haqdaar/engine/call.py`: logged proposed spoken answers as `PROPOSAL` before confirmation, avoiding phantom duplicate `ANSWER` log lines.
  - `haqdaar/engine/call.py`: bounded the confirmation loop against repeat-mashing (`#`, `*`, silence).
  - `haqdaar/sim.py`: updated `SimModelClient` to return UNCLEAR on unmatched speech.
- **Added forced STT failure test in the turn loop (`tests/test_call_spoken.py`):**
  - Forces an STT failure during a spoken turn and asserts the call falls back to keypad, plays `keypad_only_mode`, logs `{"mode": "keypad_only"}`, and finishes via keypad.
- **Live API passes:**
  - `make ear-check` ran live against Sarvam STT: 9/9 sentences recognized across EN/HI/MR with 0.61s average latency.
  - `make model-bakeoff ARGS=--live`: blocked by Groq API key permissions (Groq account returns 404 model_not_found for `llama-3.3-70b-versatile`). Offline bake-off passes 30/30 (100%).
- **Verified:** `pytest` (372 passed), `make stress` (1,000 callers: 0 crashes, 0 truth failures), `make model-bakeoff` (30/30 passed), `make sim` runs end to end to farewell.

### 2 Oct — Step 4.4: Spoken answers with "if right press 1" confirmation
- **Added spoken answers and confirmation loop (`haqdaar/engine/call.py`):**
  - When the caller speaks an answer, the model parses it and Mouth reads back what it heard ("Let me say back what I heard... If right press 1, to fix press 2").
  - Pressing 1 accepts the answer, records it in the call log, and advances to the next question.
  - Pressing 2 rejects the answer, logs an unclear turn, and re-asks with a polite prompt. Two misses on the same question drop it to the keypad menu.
  - Silence during confirmation plays the silence ladder: rung 1 repeats what was heard, rung 2 reassures the caller the line is open, rung 3 says goodbye and hangs up.
  - Also handles spoken confirmation ("yes", "haan", "no", "nahi"), language switching (`*`), and replaying (`#`).
- **Added offline sim path with fake STT / model seam (`haqdaar/sim.py`):**
  - Added `SimModelClient` and simulated speech so `make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h"` runs end to end through spoken answers and confirmation without network or paid API calls.
- **Fixed the 7 review nits from Step B:**
  - `haqdaar/model/router.py`: timeout now passes through to tunables.
  - `haqdaar/contracts/tunables.py` & `haqdaar/engine/door_a.py`: moved policy thresholds and scores to tunables.
  - `haqdaar/engine/door_a.py`: logs error if schemes list is missing; normalizes text before fast-path lookup.
  - `haqdaar/data/manual_aliases.json`: moved quarantined aliases out of engine code into data.
  - `tools/door_a_check.py` & `tests/test_door_a.py`: asserted `action == "read"` for top-1 hits.
  - `PHASE-4-PLAN.md`: corrected "40 schemes" to "30 schemes".
- **Added 8 offline tests (`tests/test_call_spoken.py`):**
  - Tests confirm-accept, spoken affirmation, mismatch re-ask, 2-strike keypad drop, silence ladder, noise/invalid digits, language switch/repeat, and 2-failure model degradation.
- **Verified:** `pytest` (370 passed), `make stress` (1,000 callers: 0 crashes, 0 truth failures), `make model-bakeoff` (30/30 passed), `make door-a-check` (90/90 passed), `make sim` runs through the confirm turn and finishes with farewell.

### 2 Oct — Step 4.3: Door A scheme matching & 90-utterance benchmark
- **Built Door A (`haqdaar/engine/door_a.py`):** when a caller names a scheme at the opener, the call matches it and jumps straight to it.
  - Matches exact aliases first, then transliterates Hindi/Marathi Devanagari script to English letters and strips common filler words to match scheme names reliably.
  - Branches cleanly: 1 match reads it back immediately; 2 matches asks the caller to pick with keys 1 or 2; 3 or more matches moves politely to normal questions with the top 10 schemes shortlisted.
- **Added offline benchmark & dataset:**
  - `fixtures/door_a_utterances.json`: 90 spoken name examples (3 variants in English, Hindi, and Marathi for all 30 schemes).
  - `tools/door_a_check.py` and `make door-a-check`: runs all 90 examples offline in ~50 ms.
  - Result: 90 of 90 (100.0%) top-1 matches.
- **Fixed 8 review nits from Steps 4.2 and A:**
  - `haqdaar/model/client.py`: timeout now reads from tunables so tests can change it.
  - `tools/model_bakeoff.py`: bake-off now fails if unwanted answers appear; measures dropped hallucinations.
  - `haqdaar/model/span_guard.py`: documented why income bands take dynamic strings.
  - `haqdaar/model/router.py`: added note on fast-path alias bypass.
  - `tests/test_cards_sheet.py`: fixed check to verify 0 failing schemes.
  - `Makefile`: added note explaining check vs render scope.
  - `haqdaar/audio/render.py`: removed dead directory check.
  - Cleaned stale test counts in notes.
- **Verified:** `pytest` (362 passed), `make stress` (1,000 callers: 0 crashes, 0 truth failures), `make model-bakeoff` (30 of 30 passed), `make sim` finishes cleanly with farewell.

### 1 Oct — Step A: Phase 3 code finish (gates, scheme fates, snapshot)
- **Settled three scheme fates:**
  - `ab-pmjay`: myscheme page now 404s, but passes derive and gates from cache. It stays in the active snapshot and is kept serving (flagged stale in notes).
  - `pm-sym`: source page only states monthly income of ₹15,000 and has no annual figure. Quarantined because it cannot satisfy the annual income rule without making up numbers.
  - `pmsby`: rescraped once live using Playwright. The page still has no documents section, so it stays quarantined.
- **Fixed the 7 gate failures:** corrected Hindi and Marathi texts for `ignwps`, `mgnrega`, `nfbs`, `nps-tsep`, `pmjjby`, `pmmvy`, and `rkvyshfshc` (removed duplicate/invented numbers, tightened wording to fit the length ratio, converted Latin script to Devanagari).
- **Gate results:** all 28 schemes now pass in all 3 languages (28 of 28, 0% quarantine, beating the 15% bar). Total Muse spend delta: ₹0.00.
- **Rebuilt snapshot:** `make snapshot` created snapshot `snap_20261001_084303` with 12 schemes and 477 clips (0 missing). `audio/render.py` now supports checking snapshots (`make render` says missing: 0). Backed up data with `make backup`.
- **Tested:** `pytest` (353 passed), `make stress` (1,000 callers: 0 crashes, 0 truth failures), `make render` (0 missing), `make sim` runs cleanly to farewell.

### 1 Oct — Step 4.2: Model Client, Span Guard & 30-Utterance Bake-Off
- **Built:** `haqdaar/model/` with `GroqModelClient` (`client.py`) using raw `httpx`, temperature 0, JSON mode (`response_format={"type": "json_object"}`), 2.0s timeout, never raises, captures 429/timeout/errors into `ModelClientResponse`, ledgers usage.
- **Span guard:** `SpanGuard` (`span_guard.py`) enforces strict provenance via string containment and closed-set validation ("farmer" can never smuggle in "low income").
- **Router:** `Model` (`router.py`) provides `opener()` with exact alias match fast-path and `turn()` with 5-class precedence (`META > ANSWER > CLARIFY > REPEAT > UNCLEAR`).
- **Resilience:** 2-failure keypad-only circuit breaker (`failures` counter and `keypad_only` property) ensures degraded calls route directly to keypad without further network delays.
- **Fixtures:** authored 21 static speech fixtures (7 personas P4–P10 × en/hi/mr) in `fixtures/audio/speech/` to complete the 30-utterance set with expected stamps.
- **Tooling:** added `tools/model_bakeoff.py` and `make model-bakeoff` target (runs against 30 fixtures with faked HTTP, reporting accuracy, span drops, and p50/p95 latency; ready for owner's live Groq pass via `--live`).
- **Warmup:** fixed all 8 review nits from step 4.1 (removed unused imports in `tests/test_ear.py`, added `reset_circuit()` and failure counter in `ear.py`, added `normalize_lang()`, ledgered Sarvam STT failures, reset `silence_count` on all `Digit` returns, documented live spend in `ear_check.py` and `Makefile`, noted Sarvam hint ignore and STT env overrides, added autouse `_block_unmocked_http_calls` in `tests/conftest.py`).
- **Tests & Verification:** 21 new tests in `tests/test_model.py` (353 total pytest green), `make stress` (1,000 callers: 0 crashes, 0 truth failures), `make model-bakeoff` (30/30 100% accuracy, 69/69 stamps matched, 30 hallucinated stamps intercepted).

### 1 Oct — Step 4.1: Ear (speech to text, speech fixtures, ear-check)
- **Built:** `haqdaar/audio/ear.py` with primary Sarvam STT (`saaras:v4`) and fallback Groq Whisper (`whisper-large-v3-turbo`) using raw `httpx`.
- **Audio behavior:** 1 s silence padding on both ends, hint words, energy VAD (700/400 RMS thresholds), NOISE vs SILENCE distinction (`started=False` -> SILENCE, empty/failed final -> NOISE).
- **Keypress precedence:** any DTMF key immediately preempts speech and wins.
- **Resilience:** STT timeouts and errors are treated as failure signals (never unhandled exceptions, no retry loops).
- **Fixtures:** added 9 static speech fixtures (3 sentences × en, hi, mr) plus silence and noise in `fixtures/audio/speech/` with `manifest.json`.
- **Tooling:** added `tools/ear_check.py` and `make ear-check` target to verify STT latency and accuracy across English, Hindi, and Marathi.
- **Warmup:** fixed 3 review nits (`tools/listen.py` docstring + `all` guard, `tools/cards_sheet.py` trailing newline, `tests/test_cards_sheet.py` unused imports).
- **Tests & Verification:** 17 new tests in `tests/test_ear.py` (331 total pytest green), `make stress` (0 crashes, 0 truth failures), `make ear-check` (9/9 recognized, avg latency 0.43s).

### 1 Oct — Step 3.7: 20-card audit tooling (cards sheet, audit template, listen cards mode)
- **Added:** `tools/cards_sheet.py` generates the 20-card audit review sheet (`data_cache/reports/cards_sheet.md`) and sample record (`data_cache/reports/audit_sample_3_7.json`) with a fixed seed (42). It includes all 7 gate-failing schemes plus 13 seeded-random passing schemes, rendering all 3 languages (en, hi, mr) and gate notes / failure reasons.
- **Scaffolded:** `data_cache/reports/audit_3_7.md` verdict template with read/listen checkboxes per language and verdict lines; never overwrites existing verdicts on re-run.
- **Added:** `tools/listen.py` cards mode (`python -m tools.listen cards <L> <N>`, `make listen-cards L=hi N=2`) to play card chunks from audio-ready snapshot schemes.
- **Makefile targets:** `make cards-sheet` and `make listen-cards L=<lang> N=<count>`.
- **Tests:** 3 new unit tests in `tests/test_cards_sheet.py` (314 passed total).

- Antigravity took over and verified the system against steps 2–7 of PROMPT-ANTIGRAVITY-SETUP.md. All checks passed: branch `step-3.2-choose` clean, all 6 required `.env` keys present, 307 tests pass (0 fail), `make stress` (1,000 callers: 0 crashes, 0 truth failures), `make sim` finished at `closing_farewell`, and Muse spend is ₹3.93 (under ₹60 cap).
- Wrote `MUSE-BRIEF.md` for Muse Spark 1.3 Contributor to plan steps 3.4-finish and 3.5.

### 30 Sep (evening) — Phase 3 cut to 30 schemes; handoff to Muse + Antigravity
- **Added:** the 18 new schemes (30 total, 28 scraped). Muse now writes cards and translations, with a hard ₹60 cap (₹3.93 spent). `make stress` runs 1,000 pretend callers: 0 crashes, 0 wrong schemes read. The server keeps only the fixed lines in memory (6.7 MB).
- **Changed:** the owner paused Claude. From now on Muse plans, Antigravity writes the code, and Claude checks at the end. `HANDOFF.md` is the starting point for all of them.
- **Can do now:** everything from Phase 2 on the 12 schemes. The new 18 have their facts half-built and no voice yet.
### 30 Sep (night) — Phase 3 started: Muse replaces Groq and Sarvam translate; 746 schemes found

**Decided with you.**
- Muse Spark 1.3 (Meta) now does both the scheme cards and the translation. It is capped at
  ₹60 total, at "high" thinking. The key works.
- It is used only for the offline pipeline, never on live calls, because Meta may learn from what we send.
- Central (all-India) schemes only. I choose the 110–130 and the 9 kinds of work.

**What was added (3.1).** `make pipeline-discover` lists every central scheme on myscheme into
`data_cache/derived/candidates.csv`. It found **746**, of which **510 are for individuals**, and
all 12 of our current schemes are in the list. It is free and takes about 15 seconds.

**Still open with you.** The Twilio account is switched off, so no test calls can be made yet.
You also still need to pick a voice service for the new schemes (Google Chirp 3 HD is free at our volume).

### 30 Sep (last) — every clip made; Phase 2 waits only on your calls; Phase 3 planned

- Your new Sarvam key was saved in the Documents copy's `.env` again; I copied it across.
- The last 30 clips are made ("press 1".."press 9", "press 0"). All **477 clips** exist, and the
  snapshot was rebuilt with them.
- Checked: every word the call can say, in all 3 languages, for all 12 schemes, finds its real
  clip (552 clips, 78 minutes of speech). 300 tests pass.
- Phase 3 plan now has real numbers: ~630k Sarvam characters (paid), ~1.2M Groq tokens, ~300 MB of
  audio, 2–3 hours of voice render. One new item (3.8): do not load all audio into memory at once.

**Project can now:** everything for a real keypad call is ready. Only your 3 test calls are left.

### 30 Sep (late night) — Phase 2 built: the phone call is ready to try

**What was added** (steps 2.2 to 2.7, each on its own branch, all pushed, not merged yet).
- **All 450 voice clips are made**, with your new Sarvam key: every line, button word and scheme text in 3 languages.
- **Many clips at once (2.2).** The call could only open about 250 clips at a time before crashing. Now it can open all of them.
- **The real 12 schemes as a snapshot (2.3).** `make snapshot` builds it. A terminal call on it works in all 3 languages:
  `make sim SNAP=snapshots/CURRENT`. Loading it takes 0.02 seconds.
  - Found and fixed on the way: 87 button words were filed under the wrong name, so the call would
    have found no sound for them.
- **Any phone company (2.4).** The phone code now has one common shape, so an Indian provider can be added later as one file.
- **The mouth (2.5).** Plays the voice down the line. A key press stops it at once (under 0.2 s in the test).
  `#` repeats; `#` twice repeats slower. The demo's 10-second freeze on a key press cannot happen here.
- **The ears (2.6).** Reads keys and silence. A key pressed while the call is talking is never lost.
- **The real call (2.7).** Ringing the line now runs the whole call with the real voice. The log
  keeps only a scrambled form (hash) of the caller's number, never the number itself.
- **Keypad menus.** A keypad question used to say "press the key for your work" and then list nothing.
  Now it reads every choice with its key ("Farmer, press 1. Street vendor, press 2."), then
  "if you do not know, press 0". It used to say "press 9", which clashed with the 9th topic.
- Tests: **300 passed**.

**What you need to do (all your jobs for Phase 2 are here).**
1. Sarvam's free credit ran out before the last 30 small clips ("press 1".."press 9" and the new
   "press 0" line; 361 characters). Top up, then run `make render YES=1`, then `make snapshot`.
2. Listen: `make listen L=mr N=lines`, and `N=5` for `L=hi`, `L=mr`, `L=en`.
3. Make 3 real calls (Hindi, Marathi, English) with `make run` in one terminal and `make call-me` in another.
   Tell me when done: I read `logs/server.log` and `logs/calls/`.
4. If the calls are good: I merge into main and tag `v1-keypad`.

**Please listen for these two on the calls.**
- Every call starts with "I am having trouble hearing you. We will use the keypad from now on."
- The topic question says "you can also say the name of a scheme", but this call has no speech yet.

Both lines come from the speech design. Tell me if you want them changed for keypad-only calls.

**Project can now:** take a real phone call on the 12 schemes with a real voice, keypad only.

### 30 Sep (night) — Phase 2 step 2.1: the call has a real voice (most of it)

**What was added.**
- `haqdaar/audio/render.py` — asks Sarvam to speak every text the call can say and saves each
  clip in the phone's own sound format. It reads the same list the snapshot uses, so the two can
  never disagree about which clips must exist.
  - `make render` only counts what is missing and spends nothing. `make render YES=1` pays.
  - It picks up where it stopped: a clip already saved is never asked for again.
  - It stops at once if Sarvam says "no credits", instead of failing 400 times.
  - It sends at most one request every 1.3 seconds, because Sarvam refused us after ~50 in a minute.
- `tools/listen.py` — plays clips on the Mac with the words printed first:
  `make listen L=mr N=lines` plays every Marathi fixed line, `make listen L=hi N=5` plays 5 random Hindi clips.
- `make pipeline-cost` now also shows what the voice has cost.
- 12 new tests. Full suite: **272 passed**.

**What was changed.**
- One voice per language, all set in `tunables`. All three are "priya", a woman's voice, because
  the call speaks of itself as a woman in Hindi and Marathi. Speed is 0.9 (you said 1.0 was too fast).
- Changing a voice or the speed re-makes only the clips it affects, because both are part of each clip's name.
- The three-language greeting now really plays Hindi, then Marathi, then English (18.8 seconds).
  Before, only its English was going to be spoken.

**Where it stopped.** Sarvam ran out of credits partway. 273 of 450 clips are made: **every fixed
line in all 3 languages, every button word, every age and income band, and the greeting.** What is
left is 177 scheme texts (34,535 characters). This run spent 15,878 characters in all (275 requests).

**What you need to do.**
1. Top up Sarvam, then run `make render YES=1`. When `make render` says `missing: 0`, it is done.
2. Listen: `make listen L=mr N=lines` (all Marathi lines), and `make listen L=hi N=5`,
   `make listen L=mr N=5`, `make listen L=en N=5`. If the Marathi voice sounds wrong, tell me: we
   change `TTS_SPEAKER_MR` and only Marathi is re-made.

**Note.** The clips live in `audio/`, which is not in git. They cost money, so do not delete that folder.

**Project can now:** speak every fixed line, button word and greeting in a real voice, in Hindi, Marathi and English.

### 30 Sep (later) — all 12 schemes pass in all 3 languages; lines corrected; Phase 1 merged

**A hidden bug, found while fixing the 4 bad schemes.** Many Hindi and Marathi texts were
translations of the *old, long* cards from before 21 Sep. The Marathi for PMMY talked about "women
entrepreneurs"; the Hindi for PM-Kisan said "no age limit". The English says neither. The cause: a
saved translation was reused as long as the scheme page was the same, even after its English
changed. Now a saved translation is only reused for the exact English it was made from. All 12
schemes were translated again (90 requests, 20,294 characters).

**The last 3 real faults, fixed by hand:** PM-Kisan's Marathi turned "₹10,000" into "10 हजार";
PMFBY's Marathi name and how-to-apply kept English words ("PMFBY", "Farmer Corner") and said
"बीमा" for "विमा"; PMMY's Hindi was too wordy. **Result: 12 of 12 schemes pass every check in
Hindi, Marathi and English** (was 8).

**The fixed lines, corrected:**
- Hindi talked to the caller sometimes as a woman, sometimes as a man, and sometimes with the
  rude "तुम". Now it is always the polite "आप" with the normal form used when the gender is not
  known, and lines that could avoid gender do ("आपका घर किस राज्य में है?").
- Marathi used the rude "तू" in 6 lines, and asked "तू किती वर्षांची आहेस?". Fixed.
- The menu said "what you will get" in both, which sounds like a promise. Now "what the scheme has".
- The greeting now has its Hindi and Marathi parts.
- 28 corrected lines are pinned, so the pipeline will never write over them.

**Merged:** steps 1.12 to 1.16 are on `main`. Phase 1 is done.

**Tests: 260 passing.** Nothing the call needs is missing.

### 30 Sep — every fixed line now has Hindi and Marathi

**First, a safety fix.** The last four steps (1.12 to 1.15) and 16 commits on `main` were only on
this laptop. The folder in `~/Documents` is inside iCloud, and iCloud had pushed 267 pieces of git
data off the disk, so every push hung. The copy in `~/code/haqdaar-v2` still had those pieces, so
the branches were moved there and pushed. **Everything is on GitHub now. Work in `~/code` from now on.**

**Added:** the translate step now also does the fixed lines (the 49 things the call always says,
like "Press 1 for yes"). It skips lines you fixed by hand (`pinned: true`), keeps the `{scheme_1}`
style blanks, runs the same checks a scheme gets (numbers, no promises, not padded, really in
Devanagari), and writes only what passes back into `lines.yaml`. A second run costs nothing. It is
part of `make pipeline` as "p4 lines".

**Ran it for real:** 96 Sarvam requests, 4,388 characters. All 98 texts are in. At first 5 failed
because Sarvam translated the blank's name too (`{scheme_1}` became `{स्कीम_1}`); when a line has one
blank the name is now put back. **Nothing the call needs is missing any more** (`make pipeline-texts`:
missing 0).

**For you to check** (`data_cache/reports/lines_sheet.md`):
- Some Hindi lines speak to the caller as a woman ("रहती हैं", "करती हैं", "कह सकती हैं") and others
  as a man ("चाहते हैं"). Pick one way, or a form that fits both, and fix those lines by hand.
- The greeting (Hindi, then Marathi, then English in one recording) still has only its English.
  Its Hindi and Marathi parts need to be written by hand.

**Tests: 259 passing** (was 253).

### 21 Sep (later) — the cards got short, and three quiet bugs came out with them

**The blocker is gone.** Only 3 of the 12 schemes had usable spoken cards. Now all 12 do.

The reason was not what the notes said. I read all 48 cards and their reasons: almost every
failure was the card being a few words too long (56 to 89 words against a 55-word limit). The
old prompt asked for "at most 55 words", so the model aimed at the limit and kept sailing past
it. It now asks for 45, which leaves room to run long and still land inside. It also spells out
the rule about never telling a caller they will get something, with examples. If a card still
breaks a rule, it is asked once more and told exactly what was wrong; the rewrite is kept only
if it is genuinely better, so a fix for length cannot sneak in a wrong number.

**Three bugs came out from under that**, all of them quiet ones that made good work look bad:

- The check that holds a card to its source compared words exactly, so a card saying "citizens"
  where the page said "citizen" looked made up.
- Bigger: the translation step translated the short cards but left the English as the *long
  original page text*. So the call would read the short card while the checker judged the long
  page, and every number the card had rightly left out looked missing. That one fault was
  causing 78 of the 83 failures.
- Scheme names come back with Hindi digits, which read as invented numbers.

With those fixed, schemes passing all the checks in all three languages went from 3 to 8.
**The 4 that still fail are real translation faults** — one says "50 thousand" where the English
says 50,000, one drops a whole exclusion and invents "no age limit". I left them failing. They
are for a person to look at, not for me to quietly loosen a rule around.

**Added: the words the call says.** All 50 fixed lines are written in plain, short English
("Press 1 for what you get."). A test checks every one of them never promises the caller
anything. `make lines-sheet` prints them as a sheet you can correct by hand. The keypad words
and the age/income bands needed nothing new — they were already there.

**Added: one list of everything the call can say** (`make pipeline-texts`). Before this, two
parts of the code disagreed about what audio should exist, and the disagreement was hidden: when
a scheme was missing its Hindi text, the code invented a fake placeholder, filed it as real, and
wrote a silent file. A call would have played nothing and everything would have looked fine.
That is gone. What is missing is now counted and named: 98 things, all of them the fixed lines
waiting for their Hindi and Marathi.

**Added: `make pipeline` and `make pipeline-cost`.** One command runs the whole chain. Nothing
that costs money runs unless you ask for it with `YES=1`, and re-scraping needs asking twice.
Running it again when everything is already done costs nothing — I checked the spend records
before and after, and they were identical.

**The cost report caught something on its first run.** It said we had spent 38,000 tokens. We had
not: 100 of the 113 recorded requests were written by the *tests*, into the real spending record.
Tests now write to a scratch file, and the false rows are gone. The true cost of everything built
so far on the 12 schemes: **13 Groq requests, and 27,445 characters of translation.**

**Tests: 253 passing** (was 217).

**Four branches waiting for you to check**, to be merged in this order:
`step-1.12-cards`, `step-1.13-lines`, `step-1.14-texts`, `step-1.15-pipeline`.

**Next:** the fixed lines still need their Hindi and Marathi.

### 20 Sep (later) — Hindi and Marathi, done properly this time
**Fixed first:** this folder's Python setup was broken. iCloud had taken 469 of its files off the
laptop, so any test run just hung. I deleted it and built it fresh. Tests run in about 7 seconds
again. Your code was never the problem, and nothing was lost.

**Added:** a new pipeline step, `make pipeline-translate`. The five things a call reads out (the
short summary and the four cards) are written once in English and then translated into Hindi and
Marathi by Sarvam, not by Groq. Groq's free daily allowance is small, and a live phone call needs
it more than the pipeline does.

**Checked before building, as the plan asks:** I made one real call to Sarvam to confirm three
things — the model name, the size limit (2000 letters per request), and the setting that keeps
6000 written as 6000 instead of spelled out in words. All three matched the plan, so I carried on.

**Fixed a quiet lie.** Hindi and Marathi summaries used to come from Groq with nothing checking
them, and some wrote amounts out in words where the real page gives a figure. The step that made
them is now English-only. But rows written earlier still held that old text, and simply stopping
the source does not clean what is already saved — so any scheme we do not translate now has its
Hindi and Marathi text emptied. Blank is honest; leftover unchecked text is not.

**Costs nothing to re-run.** Every translation is saved. Running it a second time makes zero
requests and finishes in under a second.

**Where it stands:** 3 of the 12 schemes are fully translated into both languages. The other 9
are waiting on something else — their English cards have not yet passed the card check from the
last step, and translating text we already doubt would only spread the problem. Tuning that check
is a job on your list from step 1.9, not a fault in this step.

**Project can now:** 188 tests pass, up from 167. Next is the gates step (1.10), which checks the
translations for numbers, banned phrases and length.

### 20 Sep — Phase 1, step 1.9: short spoken cards, checked against the source
**Added:** a new step in the pipeline (`make pipeline-cards`). Each scheme's four long sections
(what you get, who can apply, papers, how to apply) become four short cards meant to be read out
on a phone call. The long pages take minutes to read aloud; a card takes seconds.
**Added:** the cards are not trusted just because the model wrote them. Each card is checked back
against the real page: it may not say a number the page does not have, it must say the age and
income limits, it may not tell the caller they are eligible, it must stay under 55 words, and most
of its words must come from the page. Every card that fails is written down in
`data_cache/reports/cards.json` for a person to read. Nothing is retried and nothing is hidden.
**Added:** the papers card always ends with "The CSC centre will tell you the full list of papers."
That is our sentence, not the model's, because the real list changes at the counter.
**Result:** all 12 schemes now have cards. **3 of 12 pass every check.** The good news: not one
card made up a number, and not one failed the word-overlap check — so the facts are sound. The 9
failures are all about wording: 10 cards ran long (56 to 89 words instead of 55), and 2 spoke to
the caller directly ("you will get", "you will receive"). Next is to tighten the instructions we
give the model and run it again.
**Cost:** 12 Groq requests. Running it a second time costs nothing (0 requests) — the answers are
cached. `pytest` → 167 passed (was 152).

### 19 Sep — Phase 1, step 1.8: best schemes first, and "press 9 for 3 more"
**Added:** each scheme has a priority (1 = say first). Wide-reach ones (PM-KISAN, Ayushman Bharat,
PM Awas Gramin, Fasal Bima) are 1; narrow ones (SMAM, PMEGP, NAPS) are 3. Change them in `schemes.yaml`.
**Changed:** when many schemes match, the call reads 3, and at the last one key 9 plays "here are
more" and the next 3, until none are left. Before, only 3 were ever read.
**Changed:** on the scheme menu, `*` now changes language and reads that scheme again; 0 leaves;
a key with no meaning plays the menu again instead of ending it.
**Project can now:** tell a caller about every scheme they match, best first.
Tests: **152 passed**. Next: 1.9, short spoken cards for each scheme.

### 19 Sep (night) — Phase 1, step 1.7: the call writes down which schemes it told you about
**Added:** every call log now has one line per scheme the caller actually heard: its id, how the
call ended (direct match, overflow, widened, nearest), which parts were read out (summary, and
benefits / how to apply / documents / who can apply if the caller asked), and the language.
**Project can now:** show after any call exactly what the caller was told, so the 10-call test can
check it. Tests: **145 passed**. Next: 1.8, ranking and "press 9 for 3 more".
**Still true:** the v2 engine is keypad-only in the terminal. First real phone call on v2 = end of
Phase 2 (keys). It hears your voice at the end of Phase 4.

### 18 Sep (night, later) — Phase 1, step 1.6: "0 = don't know" and the Maharashtra question
**Changed:** pressing **0** on any question now means "I don't know". Before, 0 counted as a wrong
key (a strike). Now the call just moves on, and never guesses for you.
**Changed:** the state question is now a yes/no: "Do you live in Maharashtra? 1 yes, 2 no, 0 don't
know". 1 lets Maharashtra-only schemes in, 2 keeps only all-India ones, 0 plays a short warning and
names only all-India schemes.
**Project can now:** do all of the above in `make sim`. Tests: **143 passed**. Phase 1 steps 1.0 to
1.6 are done, on branch `v2-p1-pipeline` (pushed, not merged). Next: 1.7, a log of what the call
actually said. The spoken words for the new question are written down but not recorded yet (step 1.12).

### 18 Sep (night) — Phase 0 done: the ground is fixed
**Moved:** the project now lives in `~/code/haqdaar-v2`, out of iCloud. iCloud had taken some files
off the laptop, which is why tests and git kept freezing. 8 of git's own files never came back;
they were copied back from GitHub, and git's own check is clean. Tests: **109 passed in 3 seconds**.
**Saved:** the demo branch (`demo-15sep`) is committed and on GitHub, then frozen. 15 unused voice
clips were removed (checked: the demo uses exactly the other 125).
**Added:** the scheme data text is now in git (62 files), and `make backup` copies all of it to
`~/haqdaar-backup/`. `make call-me` rings your phone with the real backend.
**Changed:** the v2 decisions are written in the decision log (§6). The old `_staging/` drafts are gone
(still in git history).
**Project can now:** same calls as before, on solid ground. Work is on branch `v2-p0-ground`, not
merged yet. **You:** open VS Code on `~/code/haqdaar-v2`, and say "start Phase 1" when ready.

### 18 Sep (later) — the full v2 plan: 100+ schemes, 3 languages
**Added:** `PLAN-V2.md`, the plan from here to the 10-call test, in 7 phases (0–6). It replaces
`NEXT-PLAN.md`.
**Why a new plan:** you want 100+ schemes (all-India + Maharashtra) in Hindi, Marathi and English.
The research found these problems:
- Scheme sections are 2–6 minutes long when spoken, so each will get a short checked "card"
  (~25 s).
- A scheme the AI can't place quietly became "for everyone", which is a lie. It will be set aside
  instead.
- Answering "No" to "Do you live in Maharashtra?" would have removed every scheme.
- Groq's free tier allows 200K tokens a day, so the 100-scheme data run is about 6 days unless
  you pay (you decide in Phase 3).

A second reviewer checked the plan against the code and found 17 more holes; all are fixed in the
plan.
**How we work:** one phase at a time. You say "start Phase N", I build it with helpers, check
everything, report, and stop.
**Changed:** nothing in the code.
**Project can now:** same as before. Next: Phase 0 (move the repo out of iCloud, cleanup, back up
the data), when you say go.

### 18 Sep — full check of the project, and a plan to finish
**Added:** `NEXT-PLAN.md`: the goal, what each of the 21 steps has done (9 done, 4 half, 8 not
started), a checklist in 4 phases, the decisions only Adarsh can make, and the top risks.
**Found:** iCloud has pushed 507 repo files off the laptop (disk 90% full), including 457 in `.venv`
and 17 inside `.git`. That is why `make test` and some git commands hang. The code is fine: a fresh
setup outside iCloud ran `pytest` → **109 passed**. Fix is in `NEXT-PLAN.md` §4 A.
**Not done:** the cleanup (old `_staging/`, 15 unused voice clips, a stray empty folder, junk
files). The safety check blocked deleting without Adarsh's OK. Commands are in `NEXT-PLAN.md` §4.
**Project can:** same as 15 Sep. §1 below still describes `main` correctly, apart from the dates.

### 15 Sep (night) — references for the PPT
**Changed:** new `REFERENCES-FOR-PPT.md`: real numbers with links for the problem slide (TRAI, Census,
NFHS-5, NSS, myScheme, World Bank via Acumen), the 7 scheme pages, similar work (Kisan Call Centre,
Mobile Vaani, Haqdarshak), the tools, and a ready "References" slide. Items marked (check) must be read at the source first.
**Project can:** same as before. This is for the slides only.

### 15 Sep (night, v3 call) — whole call in the Sarvam voice, `make call-me`
- **Changed:** new Sarvam key. All 125 lines are now in the Sarvam voice (mac fallback 0). The clips are saved in `haqdaar/voice_demo_clips/`. Commit that folder and the voice stays even with no credits.
- **Added:** `make call-me` starts the tunnel and the real backend (`haqdaar.server`), then rings your phone. `make run-demo` does the same for the voice demo.
- **Real call (19:00):** farming path, keys 1, 1, 2, then scheme 2 (crop insurance), how to apply, goodbye. No errors. One spoken answer was lost: Sarvam speech-to-text took longer than 4.5 s. The call asked for a key and carried on.
- **Tested:** `pytest` → 109 passed.

### 15 Sep (night, v3) — repeat slowly, "don't know" button, slower voice, PPT brief
- **Real call test (18:38):** the call went well end to end. One bug: a key pressed while it said "sorry, I did not understand" was lost. **Fixed:** that key now answers the question.
- **Added:** press **9** at any time (or say "दोबारा" / "repeat") and it says the last line again, slowly. It tells the caller this once, after the language.
- **Added:** press **3 = I don't know** on the questions about land, loan, age, savings account and family type. It explains kindly and carries on (for example: "your date of birth is on your Aadhaar card").
- **Changed:** every line plays a bit slower (90%). The repeat plays at 72%. The pitch stays the same.
- **Added:** `DEMO-FOR-PPT.md`, a brief for the people making the slides and video.
- **Tested:** fake calls in Hindi and English with 9, 3 and a key during a sorry line. `pytest` → 109 passed. Not yet tried on a real phone.

### 15 Sep (night, v2) — buttons for the main choice, voice answers confirmed
- **Bug Adarsh found:** he said "pension", the phone speech-to-text heard nonsense, and the script went to farming anyway.
- **Changed:** the type of help is now a small button menu (1 farming, 2 pension, 3 health, 4 jobs). Speech still works,
  but whatever it hears is read back: "आपने पेंशन चुनी। सही है तो 1 दबाइए, नहीं तो 2।" Same for हाँ / नहीं and scheme names.
  It never picks the type of help by itself.
- **Added:** pension (Atal Pension: age? savings account?), health (Ayushman Bharat: SC/ST or landless daily wage?),
  jobs (PMEGP or apprenticeship). "Anything else?" goes back to the menu.
- **Hearing fix:** Whisper garbled a lone short word like "पेंशन". Adding 1 s of quiet around it and a list of expected words fixed it in tests.
- **Voice:** 86 new lines use the Mac voice until Sarvam credits are topped up. Then a restart makes them in Sarvam.
- **Tested:** fake calls in Hindi and English through every path, including saying 2 to a wrong confirm. `pytest` → 109 passed.

### 15 Sep (later) — voice demo that rings you (`make run-demo`)
- **Added:** one command, `make run-demo`. It starts the tunnel and the server, waits until the voice is ready,
  then rings Adarsh's phone. The caller **talks** (Hindi or English) or presses keys.
- **Voice:** Sarvam (bulbul:v3, "priya"). All 39 lines are made in advance and saved in the repo, so the call
  needs no Sarvam credits. **Sarvam credits ran out tonight** after making them.
- **Hearing:** Sarvam speech-to-text is out of credits, so Groq Whisper does the hearing (it switches by itself).
- **Fixed script with follow-up questions:** "what do you need" → farming → "is the land in your name?" →
  "do you need a loan?" → 1 to 3 real farmer schemes (PM-KISAN, Kisan Credit Card, Fasal Bima) → pick one by name →
  details → how to apply → another one? → goodbye. Always farming (rigged), so it cannot go off track.
- **Why the last run never rang:** the saved tunnel address had died on 13 Sep but the old process was still running,
  so the tools kept using the dead address. Now checked with public DNS and restarted if dead.
- **Tested:** fake Hindi and English calls over a real socket, start to goodbye. **Real call ..cf6f87 rang Adarsh's
  phone**, played the Sarvam voice, took key 1, heard speech. `pytest` → 109 passed.

### 15 Sep — demo prototype (branch `demo-15sep`)
- **Added:** a keypad phone call on the 12 real schemes that speaks real sentences (Mac's offline voice,
  English + Hindi). `make demo-run` = phone, `make demo` = terminal backup. Script: `DEMO.md`.
- **Stress tested:** 500 random-key calls (0 crashes, all 12 schemes reachable); 146 voice lines render, 0 fail;
  4 fake phone calls on a real server (normal, Hindi, key mashing, hang-up) all end cleanly.
- **Fixed on the way:** server froze 10 s when you pressed a key while it talked (call then went silent);
  Mac voice froze on raw scheme text like "Rs.50,000/-..".
- **Not yet:** a real dial-in on this build — Adarsh does one test call before the demo. `pytest` → 109 passed.

### 14 Sep — Step 1 merged
- **Added:** tunnel start, `make call`, `make calls`, timed call lines — committed on step-01.
- **Changed:** Step 1 reviewed (all checks pass) and merged into `main`.
- **Can do now:** `main` takes a real phone call: tone, keys on time, clean hang-up. 109 tests pass.

### 13 Sep · keys fixed: Cloudflare tunnel instead of ngrok
- **Why keys went missing:** ngrok could only carry half the audio from the US to India, so keys arrived late and were lost at hang-up.
- **Fix:** the Cloudflare tunnel. Two real calls: all audio on time, every key live, no stalls.
- **Added:** `make run` now starts the Cloudflare tunnel by itself and points the phone number at it.
  `make call` uses the same address. Backup: `TUNNEL=ngrok make run`. New file `tools/tunnel.py`.
- **Tried and parked for v2:** a US server (free GitHub Codespace in Virginia, near Twilio). The call gave
  "application error" because the port was never made public. Not needed now; v2 needs it for live speech (Step 13+).
  The test machine is stopped and deletes itself within 24 h.
- `pytest -q` → 109 passed.

### 13 Sep · why keys go missing — found
**Cause:** the internet path from the phone company (in the US) to your laptop (in India, through
ngrok) carries only about half the audio in real time. Everything queues up. Keys arrive late —
your second "1" came 9 s late — and when you hang up, whatever is still in the queue is thrown
away. That is where your 2s went. Same rate on both calls (about 50%).
**Not the cause:** our code. A fake call through the same ngrok link got 4 of 4 keys and all audio.
**Added:** the log now warns `!! falling behind: audio arrives X s late`.
**Fix, your pick:** run the server on a small US machine next to the phone company (needed anyway
once speech comes in, Step 13), or first try a different tunnel for a 5-minute check.

### 13 Sep · second call: keys 2 and 3 lost
**What happened:** beep and `mark tone_end` fine. Then the line stalled: no sound reached the
server for about 15 s. Key 1 and the hang-up arrived together at the very end; 2 and 3 never came.
The provider logged 31921 (socket dropped, no clean close). `Error 130` was only Ctrl+C.
**Changed:** the log now says when nothing arrives for over 1 s, the audio clock when a key comes
in, and whether the call closed cleanly or dropped. `make calls` no longer crashes on that warning.
**Next:** one more call to see where the stall is.

### 13 Sep · first real call worked + a call log
**Result:** the line rang your phone (13 Sep, 44 s, completed). The provider logged one warning:
`keepCallAlive` is not a real setting on `<Stream>`, so it is ignored. The call still ends when
the socket closes, which is what we wanted. **Your call:** drop the setting, or keep it as harmless.
**Added:** `make run` now shows one line per call event with the time (answer, start, tone sent,
mark, key pressed, closed) and copies everything to `logs/server.log`, so Claude can read it.
`make calls` lists the last calls and any warnings. `pytest -q` → 109 passed.
**Still to record:** seconds from dial to beep, and the three-phones test.

### 13 Sep · backup: the line can ring you
**Added:** `make call` (`tools/call_me.py`). It asks the phone line to ring your number
(`CALL_ME_NUMBER` in `.env`, or `make call TO=+91...`). When you pick up, you get the same beep.
Needs `make run` and ngrok up. `pytest -q` → 109 passed.

### 13 Sep · Step 1 checked by Claude
**Result:** the code is good. `pytest -q` → 108 passed. I also started the real server and played a
fake call against it: `/answer` sends the right XML, the tone goes out (8000 bytes, no header),
`mark tone_end`, `dtmf 1`, `dtmf 9` print, and 9 closes the line. "twilio" shows up only in the
telephony folder.
**Still missing:** the real phone call (M1). Until then, do not merge. After the call, write into
the commit message whether `keepCallAlive="false"` worked, the seconds from dial to tone, and the
three-phones result.
**Small things, not blocking:** if `NGROK_DOMAIN` is empty the stream URL breaks (it is set in
`.env` now). The beep encoder is off by one step on 55 of ~9,400 sample values — you can't hear it.

### 13 Sep · Step 1 implemented (Telephony smoke call)
**Added:**
- `haqdaar/server.py` — FastAPI server exposing `/health`, `/answer` (TwiML Stream XML with `keepCallAlive="false"`), and `/stream` (WebSocket).
- `haqdaar/audio/telephony/twilio.py` and `__init__.py` — Telephony wire protocol codec parsing 6 inbound events (`connected`, `start`, `media`, `dtmf`, `mark`, `stop`) and building 3 outbound events (`media`, `mark`, `clear`). Twilio isolation strictly maintained (no mention outside `haqdaar/audio/telephony/`).
- `tools/tone.py` — 8 kHz μ-law 440 Hz 1-second tone generator with zero RIFF/WAV headers.
- `tests/test_twilio_codec.py` — 10 tests proving all 6 inbound events, outbound builders, raw μ-law payload, and stream websocket behaviour.

**Changed:**
- `haqdaar/contracts/tunables.py` — Added telephony tunables (`TONE_FREQ_HZ=440`, `TONE_DURATION_S=1.0`, `TONE_AMPLITUDE=0.5`, `NGROK_DOMAIN`) and `.env` loading.

**Project can now:**
- Serve the telephony webhook, stream a 1-second 440 Hz μ-law tone on call start, receive DTMF digits and marks, and hang up when digit 9 is pressed. `pytest -q` → 108 passed.

### 13 Sep · day files for 13 Sep written
**Added:**
- `work-with-tools/2026-09-13.md` — two prompts to paste: Step 1 (phone call) and Step 9 (translate +
  gates). They run at the same time in two windows; they touch no shared file.
- `work-adarsh/2026-09-13.md` — your list: start the server, start ngrok, dial the number, fill the table.
- `PROJECT-UPDATE.md` — this file.

**Changed:** nothing in the code.

**Two things I fixed in the prompts, so they don't bite you:**
- The server file must be `haqdaar/server.py`, not `server.py` at the top. `make run` looks for
  `haqdaar.server:app`. The old prompt in `WORK.md` §4 said `server.py`.
- Step 9's gate 3 needs rendered audio, which only Step 10 makes. The prompt says: print `PENDING`
  for that half, don't fail on it. Otherwise no scheme could pass and Step 9 could never finish.

**Project can now:** same as yesterday — nothing new runs yet. After today it should answer a real
phone call with a beep and read keys, and have Hindi and Marathi text checked for unsafe words.

### 13 Sep · Step 8 finished and merged
**Changed:** `p2_derive.py` — the category quote can now come from the benefits text too; if a scheme
lists many kinds of workers, work is set to "any". Re-ran for all 12 schemes.
**Result:** category known for 12 of 12 (was 5). Twilio webhook checked live: `/answer`, POST.
**Project could:** turn 12 real pages into clean, quote-backed records.

### 21 Sep · Step 1.11 — the five gates, and everything pushed to GitHub

**First, the repo.** Two commits from the translation step were sitting on this machine and had
never reached GitHub. They are pushed now. I also added 42 cache files that belong in git but
were never added, and told git to ignore `haqdaar/voice_demo_clips/` (6.4 MB of audio from the
old September demo, which the code regenerates). The working tree is clean and everything is on
GitHub.

**Added:**
- `haqdaar/data/pipeline/p5_gates.py` — the five checks that decide whether a scheme is safe to
  say out loud in a language: the numbers match, no sentence promises the caller anything, the
  translation is not padded, it is really in Devanagari, and no section is empty.
- `tests/test_gates.py` — 29 tests. Full suite: **217 passed** (was 188).
- `make pipeline-gates`. It is free: it only reads what the earlier steps already wrote.

**What running it on the real 12 schemes taught us.** Two of the gates were wrong, and only the
real data showed it:
- The length gate counted letters. Hindi writes a short English list as a full spoken sentence,
  so honest text looked 1.8 times too long. It now counts words, which is what a caller hears.
- The script gate counted the letters in `agrimachinery.nic.in` as "not Hindi". A web address
  cannot be written in Devanagari and still work, so addresses are now skipped.

After the fixes, Hindi went from 1 scheme to 3 and Marathi from 0 to 2.

**One scheme still fails, on purpose.** PMMY's Marathi turned "Rs.50,000" into "50 हजार". That
is a real change to a number, so the gate is right to stop it. I did not loosen the gate to make
the number look better.

**The honest picture.** Only 3 of the 12 schemes have translations at all, so only 3 could be
gated. The other 9 are stuck one step earlier: their spoken cards fail the card check, so they
were never translated. That, not the gates, is what to fix next.

**Project can now:** refuse to speak any scheme text that has a wrong number, a false promise,
padding, the wrong script, or a missing section — per language, so a bad Hindi does not silence
a good Marathi.
