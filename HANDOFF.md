# HANDOFF: start here (5 Oct 2026)

Haqdaar is a phone line that tells a caller about government schemes, by talk and by keys.

## Read in this order
1. `AGENTS.md`: the rules of work.
2. `PLAN.md`: what is built, what is not, and the order of work (three phases).
3. `flow/`: the three flow charts (open the `.excalidraw` files, or the `.png` pictures).
4. `.agent/TASK.md` and `.agent/NOTES.md`: the task in hand and what was found.
5. `PROJECT-UPDATE.md`: the story so far, in plain words, newest at the end.

## Where the code is
- Folder `~/code/haqdaar-v2`, branch `v5-clean`. Work here.
- `~/code/haqdaar-v2-7.3` holds the code as it was before the clean-up (branch
  `step-7.15-cut-in`). It is the fallback for a call. Do not work there.
- GitHub repo `haqdaar-v3`. Push over https; ssh is blocked on some networks:
  `git push https://github.com/agarwaladarshcoding-maker/haqdaar-v3.git <branch>`
- Python: always `.venv/bin/python` (3.11). Keys are in `.env`, never committed, never printed.

## What is where
- `haqdaar/engine/talk.py`: the talk loop. `haqdaar/prompts/talk.py`: its prompt.
- `haqdaar/engine/planner.py`: the question picker (minimax). `haqdaar/engine/filter.py`: the bitmask.
- `haqdaar/engine/talk_pick.py`, `talk_words.py`: how the talk loop uses those two.
- `haqdaar/data/scheme_index.py`: search. `haqdaar/data/log_text.py`: the log the model reads.
- `haqdaar/engine/call.py`: the keys path. `haqdaar/audio/`: ear, mouth, turn, phone.
- `tools/`: `run_demo` (make call-me), `talk_probe` (a call with no phone), `talk_eval`, `stress`,
  `barge_eval`, `call_viewer`, `log_text`.
- `flow/build_flows.py`: draws and checks the charts. Change a chart there, then run it.

## Run
```
TALK_ONLY=true make call-me                      # ring the owner's phone, talk mode
CUT_IN_GATE=true TALK_ONLY=true make call-me     # the same with cut-in
make calls                                       # read the last calls
```

## Check
```
.venv/bin/python -m pytest -q     # 2,385 pass (5 Oct)
make talk-eval
```

## Limits to keep in mind
- One caller at a time.
- Groq: 8,000 tokens a minute and 200,000 a day for each model. A talk turn is about 3,000.
- Muse: Rs 30 a day. Run `make muse-status` before any step that spends on it.
