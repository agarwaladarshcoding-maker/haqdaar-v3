---
title: Model Module Overview
slug: model-module-overview
type: module-note
module: model
status: reviewed
tags: [module, model, router, reader, door-a, door-b]
created: 2026-09-06
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: Antigravity
---

# Model Module Overview

**Module:** Model (Router / Understanding)  
**Parent System:** [[projects/haqdaar/overview|HAQDAAR v2]]  
**Governing Rules:** [[RULES.md]]

---

## 1. Scope & Ownership

The Model module owns intent classification, scheme candidate selection, caller attribute extraction, and semantic slot validation:
- **Router:** Directs caller speech to Door A (named scheme) or Door B (demographic discovery).
- **Door A Matching:** Multi-tiered matching engine resolving spoken colloquial names to canonical scheme IDs.
- **Door B Need Extraction:** Structured fact extraction from conversational answers against a 2-turn window.
- **Span Guard Enforcement:** Ensures all extracted slot values are backed by literal substring spans in the input transcript.
*(Note: Reader eliminated by [[tickets/T17]]; read-back text is never composed live).*

---

## 2. Invariants & Ratified Decisions (Initial)

1. **Door A Search Cascade:** Evaluates exact match → alias table → fuzzy distance → semantic embedding. Below confidence threshold, it fails smoothly into Door B.
2. **Template-Driven Text:** Scheme details, requirements, and prompts are rendered strictly from verified code templates. Generative free-text output is prohibited in customer read-backs.
3. **Fact Retention:** Multi-question turns retain confirmed demographic facts (state, occupation, land holding) across subsequent queries in the same call.

---

## 3. Update (2026-09-09 — Ratified Decisions Rev 14–15)

### Model Contract & Guardrails ([[tickets/T11]], Rev 14)
- **Three-Field Contract:** Model emits strictly `class`, `box`, and `value`. No confidence numbers and no per-turn language tags.
- **Five Semantic Classes:** `ANSWER`, `CLARIFY`, `REPEAT`, `META`, `UNCLEAR`. Code rules strictly enforce precedence: `META > ANSWER > CLARIFY > REPEAT > UNCLEAR`.
- **The Span Guard:** Every extracted value carries the transcript span that produced it. Code deterministically discards any value whose span does not appear verbatim in what the caller uttered, preventing hallucinations.
- **Unconditional Echo-Confirm:** Every demographic box value is confirmed via a 2-turn cycle before becoming durable state.
- **Context Window:** Model operates on a 2-turn window, not full conversation history, preventing stale transcript spans from contaminating later slots.
- **Runtime Execution:** Runs on paid Gemini Flash-Lite. Two consecutive failures drop the call into keypad-only mode. `UNKNOWN` is accepted on first occurrence and never pushed to keypad.

### Door A Reframe & Scheme Matching ([[tickets/T12]], Rev 15 & [[tickets/T12b]])
- **Door A is the Opener:** Door A is not a preliminary routing stage; it is the opener itself. The opener returns a list of `(box, value, span)` including a `scheme` pseudo-box whose closed set is the corpus scheme IDs.
- **Two Searches Only:** Exact alias string match in code (zero cost), followed by LLM selection from the candidate alias set. Fuzzy string distance and semantic embedding search are **eliminated**.
- **Echo-Confirm Exemption:** Door A is exempt from echo-confirm. The read-back itself serves as confirmation, and keypad barge-in serves as instant error correction.
- **Ambiguity Settlement:** 1 candidate → immediate read-back; 2 candidates → single keypad disambiguation turn; 3+ candidates → smoothly seeds Door B.
- **Alias Contract:** ≥3 aliases per language, stored as spoken, checked by a build-time uniqueness gate. Non-English sets must include code-mixed forms ([[tickets/T24]]).

---

## 4. Update (2026-09-10 — Ratified Decisions Rev 19–22)

### Reader Elimination & Router-Only Scope ([[tickets/T17]], Rev 20)
- **Reader Eliminated:** Reader is removed entirely from the module. T15 eliminated live TTS from runtime, and T06 partitioned read-backs into 6 pre-rendered chunks addressed by ID. Nothing generates text while a caller is on the phone. Model is strictly **Router only**.
- **Frozen Runtime Signatures:**
  ```python
  Model(corpus)
  Model.opener(transcript, lang)                 -> list[Stamp] | Unclear
  Model.turn(transcript, box, window, ask_count) -> Answer | Clarify | Repeat | Meta | Unclear
  Model.failures                                 -> int
  ```
  `Stamp = (box | "scheme", value, span)`. Opener returns a list; question turns return exactly one result.
- **Error Behaviour:** Model never raises and never returns values outside the closed set. Hard timeout 2.0 s returns `Unclear(reason="timeout")` and increments `failures` without in-turn retry.
- **Sealed Span Guard:** Closed-set validation and literal transcript span checking run entirely *inside* Model before returning. Engine is structurally incapable of receiving an unvalidated value.

### Fallback Triggers & Degraded Modes ([[tickets/T18]], Rev 22)
- **Call-Level Keypad-Only Trigger:** Engine monitors `Model.failures`. Two failures per call (non-consecutive) trigger call-level keypad-only mode.
- **`UNCLEAR` vs Failure:** An `UNCLEAR` response is a successful model inference reporting that speech was unintelligible (managed by box-level rephrasing); it is not a system failure and does not trip call-level keypad-only.
- **Door A in Keypad-Only:** Door A is disabled under keypad-only mode because 50 scheme IDs cannot be keyed via telephone keypad.

---

## 5. Update (2026-09-10 — Ratified Decisions Rev 24–27)

### Groq Free Tier Runtime Selection ([[docs/architecture]], Rev 27)
- **Provider & Model ID:** Transitioned from Gemini Flash-Lite to **Groq free tier** with model ID pinned in `contracts/tunables.py`.
- **Closed-Set Selection Only:** Model is strictly restricted to *picking* values from fixed lists (candidate aliases in Door A, and valid state values in Door B). It never writes or generates sentences.
- **Runtime Budget & Exact String Bypass:**
  - Code-level exact alias match runs first (zero model calls). A caller who says the scheme name cleanly costs 0 LLM calls.
  - Spoken `state` is the only demographic box query invoking LLM; all other boxes are collected via keypad DTMF.
  - Typical call uses only 1–3 model calls (1–2k tokens each).
- **Failure Resilience & 429 Rate Limits:**
  - Groq free tier enforces an org-level limit (~30 req/min, 6k–30k tokens/min).
  - HTTP 429 or invalid JSON is treated as a model failure (`Result(failed=True)`).
  - Hard timeout of 2.0 s; no retry inside a turn.
  - Two model failures across the call switch Engine to `keypad_only_mode` (completing the call cleanly without stalling).
- **Prompt Caching & Offline Bake-Off:**
  - System prompts are kept identical across calls to leverage Groq prompt caching.
  - Offline pipeline uses a 30-utterance test suite to benchmark and select the optimal Groq model.

---

## 6. Related Tickets & Docs

- [[tickets/T04]] — Definition of working properly & structural validation (Closed Rev 7)
- [[tickets/T08]] — Three-language handling & closed keyword vocabularies (Closed Rev 11)
- [[tickets/T11]] — Closed set model contract & span guard (Closed Rev 14)
- [[tickets/T12]] — Door A spoken scheme matching (Closed Rev 15)
- [[tickets/T12b]] — Door A measurement on real corpus (Prototype)
- [[tickets/T17]] — Module boundaries, Reader elimination, and frozen Model contract (Closed Rev 20)
- [[tickets/T18]] — Fallback ladder, model failure counting, and keypad degrade modes (Closed Rev 22)
- [[tickets/T23]] — Confirmation ladder wording & template inventory (Closed Rev 23)
- [[tickets/T24]] — Language selection & code-mixed aliases (Closed Rev 17)
- [[docs/architecture]] — System Architecture (v1)
- [[docs/build-plan]] — Step-by-step implementation plan


