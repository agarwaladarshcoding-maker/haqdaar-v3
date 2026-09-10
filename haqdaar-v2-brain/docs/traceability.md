---
title: "Traceability — decision to ticket to doc to build step"
slug: traceability
type: module-note
module: architecture
status: reviewed
tags: [traceability, index, tickets, staging]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/MAP-done.md
---

# Traceability

**One row per closed ticket: what it decided, which document carries it, and which build step
implements it.** Use it in review — *"which ticket says this?"* should never take more than one
lookup, and a step with no ticket behind it is a step nobody ratified.

## Ticket → design → build

| Ticket | Module | Decided | Carried in | Built in |
|---|---|---|---|---|
| [[tickets/T01]] | Audio | Telephony provider; bidirectional WSS, μ-law 8 kHz, DTMF on the same socket. *Suspended for build by rev 25 — Twilio first, Plivo as a second adapter* | [[03-ARCHITECTURE]] §12 | Step 1 |
| [[tickets/T02]] | Data | What myScheme gives per scheme; exclusions arrive as their own block; **a third-party dataset fabricates rules on fetch failure** | [[05-DATA-CONTRACT]] §1 | Step 7 |
| [[tickets/T03]] | Audio | Sarvam `saaras:v3-realtime`, 8 kHz WSS, pinned per call. **Returns no confidence** | [[03-ARCHITECTURE]] §9 · [[briefs/audio]] | Step 13 |
| [[tickets/T04]] | cross | **The acceptance bar.** Ten calls, 8 must pass; three fail conditions; a laddered dead-end is a pass; seven survivable behaviours | [[02-PRD]] §5 · [[07-TEST-PLAN]] | Steps 18, 20 |
| [[tickets/T05]] | Audio | Get a number in hand | [[06-BUILD-PLAN]] Step 1 | Step 1 |
| [[tickets/T06]] | Data | One scheme record: five field groups, facets not rules, **`ANY` the only sentinel**, six read-back chunks, `summary` authored | [[05-DATA-CONTRACT]] §1 | Steps 2, 8 |
| [[tickets/T07]] | Data | The ingest **pass**, not a corpus. **N is a build parameter; nothing scales with N in human time.** The human is out of the loop everywhere | [[05-DATA-CONTRACT]] §3 · [[briefs/data]] | Steps 7–11 |
| [[tickets/T08]] | Data | The English hop; **the truth lock is suspended** — a recorded debt, not a repeal | [[03-ARCHITECTURE]] §11, §15 | Step 9 |
| [[tickets/T09]] | Engine | **Retained masks.** Box vector is the only state; survivors/tally/miss-set derived. UNASKED ≡ UNKNOWN to the filter. Hard-box miss → never spoken. Engine language-blind, no negation, no numerics | [[03-ARCHITECTURE]] §7.1 · [[briefs/engine]] | Step 3 |
| [[tickets/T10]] | Engine | **Seven-box roster**, hard/soft. **Minimax ÷ expected turns.** No mandatory questions — a **speaking rule** instead. **Three stops, 8 turns, 6-question wall.** Specificity orders survivors. Widening order. Cap-hit read-back | [[03-ARCHITECTURE]] §7.2–7.4 · [[briefs/engine]] | Steps 4, 5 |
| [[tickets/T11]] | Model | **Three fields, no confidence.** Five classes + precedence. Opener returns a list. **The span guard.** UNKNOWN a reserved value. Two-turn window. Two failures → keypad-only. *Provider line **superseded by map rev 27**: Groq free tier, two model moments per call, 429 = a [[tickets/T18]] failure. The contract itself is untouched* | [[04-INTERFACES]] · [[briefs/model]] · [[03-ARCHITECTURE]] §9 | Steps 14, 16 |
| [[tickets/T12]] | Model | **Door A is the opener**, via a `scheme` pseudo-box. Two searches. **Exempt from echo-confirm.** `t_name`/`t_end`. Candidate counts 1/2/≥3. **The alias field contract** | [[03-ARCHITECTURE]] §6 · [[05-DATA-CONTRACT]] §1B | Step 15 |
| [[tickets/T12b]] | Model | *(open, prototype)* Measure Door A on the real corpus — first evidence for the alias floor | [[09-DECISION-LOG]] §4 | after Step 11 |
| [[tickets/T13]] | Engine | *(open, prototype)* Dry-run the narrowing; carries the three-way context bake-off | [[07-TEST-PLAN]] · [[09-DECISION-LOG]] §4 | after Step 11 |
| [[tickets/T14]] | Audio | **Two clocks.** Checkpoint = the only completion signal. Silence ladder 6/6/6. 10-min ceiling. **First complete input wins.** `#` repeat. **NOISE vs SILENCE turn accounting** | [[03-ARCHITECTURE]] §9 · [[briefs/audio]] | Steps 12, 13 |
| [[tickets/T15]] | Audio | **Zero runtime TTS.** Flat content-addressed pool; **the snapshot is the manifest**; render key. Composition rule. Cardinality > 9 → UNKNOWN. `say`/`repeat`/`clear` | [[05-DATA-CONTRACT]] §2 · [[briefs/audio]] | Steps 10, 12 |
| [[tickets/T15]] **amended** | Audio · Data | **T15's *"~200 MB fits in RAM"* is demo-scale only** (~4.5 GB at ~2,500 schemes). **Zero runtime TTS and the flat pool are unchanged**; only preloading is replaced, by a pinned tier 0 + lazy `mmap`/LRU tier 1 + optional S3/R2 tier 2. **No frozen signature moves** — `Corpus.audio`/`chunks` return a key, not bytes | [[03-ARCHITECTURE]] §10.1 · [[05-DATA-CONTRACT]] §2 · [[09-DECISION-LOG]] D8 · [[10-RISK-REGISTER]] R18–R20 | Steps 11, 17 |
| [[tickets/T16]] | Data | **The trace explains, does not replay.** Per-turn schema. **Derive-don't-store**, with `stop` and `ladder_rung` the only exceptions. **No `terminal_state` field.** One file, two readers | [[05-DATA-CONTRACT]] §5 | Steps 6, 18 |
| [[tickets/T17]] | cross | **Four modules, three edges. Engine owns the loop.** The four frozen signature blocks. `contracts/` unowned. The fixture and the four day-one tests. **Four module briefs** | [[04-INTERFACES]] · [[briefs/audio]] · [[briefs/model]] · [[briefs/engine]] · [[briefs/data]] | Step 2 |
| [[tickets/T18]] | cross | **Three terminals; bad-news-first as an ordering lock.** Zero survivors = a fourth stop. Keypad-only is a **mode**. The forbidden-phrase build gate | [[03-ARCHITECTURE]] §8 · [[briefs/engine]] | Steps 5, 9, 16 |
| [[tickets/T19]] | cross | **Laptop + fixed tunnel domain.** Nothing is served. The sleep rule. Concurrency measured. **Three drills.** T20's edge cut | [[03-ARCHITECTURE]] §13 · [[07-TEST-PLAN]] §5 | Steps 1, 19 |
| [[tickets/T20]] | Audio | *(open, research)* Whether audio **and transcripts** may leave India. **Blocks nothing; post-demo** | [[10-RISK-REGISTER]] | — |
| [[tickets/T21]] | Data | **Provenance on the record**; `source_sha256` makes drift a diff. **No spoken date.** The freshness gate. Snapshots outlive logs | [[05-DATA-CONTRACT]] §1A, §3 | Steps 7, 9, 11 |
| [[tickets/T22]] | Data+Model | Closed by narrowing; the occupation cut folded into T07 | [[briefs/data]] | Step 8 |
| [[tickets/T23]] | Model | **46 lines, 139 files.** The confirmation ladder. Chip family replaces carriers. `0` = none-of-these. Two-tier gate + brand allowlist. The consent line | [[05-DATA-CONTRACT]] §4 | Steps 10, 12, 17 |
| [[tickets/T24]] | Audio | **Keypad-only language pin at turn 0.** Trilingual greeting, hi→mr→en. **`*` re-pins and clears nothing.** Codemix always. Turn 0 is not a cap turn | [[03-ARCHITECTURE]] §11 · [[briefs/audio]] | Steps 12, 13 |

## The never-mislead rules and what enforces each

Every rule in [[02-PRD]] §4 has a mechanism. **None of them is a code review.**

| Rule | Mechanism | Where | Test |
|---|---|---|---|
| No eligibility claim in any spoken line | **Two-tier forbidden-phrase build gate**, per language | Step 9 | scheme × gate table |
| Bad news before names | **Ordering assertion over the `say(sequence)`** | Step 5 | `test_terminals.py` |
| A barred scheme is never named | **Hard-box miss-set rule** in `Filter.speakable` | Step 3 | `test_filter.py` — S3 vs P1 |
| No sentence written at call time | **Zero runtime TTS**; the runtime imports no TTS client | Step 10 | an import test |
| No invented caller fact | **Span guard inside Model** — a type boundary, not a discipline | Step 14 | *"main kisan hoon"* ⇏ `income_band` |
| No out-of-set value | **Closed-set validation in code after the model returns** | Step 14 | `test_model.py` |
| No fabricated source content | **Host gate** on `source_url` + `source_sha256` drift check | Steps 7, 9 | gate table |
| Nothing spoken that cannot be finished | **Six-chunk render gate** — 18 manifest entries per row | Step 9 | fixture S6 rejected |
| The caller can name it | **Alias floor + uniqueness gate** | Step 9 | gate table |
| No unverifiable referral | **No helpline, website or number in any line** | Step 10 | inventory review |
| No spoken date | **Freshness is a gate, not a sentence** | Step 9 | inventory review |

## Frontier — open items, from the map

**No design decision remains open (rev 27).** Everything below is execution or measurement — with
the single exception of [[09-DECISION-LOG]] D3, the planner's scoring rule — **and that exception
is now closed: minimax, ratified 10 Sep 2026.**

| Item | State |
|---|---|
| [[tickets/T05]] + [[tickets/T19]] | **One errand.** Buy the number, point it at the dev domain, make the smoke call. *"The only open item that can fail the acceptance bar outright"* — survivable because [[tickets/T17]]'s duration-accurate audio stubs make the whole loop testable with no phone line |
| [[tickets/T07]] | **Head of the execution frontier.** Fully unblocked. Derives the band edges, the chip list, the occupation vocabulary and the provenance fields |
| [[tickets/T13]] + [[tickets/T12b]] | Prototypes. Share a snapshot, an utterance table and a session. Wait on T07 |
| [[tickets/T20]] | Research. **Blocks nothing, post-demo.** Residual is transcript transit |

## Related
[[01-CONTRADICTIONS]] · [[03-ARCHITECTURE]] · [[06-BUILD-PLAN]] · [[09-DECISION-LOG]] ·
[[maps/wayfinder-map]]

---
**Wayfinder Map:** [[maps/wayfinder-map|Latest Map]] · **Brain Index:** [[glossary|Glossary]]
