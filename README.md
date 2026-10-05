# Haqdaar

A phone line that tells a caller about government schemes they may have a right to. The caller
can talk in their own language, or use keys.

**Start with `HANDOFF.md`.** The design is the three flow charts in `flow/`. The order of work is
in `PLAN.md`.

```
.venv/bin/python -m pytest -q      # tests
make talk-eval                     # 2,552 scripted talk calls
TALK_ONLY=true make call-me        # ring the owner's phone
```

## Folders
- `haqdaar/`: the app (audio, engine, model, prompts, data).
- `tests/`, `tools/`, `fixtures/`: checks, helper tools, test data.
- `snapshots/`, `data_cache/`: the scheme data the app reads.
- `flow/`: the flow charts and the script that draws and checks them.
- `haqdaar-v2-brain/`, `source-docs/`, `sync_vault.py`: the older design vault (Obsidian) and
  the tool that keeps it in step with its source files. `python3 sync_vault.py --status`.
