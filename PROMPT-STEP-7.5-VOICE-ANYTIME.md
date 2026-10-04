# STEP 7.5 — Voice at any time

Goal: the greeting — the caller's voice stops it and the language spoken is picked; if unclear, it asks for a key. The busy gap — the ear stays on, and if the caller speaks again the old answer is dropped and the new words are used.

Run only when the owner says "start step 5". Paste this whole file to Antigravity as the work order. Do not merge. Stop and report when green.

## 0 Setup
- Work in `~/code/haqdaar-v2`. Never `~/Documents/haqdaar-v2` (iCloud hangs).
- Python is always `.venv/bin/python` (3.11). System `python3` is 3.14 and has no `audioop`.
- Branch from reviewed main: `git switch -c step-7.5-voice-anytime main` (main holds each reviewed step; confirm with Muse that step 4 merged).
- STOP guards: `git status` clean before you start. `.venv/bin/python -m pytest -q` green before you change anything — note the count.
- Keys live in `.env`, never committed. Never print a key.
- Line numbers below are from the 4 Oct map. Confirm each by name; lines move.

## 1 What exists
| Thing | Where | What it gives |
|---|---|---|
| Greeting | `haqdaar/audio/phone.py:78` `select_language` (`greeting_trilingual`) | says the greeting; not bargeable today |
| Greeting call | `haqdaar/engine/call.py:395-398` | no `wait_input` around it today |
| Gap wait | `haqdaar/audio/turn.py:289` `wait` / `wait_input` | gap length `SILENCE_GAP_S` (`tunables.py:62`) |
| Gap guards | `turn.py:238` G5; `:220` G3/G4/G8 drop extras | today extras are dropped, not newest-wins |
| Ear | `haqdaar/audio/ear.py:671` `listen`, `:794` async, `:606` `watch_voice` | speech listen |
| Tests | `tests/test_ear.py`, `tests/test_turn.py`, `tests/test_live_speech.py` | ear, gates, live speech |

## 2 Build
1. Greeting: wrap it in barge-in. Voice stops the greeting; run the language pick on what was heard; if unclear, ask for a key as today.
2. Busy gap: keep the ear on during the gap. If the caller speaks again, drop the old answer and use the newest words (change the G3/G4/G8 drop-extras path for this case only; keep the G5 guard).
3. Steps 1-4 rules stay green.

## 4 Sweep rule (this step's lock)
- Extend sweep tests: speech during the greeting picks the language; speech during the gap replaces the pending answer. Name it `test_voice_at_any_time`.
- Later steps must keep it green.

## 5 Tests and checks
- `.venv/bin/python -m pytest -q` — green, count must not drop.
- `make stress` — 1,000 random callers: crashes 0, truth failures 0.
- `make sim` typed call with the real models + `make ear-check` as fits.
- Phone script (owner): call 1 — speak over the greeting in Hindi, Hindi is picked with no key asked; call 2 — mid-answer speak a new question, old answer is dropped and new words are used; mumble once — asked for a key. Owner reads the log; fix; owner says "next".

## 7 Do not
- One caller at a time. No concurrency, no queues/pools/semaphores.
- Nothing in Mouth or the socket loop may block.
- Every clip the snapshot names must exist (`texts.py` is the one list; a test checks they match).
- Keypad menus: at most 9 choices; 0 means "don't know".
- Paid APIs sit behind ledger + cap. A test must never reach one (`tests/conftest.py` blocks Muse; fake your clients).
- Answers come only from scheme text. If the text lacks the answer, say you do not know.
- Smallest correct change. No refactors or renames outside this step.
- Plain short words. Add an entry to `PROJECT-UPDATE.md`; update `.agent/TASK.md` and `.agent/NOTES.md`.
- Do not merge. Report: files changed, pytest + stress output, what to try on the phone.
