# Agent Directives

**Start with `HANDOFF.md`**: where the code is, what is done, what is left, how to check it.
Work in `~/code/haqdaar-v2` (the Documents copy is in iCloud and hangs).

## State files (most important — follow these literally)
- Maintain `.agent/TASK.md`: an ordered checklist of the current task. Exactly one item marked in_progress at a time. Rewrite the file after completing each item — do not just track it in your head.
- Maintain `.agent/NOTES.md`: append findings as you discover them (file paths, function locations, why an approach failed, decisions made and the reason). Write these the moment you learn them, not at the end.
- At the start of every turn, if `.agent/TASK.md` exists, read it and NOTES.md before doing anything else. Treat them as the source of truth over your own recollection.
- Rationale to keep in mind: your context can be truncated at any point. Anything only in context is assumed lost. Anything on disk survives.

## Context hygiene
- Never run broad searches or read more than 3 files in this main thread. Dispatch the `explore` subagent instead and have it return only a summary.
- Never re-read a file you already read this session unless you edited it.
- Read files in parallel when you need several.

## Execution discipline
- Smallest correct change. No refactors, renames, or cleanup that wasn't asked for.
- State assumptions and proceed; only stop to ask if proceeding would clearly be wrong direction.
- Never claim a test passed, a build succeeded, or a file was written without having actually run it and seen the output. If you can't verify, say so plainly.
- Before declaring done: re-read `.agent/TASK.md` and confirm every item is actually complete, then run whatever the project's test/lint command is:
  - Test: `.venv/bin/python -m pytest -q`
  - Talk check: `make talk-eval`
  - Lint / Syntax Check: `python3 -m py_compile <the files you changed>`

## Output style
- No preamble, no "Great question", no restating my request back to me.
- Final summary: what changed and why, a few lines. Not a file-by-file inventory.
