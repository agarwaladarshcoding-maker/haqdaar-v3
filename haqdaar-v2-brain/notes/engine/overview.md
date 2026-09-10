---
title: Engine Module Overview
slug: engine-module-overview
type: module-note
module: engine
status: reviewed
tags: [module, engine, checker, filter, planner, rules]
created: 2026-09-06
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: Antigravity
---

# Engine Module Overview

**Module:** Engine (Checker / Filter / Planner)  
**Parent System:** [[projects/haqdaar/overview|HAQDAAR v2]]  
**Governing Rules:** [[RULES.md]]

---

## 1. Scope & Ownership

The Engine module is the deterministic decision engine and runtime coordinator of HAQDAAR:
- **Call Loop Orchestration:** Manages call execution loop, holding box vector, turn count, and ladder rung ([[tickets/T17]]).
- **Checker:** Evaluates hard demographic constraints (age, caste, income, state, land area) against scheme eligibility rules.
- **Filter:** Computes candidate scheme sets per turn from retained bitmasks.
- **Planner:** Dynamic question sequencing selecting the question that achieves maximum candidate reduction.
- **Dead-End & Fallback Ladder:** Executes monotone soft widening and resolves zero-survivor terminals ([[tickets/T18]]).

---

## 2. Invariants & Ratified Decisions (Initial)

1. **Deterministic Eligibility:** The Engine never outputs probabilistic eligibility claims. It strictly outputs: "Here are schemes matching your details; verify the requirements."
2. **Dead-End Ladder:** If zero schemes match, the engine widens the last filter mask and retries once. If still zero, it reads the nearest two schemes labeled explicitly as nearest candidates.
3. **Turn Constraint:** Never exceeds 5–6 questions per call to ensure feature-phone callers do not abandon the session.

---

## 3. Update (2026-09-09 — Ratified Decisions Rev 12–13)

### Filter Table & Mask Retainment ([[tickets/T09]], Rev 12)
- **Retained Turn Masks:** Rather than collapsing masks destructively (`survivors = survivors AND mask`), each turn retains its 64-bit mask. From these masks, the engine derives:
  - **`survivors`** (bitwise AND of all answered masks — the ground truth claim).
  - **`tally`** (count of masks holding the bit — ranks near matches).
  - **`miss-set`** (identifies which specific masks failed — governs speakability).
- **No Vector Search / No Undo Stack:** Vector search is prohibited because it cannot produce an auditable deterministic trace. The box vector is the single source of state; correcting a box simply overwrites that slot and re-evaluates.
- **Hard Box Speaking Rule:** At zero survivors, a scheme whose `miss-set` contains any hard box is **never spoken**. Widening drops soft boxes only.
- **Engine Purity:** Engine is pure code, language-blind, and numeric-free. It maps codes to bitmasks with zero LLM dependence.

### Box Roster, Minimax Planner & Stop Conditions ([[tickets/T10]], Rev 13)
- **The Seven-Box Roster:**
  - **Box 0 (`category`):** Free, extracted from the opener, zero turn cost.
  - **Hard Boxes (`state`, `gender`, `social_category`):** Caller cannot be mistaken; walls that are never dropped during widening.
  - **Soft Boxes (`age`, `income_band`, `occupation`):** Approximations/blur; eligible for graceful widening.
- **Minimax Elimination Score:** Questions are ranked by worst-case survivor reduction divided by expected turns:
  $$\text{Score} = \frac{\min_{\text{value}} (\text{eliminated})}{\text{expected turns}}$$
  Keypad costs 1 turn; spoken costs 2 turns (due to echo-confirm).
- **Three Stop Conditions:**
  1. **Survivor Threshold:** $\le 4$ survivors remaining (stop at 1 and speak it; do not widen to manufacture a second).
  2. **Turn Ceiling:** 8 total turns reached (opener 2 + 6 question turns).
  3. **Zero-Information Stop:** No remaining askable box splits the survivor set.
- **Widening Ladder Order:** When survivors reach zero: `income_band` $\to$ `age` $\to$ `occupation` $\to$ `category`.
- **Specificity Tie-Breaker:** When survivor counts tie, rank schemes by **specificity** (count of non-`ANY` criteria matched).

---

## 4. Update (2026-09-10 — Ratified Decisions Rev 19–22)

### Call Loop Orchestrator Assigned to Engine ([[tickets/T17]], Rev 20)
- **Engine Owns the Loop:** `Engine.run_call(audio, model, corpus, log)` coordinates the conversation. Engine holds the three state variables: `box_vector`, `turn_counter`, and `ladder_rung`.
- **Purity Seam Preserved:** While `run_call` is stateful, `Planner` and `Filter` are strictly pure functions:
  ```python
  Planner.next_action(box_vector, corpus) -> Ask(box) | Widen(box) | Stop(reason)
  Filter.survivors(box_vector, corpus)    -> tuple[int, ...]
  Filter.tally(box_vector, corpus)        -> Mapping[int, int]
  Filter.miss_set(box_vector, corpus, ix) -> frozenset[BoxId]
  ```
  They take no Audio, Model, or Log references, enabling lightning-fast offline execution in [[tickets/T13]].
- **LOG Assembly:** Engine constructs the full turn payload from its state, Audio's input, and Model's stamp; Data module handles disk persistence.

### Fallback Ladder & Three Terminals ([[tickets/T18]], Rev 22)
- **Fourth Stop Condition (Zero Survivors):** Questioning halts immediately when survivors reach zero. Evaluated and logged separately from zero-information.
- **Monotone Widening:** Widens in trust order (`income_band` $\to$ `age` $\to$ `occupation` $\to$ `category`). Skips unasked/unknown soft boxes. Stops at the first rung producing $\ge 1$ survivor and immediately hands control back to T10 delivery rules.
- **Three Mutually Exclusive Terminals:**
  | Terminal | Trigger | Ranking | Cap | Spoken Content |
  |---|---|---|---|---|
  | **Widened Match** | Ladder yielded survivors | Specificity (T10) | T10 rule ($\le 4$ all; $> 4$ top 3 + overflow) | 6 chunks + keypad drill-downs |
  | **Nearest** | Ladder exhausted at 0 survivors | Tally (miss-set hard box excluded) | **2** | **`summary` chunk only** (no keypad drill-downs) |
  | **Empty** | No scheme passes hard-box gate | — | 0 | Empty disclaimer line |
- **Bad-News-First Ordering Lock:** In every non-exact terminal, the negative qualification line is spoken *before* scheme names. Dropped boxes are named explicitly. Words *"eligible"*, *"qualify"*, *"entitled"*, *"you will get"* are strictly prohibited across all languages.
- **Keypad-Only Mode (Call-Level vs Box-Level):**
  - *Box-Level:* 2 non-ANSWER turns on a box drop that box to keypad (or `UNKNOWN` if cardinality $> 9$, [[tickets/T15]]). If a keypad box fails twice, it drops to `UNKNOWN`.
  - *Call-Level:* 2 non-consecutive model failures or 1 unrecovered ASR socket drops the entire remaining call to keypad. Keypad-only completes the call end-to-end. `state` falls to `UNKNOWN` with an explicit spoken disclaimer ("I could not get your state, so I only looked at schemes for the whole country"). Door A is disabled in keypad-only.
- **Door A to Door B Transition:** *"Anything else?"* clears only the need box, allowing Door A callers to transition smoothly into Door B demographic discovery at regular cost.

---

## 5. Related Tickets

- [[tickets/T06]] — Eligibility record structure & flat facet schema (Closed Rev 10)
- [[tickets/T09]] — Filter table & mask retainment architecture (Closed Rev 12)
- [[tickets/T10]] — Seven-box roster & minimax question planner (Closed Rev 13)
- [[tickets/T11]] — Closed set model contract & box drop to keypad (Closed Rev 14)
- [[tickets/T13]] — Dry-run narrowing prototype on real schemes (Prototype)
- [[tickets/T16]] — Audit LOG trace requirements (Closed Rev 16)
- [[tickets/T17]] — Module boundaries, loop orchestrator, and frozen signatures (Closed Rev 20)
- [[tickets/T18]] — The fallback ladder: zero survivors, 3 terminals, bad-news-first lock (Closed Rev 22)
- [[tickets/T23]] — Confirmation ladder wording & template inventory (Closed Rev 23)
- [[docs/architecture]] — System Architecture (v1)
- [[docs/build-plan]] — Step-by-step implementation plan


