# work-with-tools/ — the tool does the work

One file per day: `work-with-tools/<YYYY-MM-DD>.md`.

Each day file is a list of **orders**. One order = one build step = one branch.
Every order has the same four parts, in this order:

1. **Branch** — the `git checkout -b step-NN` line. Run it first, always (**R2**).
2. **Prompt** — the block to paste into Antigravity. Paste it exactly as written.
   It is finished. Do not shorten it, do not explain it, do not add to it.
3. **Verify** — commands you run yourself when Antigravity says it is done.
4. **Review + merge** — the block you paste into Claude Code, then the merge line.

**One order at a time** (**R3**). Do not paste order N+1 before order N is merged.
The only exception is marked **parallel** in the day file.

The full plan lives in [`WORK.md`](../WORK.md). This folder is just today's slice of it,
with nothing left to look up.

Your hands-only jobs are in [`work-adarsh/`](../work-adarsh/).
