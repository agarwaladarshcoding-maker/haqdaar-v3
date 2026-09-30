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
- `pytest -q` → **152 passed**.
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
| `telephony/twilio.py` | Telephony wire codec (parse 6 inbound events, build 3 outbound events). |
| `telephony/__init__.py` | Isolates telephony wire codecs so vendor names never leak outside telephony. |

### Server and Tools
| File | What it does |
|---|---|
| `haqdaar/server.py` | FastAPI app exposing `/health`, `/answer` (TwiML Stream XML), `/stream` (audio WS). |
| `tools/tone.py` | 8 kHz μ-law 440 Hz 1-second pure tone generator (no WAV/RIFF headers). |
| `tools/run_demo.py` | `make call-me`: tunnel + server + rings your phone, in one command. |

### Other
| File | What it does |
|---|---|
| `haqdaar/sim.py` | The terminal call. `make sim`. |
| `fixtures/` | 5 test schemes, 3 test callers, sample sounds — used by the tests. |
| `tests/` | 108 tests across filter, planner, terminals, call, scrape, derive, corpus, twilio_codec. |
| `Makefile` | Short commands: `make test`, `make sim`, `make run`, `make pipeline-scrape`, `make pipeline-extract`. |

### Not written yet
`p3_translate.py` · `p4_gates.py` (Step 9) · render (Step 10) · `model/` · `ear.py` `mouth.py` `turn.py`.

---

## 3 · Log — newest first

### 30 Sep — the fixed lines can now get their Hindi and Marathi (waiting on Sarvam credit)

**First, a safety fix.** The last four steps (1.12 to 1.15) and 16 commits on `main` were only on
this laptop. The folder in `~/Documents` is inside iCloud, and iCloud had pushed 267 pieces of git
data off the disk, so every push hung. The copy in `~/code/haqdaar-v2` still had those pieces, so
the branches were moved there and pushed. **Everything is on GitHub now. Work in `~/code` from now on.**

**Added:** the translate step now also does the fixed lines (the 49 things the call always says,
like "Press 1 for yes"). It:
- skips any line you have fixed by hand (`pinned: true`) and any line already done;
- keeps the `{scheme_1}` style blanks exactly as they are;
- runs the same checks a scheme gets: numbers, no promises, not padded, really in Devanagari;
- writes only the lines that pass back into `lines.yaml`, and keeps the file's notes;
- remembers each result, so a second run costs nothing.

It is also part of `make pipeline` as the step "p4 lines".

**Blocked:** the real run was stopped by Sarvam: "No credits available". Nothing was written and
nothing was spent. It needs about 96 requests and 4,400 characters. Once the account has credit,
run `make pipeline-translate`. Then `make lines-sheet` gives you the sheet to correct.

**Tests: 258 passing** (was 253).

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
