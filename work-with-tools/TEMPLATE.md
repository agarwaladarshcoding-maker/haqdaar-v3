# <YYYY-MM-DD> — <weekday> · tool orders

**Days to D-day (14 Sep):** <n> · **Milestone in reach:** <…>
**Your hands-only list:** [`work-adarsh/<date>.md`](../work-adarsh/<date>.md)

**Today's shape.** <one paragraph: what goes to the tool, what was pulled out, and why>

| # | Step | Branch | Needs | Time in tool |
|---|---|---|---|---|
| 1 | **Step NN** · <name> | `step-NN` | <nothing / order N merged> | ~<n> min |

**If the day runs short, stop after order <n>.**

**Every terminal starts with:**
```bash
cd /Users/adarshagarwala/Documents/haqdaar-v2 && source .venv/bin/activate
```

---

## Order <n> · Step NN — <name>

```bash
git checkout -b step-NN
```

**Paste into Antigravity:**

> Implement **Step NN** of `haqdaar-v2-brain/docs/build-plan.md`. Follow `AGENTS.md`.
> Read <docs and tickets> before writing code.
> Work only on branch `step-NN`. Do nothing outside this step.
>
> Files: <exact paths, nothing else>
>
> Spec: <the step's spec, spelled out — never "see the plan">
>
> Hard rules:
> - <the review-focus lines from the build plan, as rules>
> - **One caller at a time (R1).** No queue, no worker pool, no concurrency setting.
> - Numbers live in `tunables.py`, never inline.
>
> **Done when** <the exact command and the exact assertions>.
>
> Finish by running <command> and pasting its real output.

**Verify:**
```bash
<the commands you run yourself>
```

**Then:** review block with `N = NN` → on yes:
```bash
git checkout main && git merge --no-ff step-NN -m "step NN: <name>"
```

---

## Review block — paste into Claude Code after every order

*(Copy the block from `WORK.md` §5 — it is the same every day. Change only `N`.)*

---

## Merge log — fill as you go

| Order | Step | Branch | Review said | Merged | Tag |
|---|---|---|---|---|---|
| | | | | | |

**End of day:** tell me what merged. I update `WORK.md` §1 and §6 and write both files for tomorrow.
