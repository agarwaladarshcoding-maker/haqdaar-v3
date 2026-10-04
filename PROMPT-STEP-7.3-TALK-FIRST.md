# STEP 7.3 — Talk-first opening

Goal: the opening becomes one line: "what do you want to know? Say it, or press 0 for the list." The nine choices play only on 0, or after two misses. Needs one new clip.

Run only when the owner says "start step 3". Paste this whole file to Antigravity as the work order. Do not merge. Stop and report when green.

## 0 Setup
- Work in `~/code/haqdaar-v2`. Never `~/Documents/haqdaar-v2` (iCloud hangs).
- Python is always `.venv/bin/python` (3.11). System `python3` is 3.14 and has no `audioop`.
- Branch from reviewed main: `git switch -c step-7.3-talk-first main` (main holds each reviewed step; confirm with Muse that step 2 merged).
- STOP guards: `git status` clean before you start. `.venv/bin/python -m pytest -q` green before you change anything — note the count.
- Keys live in `.env`, never committed. Never print a key.
- Line numbers below are from the 4 Oct map. Confirm each by name; lines move.

## 1 What exists
| Thing | Where | What it gives |
|---|---|---|
| Opener block | `haqdaar/engine/call.py:488-556` | opener prompt + full menu spoken upfront |
| Spoken sort | `haqdaar/model/router.py:75` `Model.opener` | sorts what the caller said |
| Keypad menu | `haqdaar/audio/phone.py:262` `PhoneAudio._menu` | chip + key_N clips + unknown suffix |
| Door A read/pick | `haqdaar/engine/call.py:74` `_door_a_read`, `:104` `_door_a_pick` | named-scheme jump |
| Door A matcher | `haqdaar/engine/door_a.py:156` `DoorA` | name matching |
| Clip texts | `haqdaar/audio/lines.yaml`, `haqdaar/data/pipeline/texts.py:49` | new line id to words to `make render` |
| Tests | `tests/test_door_a.py`, `tests/test_call_spoken.py`, `tests/test_gates.py` | door A, spoken path, gates |

How today: opener question + full keypad menu spoken upfront; no short "say it or press 0" line.

## 2 Build
1. Opener (`call.py:488-556`): speak one short line only: "what do you want to know? Say it, or press 0 for the list." Route speech through `Model.opener` / Door A exactly as today.
2. Full 9-choice menu (`PhoneAudio._menu`) plays only when the caller presses 0, or after two misses at the opener (a miss is silence or unclear; count it, log it).
3. New clip: add the line id in `lines.yaml`, words in `texts.py`, render with `make render`. Draft the wording in your report first — do not render until the owner approves the words.
4. Steps 1-2 rules stay green (never silent; one scheme at a time downstream).

## 4 Sweep rule (this step's lock)
- Extend `tests/test_barge_sweep.py`: the opener speaks exactly one line; menu clips play only after 0 or 2 misses. Name it `test_talk_first_opener`.
- Later steps must keep it green.

## 5 Tests and checks
- `.venv/bin/python -m pytest -q` — green, count must not drop.
- `make stress` — 1,000 random callers: crashes 0, truth failures 0.
- `make sim` typed call with the real models: fresh call shows one line; press 0 shows the list; silent twice shows the list.
- Phone script (owner): call 1 — hear one line, say a need ("I am a farmer"); call 2 — press 0, hear the 9-choice list; call 3 — stay silent twice, the list plays. Owner reads the log; fix; owner says "next".

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
