---
title: Data Module Overview
slug: data-module-overview
type: module-note
module: data
status: reviewed
tags: [module, data, corpus, myscheme, log, audit]
created: 2026-09-06
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: Antigravity
---

# Data Module Overview

**Module:** Data (Corpus / myScheme Scrape / LOG Trace)  
**Parent System:** [[projects/haqdaar/overview|HAQDAAR v2]]  
**Governing Rules:** [[RULES.md]]

---

## 1. Scope & Ownership

The Data module owns all scheme data pipelines, storage formats, and execution auditing:
- **myScheme Ingestion:** Scraping, normalization, and parsing of government schemes from `myScheme.gov.in`.
- **Corpus Versioning:** Management of immutable, version-pinned scheme snapshots.
- **LOG Storage:** Audit trail persisting caller decisions, applied filters, and rationale.
- **Audio Pre-render Pipeline:** Generating content-addressed cache files for all pre-computed prompts.

---

## 2. Invariants & Ratified Decisions (Initial)

1. **Snapshot Pinning:** A call binds to a specific corpus snapshot ID upon connection and holds it until hangup. Updates create new numbered snapshots; in-flight calls are never invalidated.
2. **Privacy Architecture:** Caller phone numbers are one-way hashed; raw call audio is destroyed at hangup.
3. **LOG Persistence:** The decision trace survives call termination to satisfy the acceptance bar: proving deterministically why each scheme was chosen.

---

## 3. Update (2026-09-09 — Ratified Decisions Rev 10, 11, 16)

### Scheme Record Schema & Facet Ingest ([[tickets/T06]], Rev 10)
- **Flat Facet Table:** One flat row per scheme; five field groups (identity/provenance, matching aliases, filtration facets, negative exclusions/`gate_notes`, and read-back chunks).
- **Exact Numerics:** Stored exact; expanded to closed-set bitmasks during offline snapshot build.
- **Six Read-Back Chunks:** `summary` (authored natively in ~35 words per language), plus verbatim `benefit`, `eligibility`, `documents`, `process`, and non-spoken `gate_notes`.

### Multi-Language Pipeline & Debt ([[tickets/T08]], Rev 11)
- **Truth Lock Suspended for 12 Sep:** Automated translations are shipped without per-line human signoff (recorded technical debt). English text remains ground truth.
- **Closed Keyword Vocabularies:** Inbound speech is mapped to a frozen keyword list (~150–200 items per language) via an English semantic hop. Outbound audio is strictly pre-rendered.

### The LOG Trace Specification ([[tickets/T16]], Rev 16)
- **Explains, Does Not Replay:** Raw audio is destroyed upon disconnect. Proof consists of text reconstruction from a single JSONL file per call (one line per turn).
- **Derive on Read:** LOG does **not** store masks, survivor tallies, or confidence scores. Any property deterministically derivable from `snapshot_id` and the ordered box vector is computed dynamically by the audit reader.
- **Stored Exceptions:** The only explicitly recorded execution branches are `ladder_rung` (when widening or stopping) and `stop_condition`.
- **Full Transcripts & Personal Data Debt:** Persisting verbatim transcripts across sensitive demographic slots (caste, income) is an accepted regulatory exposure for 12 Sep, necessary to audit `CLARIFY` and `UNCLEAR` turns.
- **Noise & Silence Line Logging:** `NOISE` produces a minimal line to make the 8-turn cap auditable. Keypad interrupts write `discarded_transcript` ([[tickets/T14]]). Turn 0 records language and `lang_source` ([[tickets/T24]]).

---

## 4. Update (2026-09-10 — Ratified Decisions Rev 19–22)

### Automated Ingest Pass & N as a Parameter ([[tickets/T07]], Rev 22)
- **Zero Human Time Scaling:** The pass runs completely unattended. No step in the ingest path waits on a person.
- **`facets_verified` Retired:** Demoted from a build gate to a tracking column `facets_source: derived | audited`. Model extracts facets against the closed sets. Verifier initials are dropped; row provenance consists of snapshot ID, scrape timestamp, and source URL. Sampling audit is handed to [[tickets/T21]].
- **Machine Generated Summaries:** `summary` (~35 words) is generated in English at ingest, then machine-translated to Hindi and Marathi like all other outbound text.
- **Fabrication Handled by Assertion:** Third-party dataset risks are eliminated by requiring scrape direct from myScheme with all four section anchors non-empty. Disclaimed portal Hindi/Marathi is bypassed entirely by translating our own English text.

### The Build Gates (Pre-Filter Architecture, [[tickets/T07]], [[tickets/T21]])
A scheme must satisfy all gates to enter a snapshot:
1. **Expressibility ([[tickets/T06]]):** Every facet resolves to a closed-set value or `ANY`.
2. **Alias Floor ([[tickets/T12]], [[tickets/T24]]):** $\ge 3$ aliases per language, stored as spoken, with $\ge 1$ code-mixed alias for non-English languages. Uniqueness gate drops aliases appearing on $\ge 3$ schemes (category words) and identifies exact-2 pairs as disambiguation candidates.
3. **Read-Back Completeness ([[tickets/T15]]):** All 6 read-back chunks rendered across all 3 languages (18 clips per row present in audio manifest).
4. **Forbidden-Phrase Lock ([[tickets/T18]]):** Regex check over read-back chunks and terminal lines ensuring no second-person eligibility claims (*"eligible"*, *"qualify"*, *"you will get"*, *आप पात्र हैं*, *तुम्ही पात्र आहात*) reach citizens while truth lock is suspended.
5. **Provenance & Freshness Gate ([[tickets/T21]]):** Host check (`source_url` on `myscheme.gov.in`), age check (`fetched_on` within `max_source_age_days` $\le 14$ in `contracts/tunables.py`), and sha256 drift check before freeze.

### Folding the Occupation Cut ([[tickets/T22]], Closed 10 Sep)
- Portal wizard rail and 18-box schema retired. The `occupation` value list is cut directly inside T07 from eligibility prose during ingest.
- **Closed Over Corpus:** A value is included only if at least one scheme discriminates on it.
- **Cardinality Constraint:** Target $\le 9$ values to retain keypad menu compatibility ([[tickets/T15]]). If $> 9$, `occupation` drops directly to `UNKNOWN` on fallback.

### Frozen Snapshot Layout & Contracts ([[tickets/T17]], Rev 20)
- **Artifact Layout:**
  ```
  snapshots/<snapshot_id>/
    schemes.jsonl      # Flat rows per T06
    masks.bin          # Packed (box, value) -> bitmask
    vocab.json         # Closed value sets + code map
    templates.json     # line_id -> {lang -> render_key}
    manifest.json      # Snapshot IS the audio manifest
  audio/<render_key>.ulaw  # Flat shared pool
  ```
- **Sizing Footprint:** Whole corpus audio pool is ~200 MB (8 kHz μ-law), held in RAM/local disk. No object store needed for 12 Sep ([[tickets/T19]]).
- **Runtime Interfaces:**
  - `Corpus`: Total at runtime; raises at `load()`, never mid-call.
  - `Log`: `write(line)` never raises or aborts a call; malformed lines write `invalid: true` to preserve structural evidence for [[tickets/T04]].
- **Fixture Curation:** Data owner curates the canonical 5-scheme fixture (match, soft-miss on `income_band`, hard-miss on `state`, generic `ANY`, alias-sharing pair) + 3 personas, which serves as T08's offline test base.

---

## 5. Update (2026-09-10 — Ratified Decisions Rev 24–27)

### Record Provenance & Freshness Gate ([[tickets/T21]], Rev 25)
- **Provenance Lives on the Record:** Flat fields in T06's identity/provenance group:
  - `source_url`: Official page on `myscheme.gov.in` captured by our scraper.
  - `fetched_on`: Date read by our scraper.
  - `source_sha256`: SHA-256 hash of the five captured English blocks (benefits, eligibility, documents, how-to-apply, exclusions). Makes drift detection a fast bitwise diff (`make refetch-check`) rather than requiring manual human re-reading.
- **Per-Language Origin & Verification Schema:**
  - `{lang}_sections_origin`: `source` (English) | `machine` (Hindi/Marathi) | `human`.
  - `{lang}_summary_origin`: `human` | `machine`.
  - `{lang}_verified_by` and `{lang}_verified_on`: Null for unreviewed machine translations for 12 Sep, recording the debt directly inside the data.
  - Verification rule: If either origin is `human`, `verified_by` and `verified_on` are strictly required. Null can only ever mean "no human touched this".
  - `facets_verified` gains `facets_verified_by` and `facets_verified_on` (null in v1).
- **Spoken Caveats & Freshness Bar:**
  - Ratified from [[tickets/T23]]: `section_source_frame` precedes every verbatim section (says *translated* in Hindi/Marathi).
  - **Never precedes `summary`:** The summary is our authored compression; attributing it to the official page is disallowed.
  - Never precedes names, terminals, or nearest schemes (nearest reads `summary` only).
  - **Freshness caveat refused:** Caller never hears a date. Freshness is enforced as a build gate (`max_source_age_days <= 14` in `contracts/tunables.py`), not an in-call spoken sentence.
- **Snapshot Retention Obligation & Audio Sweep:**
  - Derive-on-read in [[tickets/T16]] requires snapshot records and manifests to be committed to the repository and preserved as long as any LOG file that cites them.
  - [[tickets/T15]]'s mark-and-sweep rule is amended: sweep may delete audio, never records.
  - Manifest carries `vocab_source` per box (`occupation: corpus_prose_cut`, other boxes `authored`).

---

## 6. Related Tickets & Docs

- [[tickets/T02]] — myScheme scrape extraction & data completeness (Closed Rev 5)
- [[tickets/T06]] — Scheme record schema & facet table (Closed Rev 10)
- [[tickets/T07]] — Build the corpus ingest pass (Fully unblocked Rev 22)
- [[tickets/T07-amendment-from-T22]] — Ingest amendment for occupation cut (Superseded by T07)
- [[tickets/T08]] — Three-language content survival & keyword list (Closed Rev 11)
- [[tickets/T12]] — Door A alias contract & uniqueness gate (Closed Rev 15)
- [[tickets/T15]] — Mouth audio generation & manifest contract (Closed Rev 19)
- [[tickets/T16]] — Audit LOG trace specification (Closed Rev 16)
- [[tickets/T17]] — Module boundaries, snapshot layout, and Corpus/Log contracts (Closed Rev 20)
- [[tickets/T18]] — The fallback ladder & forbidden-phrase build gate (Closed Rev 22)
- [[tickets/T19]] — Deployment target & host architecture (Decided Rev 24)
- [[tickets/T20]] — Data residency & transcript persistence regulation (Narrowed Rev 24)
- [[tickets/T21]] — Corpus provenance, freshness gate, and verification schema (Closed Rev 25)
- [[tickets/T22]] — Recover myScheme value lists (Closed Rev 21 — folded into T07)
- [[tickets/T23]] — Confirmation ladder wording & template inventory (Closed Rev 23)
- [[docs/architecture]] — System Architecture (v1)
- [[docs/build-plan]] — Step-by-step implementation plan

