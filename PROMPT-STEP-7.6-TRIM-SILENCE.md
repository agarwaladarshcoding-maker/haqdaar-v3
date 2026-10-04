# STEP 7.6 — Trim silence

Goal: when a clip is loaded, quiet at its start and end is cut to a short fixed gap. No new recording.

Run only when the owner says "start step 6". Paste this whole file to Antigravity as the work order. Do not merge. Stop and report when green.

## 0 Setup
- Work in `~/code/haqdaar-v2`. Never `~/Documents/haqdaar-v2` (iCloud hangs).
- Python is always `.venv/bin/python` (3.11). System `python3` is 3.14 and has no `audioop`.
- Branch from reviewed main: `git switch -c step-7.6-trim-silence main` (main holds each reviewed step; confirm with Muse that step 5 merged).
- STOP guards: `git status` clean before you start. `.venv/bin/python -m pytest -q` green before you change anything — note the count.
- Keys live in `.env`, never committed. Never print a key.
- Line numbers below are from the 4 Oct map. Confirm each by name; lines move.

## 1 What exists
| Thing | Where | What it gives |
|---|---|---|
| Load point | `haqdaar/audio/pool.py:119` `AudioPool.get` | reads `.ulaw` bytes into tier1 LRU; no trimming |
| Silence const | `haqdaar/audio/render.py:218` | only used for stub check today |
| Tunables | `haqdaar/contracts/tunables.py` | new gap const goes here |
| Tests | `tests/test_pool_fds.py`, `tests/test_mouth.py` | pool + mouth |

How today: clips play with baked-in leading/trailing silence.

## 2 Build
1. `AudioPool.get` (`pool.py:119`): after reading the `.ulaw` bytes, trim leading/trailing quiet to a short fixed gap; the new tunable (e.g. `TRIM_EDGE_MS`) holds the gap. Cache the trimmed bytes in the tier1 LRU.
2. Never trim to empty: silent stubs and short chips must survive. No new recording.
3. Steps 1-5 rules stay green.

## 4 Sweep rule (this step's lock)
- New unit tests with fixtures: loaded clip edge quiet is never more than the fixed gap, and no clip loads empty. Name it `test_trim_silence_at_load`.
- Later steps must keep it green.

## 5 Tests and checks
- `.venv/bin/python -m pytest -q` — green, count must not drop.
- `make stress` — 1,000 random callers: crashes 0, truth failures 0.
- `make sim` typed call with the real models: same flows, tighter clips.
- Phone script (owner): call in; listen to 3-4 clips — no dead air at start/end, no clipped words. Owner reads the log; fix; owner says "next".

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
