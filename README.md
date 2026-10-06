# Haqdaar

A phone line that tells a caller about government schemes they may have a right to. The caller
can talk in their own language, or use keys. A photo (a crop, a paper) can come in by SMS, and
a person answers when the model is not sure. A call-back that is not picked up gets the answer
by SMS, as text plus a sound link.

**Start with `HANDOFF.md`.** The design is the flow charts in `flow/`. The order of work is
in `PLAN.md`.

```
.venv/bin/python -m pytest -q      # tests
make talk-eval                     # scripted talk calls
TALK_ONLY=true make call-me        # ring the owner's phone
make full                          # talk + keys + photo + call-back demo
```

## Folders
- `haqdaar/`: the app (audio, engine, model, prompts, data, keypad_sms, photo).
- `keypad_app/`: the keypad-phone SMS photo sender.
- `tests/`, `tools/`, `fixtures/`: checks, helper tools, test data.
- `snapshots/`, `data_cache/`: the scheme data the app reads.
- `flow/`: the flow charts and the script that draws and checks them.
- `docs/old-design/`: five design papers from September. Background only; `PLAN.md` wins.
