# REVIEW.md — paste into Claude Code after every step

**Usage:** open Claude Code in the repo root, on the step's branch, and paste the block below with `N` replaced.

---

```
Review Step N of brain/docs/BUILD-PLAN.md on the current branch.

Read first, in this order:
1. AGENTS.md
2. brain/docs/BUILD-PLAN.md → Step N (goal, files, spec, done when, review focus)
3. brain/docs/ARCHITECTURE.md → sections the step touches
4. Every ticket the step names, in brain/

Then check, and report each item as PASS / FAIL / FIXED:

A. Scope
   - Only the files the step lists were created or changed (plus tests). List any others.
   - Nothing from a later step was started.

B. Done when
   - Run the step's "Done when" command yourself. Paste the real output.
   - If it needs a phone call, say so and list exactly what Adarsh must check.

C. Architecture
   - Imports obey: Audio imports nothing from engine/model/data;
     filter.py, planner.py, terminals.py import only contracts/;
     the runtime never imports data/pipeline/.
   - The word "twilio" appears only under haqdaar/audio/telephony/.
   - contracts/ holds types and numbers only, no logic.
   - Signatures match T17 in the vault. If ARCHITECTURE.md and T17 disagree, T17 wins.

D. v1 safety (every step, even if it seems unrelated)
   - No string containing "eligible", "qualify", "entitled", "you will get", "you can get"
     (or पात्र / हकदार / मिलेगा / मिळेल) is spoken outside a verbatim source section,
     except the brand in closing_farewell.
   - No scheme name is sequenced before a non-exact terminal's preamble.
   - No free text from the model reaches Engine; every value is in its closed set with a span found in the transcript.
   - A scheme failing a hard box (state, gender, social_category) is never spoken.
   - No live TTS, no live translation, no text generated at call time.
   - Model never raises; Log.write never raises; Corpus raises only at load.

E. Hygiene
   - No API keys or tokens in code, tests, fixtures or commit history of this branch.
   - Tests exist for the new behaviour and pass: run `make test`.
   - Numbers that might change live in contracts/tunables.py, not inline.

Fix every FAIL that is inside this step's scope, re-run tests, and commit with message
"review step N: <what you fixed>".

Do NOT fix things outside the step. List them under "Out of scope — for later".

End with a plain-language summary for Adarsh, max 8 lines:
- Is the step done? (yes / no)
- What you fixed
- What he must test by hand (phone call, listening) — exact actions
- Anything that contradicts the brain (quote the ticket)
- Safe to merge? (yes / no)
```

---

## When to go back to the planning chat instead

- The same step fails review twice.
- The review finds a contradiction between a ticket and the build plan.
- A step needs a decision that isn't in the brain (a new tunable, a new line, a new field).

Bring back the failing step number, the review summary, and the error output.
