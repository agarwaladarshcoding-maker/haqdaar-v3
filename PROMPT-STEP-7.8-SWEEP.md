# STEP 7.8 — Whole thing

Goal: the cut-in test grows to cover every new rule (1,200 runs), then one long phone call.

Run only when the owner says "start step 8". Paste this whole file to Antigravity as the work order. Do not merge. Stop and report when green.

## 0 Setup
- Work in `~/code/haqdaar-v2`. Never `~/Documents/haqdaar-v2` (iCloud hangs).
- Python is always `.venv/bin/python` (3.11). System `python3` is 3.14 and has no `audioop`.
- Branch from reviewed main: `git switch -c step-7.8-sweep main` (main holds each reviewed step; confirm with Muse that step 7 merged).
- STOP guards: `git status` clean before you start. `.venv/bin/python -m pytest -q` green before you change anything — note the count.
- Keys live in `.env`, never committed. Never print a key.
- Line numbers below are from the 4 Oct map. Confirm each by name; lines move.

## 1 What exists
| Thing | Where | What it gives |
|---|---|---|
| Stress | `tools/stress.py:147` `run`, `:87` `check_truth`, `:70` `ScriptedCaller` | `make stress` (`N=1000 SEED=1`) |
| Cut-in sweep | `tests/test_barge_sweep.py:24` `SweepAudio`, `:158` `test_anything_at_any_point` | cut positions |
| Terminal sim | `haqdaar/sim.py:622` `_run_call`, `:182` `FakeAudio` | `make sim`, `make demo-fixture` |
| Live phone | `haqdaar/server.py:100` `answer` to `/stream` to `:209` `_run_engine`; `tools/call_me.py:18` | `make call-me`, `make call`, `make run` |
| Prior rules | `test_cut_is_always_answered`, `test_one_scheme_at_a_time`, `test_talk_first_opener`, `test_one_moment_before_answer`, `test_voice_at_any_time`, `test_trim_silence_at_load`, `test_clip_pace` | one per step 1-7 |

## 2 Build
1. Grow the cut-in test to cover every new rule: extend `test_barge_sweep.py` and `tools/stress.py` to 1,200 runs; every step 1-7 rule stays green inside the sweep.
2. Full pass: pytest green, stress 0/0, sim scripts, typed call with the real models.
3. One long phone call (`make call-me`, all QA switches on): talk-first, cut-ins, questions, 9-next, keys-only fallback after two speech fails. Owner reads the log; fix; owner says "next" — then merge.

## 4 Sweep rule (this step's lock)
- This step IS the sweep: 1,200 runs green, covering all seven prior rules. Name it `test_whole_call_sweep`.

## 5 Tests and checks
- `.venv/bin/python -m pytest -q` — green, count must not drop.
- `make stress` — 1,200 runs: crashes 0, truth failures 0.
- Phone script (owner): one long call mixing everything above. Owner reads the log; fix; owner says "next".

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
