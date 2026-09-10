# Changelog: 2026-09-10 Adarsh Docs Rebuild Rev 27

## Author: Adarsh Agarwala
## Date: 2026-09-10
## Source: _staging/v2-rebuild/ merged into source-docs/ and synced to vault per 00-README.md §4

### Files Created
- `docs/contradictions.md` — Contradiction audit against ratified brain
- `docs/interfaces.md` — Four frozen signature blocks adhering to [[tickets/T17]]
- `docs/data-contract.md` — Scheme record, snapshot layout, five build gates, 46 lines, LOG schema
- `docs/test-plan.md` — Day-one tests, fixture specifications, property tests, ten acceptance calls, drills
- `docs/traceability.md` — Ticket to design to build step traceability matrix
- `docs/decision-log.md` — Supersession chains and ratified architectural decisions
- `docs/risk-register.md` — Decided debts vs open operational risks
- `docs/readme.md` — Rebuild overview and merge procedures
- `briefs/audio.md` — Module Brief: Audio ([[tickets/T17]] §5)
- `briefs/data.md` — Module Brief: Data ([[tickets/T17]] §5)
- `briefs/engine.md` — Module Brief: Engine ([[tickets/T17]] §5)
- `briefs/model.md` — Module Brief: Model ([[tickets/T17]] §5)

### Files Updated
- `docs/architecture.md` — Rewritten against [[maps/wayfinder-map|MAP rev 27]] with 11 Obsidian mermaid flow diagrams, restored frozen signatures, and Groq free-tier mitigations
- `docs/build-plan.md` — Expanded to 21 steps traced directly to tickets, incorporating lazy tiered audio pool and minimax planner
- `docs/prd.md` — Product requirements aligned with 14 Sep acceptance bar, explicit [[tickets/T04]] failure criteria, and presentation team deliverables

### Decisions Ratified
- **D8 (Lazy Tiered Audio Pool):** Preloading the entire audio pool in RAM (~4.5 GB at national scale) replaced by a three-tier architecture without modifying frozen signatures (`Corpus.audio` and `Corpus.chunks` return `RenderKey`, str):
  - **Tier 0:** Pinned in RAM (~35 MB for 139 lines + ~600 chips, bounded by frozen numbers).
  - **Tier 1:** Local SSD (`mmap` + byte-bounded LRU cache for scheme chunks, announced one turn ahead).
  - **Tier 2:** S3/R2 read-through (disabled on demo host).
  Zero-runtime-TTS is strengthened: lazy means read later, never synthesize later. 50 ms Mouth budget preserved.
- **D9 (Map Source-of-Truth Rule):** `maps/wayfinder-map.md` (latest by name and timestamp) is the single authoritative map; `maps/history/` is historical supporting record. The map remains solely Adarsh's to edit.
