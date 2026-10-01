# Combined 3+4 work — DISPATCH INDEX (details moved to step files A–D)

Flow: owner pastes ONE step prompt to Antigravity → Antigravity builds on its branch →
reviewer (Muse) checks, then merges to `main` → owner pastes the next step. One step at
a time, in order. Each step prompt has a base check: if the previous step is not merged,
Antigravity must stop and say so.

| Order | Prompt file | Branch | What |
|-------|-------------|--------|------|
| A | `PROMPT-ANTIGRAVITY-A-GATES.md` | `step-3x-gates-snapshot` | 7 gate fixes, 3 scheme fates, snapshot rebuild, stress 0/0 |
| B | `PROMPT-ANTIGRAVITY-B-DOOR-A.md` | `step-4.3-door-a` | 4.2-nits warmup + 4.3 Door A + offline accuracy |
| C | `PROMPT-ANTIGRAVITY-C-SPOKEN.md` | `step-4.4-spoken` | 4.4 spoken answers + "if right press 1", sim-proven |
| D | `PROMPT-ANTIGRAVITY-D-FALLBACK.md` | `step-4.5-fallback` | 4.5 ear/model wiring + keypad fallback + live API passes |

Base for A: `main` after the 4.2 merge. Base for B/C/D: `main` after the previous step
merges. Reviewer merges every step (`--no-ff`, re-verify pytest + stress on `main`).

Owner work (physical tests, decisions, tags) is NOT in these steps — it is collected in
`OWNER-END-TODO.md` for the end, when the owner can run physical tests again.

After D merges: Phase 3 + Phase 4 code is done. Remaining: Phase 5, Phase 6, and the
owner end-file.
