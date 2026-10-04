# STEP 7.7 — Speed

Goal: re-record the clips at the new pace, after the owner hears three samples on the laptop.

Run only when the owner says "start step 7". Paste this whole file to Antigravity as the work order. Do not merge. Stop and report when green.

## 0 Setup
- Work in `~/code/haqdaar-v2`. Never `~/Documents/haqdaar-v2` (iCloud hangs).
- Python is always `.venv/bin/python` (3.11). System `python3` is 3.14 and has no `audioop`.
- Branch from reviewed main: `git switch -c step-7.7-speed main` (main holds each reviewed step; confirm with Muse that step 6 merged).
- STOP guards: `git status` clean before you start. `.venv/bin/python -m pytest -q` green before you change anything — note the count.
- Keys live in `.env`, never committed. Never print a key.
- Line numbers below are from the 4 Oct map. Confirm each by name; lines move.

## 1 What exists
| Thing | Where | What it gives |
|---|---|---|
| Render | `haqdaar/audio/render.py:254` `render` | clip render |
| Format/pace | `render.py:59` `wav_to_ulaw`, `:84` `stretch(ulaw, speed)` | offline fallback |
| Sarvam | `render.py:113` `SarvamTTS` | speaker/model/pace from `TTS_SPEAKERS/MODEL/PACE` tunables |
| Live TTS | `haqdaar/audio/live_tts.py:51` `speak` | live speak path |
| Slow replay | `tunables.py:119` | `#`-twice slow replay stretched at play time |
| Tests | `tests/test_render.py`, `tests/test_texts.py` | render + texts |

## 2 Build
1. Owner listens first: render 3 short samples at candidate paces on the laptop (`render` / `stretch` for pace mock-ups). Report them; the owner picks one. Do NOT re-record before the pick (open: too slow or too fast? full re-record is Sarvam spend).
2. Re-render all clips at the picked pace (`SarvamTTS`, tunables `TTS_SPEAKERS/MODEL/PACE`); rebuild the snapshot; verify every named clip exists.
3. Live TTS path (`live_tts.py` `speak`) uses the same pace.
4. Steps 1-6 rules stay green.

## 4 Sweep rule (this step's lock)
- Rendered clip durations match the picked pace within tolerance (spot-check, not every byte). Name it `test_clip_pace`.
- Later steps must keep it green.

## 5 Tests and checks
- `.venv/bin/python -m pytest -q` — green, count must not drop.
- `make stress` — 1,000 random callers: crashes 0, truth failures 0.
- Phone script (owner): after the pick + re-render, one call — all clips at the new pace, words clear. Owner reads the log; fix; owner says "next".

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
