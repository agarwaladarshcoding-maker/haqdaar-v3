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
- Read results one scheme at a time: plays each scheme, its menu, waits for keypad or spoken questions, and answers 'this scheme' questions from the scheme currently sounding (Step 7.2).
- `pytest -q` → **2,267 passed**.
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

### 5 Oct 2026 — Talks more like a real call; work is committed; a prompt for the rest is ready
- **Your call was good.** Two things you asked for are built.
- **"One moment".** It is said when the line has been checking for about 2 s, and again every 4 s while it still checks.
- **How the call goes now.** It names one or two schemes and asks which one. You ask one thing, it tells that
  and offers the other parts (papers, how to apply). You say "details" / "विस्तार से", it tells the whole scheme
  (what it gives, who it is for, papers, how to apply) and asks what more you want. You say "yes", it gives the
  part it offered, not everything again.
- **Saved.** Two commits on `step-7.13-talk` in `~/code/haqdaar-v2-7.3`: `26a9828` and `d53b483`. Not pushed.
- **For the rest.** `PROMPT-STEP-7.14-TALK-REST.md`: paste it into a new chat to do stage times and speed,
  real cut-in (Silero + the strict gate), the stress run, and the write-up.
- **Checks.** pytest 2373 passed + the 1 old failure; stress clean.

### 5 Oct 2026 — The six open points from the test calls are fixed (not committed; waits for your phone)
- **Faster, and "one moment" is rare now.** The fastest model goes first (about 0.5 s). Live voice is at pace 1.0.
  The line waits 600 ms of quiet, not 800, to know you stopped. Later sentences are made while the first is said.
  On the test calls the answer starts about 2 to 3 s after you stop. "One moment" was heard once in 7 calls.
- **Another topic** ("what is the weather") now gets: "I can only help with government schemes."
- **No "man or woman?"** when only a few schemes are left; it shows the schemes.
- **Same need said twice** no longer gets the same sentences back.
- **Talking over it** was tested: it finishes its reply and does not lose the thread. It does not stop for you yet
  (real cut-in is step B5, not built).
- **"1.3 लाख"** is now said, not refused.
- **Checks.** pytest 2372 passed + the 1 old failure; stress clean; cut-in check same as before.

### 5 Oct 2026 — Your phone check failed; cause found, fixed, and tested with a caller that needs no phone
- **What you heard.** You said "farmer schemes" and it asked "farming or business?". You said "farming" and it
  asked the same thing again, and read out code names (farming, business_loans).
- **Why.** The model did not write down "farming" from your words, twice. The fixed picker then kept asking for it.
- **Fixed.**
  - Clear words (खेती, किसान, फार्मर, लोन, पेंशन, घर ...) are now read by fixed code, before the model.
  - The same question is never asked more than twice.
  - Code names, letters of other languages and very long sentences are refused and tried again.
  - "1.2 लाख" is now read as 1,20,000 by the number check (it was refused before and you would get "not sure").
  - The scheme you are talking about is always given to the model in full (it had said "no information on papers").
  - Side talk ("अरे रमेश, चाय ला दो", "वहाँ मत रखो") is ignored better. Replies are shorter.
- **Added.** `tools/talk_probe.py`: a caller with no phone. It uses the Mac's own Hindi and English voice and
  talks to the real server: real ear, real speech-to-text, real search, real model, real voice.
  Five scripts: your call, a vague caller, side talk, an English street vendor, a silent caller. 11 calls run.
- **Checks.** pytest 2369 passed + the 1 old failure; stress 1000 callers, 0 crashes, 0 truth failures.
- **What it can do now.** Your exact call now gets farming schemes at once, then PM Kisan money, papers, repeat, goodbye.
- **Not fixed yet.** "One moment" on every turn; the answer starts 3 to 6 s after you stop (B4 cuts this);
  a question on another topic gets silence. Not committed.

### 5 Oct 2026 (night of 4 Oct) — TALK BUILD: B0 to B3 done. You can now talk to it. Waits for your phone check.
Folder `~/code/haqdaar-v2-7.3`, branch `step-7.13-talk`. Not committed (B2 + B3), not pushed.

**Added**
- T2 (the one call log) is committed: `2af3644` on `step-7.12-log`.
- **Search over all schemes** (`haqdaar/data/scheme_index.py`). Two searches, best score wins: by meaning
  (a free model that runs on this Mac and knows Hindi and English) and by name. No database. On 30 test
  sentences in Hindi and English the right scheme is in the top 3 for 28. A search takes 2 to 4 ms.
- **The fixed question picker on the search results** (`haqdaar/engine/talk_pick.py`). Search gives the 10
  nearest schemes, the filter drops the ones that do not fit, the same picker as the keys path names the ONE
  thing to ask next. The model does not choose the question (your change C1).
- **The talk loop** (`haqdaar/engine/talk.py`, prompt in `haqdaar/prompts/talk.py`). Switch: `TALK_ONLY=true`.
  After the language key: a short hello, then you talk. Each turn: your words -> search -> filter + picker ->
  ONE model call -> facts checked -> truth checks -> live voice -> the log.
  The model can: answer, ask (only the picker's question), show schemes, say it again, say goodbye, or stay
  silent when the words were not for it (side talk).
- New rows in the call log: what the caller said (`heard`) and what the model chose (`act`, with the time in ms).

**Changed**
- A failed speech-to-text call no longer makes a TALK call "keys only" (it would go deaf).
- The truth check takes a length limit: talk replies may be up to 4 sentences / 80 words (your change C5).
- `TALK_ONLY=true` turns live voice on by itself (no need for `QA_SPEAK=true`).
- With the flag off the keys call is the same as before.

**Checks I ran**: pytest 2362 passed + the 1 old door_a failure; `make stress` 1000 callers, 0 crashes,
0 truth failures; `make barge-eval` 65,622 scenarios, same known failing checks; py_compile ok; vault in sync.
Two scripted calls through the REAL model and REAL search (no phone, no voice): Hindi vague caller
(asked the kind of help -> farming -> schemes -> "PM Kisan gives how much" -> papers -> say again -> side talk
ignored -> goodbye) and English street vendor (found PM SVANidhi, told how to apply). Both read right.

**What it can do now**: hold a back-and-forth talk about schemes in Hindi or English, by voice, strict turns
(it does not listen while it talks).

**Things you should know**
- Groq gives each model only 8,000 tokens a minute. One turn is about 1,900. So the loop moves to the next
  model when one says "too many" (gpt-oss-120b -> gpt-oss-20b -> qwen3.8-27b). About 12 turns a minute in all.
  Also 1,000 requests a day per model.
- "One moment" is said on almost every turn today, because the model takes 1 to 2.5 s. Setting:
  `TALK_ONE_MOMENT_S` (0.6 now).
- The picker stops asking at 4 schemes left (its own old setting), not 3.
- A question on another topic ("what is the weather") gets silence, not "I only help with schemes".
- Not done yet (B4 to B6): pace 1.0, sentence-by-sentence speed work, stage times, cut-in with the strict
  gate, Silero, the 200-call stress.

### 4 Oct (late night) — Side talk: what can fix it, and the "keys off first" idea (nothing built)
- **Why.** In the two real calls, voices near the phone kept cutting the agent. The owner asked for a library that fixes this, and asked if we should drop keys for now and build the talk + scheme search first.
- **Found.** No library fully fixes side talk on a phone line. Krisp BVC is made for it but is paid. Silero VAD is free and tells a voice from a noise, but not the caller from another person. The biggest win is free: the agent does not listen while it talks.
- **Decided by the owner.** Plan v4 "TALK BUILD" in `.agent/TASK.md`, to be built tonight in a new chat: keys off but the language pick (Hindi and English); the fixed question picker chooses what to ask a vague caller, the model only words it; only free tools for anything new; vector search + name search over all schemes; one model call per turn; voice pace 1.0; cut-in with a strict gate; stress tests. Keys come back at the hackathon.
- **Written down on purpose.** A paid tool (Krisp BVC) could fix side talk better. We have no money for it, so it is not done. Side talk is handled by turn rules for now.
- **What the project can do.** Same as before. No code changed in this chat.

### 4 Oct — Step 7.2: One scheme at a time (results read one by one)
- **Why.** In phone test 2, all matching schemes and section menus were dumped into a single audio queue at once (~200 seconds of audio). When a caller interrupted during a scheme's menu, clearing the audio queue lost all subsequent schemes and caused "this scheme" questions to be answered against whatever scheme the loop index drifted to, rather than the scheme the caller actually heard.
- **Fixed — One scheme at a time.** Terminal sequences are now segmented into individual per-scheme blocks (`render_scheme_block`). The engine plays one scheme, its summary, and its section menu, and waits for input before playing the next scheme.
- **Fixed — Current scheme tracking.** `Engine.current_scheme` is maintained to strictly reflect the scheme currently sounding or just heard. Unnamed "this scheme" questions are answered against `Engine.current_scheme`. Spoken questions naming another scheme jump to that scheme via Door A.
- **Lock test added.** Added `test_one_scheme_at_a_time` in `tests/test_barge_sweep.py` verifying that N matching schemes produce N separate waits, and that `current-scheme` strictly equals the scheme last heard at each wait across both keypad navigation and spoken questions.
- **Checks:** pytest passes with 2,267 tests (up from 2,264); `make stress` on 1,000 random callers completes with 0 crashes and 0 truth failures; `make sim` cleanly walks through matching schemes one by one and completes to `closing_farewell`.

### 4 Oct — Step 7.1: Never silent (after a cut, the engine always speaks)
- **Why.** On the owner's test phone call (..637351), interrupting a scheme readout with a question led to 20 seconds of dead silence because the mouth was cleared and unhandled speech in readback bypassed the menu without speaking.
- **Fixed — Never silent after a cut.** After any cut (voice barge-in or key cut-in), the engine is guaranteed to speak before it listens again: either the answer to the question, or "sorry, say that again" (`unclear_prompt`) plus the menu it was on. No cut path returns to listen with an empty mouth.
- **Fixed — Question check retry and logging.** In `Engine._try_question`, if the answer check fails, it retries exactly once more. Both tries are logged to `questions.jsonl` with `write_question_line`. Only if both fail does it fall back to "don't know" / unclear.
- **Lock test added.** Added `test_cut_is_always_answered` to `tests/test_barge_sweep.py` covering 400 test cases across 8 cut types at every position in both keyed and spoken calls, verifying the engine always speaks after a cut before listening again.
- **Checks:** pytest passes with 2,264 tests (up from 1,859); `make stress` on 1,000 random callers completes with 0 crashes and 0 truth failures; `make sim` finishes cleanly to closing_farewell.

### 3 Oct (late night) — Live call page built. Hosting dropped for good. Home stays.
- **Dropped — hosting.** Owner's word: nothing is hosted, not the site and not the engine.
  `PLAN-DASHBOARD.md` no longer carries the hosting plan (it is in git history, e45d2f7).
- **Kept — Home.** The owner asked whether the first plan had a Home page. It did, from the
  first round of the dashboard plan, so it stays.
- **Added — the Live call page** (`/live`). Simple: two cards on top, the call below.
  - **Call my phone** rings the number saved in `.env` (`CALL_ME_NUMBER`), and only that one.
    It says in plain words why it cannot ring: the engine is off, a call is already live, no
    number is saved, no public address yet, Twilio refused the login, or the phone was rung a
    few seconds ago. **Not tried on a real phone yet**: the engine is off and Twilio still
    refuses the login (401).
  - **Typed test call**: free, no phone. The real engine runs, and you type what the caller
    presses or says, or press Say nothing or Hang up. A hint says what the AI is waiting for.
    Left alone for 5 minutes, it hangs up by itself.
  - **The call** shows line by line: the AI's words on the left, the caller on the right, and
    under each caller line what the engine made of it in plain words ("Understood: Topic =
    farming", "Not understood"). It follows the call down as it grows.
  - **This call** beside it: language, turns, not understood, problems, what the engine knows
    so far, the schemes read out, and the judge's word once it ends.
  - The page address carries the call (`/live?call=...`), so a call can be opened again.
- **Safety.** The two actions (ring, test call) are refused unless they come from the
  dashboard's own page, so another website open in the browser cannot fire them.
- **You need to restart `make dashboard`** once (Ctrl+C, then again) for the Live call page to
  work: the data door you have running is the old one.
- **Checks:** pytest 501 (was 496) · `make stress` 0 crashes, 0 truth failures · the site
  type-checks and builds clean · a real typed test call was run through the page and looked
  at in a browser: live, ended, light, dark, narrow · no paid API was called, no call placed.

### 3 Oct (late night) — Dashboard look redone from the owner's reference. One page: Home.
- **Why.** The owner said the first look (yellow signboard, wide heavy letters) was very bad,
  gave a reference picture of a dark left bar, and asked for a simpler font and one page at a time.
- **Changed — the left bar.** Now a dark rounded panel with thin line icons and grey names.
  The open page is a mint pill, as in the reference. **Fold menu** shrinks it to icons only and
  remembers the choice. "Usage and money" and "Plan and architecture" are "Usage" and "Plan"
  in the bar so nothing wraps.
- **Changed — Home.** Same facts, calmer layout: the engine and Call my phone card, the
  schemes bar, four number cards, Needs a look (each line is one click), money and use, last calls.
  The yellow plate and the keypad picture are gone.
- **Changed — the font.** One plain font, Inter, for everything. Hindi and Marathi use Noto
  Sans Devanagari.
- **Added — the UI UX Pro Max skill** (free, MIT licence, from GitHub), in
  `.claude/skills/ui-ux-pro-max/`. It is 3 MB of design rules, so it is not kept in git. I read
  its scripts before running them: they only search its own files.
- **Added — icons** from the `lucide-react` package.
- **Checks:** the site type-checks clean · looked at in a browser: dark, light, narrow · no
  Python changed, pytest still 496.
- **Not done on purpose:** no other page was touched. Calls is next, with its own design pass.

### 3 Oct (late night) — The dashboard: left bar and Home page built. Hosting dropped for now.
Branch `step-6.1-dashboard-home`. Not merged, not pushed.
- **Changed — the plan.** Owner's word: no hosting for now. The dashboard runs on this
  computer. `PLAN-DASHBOARD.md` keeps the hosting parts as "parked", and now also holds the
  look (§13) and the data shapes (§14).
- **Added — the dashboard.** `make dashboard`, then open http://127.0.0.1:3210.
  - **The left bar** has every page: Home, Live call, Calls, Schemes, Voice lines, Usage and
    money, Quality, Plan and architecture, System, Settings. Only Home is built. Each of the
    others shows its step number and says what it will show.
  - **Home** shows, on real data:
    - the yellow plate: is the engine on, the Call my phone button, schemes live on calls,
      the snapshot, and what the keys mean on a call;
    - the last 24 hours: calls, passed the judge, average length, slowest AI reply;
    - **Needs a look**, worst first. Tonight it lists: Twilio refused the login, Groq cannot
      run the engine's model, the engine is off, Muse is blocked for today, 16 checked
      schemes have no voice, 21 audit verdicts are waiting, 3 schemes are set aside, no real
      phone call yet;
    - schemes: 11 live, 16 with no voice, 3 set aside;
    - money: Muse in rupees against its two caps, the other services in units;
    - the last 5 calls, each drawn as a "call tape": a bar when the AI spoke, a tick when
      the caller did something.
  - It refreshes by itself every 5 seconds.
- **Added — the data door.** `tools/dashboard_api.py` (port 8001). It only reads files. The
  old call page and its routes are still served from it.
- **The look.** From the yellow PCO booth sign: a yellow plate with black and red letters,
  indigo ink, cool grey behind. Light and dark. Works on a narrow screen.
- **Know this:**
  - The Call my phone button does not place a call yet. That is step D3. Tonight it is off
    anyway, because the engine is off.
  - The site is on port 3210, not 3000: another app of yours already uses 3000.
  - `dashboard/` needs Node. `make dashboard` installs what it needs the first time.
  - A call still opens in the first call page (port 8001) until the Calls page is built (D2).
- **Checks:** pytest 496 (was 491) · `make stress` 1,000 callers, 0 crashes, 0 truth failures ·
  the site builds clean · looked at in a browser: light, dark, narrow · vault in sync · no
  paid API was called.

### 3 Oct (night) — Dashboard plan, round 2: can the engine be hosted? Not yet, but close.
- **Changed — `PLAN-DASHBOARD.md`.** The engine now gets hosted too (Fly.io, Mumbai), so the
  site is live all day and the laptop can be shut. The Schemes page gets a real table and an
  "add a scheme" flow in seven stages with two owner approvals. The build order now starts
  with the engine: E1 lock the doors, E2 host it, E3 data door, then the dashboard.
- **Found — what the engine lacks before hosting** (audit, nothing changed in code):
  - No lock: anyone with the address can hold the one call slot, or run fake calls that spend
    Sarvam and Groq credit. A crafted call id can write files outside the logs folder.
  - No build recipe. The 37 MB of voice clips are not in git, so a fresh copy cannot start a call.
  - The "longest call" limit is never enforced. The health check says ok even with no clips.
  - The last `make run` logged a Twilio "401 Unauthorized": the Twilio login looks wrong.
  - The Groq key still cannot use the engine's model, so calls drop to keypad after two
    spoken answers.
  - The current engine has never taken a real phone call (the Sept calls were the old code).
- **Found — adding a scheme today** is 11 hand steps, runs over the whole list every time, and
  the voice step would also make clips for all 16 waiting schemes. About half a rupee of Muse
  and 3,200 characters of Sarvam voice per scheme so far.
- **Waiting on the owner:** the five choices in `PLAN-DASHBOARD.md` §10. Step E1 needs nothing
  from the owner and can start on his word.

### 3 Oct (night) — Plan for the dashboard (`PLAN-DASHBOARD.md`). Nothing built yet.
- **Added — a plan, not code.** The owner wants the UI to be the front door: a CRM-style site
  on Vercel with a "call my phone" button, call logs, the scheme list, API use, the plan and
  architecture, and settings for keys. `PLAN-DASHBOARD.md` says what pages it has, how it
  works, how it is hosted, how it stays safe, and the build steps D0 to D8.
- **The main finding.** The website can live on Vercel. The call engine cannot for now: it
  holds a live audio socket for the whole call and reads its clips from disk. So the site
  talks to the engine through the tunnel, with a secret token. When the laptop is off, the
  site still opens and says the engine is offline.
- **Checked.** The Vercel account is reachable from here (4 projects, none for Haqdaar yet).
- **Waiting on the owner:** the five choices in `PLAN-DASHBOARD.md` §8, then "go" for D0.

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

## 3 Oct 2026 — plan for questions the recorded clips cannot answer (nothing built yet)

**The problem.** A caller can ask "can I apply if the land is in my father's name?". Today the
app has no answer for that. It only plays clips made ahead of time.

**The plan, in four rungs, cheapest first.** (0) A word check, in a few milliseconds, to see if
the caller asked a question. (1) If the question is about papers, how to apply, money, or who can
apply, play the clip we already have for that scheme. (2) If not, the model picks the closest one
from a list of ready-made questions and answers for that scheme. (3) Only if nothing fits, write
and speak a new answer live, from the scheme's own text, and save it for next time.

**Rungs 0 to 2 break no rule.** Rung 3 breaks the "never make up a sentence live" rule, so it
sits behind a switch that is off until the owner says yes.

**Waiting on the owner:** OK on the plan, OK to change that rule for rung 3, and a working Groq key.

**Later the same night — plan changed after the owner's steer (still nothing built).**
The owner wants live answers that sound like a person, and fast. New plan: when the caller is
down to a few schemes, load all the text of those schemes into memory, so there is nothing to
search. A small fast model writes a short spoken answer in the caller's language. The first
sentence is spoken while the second is still being written, with a short human "one second" clip
first. First step is to measure the speed, before building anything.

**Same night — first numbers (new branch `step-7.0-live-answers`, app not changed).**
The new Groq key works. The old model name is gone from Groq; that was the 404. The big model
writes a short answer in about 1 second. Sarvam takes 2 to 3 seconds to speak one sentence, so
speech is the slow part. One test answer was wrong: the card says land in the family's name, and
the model told the caller "you cannot apply". So the model will be made to say the rule only,
never yes or no about the caller, and code will block such lines.

**Same night — the plan was stress-tested and the first work order is written.**
I ran 41 hard cases against the real model. Three things changed in the plan. One: the system
does not ask a model "is this a question?" any more, because that got 5 of 26 wrong; it tries
the normal answer first and only then treats the words as a question. Two: the model must say
the rule, never "you can" or "you cannot". Three: questions about the caller's own money or
application get no made-up reply. Sarvam's streaming speech works with our voice and starts in
0.3 seconds, so live speech can be fast. The work order for step 7.1 (answers as text only,
behind a switch that is off) is `PROMPT-ANTIGRAVITY-7.1-QUESTIONS-TEXT.md`. Nothing is built yet.

**NVIDIA as a backup for Groq — tested, not fast enough for a live call.** The owner gave an
NVIDIA key. I timed 12 of its free models. Only one answered, and it took 3.5 to 21 seconds. A
caller cannot wait that long. So on a live call the backup is a second Groq model, and after
that the recorded line. The NVIDIA key is kept for work done ahead of time, not on calls.

**The owner's idea tested: one small, well-prompted router decides what is a question.** It
works. On 50 hard inputs the small model (qwen) got 49 right in about half a second each. The
bigger model got 46 and was slower. So the keyword check is dropped and the work order for 7.1
now has the router decide, with fences in code around it. I also ran today's system three
times: it reads schemes well by keypad, but it answers no question.

**Keys, words and questions — the rules are now written down.** A key always beats speech. A key
means what the menu at that moment says. A spoken answer is read back; a key answer is taken at
once. A question never moves the call: it is answered and the same prompt comes again. I also
found a bug in today's app: a spoken "हाँ" or "नहीं" in Hindi script is not understood at the
yes/no turn, only Roman "haan". The fix is in the 7.1 work order.

**Two new asks from the owner: the caller's own words, and cutting in.** I checked the code for
both. Language: the line already writes down what the caller says in their own language; it does
not translate. But the router is not told which language it is reading, and it sees our answer
list only as English ids. Cutting in: a key pressed in a gap is kept and used for the next
prompt, even if the caller never heard that prompt. Speech during a clip is thrown away. The
line also does not know how much of a clip was heard. I gave the owner a plan: one gate that
stamps every key and every spoken turn with the prompt it belongs to. Nothing is changed yet;
the plan waits for his yes.

**The owner set me right on language.** He wants Sarvam to turn the caller's words into English,
and the router and the answer step to work on that English. I had read it the other way. This
is not tested yet. He also wants every way a caller can cut in (speaking over the line, double
key presses, a key and words together) planned now, with fixed rules first and AI only where
rules cannot decide. I gave him the short plan. Nothing is changed in the app.

**Tried to ring the owner; the phone company said no.** Twilio refused the call because calls to
India are not switched on in the account (one tick box in the Twilio console; only the owner can
do it). The server is ready and waiting. **Two work orders are ready for Antigravity.** First
`PROMPT-ANTIGRAVITY-7.0b-GATE.md`: fixed rules for double presses, random keys, a key in a gap,
and a key after speech, with every event logged. Then the 7.1 work order, which now says: the
caller's speech is turned into English, worked on in English, and the answer is turned back into
the caller's language. I tested that on 5 saved clips: Sarvam's English is good and just as
fast. One of Sarvam's two translators got money amounts wrong, so the work order uses the other
one and has code check the numbers.

**Step 7.0b (the key rules) is checked, fixed, and tried on a real call.** Antigravity built it
and its tests passed, but I found faults the tests did not see. The worst: on a real line every
key press would have been used twice, once for its own question and once for the next. Also a
key pressed too early could cut off the next question and then be thrown away, leaving silence.
I fixed these and added tests that go through the real key path. All 518 tests pass. Then I
rang the owner: two keys pressed, each counted once, the hang-up was logged cleanly. He hung up
before trying the hard cases (fast presses, wrong key, speaking then pressing), so those are
proven only in tests, not yet on the phone. Three smaller gaps are written in the notes.
Nothing is committed.

**All of step 7 is built: a caller can now ask a question and get a spoken answer.** It is all
behind five switches that are off, so the app behaves as before until they are turned on.
What is new: a caller's question ("how much money comes in PM Kisan?") is spotted, answered
in one or two short sentences from the scheme's own text, and the call goes back to where it
was. The words go to English first, the answer is written in English, checked by code (no
yes/no about the caller, no number that is not in the text), and turned back into Hindi or
Marathi. On a real call the answer is spoken in the same voice as the recorded lines. The
caller's voice can also stop a line that is playing. I ran a full typed call with the real
models: four questions at four different points, all answered in Hindi in about 1.2 seconds
each. 653 tests pass. **Not yet tried on a real phone**: the spoken answer and the voice
cut-in. That is the next thing to do, with the owner on the line. Nothing is committed.

**The greeting is fixed and Marathi is paused.** The owner heard the greeting say everything
three times. The English part was reading all three choices again. Now it says hello once in
Hindi with "press 1 for Hindi", then in English "For English, press 2", and stops: 7 seconds,
down from 19. Marathi is kept in the system but not offered, and the star key no longer
switches to it; one setting brings it back. **A mistake of mine:** the command that records
new clips ran wider than I meant and recorded about 142 clips for schemes that are not in use
yet, before I stopped it (about 19,000 characters of Sarvam speech; not Muse). The clips are
kept and will be used when those schemes go live. **A new fixed test for cutting in:** 24
kinds of caller action, put in at every point of two whole calls, 1,200 runs, the same every
time. All pass. 1,859 tests pass in total. What it cannot prove is timing on a real line.

**The owner's two answers, and one more check of the whole system (4 Oct, later).** The greeting
stays keys-only; the owner agreed. Keeping words spoken in the 1 to 2 seconds while an answer is
being made: the owner is still thinking, so it stays as it is (words dropped, a key is kept).
Nothing new was built. Checked again: all 1,859 tests pass, one test call in the terminal ends
the right way, 1,000 random callers give 0 crashes and 0 wrong answers, the code compiles, the
brain is in sync, Muse spend today is ₹0. Still nothing is committed, and the new parts have
still not been heard on a phone.

**Second phone test with the new parts on (4 Oct).** The owner asked a question while the
results were being read. The line stopped, and then nothing was said for about 20 seconds.
Cause found in the log: when a voice stops the reading, every clip waiting to play is thrown
away; the question was not understood the first time (most likely the model service was busy),
so the call moved on in silence. A second fault: the call lost track of which scheme the caller
was hearing, so the answer it did write was about the wrong scheme. The owner also asked for a
"one moment" line, a shorter first script, voice cut-in at any time, and better speed and
pauses. Nothing is built yet; a plan is with the owner.

**The consent line is off (4 Oct).** The owner said it is not needed for now. The call no longer
says "this call is recorded" after the language pick; that saves about 8 seconds. The line and
its clips are kept, and one setting plays it again. Calls are still logged as before. The owner
also set the aim in one line: a person you can talk to about schemes, with keys working as
well. The plan is now ordered around that. All 1,859 tests pass; nothing is committed.

**Third phone test: a long quiet after "press 1" (4 Oct, late night).** The owner pressed 1 for
Hindi and then heard nothing for about 18 seconds. Cause found in the log: three new lines
("what do you want to know", "I did not get your reply", "one moment") were written but their
sound was never made, so the call had nothing to play and just waited. When a sound file is
missing the call does not fall back to anything; it stays quiet. The owner asked for a plain
map of the system first, then the fix. The map is given; nothing is changed yet.

**The quiet is fixed; a simpler plan is on the table (4 Oct, late night).** If a line has no
sound, the call now says an older line that has one, so it can not go quiet again; the server
also names such lines when it starts. All 2,293 tests pass (one old known failure stays). Not
committed, not yet heard on the phone. Checked the owner's point about old clips: all scheme
clips are already made and nothing needs to be paid for them; only the three new lines were
never made (9 small clips). The owner put forward a simpler design: keys follow a fixed path,
and for speech the model reads a running log of the call plus a search over the schemes. Most
of the parts are there already; a plan in six small steps and a few questions are with the owner.

**The missing sounds are made; the live set is now 17 schemes (4 Oct, late night).** The owner
said yes to the nine clips and to a new snapshot. Both are done. The new snapshot needed six
more very small clips (new age groups), so those were made too: 15 clips, 460 characters in
all. Every line now has sound in all three languages. All 2,293 tests pass. The owner also set
the frame: this is a hackathon proof of concept, the model works in English, no work on "model
is down", one ordered log that the model reads, a small fast model, and work done side by side
for speed. Next: hear the fix on the phone, then build that path step by step.

**The plan is agreed; building starts in a new chat (4 Oct, late night).** No code was written
in this last part. The plan in short: keys keep their fixed path. For speech, one small fast
model works in English and reads one ordered log of the whole call, so it can talk like a person
who learns about the caller turn by turn. If the caller is unclear it asks a clarifying
question; after two or three tries it reads the key list. If the line is fully quiet it says
"we are waiting for your reply" after about 30 seconds and hangs up about 30 seconds later;
noise on the line does not count as quiet. Speed work comes last, after each stage is timed.
The steps are in `.agent/TASK.md`.

**Saved, and the first build step is written out (4 Oct, late night).** The pause fix and the
17-scheme snapshot are committed (step 7.10). The next step, T1, is the silence and unclear
rules; its work order is in `.agent/TASK.md`. It starts in a new chat. The owner will try the
whole system on the phone after each step before the next one starts.

**T1 built: the silence and unclear rules (4 Oct, night). Not committed, waiting for the phone check.**
Folder `~/code/haqdaar-v2-7.3`, branch `step-7.11-silence`. No money was spent.
- *Added.* If the line is fully quiet, after about 30 seconds the agent says "we are waiting
  for your reply" and asks again. After about 30 seconds more it says goodbye and hangs up. It
  is the same at every stage of the call. At the language pick it plays the greeting again, as
  no language is known yet. Three settings: `SILENCE_REMIND_S` (30), `SILENCE_HANGUP_S` (60),
  `UNCLEAR_TRIES` (3).
- *Changed.* The old rule was three short waits of 6 seconds. Unclear words now get three tries
  (it was two) at the opener and at each question, then the key list. A good key, a good answer
  or an answered question starts the count again. Quiet no longer counts as an unclear try.
- *Not done yet.* The new line has no voice clip. Until the words are agreed it plays the old
  "I did not get your reply" clip in its place. A burst of noise is not counted as quiet, but a
  low steady hum, or any sound while the agent waits for a key only, still is.
- *Checks.* pytest 2,318 passed and the 1 known side-folder failure; stress 1,000 callers, 0
  crashes, 0 truth failures; barge-eval 62,082 cases, the same checks pass and fail as before.

**T1 fixed after the phone check and saved (4 Oct, night).** Commit `4b7ef6f`, branch
`step-7.11-silence`, folder `~/code/haqdaar-v2-7.3`. No money was spent.
- *Changed.* Only a key or real words now count as a reply. A cough or room sound with no words
  is dropped: it does not start the wait again, and it is not a wrong try at the language pick.
  So no reply twice in a row ends the call at every stage, noise or not.
- *It can now:* remind at about 30 seconds of no reply and hang up at about 60; give three tries
  for unclear words, then the key list.
- *Still open:* the "waiting for your reply" clip (words not agreed yet, an old clip plays in its
  place). Next is T2, the call log; its work order is in `.agent/TASK.md`.
- *Checks.* pytest 2,324 passed and the 1 known side-folder failure; stress 1,000 callers, 0
  crashes, 0 truth failures; barge-eval 62,082 cases, same passes and fails as before.

**T1 finished: the owner's two asks (4 Oct, night).** Commit `a2d9320`, branch `step-7.11-silence`,
folder `~/code/haqdaar-v2-7.3`. Spend: 3 Sarvam requests, 102 characters.
- *Changed.* "We are waiting for your reply" now has its own clip in Hindi, Marathi and English
  (the owner said yes to the words). New snapshot `snap_20261004_161538`: 17 schemes, 582 clips.
  A caller who stays quiet at the opener now hears the reminder and then the key list once; a
  second quiet wait ends the call. Wrong keys stay at three tries (the owner agreed).
- *Checks.* pytest 2,325 passed and the 1 known side-folder failure; stress 1,000 callers, 0
  crashes, 0 truth failures; barge-eval 65,622 cases, same passes and fails as before.

**T2 built, NOT saved yet: the call log a model can read (4 Oct, night).** Branch `step-7.12-log`,
same folder, uncommitted. It waits for the owner's phone check. No money was spent.
- *Changed.* The call log (`logs/calls/<id>.jsonl`) now also holds, in call order: what each key
  meant ("pressed 3 = age 18-35"), what the agent said as text (caller's language and English),
  where a cut-in cut the agent (which clip, how many milliseconds in), and each answer the truth
  checks blocked, with the rule. Nothing the caller hears has changed.
- *It can now:* print a call as short English lines with `make log-text ID=<call id>`. This is
  the text the model will read in T4. The model does not read it yet.
- *New files.* `haqdaar/data/log_text.py` (clip name to words, and log to short text),
  `tools/log_text.py` (the command), `tests/test_log_text.py` (11 tests).
- *Known gaps.* The greeting on a real call is said by the phone part, not the engine, so it may
  not show as an "agent said" line. A live answer has no English copy. A cut-in gives time, not
  the exact word. False cut-ins stay only in the trace. Caller words are not put into English.
- *Checks.* pytest 2,336 passed and the 1 known side-folder failure; stress 1,000 callers, 0
  crashes, 0 truth failures; barge-eval 65,622 cases, scorecard the same as before.

**Step 7.14, B4: stage times and a faster first word (5 Oct).** Branch
`step-7.14-talk-rest`, folder `~/code/haqdaar-v2-7.3`. The owner's phone check is still owed. No new tool. Spend: a few Sarvam test sentences and three no-phone test calls.
- *Changed 1: times in the log.* Each talk turn's `act` row now also holds, in milliseconds: the
  end wait, speech-to-text, search, the model, the first voice, and the whole wait from the
  caller's last word. `make log-text ID=<call id>` shows them as one `TIMES` line per turn. The
  copy of the log the model reads has no times in it. Old logs still read fine.
- *Changed 2: the voice plays as it arrives.* Before, a new sentence was made whole and then
  played. Now its first sound goes out as soon as Sarvam sends it, and the next sentences are
  made at the same time. Switch: `LIVE_TTS_STREAM` (on in a talk call; `LIVE_TTS_STREAM=false`
  puts it back as it was). The keys call is not touched.
- *Numbers (no-phone caller).* Before: end wait 600, speech-to-text 380-700, search 50-80, model
  670-970, first voice 840-1370 for a new sentence; 2.0 to 2.8 s from the caller's last word.
  After: first voice 410-430 for a new sentence (two turns measured). So about half a second to
  one second less on a turn with a new sentence.
- *Sarvam ran out of credit in the middle (error 402).* The owner gave a new key the same day;
  it is in `.env` and works. The "after" calls were then run in full: the answer starts 1.2 to
  2.1 s after the caller's last word (worst 2.3), where it was 2.0 to 2.8 s. Saved as commit
  `42ec2a6` on `step-7.14-talk-rest`, pushed.
- *Seen, not changed.* The talk prompt is about 3,000 tokens (not 2,000), so the fastest model
  takes only two turns a minute and the third turn goes to a slower one. A true reply is
  sometimes refused by the old word list ("you will get" in "you will get an OTP"); the second
  try costs about one second. Both are for B6 (the 40-question score).
- *Checks.* pytest 2,378 passed and the 1 known side-folder failure; stress 1,000 callers, 0
  crashes, 0 truth failures; barge-eval 65,622 cases, the report is the same as before the
  change, line by line; all changed files compile; vault in sync.

## 5 Oct — all branches pushed to GitHub
- *Before.* Nothing from step 6 (dashboard) or step 7 (talk) was on GitHub.
- *Now.* Every branch is on GitHub (`haqdaar-v3`), each at the same commit as on this Mac.
  Checked against GitHub's own list. `step-1.9` was skipped: GitHub already has a newer one.
- *Not pushed.* Work that is not committed yet: the step 7.14 speed work in
  `~/code/haqdaar-v2-7.3` (times in the log, voice played as it arrives). It waits for the
  phone check and the word "commit".
- *Branch for the dashboard team:* `step-7.13-talk` (commit `d53b483`). It is the last one
  checked on the phone. It has the dashboard folder (Home + Live call page) and the new call log.
- *Note.* This network blocks GitHub on port 22. The push went over port 443.

**Step 7.14, B5 to B7: cut-in, stress, write-up (5 Oct).** Branch `step-7.15-cut-in` (off
`step-7.14-talk-rest`), folder `~/code/haqdaar-v2-7.3`. Commits `6d1d463` (cut-in) and `540ae07`
(stress tools), both pushed. Keys were not touched. The phone check is the owner's.
- *It can now: be cut in on.* With `CUT_IN_GATE=true` the agent listens while it talks. 600 ms of
  a real voice makes it stop. Then: two or more real words are the caller's turn. Fewer ("hmm",
  "ok ok"), or words the model says were not for it (someone talking in the room), and the agent
  says the cut sentence again from its start and goes on. No "sorry". With the flag off (the
  default) it is strict turns, just as before.
- *A noise is not a voice.* New free voice check (Silero, one 2 MB file in the repo, no new
  package, runs on this Mac). A hiss, a tone, claps and a hum at full loudness: the old loudness
  check called all four a voice, the new one none. It is used only when the gate is on.
- *Tried with the no-phone caller, gate on.* "Wait, tell me about pension" over the reply: it
  stopped and answered about pension 1.6 s later. "Yes yes, ok ok" over the reply: it stopped and
  went on from the cut sentence 1.4 s later. "Ramesh, bring the tea" over the reply: the same,
  1.1 s later. Two seconds of loud hiss over the reply: it went on talking.
- *Stress, no money: 2,552 scripted talk calls* (`make talk-eval`, about one second). Side talk, a
  real cut-in, "hmm", "ok ok", a noise, a long noise, a key and a hang-up, each put in at every
  place the agent speaks, with the gate off and on. Rules: the call always ends; never more than
  2.5 s of dead air; never the same line twice in a row; never a restart; never a spoken reply to
  side talk. Broken: 0.
- *Replay of the two real calls of 4 Oct* (their words; no sound was kept). The call that was
  all side talk: the agent said nothing, three times. The other: it asked what help is needed.
  No "sorry", no restart in either.
- *The 40 real questions were stopped after 4.* Reason, new and important: Groq's free tier has
  a limit of 200,000 tokens A DAY for each model. One talk turn is about 3,000 tokens, so one
  model gives about 65 turns a day, about 10 calls. The night's test calls used up the fastest
  model's day. The call still works: it moves to the next model, which is slower. What the 4
  questions gave: fastest model 3 of 3 right at about 0.5 s; the two others 3 of 4 right at about
  0.6 to 1.3 s. The model order stays. The full run is ready for another day: `make talk-questions`.
- *Fixed on the way.* "How much does PM Kisan give" was sometimes answered "I am not sure". The
  old word list holds "आपको ज़रूर" and found it inside "आपको ज़रूरी कागज़" (needed papers), so a
  true reply was refused twice. The second try is now told which words to avoid. The list itself
  is not changed (it is a truth guard).
- *Limits to know.* Words said in the first one to two seconds of a reply are not heard. A real
  voice near the phone still stops the agent for two to three seconds before it goes on. On
  speakerphone the agent may hear itself (no echo handling). The weakest of the three models
  writes broken Hindi.
- *How to run the demo call.* Strict turns: `cd ~/code/haqdaar-v2-7.3 && TALK_ONLY=true make call-me`.
  With cut-in: `CUT_IN_GATE=true TALK_ONLY=true make call-me`. Read the call after:
  `make log-text ID=<call id>` (it shows the times of each turn).
- *What is left for keys (the owner's part).* In a talk call a key after the language pick does
  nothing but stop the reply that is playing, and the log says "keys are off". To bring keys
  back: decide what each key means in a talk call (0 the list, # say it again, a number for a
  choice), hand a key to the same turn as spoken words, and do not let a key cut a reply unless
  it is a known key. The keys-only call (`TALK_ONLY` off) is untouched and still passes all its
  tests.
- *Checks.* pytest 2,388 passed and the 1 known side-folder failure; stress 1,000 callers, 0
  crashes, 0 truth failures; barge-eval 65,622 cases, the report the same as before, line by
  line; talk-eval 2,552 calls, 0 rules broken; all changed files compile; vault in sync.

## 5 Oct, about noon: after the owner's good call (replies off the point, sound cut)
- *What the call showed.* Call ...c18fba worked end to end. Two things were off. The line "one
  moment" was said three times and each time the answer chopped it after half a second. And the
  replies were sometimes off the point: one sentence was said twice word for word, "tell me more"
  gave everything at once, and right after telling the papers and how to apply it asked "shall I
  tell you the papers, or how to apply?".
- *Sound fix.* "One moment" is never chopped now: the answer waits behind it. It is also said
  later (1.6 s, was 1.0 s), so a usual turn has no "one moment" at all; only a slow turn does.
- *The tunnel is not the cause.* All the sound of a sentence is sent ahead at once and the phone
  company holds it, so a slow tunnel can not chop a sentence. Cloudflare can not be used in the
  hall (it needs a port the hall blocks). On a phone hotspot `make call-me` picks Cloudflare by itself.
- *Relevance fix.* On each turn the model now first writes what the caller wants, and it is told
  which scheme the talk is about and which parts of it were told (what it gives, who it is for,
  papers, how to apply) and which were not. It offers only the parts not told. "Tell me more"
  gives only the new parts.
- *Tested.* All tests pass (2,389 and the 1 known side-folder one). 2,552 scripted talk calls: no
  rule broken. With the real model, 9 turns: no sentence said twice, "more" gave only the new
  part, the offers were right.
- *Warning for the demo.* Both good models are at their limit of tokens for the day (200,000
  each). My 9 test turns used about 30,000 of the second model's, and a check of mine wasted
  6,000 more. Until the use of last night rolls off, a call can fall to the weak model (broken
  Hindi) or say "I am not sure". The ways out: the paid Groq tier, a second key, or few calls.
- *Run.* `cd ~/code/haqdaar-v2-7.3 && TALK_ONLY=true make call-me`. With cut-in:
  `CUT_IN_GATE=true TALK_ONLY=true make call-me`. Commit 8b20892, pushed.

## 5 Oct, about 12:45: second Groq key, Muse as a spare, two more fixes
- *Second Groq key.* It is in the settings file. When the first key is refused for its limit, the
  same question goes out again on the second key. It is a separate account, so the fast model
  answers again. This takes away the demo risk of this morning.
- *Muse.* It is wired in and its money guard is kept. But it is slow on this job: 8.6 seconds a
  turn at its lowest effort, 16.8 at "low" (Groq takes 0.6 to 0.9). So it is not in front and not
  on by default. It can be switched in as a last resort with one setting. If Muse has a smaller
  model, tell me its name and I will time it. Note: on this path the caller's words go to Muse.
- *Two more causes of replies off the point, found by the test calls and fixed.* (1) After the
  talk moved to one pension scheme, "how much money?" was answered about another one. Now such a
  reply is sent back once. (2) Right replies that ended with "shall I tell you the needed papers?"
  were thrown away and the caller heard "I am not sure": an old word check took "needed" for
  "you will surely get". Fixed for talk calls; a real promise is still refused.
- *Tested.* All tests pass (2,394 and the 1 known side-folder one). 2,552 scripted talk calls: no
  rule broken. Two test calls of 5 turns each on the real fast model: every reply on the point.

## 5 Oct, about 13:00: the call that "went dead" after the greeting
- *What happened.* Call ...e0b2b5: the greeting played, then nothing for 14 seconds, then it was
  stopped by hand. The phone company's own record says the call was never dropped: it stayed open
  until the stop. No key press reached the server.
- *The cause found.* At the greeting a talk call listened for a KEY only, and waited 30 seconds
  before saying anything. So a caller who says "Hindi", or just starts to talk, hears a dead line.
- *Fix.* At the greeting you can now say the language ("Hindi", "English") or press the key.
  Tested with a no-phone call that says "हिंदी": it went on in Hindi 0.7 seconds later.
- *So the next time can be proved.* The call log now says when the first sound from the phone
  came in, any gap of over a second in it, and at the end how much sound and how many keys came
  in and how many clips were played out. A real network fault will show there.

## 5 Oct, about 13:15: the call that kept saying the greeting again
- *What happened.* Call ...50a7a2: the greeting was said three times in 39 seconds and the talk
  never started. Key 1 was pressed and nothing came of it. "Hello" and a full Hindi question
  both got the greeting again.
- *Cause 1, proved from the call's own record.* A small sound with no words came just after the
  greeting. The code took that as "this question is over" and shut the door on keys. Key 1 came
  0.6 seconds later and was thrown away. This came in with the fix of 13:00 (voice at the
  greeting). The throw-away is written only in the detailed record, not in the log on screen.
- *Cause 2.* By voice, only the bare words "Hindi" or "English" pick a language. Any other
  sentence, even one in clear Hindi, counts as a miss and the whole greeting is said again. The
  speech service already knows the sentence is Hindi; that is not used.
- *Cause 3.* What the caller asks at the greeting is thrown away, so it has to be asked again.
- *Against the simple plan.* Search, the call log, the model and the question picker are all
  built. This call never reached them. The part that failed is the old keys gate at the greeting,
  which is not in the simple plan.
- *Not changed yet.* This was a look only; no code was changed. The small fix is ready to do:
  keep keys open after a stray sound, and let any real words at the greeting start the talk.

## 5 Oct, about 14:00: the owner's flow drawing, made into three full charts
- *What was asked.* The owner drew his own call flow and asked for three things: finish it
  (close the loops, add edge cases, keep his boxes where they are), a second chart with the
  cut-in, and a third with the keys as well. Then run the tests and say plainly how things stand.
- *What was made.* Three Excalidraw files in the folder `flow/`, with a plain picture of each:
  `1-talk-flow`, `2-talk-flow-barge-in`, `3-talk-flow-with-keys`. Black boxes are the owner's own.
  Orange is what was added. Blue is the cut-in. Green is the keys. Red is where the call ends.
- *Loops that are now closed.* After the caller hears a reply the line goes back to listening.
  Search results go back to the model. A reply that fails the truth check goes back to the model
  once. Quiet at the greeting and quiet in the talk both end: once a reminder, the second time
  goodbye. Side talk gets no reply and the line keeps listening.
- *How the built system differs from the drawing.* The greeting is still "press 1, press 2" in
  two languages, with no key 6. The language is fixed for the whole call; what Sarvam hears is
  not used. The search runs on every turn by code, not when the model asks, and it does not
  cover papers or how to apply. The model writes Hindi itself; there is no English-then-translate
  step. Keys and talk can not be mixed inside one call. The log, the keyword bits, the quiet
  rule, the truth check and the cut-in gate are built.
- *Checks.* The charts are drawn by a small script that also checks them: no box on a box, no
  line through a box, every box has a way in and a way out, every path can reach an end. All
  pass. They were not opened in Excalidraw itself. Code tests: 2,394 pass and the one known
  failure; 2,552 scripted talk calls with no rule broken. No app code was changed.

## 5 Oct, about 15:00: everything pushed, a clean branch, and a new plan
- *Everything is saved.* All loose work in every folder was committed and pushed to GitHub:
  the half-done keys edits and patch scripts of the main folder, the pace samples, the scratch
  probes. Two test-result files of 70 MB each were left out; the test writes them again.
- *A clean branch.* The new branch is `v5-clean`, in the main folder `~/code/haqdaar-v2`. It is
  the working code of today with the old paper taken out: 25 prompt files, five old plans, the
  audit, the scratch and work folders, and the dashboard. All of it is still in git on the old
  branches. The design vault (`haqdaar-v2-brain`) was kept; the owner decides.
- *The fallback.* The folder `~/code/haqdaar-v2-7.3` was not touched. A call can still be made
  from it as before.
- *A new plan.* `PLAN.md` has three phases, one for each flow chart: talk, then cut-in, then
  keys. It says what is built and what is not, the steps, the checks and the risks.
- *Clarifying questions first.* This was looked into. The rule that picks the question is
  already a fixed one (minimax: the question whose worst answer leaves the fewest schemes), with
  no model in it. But a second rule says "ask nothing when 4 or fewer schemes are left", and no
  kind of need has more than 4 schemes. So today a caller who says "my crops died" gets a list
  of schemes and no question. The fix is step 1.3 of the plan. It is not built yet.
- *The charts* now show this: the question is picked by fixed code from the keyword bits, and a
  situation gets up to 3 questions before any scheme is shown.
- *No app code was changed.* Only files were removed and papers written.

## 5 Oct 2026, evening: the repo made ready for step 1.1; the plan stressed with human-style talk

- *What was asked.* Go through every folder, find what could harm us, clean the repo, stress
  the plan, and think about how a real person talks ("no no, just tell me the scheme").
- *No app code was changed.* The rule stands: building starts on "start Phase 1".
- *Folder check.* Every folder was read. No key or secret is in git. Things that could harm us
  were found and are now step 1.0 of the plan: the make commands take the one Twilio number
  away from the fallback folder without asking; the server listens on the whole wifi; the
  `/stream` door takes anyone as a caller; two test commands spend many Groq tokens.
- *Cleaned.* 7 old snapshots that nothing used; an empty folder; old compiled files; old agent
  drafts and old task files (moved to `~/code/haqdaar-old-agent-files`, not deleted, as they
  are in no git branch). `make talk-questions` now needs `YES=1`.
- *Human-style talk, run on today's code with no model.* 55 cases are in
  `fixtures/talk_human.json`. What broke:
  - "I am NOT a farmer" is taken as a farmer. "I do not want a loan" is taken as a loan.
  - "PM Kisan", "MNREGA", "KCC", "PM Awas" are not found as scheme names; only the full written
    name is. So "answer first for a named scheme" can not work yet.
  - A scheme we do not hold (Ayushman, ration card, Ladli Behna) looks like any loose need.
  - "My husband was a farmer, I am a widow" makes the caller a farmer.
  - "For my mother" is not kept; the questions say "your age".
  - Two needs in one sentence: one is lost.
  - "One minute, I will get the paper": the line hangs up after about 60 s.
  - "I do not know" gets the same question a second time. There is no "just tell me".
- *The plan (added, nothing taken out).* Step 1.0 (safe before the first call). More ways a
  call can start, and the traps of the greeting, in 1.1. The fixes for the list above in 1.3.
  A new step 1.8 for follow-up talk: "the second one", "any other?", "will I get it?", "did not
  understand", "hold on", is it free, a caller in distress, "thanks" is not goodbye.
- *One thing to know for 1.1.* The greeting is a recorded clip. New greeting words cost a
  Sarvam render and a new snapshot. So 1.1 is in two parts: the three bugs first (free), the
  new words after.
- *The charts* have a new box, "how people really talk", and three more rule lines. All checks pass.
- *Checks.* 2,385 tests pass, none fail. 2,552 scripted talk calls break no rule.
- *Left for the owner.* The brain folder and its rule file still call themselves binding (D2,
  D8). The help-line numbers for a caller in distress must be checked (D5).

## 5 Oct 2026, night: the owner's answers written into the plan

- *The brain folder.* Only five design papers were kept, in `docs/old-design/`, as background.
  The rest, its sync tool and the rule file that called it "binding" were removed. No code used them.
- *The greeting.* Short, about 12 s: Hindi, Marathi and English each say "welcome to Haqdaar,
  speak in English or your own language, for keys press 6". Key 6 will work at the greeting
  from step 1.1, so the greeting does not promise what is not there. Languages by the place of
  the caller's number come later.
- *No help-line number.* Dropped. A caller in distress gets one kind sentence, then help.
- *"Will I get it?"* The line says who the scheme is for and what the caller told it. Never yes or no.
- *A smooth line.* New part of step 1.0: measure each call, test the network before ringing,
  keep connections open, connect again if the line drops. The real fix is a better network
  place (a hotspot now, a small cloud server later).
- *A gate after every phase.* All tests, five phone calls from a fixed list, the logs read, the
  cost counted. No next phase with a red line.
- *Checks.* 2,385 tests pass. 2,552 scripted talk calls break no rule. Charts pass.

## 5 Oct 2026, late night: three more answers from the owner

- *Greeting in five languages:* Hindi, English, Marathi and two more spoken in Mumbai and
  Maharashtra. Gujarati and Tamil were picked; it is one setting to change. Five languages
  take about 20 s, so a shorter line for the two new ones is offered in the plan.
- *One path for every language.* Hindi and English too: the caller's words become English, the
  model works in English, the reply is translated back by Sarvam.
- *The cloud server in Mumbai* stays in the plan as a path, with the set-up steps (section 8).
  Nothing is bought or built.
- Only the plan and the charts changed. The chart checks pass.

## 5 Oct 2026, late: two last choices

- *Greeting:* Gujarati and Tamil are right. They say a short "welcome, speak in your own
  language"; Hindi, English and Marathi say the full line. About 16 s in all.
- *Network:* a phone hotspot. No cloud server; no money is spent on it.

## 5 Oct 2026, night: Phase 1 step 1.0 built (safe and smooth line). Not committed yet. Not tried on the phone yet.

What the caller hears in a normal call is the same as before.

- *The number is not moved without a question.* `make call-me` and `make run` now say where
  the phone number points and ask before they point it at this folder. A small file in the
  home folder (`~/.haqdaar/number_holder.json`) remembers which folder took it last.
- *The server is closed to the outside.* It listens on this computer only. `/answer` takes
  only a request signed by Twilio; `/stream` takes only a call that `/answer` saw. The test
  route `/tone` and the open `/docs` pages are gone. A call is closed after 10 minutes.
- *Cheaper checks.* `make stage-check` sends a few words to each model, not 2,500 tokens.
  `make ear-check` is offline unless `ARGS=--live`. `make pipeline-scrape` makes a backup first.
- *Line report.* Every call's log ends with one row: why the line closed, the longest gap in
  the caller's sound, how far ahead our sound was sent, the slowest Sarvam and Groq reply, and
  how many times the stream dropped. The same is one line in `logs/server.log`.
- *Network test before the ring.* `make call-me` times three tiny requests to the tunnel,
  Sarvam and Groq (no cost). Slower than 2 s or no reply: it says "weak network" and does not ring.
- *Connections stay open.* Sarvam and Groq requests share one kept-open connection, and a
  network error gets one quick second try. A time-out is not tried again.
- *A dropped stream is opened again.* Twilio asks `/answer-again`; the same call goes on, and
  the sound that was cut is said again. After 3 drops or 60 s the caller hears, in Twilio's own
  voice, "the line dropped, please call again" (no recorded clip yet; that needs a paid render).
- *Dead code cut:* `TURN0_KEYS`, the `voice_demo` branch, four settings no code read, one stale pointer.
- *Switches, if a call fails:* `PHONE_CHECK=false` (Twilio check off), `LINE_RECONNECT=false`
  (connect-again off, the line then behaves as before).
- *Checks.* 2,429 tests pass. 2,552 scripted talk calls break no rule. 1,000 key callers: 0
  crashes, 0 truth failures. Cut-in scorecard: 65,622 runs, the same pass / fail rows as the
  morning's run on the old folder (its red rows are old and belong to Phase 2).
- *Not proven without a phone:* that Twilio's signature matches through the tunnel, and that
  Twilio really asks `/answer-again` when a stream drops. One phone call shows both.


## 5 Oct 2026, late night: step 1.0 pushed; step 1.1 part A built (the greeting door). Not tried on the phone yet.
- *Step 1.0.* The owner's phone call worked (replies felt a bit slow on the hall network). It is
  committed and pushed (a3958c6).
- *Added, step 1.1 part A (no cost).* In a talk call:
  - Any real words at the greeting start the talk. A full Hindi question is no longer "no
    language heard". The language is the one Sarvam heard: Hindi, Marathi or English; any other
    is Hindi for now.
  - Those words are the first turn. They are answered, and there is no second hello.
  - "hello?" or "haan?" alone gets the talk's short hello, not the whole greeting again.
  - A noise with no words no longer shuts the keys: noise, then key 1, works.
- *Checked, not changed.* Room sound does not reset the 30 s quiet rule; a test now pins it.
- *Not built yet (rest of 1.1).* The new greeting words (five languages): they need a paid Sarvam
  render and the owner's OK on the words. Key 6 at the greeting. The 60 s answering-machine rule.
- *Still true.* Words said WHILE the greeting plays are thrown away (that is step 2.3). "Hindi
  mein PM Kisan batao" picks Hindi and drops the rest.
- *Checks.* 2,448 tests pass, none fail. 2,552 scripted talk calls break no rule. Stress: 1,000
  callers, 0 crashes, 0 truth failures. Cut-in check: 65,622 runs, the same red rows as before
  the step (C4.voice, C7, C8, C15, C18.bed550, C18.bed900, 8 of C19).
- *What the project can do now.* A caller can start talking right after the greeting, in a full
  sentence, and gets an answer to that sentence.
- *Side folders, to merge later.* 1.3a (Muse) and 1.5a (Antigravity) started before 1.0. They are
  merged into this branch after the phone check of 1.1, 1.3a first.

**5 Oct, 4:25 pm — the call that cut after the Twilio message.** I read Twilio's own record of
that call. It lasted 13 seconds and Twilio never reached our app. That is Twilio's trial rule:
after its message you must press any key, or it hangs up. Our code was not at fault, so there is
nothing to fix in the app. Step 1.1 part A (the greeting door: any first words start the talk,
a key after a noise is taken) is now committed and pushed so it cannot be lost.
