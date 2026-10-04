# STEP 7.2 — One scheme at a time

Goal: results are queued one scheme at a time: read the scheme, play its menu, wait, then the next. The engine's "current scheme" is then always the one the caller hears.

Run only when the owner says "start step 2". Paste this whole file to Antigravity as the work order. Do not merge. Stop and report when green.

## 0 Setup
- Work in `~/code/haqdaar-v2`. Never `~/Documents/haqdaar-v2` (iCloud hangs).
- Python is always `.venv/bin/python` (3.11). System `python3` is 3.14 and has no `audioop`.
- Branch from reviewed main: `git switch -c step-7.2-one-at-a-time main` (main holds each reviewed step; confirm with Muse that step 1 merged).
- STOP guards: `git status` clean before you start. `.venv/bin/python -m pytest -q` green before you change anything — note the count.
- Keys live in `.env`, never committed. Never print a key.
- Line numbers below are from the 4 Oct map. Confirm each by name; lines move.

## 1 What exists
| Thing | Where | What it gives |
|---|---|---|
| Result sequences | `haqdaar/engine/terminals.py:390` `terminal_sequence`, `:442` `render_terminal` | multi-scheme queue |
| Per-scheme blocks | `haqdaar/engine/terminals.py:193` `_render_schemes_sequence` | name to summary to section_menu blocks |
| Read-back driver | `haqdaar/engine/call.py:1409` `Engine._read_back` | `say()`s the queue today |
| Next/paging | `haqdaar/engine/call.py:1532,1562` `next_scheme_intro`, `:1522` `more_sequence` | move between schemes |
| Question check | `haqdaar/engine/call.py:298` `Engine._try_question` | answers from a scheme's text |
| Tests | `tests/test_terminals.py`, `tests/test_call.py`, `tests/test_barge_sweep.py` | sequences, call path, cut sweep |

How today: all survivors render into one clip queue, so "this scheme" is unclear after a cut.

## 2 Build
1. `_render_schemes_sequence` (`haqdaar/engine/terminals.py:193`): keep building per-scheme blocks, but hand them to the engine one at a time instead of one joined queue.
2. `Engine._read_back` (`haqdaar/engine/call.py:1409`): loop — say the scheme, say its menu, wait for input (a question / 9 is next scheme / hangup), then the next scheme. Set the engine's current-scheme to the scheme just read before each wait.
3. `_try_question` answers "this scheme" questions from current-scheme (a named scheme still jumps to that scheme).
4. Step 1's rule stays green: after any cut the engine says something before it listens again.

## 4 Sweep rule (this step's lock)
- Extend `tests/test_barge_sweep.py`: N matching schemes produce N separate waits, and current-scheme always equals the scheme last heard. Name it `test_one_scheme_at_a_time`.
- Later steps must keep it green.

## 5 Tests and checks
- `.venv/bin/python -m pytest -q` — green, count must not drop.
- `make stress` — 1,000 random callers: crashes 0, truth failures 0.
- `make sim` typed call with the real models: trigger 2+ matching schemes; check one scheme, menu, wait, next.
- Phone script (owner): call in; get 2+ schemes; ask about "this scheme" after a cut — answered from the scheme just heard; press 9 — next scheme reads. Owner reads the log; fix; owner says "next".

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
