You are taking over the HAQDAAR v2 project. This first job checks that everything works and
prepares a brief for the planner (Muse Spark). **Do not write or change any project code in
this job.**

Rules for this job:
- Work only in `~/code/haqdaar-v2`. Never use `~/Documents/haqdaar-v2`: it is an iCloud copy and hangs.
- Use `.venv/bin/python` (Python 3.11). The system `python3` has no `audioop`.
- Never print, copy or commit any key from `.env`.
- Do NOT run anything that calls a paid API: no `make pipeline-*`, `make render`, `make run`,
  `make call-me` or `make snapshot`. Only the commands below.
- Stop as soon as a step fails, and report exactly what failed with its output. Do not try to fix it.

Steps:

1. **Read these in order:** `HANDOFF.md`, `AGENTS.md`, `.agent/TASK.md`, `.agent/NOTES.md`,
   then `PLAN-V2.md` §2 (the design decisions) and §3 Phases 3–6.

2. **Git state.**
   - Run `git status -sb`, `git log --oneline -5`, then `git fetch origin`.
   - Expect branch `step-3.2-choose`, a clean tree, level with `origin/step-3.2-choose`, and
     latest commit `9c5ab0c` or later. If the branch is behind, run `git pull --ff-only`.

3. **Keys present.** Check names only, never values. Run:
   `grep -o '^[A-Z_]*=' .env | sort`
   Expect `MUSE_API_KEY`, `SARVAM_API_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
   `TWILIO_US_PHONE_NUMBER` and `HF_TOKEN`. Report any that are missing.

4. **Tests:** `.venv/bin/python -m pytest -q`. Expect 307 or more passed and 0 failed.

5. **Stress:** `make stress`. Expect `crashes 0   truth failures 0`. Copy the whole report
   into your answer.

6. **One call in the terminal:**
   `make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h" < /dev/null`
   It must end with `closing_farewell` and write a log in `logs/`.

7. **Muse spend so far:**
   `.venv/bin/python -c "from haqdaar.data.pipeline.muse import spent_inr; print(spent_inr())"`
   Expect about ₹3.93, well under the ₹60 cap.

8. **Write `MUSE-BRIEF.md`** in the repo root. It is the one file the owner pastes into Muse
   for planning, so it must stand on its own and stay under about 1,500 words. Plain, short
   words. Include:
   - what HAQDAAR is: a phone helpline that tells rural families in Maharashtra which
     government schemes fit them, in Hindi, Marathi and English, keypad first;
   - what is done (from HANDOFF.md §3) and today's check results from steps 4–7;
   - what is left, in order (HANDOFF.md §4);
   - the binding rules (HANDOFF.md §5, plus the design decisions from PLAN-V2.md §2 that
     affect the next steps);
   - the open owner decisions (voice for new clips, menu length, the 3 real calls);
   - the file map: one line for each main module in `haqdaar/` and `tools/`;
   - the ask to Muse: "Plan step 3.4-finish and 3.5 as small steps. For each step give: the
     files to touch, the change, the test that proves it, and the command to verify. Never
     plan anything that sends live caller audio or text to Muse."

9. **Record it.**
   - Add one line under the top of `.agent/NOTES.md` with today's check results.
   - Add a short entry at the top of the log in `PROJECT-UPDATE.md`: "Antigravity took over,
     checks passed/failed".
   - Commit `MUSE-BRIEF.md`, `.agent/NOTES.md` and `PROJECT-UPDATE.md` with the message
     "setup: checks + MUSE-BRIEF.md for planning", then `git push`.

10. **Report back in 10 lines or fewer:**
    - pass or fail for each of steps 2–7;
    - the path to `MUSE-BRIEF.md`;
    - anything that looked wrong.
    Then stop and wait.
