# STEP 7.4 — "One moment" line

Goal: a short clip plays the moment the caller's words are taken as a question, and is cut when the answer is ready. Needs one new clip per language.

Run only when the owner says "start step 4". Paste this whole file to Antigravity as the work order. Do not merge. Stop and report when green.

## 0 Setup
- Work in `~/code/haqdaar-v2`. Never `~/Documents/haqdaar-v2` (iCloud hangs).
- Python is always `.venv/bin/python` (3.11). System `python3` is 3.14 and has no `audioop`.
- Branch from reviewed main: `git switch -c step-7.4-one-moment main` (main holds each reviewed step; confirm with Muse that step 3 merged).
- STOP guards: `git status` clean before you start. `.venv/bin/python -m pytest -q` green before you change anything — note the count.
- Keys live in `.env`, never committed. Never print a key.
- Line numbers below are from the 4 Oct map. Confirm each by name; lines move.

## 1 What exists
| Thing | Where | What it gives |
|---|---|---|
| Say path | `haqdaar/audio/phone.py:89` `say`, `:98` `say_text` | fixed clips + live TTS speak |
| Question check | `haqdaar/engine/call.py:298` `Engine._try_question` | where words become a question |
| Cut path | `haqdaar/audio/turn.py` `Mouth.clear()` via `wait_input` | how a clip is stopped |
| Clip texts | `haqdaar/audio/lines.yaml:29` onward, `texts.py:49` `fixed_line_texts` | new `one_moment` id goes here |
| Tests | `tests/test_mouth.py`, `tests/test_phone_call.py` | nearest; no filler tests yet |

How today: no filler exists (only comments in `prompts/kinds.py`, `confirm.py`).

## 2 Build
1. Add the `one_moment` fixed line: id in `lines.yaml`, words per language in `texts.py`, render. Draft the words first — do not render until the owner approves (needs the owner's yes; mind the SNAP limit).
2. In `_try_question`: `say(one_moment)` the moment words are taken as a question; cut it when the answer is ready, then say the answer. Clean cut: no overlap, no gap.
3. Must work on the voice path and the keypad path. Steps 1-3 rules stay green.

## 4 Sweep rule (this step's lock)
- New or extended tests: every question attempt says `one_moment` before the answer. Name it `test_one_moment_before_answer`.
- Later steps must keep it green.

## 5 Tests and checks
- `.venv/bin/python -m pytest -q` — green, count must not drop.
- `make stress` — 1,000 random callers: crashes 0, truth failures 0.
- `make sim` typed call with the real models: ask a question; filler speaks at once, then the answer; no overlap.
- Phone script (owner): call in; ask a question; hear "one moment" at once, then the answer; check the cut is clean. Owner reads the log; fix; owner says "next".

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
