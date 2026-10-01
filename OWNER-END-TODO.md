# OWNER END-FILE — physical tests, decisions, tags (do at the end)

The owner cannot run physical tests right now, so everything needing ears, a phone, or
an owner decision is parked here. Code steps A–D do NOT wait on this file. Work it top
to bottom when physical testing is possible again.

## Decisions (no phone needed — can go first)

1. **Voice for the 18 new scheme clips.** AI4Bharat Indic Parler-TTS (free local samples
   in `logs/voice-trial/`) vs Bhashini (government, free). Blocks ONLY the 18-clip render
   + 30-scheme snapshot — nothing in steps A–D.
2. **Menu length.** Topic menu is 44 s in Hindi; age and occupation ~30 s each. Say fewer
   options, speak faster, or leave as is. A code change (if any) becomes a new step.
3. **Server location.** Laptop vs US machine. See the ear-check latency in
   `.agent/NOTES.md` (0.43 s avg measured 1 Oct; step D re-measures).

## Ears (headphones, no phone)

4. **Listen to the clips:** `make listen-cards L=hi N=10` and `make listen-cards L=mr N=10`.
5. **3.7 audit:** read the 20 cards in `data_cache/reports/audit_3_7.md` against their
   source pages, fill in the verdicts (all PENDING; tooling done, sample seeded).

## Phone (Twilio trial → the one verified number only)

6. **3 real keypad calls.** Listen, note what breaks.
7. **3 real voice calls** (after step D merges — needs the voice path wired).
8. **Door A live check:** say a scheme name, confirm it lands in under 20 s.

## Tags (after the above passes)

9. Tag `v1-keypad` (needs: 3.7 verdicts + 3 keypad calls OK).
10. Tag `v1-voice` (needs: 3 voice calls OK).

## Then

Phase 5 (solid: anything-else + prefetch, judge tool, crash restart, Indian phone
provider) and Phase 6 (10 outside callers, ≥8 PASS, tag `v1`) per `PLAN-V2.md` §3.
