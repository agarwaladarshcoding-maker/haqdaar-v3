# STEP 7.7a — Pace samples (side branch, no spend)

Goal: the owner hears the same few lines at three speeds on the laptop and picks one.
This is only the first half of step 7.7. The full re-record (7.7b) waits for the pick
and for steps 7.3 and 7.4, because those add new clips.

Paste this whole file to Antigravity as the work order. Do not merge. Stop and report when green.

## 0 Setup
- This is a side branch. It runs at the same time as the main line (7.3 -> 7.4 -> 7.5), so it
  works in its OWN folder. Make it once:
  `cd ~/code/haqdaar-v2 && git worktree add -b step-7.7-speed ../haqdaar-v2-7.7 step-7.2-one-at-a-time`
  `ln -s ~/code/haqdaar-v2/audio ../haqdaar-v2-7.7/audio && ln -s ~/code/haqdaar-v2/.venv ../haqdaar-v2-7.7/.venv`
- Work ONLY in `~/code/haqdaar-v2-7.7`. Never edit `~/code/haqdaar-v2` (the main line is being
  written there) and never `~/Documents/haqdaar-v2` (iCloud hangs).
- `audio/` is a link to the real clips. Read only. Never write into it.
- Python is always `.venv/bin/python` run from the folder root (3.11). System `python3` has no `audioop`.
- First: `.venv/bin/python -m pytest -q` must be green. Note the count (2267 expected).
- Keys live in `.env`. This step needs none. Never print a key.

## 1 What exists
| Thing | Where | What it gives |
|---|---|---|
| Pace change | `haqdaar/audio/render.py` `stretch(ulaw, speed)` | changes speed of a clip offline, no API |
| Format | `haqdaar/audio/render.py` `wav_to_ulaw` | 8 kHz mu-law, the phone format |
| Pace now | `haqdaar/contracts/tunables.py` `TTS_PACE` (0.9), `SLOW_PACE` | what Sarvam was asked for |
| Clips | `audio/` through `haqdaar/audio/pool.py` `AudioPool.get` | the recorded lines |
| Listen tool | step 2.1 added one (see `Makefile`, look for `listen`) | plays a clip on the laptop |

Confirm each by name. Line numbers move.

## 2 Build
1. New tool `tools/pace_samples.py` and a `make pace-samples` target.
   - Takes 3 lines the caller hears most: the greeting, one scheme card, one section menu.
     In all 3 languages (en, hi, mr).
   - For each, writes 3 files with `stretch`: a bit slower than now, same as now, a bit faster
     than now. Pick the two side speeds so the change is easy to hear but still natural
     (about 10 percent each way). Speeds come from a flag, with those as the default.
   - Output: WAV files a laptop can play (`afplay`), in `scratch/pace-samples/`, named so the
     owner can tell them apart: `<line>.<lang>.<slower|now|faster>.wav`. Also print a small table:
     file, speed, length in seconds.
2. No Sarvam call. `stretch` is a mock-up: it shows the speed, not the final voice quality.
   Say that in the report.
3. Do not change `TTS_PACE`. Do not re-record anything. Do not rebuild the snapshot.

## 4 Test
- `tests/test_pace_samples.py`: with fixture clips, the tool writes 3 files per line, the
  slower one is longer and the faster one is shorter than "now", none is empty, and the
  source clip is not changed. Name the main test `test_pace_samples`.
- Do NOT edit `tests/test_barge_sweep.py`, `haqdaar/engine/call.py`, `haqdaar/audio/lines.yaml`,
  `haqdaar/audio/pool.py`, `PROJECT-UPDATE.md` or `.agent/*`. Other branches are editing those.

## 5 Checks
- `.venv/bin/python -m pytest -q` — green, count must not drop.
- `make pace-samples` — files written, table printed.
- `.venv/bin/python -m py_compile tools/pace_samples.py`

## 7 Do not
- No paid API of any kind. No `make render`. No Muse.
- One caller at a time. No threads, queues, pools.
- Smallest correct change. No refactors or renames.
- Plain short words.
- Commit on `step-7.7-speed` only. Do not merge, do not push.

## Report
Files changed, pytest count before and after, the table of sample files, the commit hash, and
the exact command the owner runs to hear them, for example
`afplay scratch/pace-samples/greeting.hi.faster.wav`.
Then the owner's question to answer: slower, same, or faster?
