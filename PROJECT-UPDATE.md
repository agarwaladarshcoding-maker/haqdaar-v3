# PROJECT-UPDATE — what HAQDAAR can do right now

**How this file works.** Every time we chat or finish something, I add one entry at the top of
the log (§3) and fix §1 and §2 so they stay true. Plain words only.
Each entry says: what was added, what was changed, and what the project can do at that point.

---

## 1 · What the project can do today (13 Sep, D-day is 14 Sep)

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
- `pytest -q` → **109 passed**.

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
