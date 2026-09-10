---
title: HAQDAAR v2 Canonical Glossary
slug: glossary
type: glossary
module: general
status: reviewed
tags: [glossary, architecture, definitions]
created: 2026-09-06
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: Antigravity
---

# HAQDAAR v2 Canonical Glossary

This document provides canonical definitions for the shared vocabulary, architectural concepts, modules, and tags across the HAQDAAR v2 knowledge base.

---

## 1. Core Architecture & Destination

### HAQDAAR
The inbound Interactive Voice Response (IVR) system designed for feature-phone users across India to discover government schemes they are entitled to. Operates with keypad-primary navigation, speech overlay, 5–6 questions maximum (hard cap at 8 total turns), and strictly adheres to the principle of never declaring "you are eligible" (only indicating matched schemes and application requirements).

### Acceptance Bar (Target: 14 Sep 2026)
The standing validation test against which all architectural decisions are judged:
- A live telephone inbound number accepts real calls in **Hindi**, **English**, and **Marathi** over a **Twilio +1 number** (amended in Rev 25 due to Plivo KYC; Plivo retained as alternate adapter).
- A caller who names a scheme gets its details read back in under **20 seconds** (measured from opener `vad.speech_end` to provider `playedStream` checkpoint immediately preceding the first word of the scheme name). Exact alias match in code costs zero model calls.
- A caller who describes their situation receives **2 to 4 named schemes** (or a structurally proven dead-end nearest resolution with nearest schemes labelled honestly, [[tickets/T18]]).
- The **LOG** trace can prove why each scheme was chosen from text reconstruction alone.

### The Four Modules
The core ownership seams dividing the HAQDAAR system into four independently testable components ([[tickets/T17]]):
1. **Audio Module:** Telephony (Twilio `<Connect><Stream>` primary, Plivo alternate), Ear (Sarvam ASR), and Mouth (Playback primitives over checkpoints; depends on nothing).
2. **Model Module:** Opener/Door A, Door B understanding, 3-field model contract, span guard (Router only on Groq free tier; Reader eliminated).
3. **Engine Module:** Checker, Filter (Retained bitmasks), Minimax Planner, and the Call Loop Orchestrator (`run_call`).
4. **Data Module:** Scheme Corpus snapshots, facet schema, automated ingest pass, provenance/freshness gate, and the audit LOG trace.

### Host Architecture (Laptop behind ngrok)
The entire system runs as a single Python 3.11 asyncio process on Adarsh's laptop in Bengaluru, fronted by a fixed ngrok development domain ([[tickets/T19]]). No database, no queue, no Docker, no frontend, and zero static audio web serving (audio is pushed down the WebSocket directly from the in-memory pool).

### Bad-News-First Ordering Lock
An architectural ordering constraint enforced at build time ([[tickets/T18]]): in every non-exact terminal (widened match, nearest, empty), the qualifying negative clause is spoken *before* any scheme names are read. A caller hanging up prematurely always hears the disclaimer rather than an unfulfilled promise.

---

## 2. Audio Module Vocabulary

### Inbound Telephony (Twilio `<Connect><Stream>`)
Primary telephony provider for build and demo ([[tickets/T05]]). Inbound calls to a +1 number request `/answer` which returns TwiML opening a bidirectional 8 kHz μ-law WebSocket to `/stream`. Plivo is retained as an alternate adapter behind the same audio seam.

### Two Clocks & Checkpoint Timers
Turn latency is governed by two decoupled clocks ([[tickets/T14]]):
1. **Endpoint Window:** 700 ms (`silence_duration_ms=700`, above vendor default to prevent clipping hesitant callers).
2. **System Response Budget:** $\le 1.2\text{ s}$ from `vad.speech_end` to the first byte on the wire.
Timers do not rely on local send dispatch; they start upon receiving provider `playedStream` / `mark` event from a terminal `checkpoint`.

### Barge-in Policy (Listen Always, Keypad Interrupt)
- **Keypad Barge-in:** DTMF interrupts playback immediately; triggers `clearAudio` and causes Sarvam to flush in-flight speech into `discarded_transcript`.
- **Speech Barge-in:** Formally evaluated and **declined**. The system listens continuously through prompts but does not cut off its own speech unless interrupted via DTMF.
- **Control Keys:** `*` re-pins language at any point without clearing facts; `#` repeats the last spoken prompt without consuming an interaction turn.

### Mouth (Zero Runtime TTS & Content-Addressed Pool)
TTS is an ingest build tool only; runtime live synthesis ceiling is zero ([[tickets/T15]]). Audio is stored in flat directory `audio/<render_key>.ulaw` where:
$$\text{render\_key} = \text{sha256}(\text{text} \parallel \text{lang} \parallel \text{voice\_id} \parallel \text{tts\_model} \parallel 8000)$$
Fixed line templates span 41 lines ($3N + 1 = 124$ files, [[tickets/T18]], [[tickets/T23]]) or 46 template lines in YAML. Playback primitives: `say(sequence)`, `on_mark(mark)`, `repeat()`, `clear()`.

### Ear (ASR)
Sarvam `saaras:v3-realtime` over 8 kHz WebSocket (μ-law, unbatched 20 ms frames, `stream_type="fast"`). Language is pinned per call at Turn 0, with `mode="codemix"` active unconditionally across all pins.

---

## 3. Model Module Vocabulary

### Door A (Opener Scheme Name Matching)
The direct entry path when a caller states a specific scheme name ([[tickets/T12]]). Door A is reframed as the opener itself:
- Emits a list of `(box, value, span)` including a `scheme` pseudo-box whose closed set is corpus scheme IDs.
- Two search tiers: Exact alias match in code (costs 0 model calls), followed by model selection from the alias candidate set (fuzzy string and embeddings eliminated).
- Exempt from echo-confirm (the read-back itself is confirmation, and keypad barge-in provides error correction).

### Door B (Demographic Discovery)
The discovery path where a caller answers structured questions. Operates under unconditional 2-turn echo-confirm for each demographic box.

### Three-Field Model Contract & Span Guard
- **Fields:** The model emits strictly `class`, `box`, and `value`.
- **Classes (5):** `ANSWER`, `CLARIFY`, `REPEAT`, `META`, `UNCLEAR`.
- **The Span Guard:** Code drops any extracted value whose declared span does not appear verbatim in what the caller spoke, preventing hallucinated slots.
- **Context Window:** Strictly scoped to a 2-turn window to prevent stale references from past utterances.

### Router-Only Architecture (Groq Free Tier)
Reader was eliminated by [[tickets/T17]]. Model runs on **Groq free tier** (model ID in `contracts/tunables.py`, [[docs/architecture]]) and is strictly restricted to *picking* values from fixed lists. Model never synthesizes response text or writes sentences. Model never raises exceptions; timeouts (2.0 s) or 429 rate limits return typed failures (`Result(failed=True)`). 2 model failures across a call switch Engine to `keypad_only_mode`.

---

## 4. Engine Module Vocabulary

### Call Loop Orchestrator
The stateful conversation loop (`run_call`) assigned to Engine in [[tickets/T17]]. Holds the three mutable state variables: `box_vector`, `turn_counter`, and `ladder_rung`. `Planner` and `Filter` remain pure functions with zero external dependencies.

### Retained Turn Masks
Rather than collapsing candidate sets destructively, the engine retains one 64-bit bitmask per turn, deriving:
- **`survivors`**: Bitwise AND across answered masks (ground truth claim).
- **`tally`**: Count of masks holding each scheme's bit (ranks near matches).
- **`miss-set`**: Which specific masks failed for each scheme (governs speakability).

### Seven-Box Roster
- **Box 0 (`category`):** Free, extracted from opener.
- **Hard Boxes (`state`, `gender`, `social_category`):** Caller cannot be mistaken; walls that are never dropped during widening. Non-`ANY` schemes on unasked hard boxes can never be spoken.
- **Soft Boxes (`age`, `income_band`, `occupation`):** Blur/approximations; eligible for widening in order: `income_band` $\to$ `age` $\to$ `occupation` $\to$ `category`.

### Minimax Planner
Scores askable boxes by guaranteed worst-case candidate reduction divided by expected turn cost (keypad = 1 turn; spoken = 2 turns due to echo-confirm).

### Stop Conditions (4)
1. **Survivor Threshold:** $\le 4$ survivors remaining (stop at 1 and speak it).
2. **Turn Ceiling:** Hard turn ceiling reached (8 total turns).
3. **Zero-Information Stop:** No remaining askable box splits the survivors.
4. **Zero Survivors Stop ([[tickets/T18]]):** Questioning halts immediately when survivors reach zero, triggering the fallback ladder.

### Three Mutually Exclusive Terminals ([[tickets/T18]])
1. **Widened Match:** The ladder produced survivors; real match on smaller box set; ranked by specificity; full read-back with keypad drill-downs.
2. **Nearest:** The ladder exhausted at 0 survivors; non-match; ranked by tally (hard box misses excluded); capped at 2; `summary` chunk only.
3. **Empty:** No schemes pass hard-box miss-set gate; empty disclaimer line spoken.

### Keypad-Only Mode
Call-level degraded mode triggered by 2 non-consecutive model failures or 1 unrecovered ASR socket. Completes the call end-to-end without LLM calls.

---

## 5. Data Module Vocabulary

### Automated Ingest Pass ([[tickets/T07]])
Unattended batch processing pipeline where N is a build parameter. Runs zero human-scaling operations; `facets_verified` is retired as a gate and tracked via `facets_source: derived | audited`.

### The Five Build Gates ([[tickets/T07]], [[tickets/T21]])
Every scheme must pass all gates to enter a snapshot:
1. **Expressibility ([[tickets/T06]]):** Every facet resolves to closed-set value or `ANY`.
2. **Alias Floor ([[tickets/T12]], [[tickets/T24]]):** $\ge 3$ aliases per language, $\ge 1$ code-mixed alias for non-English, uniqueness gate applied.
3. **Read-Back Completeness ([[tickets/T15]]):** All 6 read-back chunks rendered across all 3 languages (18 clips per row).
4. **Forbidden-Phrase Lock ([[tickets/T18]]):** Regex check on read-back chunks and terminals for second-person eligibility claims.
5. **Provenance & Freshness Gate ([[tickets/T21]]):** `source_url` on `myscheme.gov.in`, `fetched_on` within `max_source_age_days <= 14`, and SHA-256 drift check before snapshot freeze.

### Corpus Snapshot
Immutable, versioned scheme dataset pinned for the entire duration of a call (`schemes.jsonl`, `masks.bin`, `vocab.json`, `templates.json`, `manifest.json`). Deployments build new snapshots and flip an atomic pointer without invalidating in-flight calls.

### LOG (Decision Trace)
Single JSONL file per call (one line per turn). Explains rather than replays (raw audio destroyed at hangup; caller numbers hashed).
- **Derive-on-Read:** Does not store masks, survivors, or confidence. Everything derivable from `snapshot_id` and the box vector is computed dynamically by the audit reader. Snapshot records and manifests are retained permanently alongside logs citing them ([[tickets/T21]]).
- **Stored Exceptions:** Only explicit branches taken (`ladder_rung`, `stop_condition`, `unknown_source`, `lang_source`) are persisted.
- **Full Transcripts:** Stored as personal data debt to audit `CLARIFY`, `UNCLEAR`, and `NOISE` turns.

---

## 6. Standardized Tags

- `#module/audio`: Telephony, ASR, TTS, codecs, provider integration, barge-in, turn clocks.
- `#module/model`: Door A opener, Door B, 3-field contract, span guard, Groq free tier.
- `#module/engine`: Retained masks, 7-box roster, minimax planner, widening ladder, call loop.
- `#module/data`: Corpus snapshots, ingest pass, build gates, provenance, LOG trace, audio cache.
- `#module/architecture`: System-wide specifications and end-to-end design.
- `#type/ticket`: System tickets (T01 through T24).
- `#type/map`: Wayfinder architecture maps (Rev 3 through Rev 27).
- `#type/doc`: Core documentation (Architecture, Build Plan, PRD, Review, Today).
- `#status/open`: Unresolved ticket or work item.
- `#status/in-progress`: Currently being researched or prototyped.
- `#status/closed`: Ratified decision recorded.
- `#status/superseded`: Replaced by later ticket or specification.

