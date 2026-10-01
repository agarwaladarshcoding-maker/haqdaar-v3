# Phase 4+ plan — owner-free code steps (1 Oct 2026)

Every step below runs WITHOUT the owner: no listening, no live calls, no
decisions needed. One Antigravity prompt per step; each prompt follows the
shape of `PROMPT-ANTIGRAVITY-4.1.md` (setup, job, rules, verify, done-when).
Later prompts are written when the previous step merges — never whole-phase.

Owner keeps, in parallel: A2 read/listen verdicts, A3 voice/menu decisions,
3 real keypad calls, all merges + tags, live-voice passes, server-location pick.

| Step | Scope | Prompt | Status |
|------|-------|--------|--------|
| 4.1 | `haqdaar/audio/ear.py` (Sarvam STT + Groq fallback), speech fixtures, `tests/test_ear.py`, `make ear-check`, 3 nits | `PROMPT-ANTIGRAVITY-4.1.md` | MERGED 1 Oct (da2557a, pytest 331) |
| 4.2 | `haqdaar/model/` client + span guard; author ~21 utterances (9 exist); 30-utterance bake-off, p50/p95 in NOTES | `PROMPT-ANTIGRAVITY-4.2.md` | READY |
| 4.3 | `haqdaar/engine/door_a.py`; offline top-1 accuracy (3 forms × 40 schemes); live "<20 s" check stays owner | written after 4.2 merges | queued |
| 4.4 | Spoken answers + "if right press 1" confirmation (`call.py`, `turn.py`, `server.py`, `sim.py`); sim-path acceptance | written after 4.3 merges | queued |
| 4.5 | Voice-break → keypad fallback; forced-STT-failure test; `v1-voice` tag stays owner | written after 4.4 merges | queued |
| 5.1 | "Anything else?" loop + prefetch (cold ≤50 ms test) | written after 4.5 merges | queued |
| 5.2 | `tools/judge.py` on `DeliveryRecord` + hand-made pass/fail logs | written after 4.5 merges | queued |

Notes:
- 4.4/4.5 touch the live call path (`call.py`, `server.py`, `turn.py`) — prompts
  will carry the non-blocking + one-caller rules explicitly.
- 5.3 drills and 5.4 Indian adapter need the owner (live number) — not queued.
- Standing rule: each step ends pytest-green + `make stress` 0/0, or it is not done.
