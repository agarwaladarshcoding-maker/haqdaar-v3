# STEP 7.1 — Never silent

Goal: after the caller's voice stops a clip, the engine must say something before it listens again: the answer, or "sorry, say that again" plus the menu it was on. A missed question check is tried once more, and both tries are logged.

Run only when the owner says "start step 1". Paste this whole file to Antigravity as the work order. Do not merge. Stop and report when green.

## 0 Setup
- Work in `~/code/haqdaar-v2`. Never `~/Documents/haqdaar-v2` (iCloud hangs).
- Python is always `.venv/bin/python` (3.11). System `python3` is 3.14 and has no `audioop`.
- Branch from the step 7.0 base: `git switch -c step-7.1-never-silent step-7.0-live-answers`
- STOP guards: `git status` clean before you start. `.venv/bin/python -m pytest -q` green before you change anything — note the count (1859 on 4 Oct).
- Keys live in `.env`, never committed. Never print a key.
- Line numbers below are from the 4 Oct map. Confirm each by name; lines move.

## 1 What exists
| Thing | Where | What it gives |
|---|---|---|
| Call driver | `haqdaar/engine/call.py:387` `Engine.run_call` | sync one-caller turn loop |
| Cut-in gate | `haqdaar/audio/turn.py:298` `Turn.wait_input` (:324-387) | key-during-line cuts clip (G1), `Mouth.clear()` |
| Cut query | `haqdaar/audio/phone.py:145` `PhoneAudio.was_cut` | call.py uses it (:1445,1540,1570) to skip re-say |
| Question check | `haqdaar/engine/call.py:298` `Engine._try_question` | single `model.answer` try; exception goes silent False |
| Answer check + ledger | `haqdaar/model/answer.py:70` `check_answer`, `:84` `write_question_line` | check helper + question log line |
| Fixed-line texts | `haqdaar/audio/lines.yaml`, `haqdaar/data/pipeline/texts.py:49` | clip ids to words; render via `make render` |
| Tests | `tests/test_turn.py` (G1-G8), `tests/test_barge_sweep.py:158`, `tests/test_qa_engine.py` | gates, cut-at-every-point, QA engine |

## 2 Build
1. `Engine._try_question` (`haqdaar/engine/call.py:298`): when the check fails, try exactly once more. Log both tries with `write_question_line` (`haqdaar/model/answer.py:84`). Only then fall through to "don't know".
2. After any cut — voice (`SPEECH_CUT_IN`) or key (G1) — the engine must `say()` something before it listens again: the answer, or the "sorry, say that again" line plus the menu it was on. No cut path may return to `wait_input` with an empty mouth.
3. If the "sorry, say that again" line has no clip, add it: new id in `lines.yaml`, words in `texts.py`, render. The keypad-only path must keep working.
4. Keep the 5 QA switches working as today (all off gives the old call).

## 4 Sweep rule (this step's lock)
- Extend `tests/test_barge_sweep.py`: a cut at any point is always followed by speech before the next listen. Name it `test_cut_is_always_answered`.
- Later steps must keep it green.

## 5 Tests and checks
- `.venv/bin/python -m pytest -q` — green, count must not drop.
- `make stress` — 1,000 random callers: crashes 0, truth failures 0.
- `make sim` typed call with the real models: cut in twice mid-scheme; expect speech right after each cut, never silence.
- Phone script (owner): call in; cut in mid-scheme twice with a question; ask one question the text cannot answer — retry is logged and "don't know" is spoken. Owner reads the log; fix; owner says "next".

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
