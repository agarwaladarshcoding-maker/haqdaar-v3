---
title: "Contradiction Audit — docs/ against the ratified brain"
slug: contradiction-audit
type: module-note
module: architecture
status: reviewed
tags: [audit, architecture, staging, traceability]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/ARCHITECTURE.md
---

# Contradiction Audit

**Why this file exists.** The rebuild is not a style pass. `docs/architecture`, `docs/prd` and
`docs/build-plan` disagree with [[maps/wayfinder-map|the ratified map]] and with closed tickets in
ways that change what gets built and whether the [[tickets/T04|acceptance bar]] can be met. This
file is the evidence. Every row cites the ticket that governs.

> **Correction, 10 Sep (second pass).** The first draft of this audit was written against a vault
> whose newest map was rev 25, and concluded that the *"MAP rev 27"* the docs cite did not exist.
> **It does** — rev 27 was ratified and simply had not been placed in the vault yet. It is now
> `maps/wayfinder-map.md`. **Two findings are therefore withdrawn** (§1.1 the provider, §5 the
> date), **one reverses** (§4's laptop drill), and **the rest stand** — see §0.

**Scope of the finding:** the vault's own module notes — [[notes/engine/overview]],
[[notes/audio/overview]], [[notes/model/overview]], [[notes/data/overview]] — are **accurate**.
They carry the 8-turn cap, the three terminals, the widening ladder and the ASR failure trigger
correctly. It is specifically the `docs/` set that drifted. The docs contradict the vault's own
notes, not merely the tickets.

---

## 0 · The authority: map rev 27, ratified — and what it does and does not cover

`docs/architecture`, `docs/prd` and `docs/today` state they were written **"against MAP rev 27."**
That authority is real. The ratified map is now **rev 27**, with
`maps/history/wayfinder-map-rev27.md` beside it; rev 25 is superseded.

**Rev 26 and rev 27 are three entries. This is all of them:**

| Entry | What it ratifies |
|---|---|
| **Working agreement for the build** (rev 26, amended rev 27) | Adarsh builds solo; the team does the presentation. Claude plans, Antigravity writes code, Claude Code reviews. **The brain lives at `brain/` inside the git repo**, with `brain/docs/` holding ARCHITECTURE, PRD, BUILD-PLAN, REVIEW, TODAY. **Architecture and build plan by 12 Sep; the ten-call acceptance test moves from 12 Sep to 14 Sep.** **v1 = every feature present in its simplest form, a whole call end to end; v2 = each feature improved, after v1 is tagged.** *"v1 cuts features, never safety."* |
| **Solo, dated, and automated** (rev 26) | **Four modules and `contracts/` kept** — T17's merge rule for a team under four is *not* taken. **[[tickets/T19]]'s spare-laptop drill is dropped**; restart loop and hotspot drills stay. Pipeline automated end to end; **`facets_verified_by: null` on every v1 record**; the build gates still run. |
| **Groq free tier replaces paid Gemini** (rev 27) | Overturns [[tickets/T11]] §5 **on budget, not on argument.** Two model moments only — **the opener and spoken `state`**; every other box keypad. Exact alias match in code before the model. **A 429 is a model failure under [[tickets/T18]].** No in-turn retry. Model id a tunable chosen by a **30-utterance bake-off**. Pipeline calls throttled and cached. **Named risk: one caller at a time**, announced before judging. T11's three-field contract, span guard and closed sets untouched. |

**What that does to this audit:**

- **§1.1 is withdrawn as a contradiction.** The supersession is recorded in the map, in the
  ticket's own terms. What replaces it is a **completeness** finding — the docs took rev 27's
  provider and left out four of the five things rev 27 attached to it.
- **§5's date question is closed: 14 Sep**, ratified by rev 26 as an explicit move of the
  acceptance test. Every document in this rebuild is now written to 14 Sep.
- **§4's laptop-dies drill reverses** — rev 26 drops it by name. Corrected in place.
- **Everything else stands, unchanged.** Rev 26 and rev 27 concern who builds, by when, and which
  provider. They say nothing about the widening ladder, the 8-turn cap, the frozen signatures, the
  audio pool's location, class precedence, the ASR keypad-only trigger, the SILENCE/NOISE turn rule
  or the fifth build gate. Those findings were never claims about rev 27's existence — each is a
  place where `docs/` disagrees with a **closed ticket that rev 27 never touched**, and under
  [[RULES.md|§6 Merge & Conflict Rules]] a ticket stands until something supersedes it.

`docs/review` already states the precedence rule this rebuild applies — *"If ARCHITECTURE.md and
T17 disagree, T17 wins"* — and rev 27 leaves it intact: a map revision outranks a ticket, a ticket
outranks a doc, and rev 27 amends exactly one ticket clause.

---

## 1 · Ratified decisions the docs reverse

### 1.1 The LLM — Groq free tier · **finding withdrawn; a completeness gap replaces it**

**The first draft called this a reversal of a closed ticket with nothing behind it. That was
wrong.** Map rev 27 records the supersession explicitly, and in the ticket's own terms:
*"overturns T11's provider line on budget, not on argument… T11's objection stands as fact — Groq's
free tier is rate-limited per organization, and it does fail on concurrency — so the answer is to
**spend fewer model calls**, not to pretend the limit away."*

| | Position now | Authority |
|---|---|---|
| Provider | **Groq, free tier** | map **rev 27** (10 Sep) |
| Superseded | Gemini Flash-Lite on a paid key — [[tickets/T11]] §5, *"turn billing on"* | on **budget**, not on argument |
| Untouched | three fields · span guard · closed sets · five classes and their precedence | [[tickets/T11]] |

**What is still a finding is completeness.** Rev 27 does not merely name a provider — it attaches
five mechanisms that are what make a free tier survivable, and a document that carries the provider
without them has taken the risk and dropped the mitigation. All five are now carried in
[[06-BUILD-PLAN]] Steps 8, 14 and 15, [[03-ARCHITECTURE]] §8, [[briefs/model]] and
[[10-RISK-REGISTER]]:

1. **Two model moments per call — the opener and spoken `state`; every other box is keypad.** A
   typical call makes one to three model calls.
2. **Exact alias match runs in code before the model** ([[tickets/T12]]'s first search), so a
   cleanly named scheme costs zero model calls.
3. **A 429 is a model failure under [[tickets/T18]]** — it counts toward the two-per-call drop to
   keypad-only. That is precisely what makes the worst case *a slower call, never a dead one*.
4. **No in-turn retry** ([[tickets/T14]]) and a **byte-identical system prompt** across calls.
5. **Model id is a tunable**, chosen by a **30-utterance bake-off at build**; pipeline calls are
   throttled and cached to disk.

> **One thing the provider change leaves genuinely open.** [[tickets/T14]]'s latency budget prices
> the model call at **300–500 ms**, and that number was measured against Gemini Flash-Lite. It is
> now unverified, and §3.7's 1.2 s response budget is built on it. **The Step 14 bake-off must
> report latency as well as accuracy** — if Groq's chosen model does not land inside the budget,
> the second clock moves, not the provider.

### 1.2 The widening ladder, deferred to v2 — this alone can fail the bar

`docs/prd` §7 lists *"Full widening ladder"* under **v2**. `docs/build-plan` Step 4 builds a
planner with no `Widen` action.

Three ratified things break:

1. **[[tickets/T17]] froze the signature** `Planner.next_action(...) -> Ask(box) | Widen(box) | Stop(reason)`.
   Removing `Widen` changes a frozen interface, which per T17 §6 requires the owners on both sides
   of the edge **plus a map revision**.
2. **[[tickets/T18]] §2 loses a whole terminal.** The *widened match* terminal only exists if the
   ladder runs. The docs' four endings silently drop it.
3. **[[tickets/T04]] branch 3 makes it a pass/fail condition, not a feature.** Verbatim:
   > *"A dead-end is a pass **if and only if** the widening ladder ran first. […] Zero survivors →
   > dead-end delivered without the widening step: **fail**. The mechanism is what is being judged,
   > not the caller's luck."*

   T04 also predicts dead-ends are *"the common case, not the edge — plausibly two or three of the
   ten."* With the ladder deferred, **every one of those calls scores an automatic fail**, against a
   bar of 8-of-10. The v2 deferral does not cost polish; it can cost the demo.

**Rev 26 closes the "it is a v2 feature" defence rather than opening it.** Its own definition:
*"v1 = **every feature present in its simplest form**, a whole call end to end — v2 = each feature
improved."* Widening is a feature, so v1 owes it in its simplest form. **The simplest form is the
ladder with its rungs in a fixed order** — soft boxes dropped one at a time, stop at the first rung
with ≥1 survivor ([[tickets/T18]] §1) — which is cheap and is exactly what T04 branch 3 judges.
Deleting it is not a simplification, it is a cut, and rev 26's next clause is *"v1 cuts features,
never safety."* Restored on that basis.

### 1.3 `*` mid-call language re-pin, deferred to v2

`docs/prd` §7 defers it. [[tickets/T24]] §3 ratified it and costed every module at **zero**: Mouth
zero (parity already bought by T04), verification zero, Sarvam one `config.update`, Engine zero
(language-blind). [[tickets/T23]] then implemented it with **no new audio** — `*` simply replays
`greeting_trilingual`. Deferring it saves nothing and removes the only route that works for a
mis-pinned caller, which T24 established is *structurally* the one case speech cannot rescue:
*"to hear 'can we speak in Marathi?' you must understand a caller you have just established you
cannot understand."*

**Rev 26's test again:** a feature costed at zero in every module has a simplest form identical to
its full form. There is nothing left to defer to v2.

---

## 2 · Frozen interfaces the docs restate incorrectly

[[tickets/T17]] §2 froze four signature blocks. `docs/architecture` §5 rewrites them from memory.
Almost every name is wrong, which means code written against the doc will not compile against the
contract.

| Contract | T17 (frozen) | docs/architecture §5 |
|---|---|---|
| Corpus | `mask(box,value)` · `values(box)` · `specificity(ix)` · `scheme_id(ix)` · `alias_lookup(text,lang)` · `alias_set(lang)` · `audio(line_id,lang,value)` · `chunks(scheme_id,lang)` · `gate_notes(id)` | `closed_set(box)` · `aliases(lang)` · `record(scheme_id)` · `masks` · `line_audio(line_id,lang)` |
| Model | `opener(transcript, lang)` · **`turn(transcript, box, window, ask_count)`** · **`failures`** | `opener(transcript_en, lang)` · `answer(transcript_en, box, window)` — no `ask_count`, no `failures` |
| Audio | `connect` · **`select_language()`** · `say` · `repeat` · `clear` · **`on_mark(mark)`** · `next_input(**profile**)` · `language` · `hangup` | no `select_language`; `played(mark)`; `next_input(silence_gap_s)`; `set_language(lang)` |
| Audio input union | `Digit \| Speech \| **Noise** \| Silence(n) \| **Hangup**` | `Digit \| Control \| Speech` + `Silence(n)` — **`Noise` and `Hangup` missing** |
| Log | `open(call_id, snapshot_id)` · `write(line)` · `close(reason)` | `write(line)` only |
| Engine | `run_call(...)`; `Planner.next_action -> Ask\|**Widen**\|Stop`; `Filter.survivors/tally/miss_set` | no signature block at all |

**`Noise` is not cosmetic.** [[tickets/T14]]'s turn-count table makes NOISE and SILENCE behave
differently — see §3.1. Collapsing them into `Silence` erases the distinction in the type system.

### 2.1 The snapshot layout

[[tickets/T17]] §2 froze it, and [[tickets/T15]] is explicit that **the snapshot is the manifest**
and the audio pool is **one flat pool shared across snapshots**:

```
snapshots/<snapshot_id>/  schemes.jsonl · masks.bin · vocab.json · templates.json · manifest.json
audio/<render_key>.ulaw   ← flat, shared, NEVER nested inside a snapshot
```

`docs/architecture` §3 and §9 invent `records.json` / `masks.json` and place `audio/` **inside**
`snapshots/<id>/`. That nesting defeats the entire point of content-addressing: a shared pool means
a re-render only writes changed keys, and [[tickets/T21]]'s mark-and-sweep runs over *the union of
live manifests*. A per-snapshot audio directory makes every snapshot a full ~200 MB copy.

---

## 3 · Ratified mechanics the docs simply omit

### 3.1 SILENCE does not consume a turn; NOISE does

[[tickets/T14]], *Inherited item — T16's turn-count agreement*:

| Condition | Class | Consumes a cap turn? | Counts toward T11's two-strike drop? |
|---|---|---|---|
| `vad.speech_start` fired, final empty or span-less | **NOISE** | **yes** | yes |
| no `vad.speech_start` in the window | **SILENCE** | **no** | no |

*"So the silent caller is bounded by the ladder and the noisy caller by T11's keypad drop — two
different failures, two different bounds, neither borrowing the other's."*

The docs contain neither the distinction nor the `silence_n` field's role. Implemented as written,
a caller on a bad line burns the cap through silence and the call dies early.

### 3.2 Both caps — 8 turns **and** 6 questions

[[tickets/T10]] D4 stop 2: *"**8 turns spent**, with a hard wall at **6 questions** regardless of
turn count."* Two counters, not one. A spoken box costs 2 turns, a keypad box 1 (T10 D2); the
opener costs 2 turns if it fills anything and 1 if it fills nothing ([[tickets/T11]] §3).

`docs/build-plan` Step 2 defines `MAX_QUESTIONS=6` and no turn cap. The 8 is load-bearing
downstream: [[tickets/T14]]'s 6-second silence rung is derived from it (*"if T10's 8 moves, this
moves with it"*), [[tickets/T18]] §4 uses it to prove keypad-only completes a call
(*"five askable boxes at keypad cost 1 = 5 turns against a cap of 8. It fits, and it is the binding
case"*), and [[tickets/T16]] requires `turn_n` and the cap to count the same thing.
[[tickets/T17]] §6 lists *"8-turn cap"* by name in `tunables.py`.

### 3.3 The fourth stop condition

[[tickets/T18]] §1: *"Zero survivors is a **fourth** stop condition, **named separately in the
LOG**. […] a reader must be able to tell *nothing was left* from *no question helped*."* The docs
list four stops but fold zero-survivors in without naming it distinctly.

### 3.4 Model class precedence

[[tickets/T11]] §2 froze the order **`META > ANSWER > CLARIFY > REPEAT > UNCLEAR`**, with two rules
argued at length: ANSWER beats CLARIFY (*"losing a value is worse than delaying an explanation"*)
and META beats everything (*"the only class where carrying on is actively harmful"*). The docs list
the five classes and never state the precedence — leaving the single most ambiguous runtime
decision to the implementer.

### 3.5 Keypad-only has two triggers, and one ladder is really two

[[tickets/T18]] §3:

- **Model:** two failures per call, **not consecutive** (*"consecutive would let an alternating
  pattern burn eight turns"*).
- **ASR:** **one unrecovered socket**, after one free reconnect that consumes no turn. The docs
  omit this trigger entirely.
- **An UNCLEAR is not a failure** — *"it is a successful model turn reporting that it could not
  hear."* Counting it *"would drop healthy calls on a noisy line."*

And the two ladders must not be muddled: **box-level** keypad drop ([[tickets/T11]]) vs
**call-level** keypad-only ([[tickets/T18]]). The docs blur them into one bullet.

### 3.6 Sarvam's `stream_type="fast"`

[[tickets/T14]] branch 1: *"**`stream_type="fast"` is not optional.** `balanced` buffers audio into
~1000 ms chunks […] That is a full second in front of every turn, for free, invisibly."* Full
ratified config: `endpointing=vad`, `stream_type="fast"`, `silence_duration_ms=700`,
`min_speech_duration_ms=250`, `audioTrack="inbound"`. The docs name the model and `codemix` and omit
the single largest latency item in the chain.

### 3.7 The second clock

Two clocks, not one: a **700 ms endpoint window** that belongs to the caller, then **1.2 s of ours**
from `vad.speech_end` to first byte on the wire ([[tickets/T14]] branch 1). The docs carry
`ENDPOINT_MS=700` and no response budget, so there is no number for anything to be measured against.

### 3.8 Smaller omissions, each ratified

- **`UNKNOWN` is a reserved value in every box's closed set** — accepted first time, never re-asked,
  never pushed to a keypad menu, and **declining does not count as a failed turn** ([[tickets/T11]] §4).
  *"A declining caller must not be marched onto a keypad menu for caste — that is the worst
  available behaviour in this system."*
- **UNKNOWN counts as NOT satisfied** for T10's speaking rule, identically to UNASKED; the only
  difference is that UNASKED is still askable (T11's amendment to [[tickets/T09]]).
- **`#` at turn 0 does not consume one of T24's two greeting plays** ([[tickets/T14]]).
- **`*` and `#` never close a turn; digits 0–9 do** ([[tickets/T14]] branch 5).
- **NOISE writes a LOG line** although it never reaches the model ([[tickets/T16]] §3) — without it
  *"an 8-turn cap that fired after three visible turns reads as a bug."* The docs' `class` list omits NOISE.
- **[[tickets/T16]] §4 struck any `terminal_state` field**; `docs/architecture` §10 reintroduces a
  `terminal` field. T16's reasoning: *"a flag that disagrees with the trace is worse than no flag."*
- **Hindi and Marathi lines are authored impersonal on purpose** — gendered first-person verbs
  *"bind the render to a male voice and defeat T15's cheap voice swap"* ([[tickets/T23]] §5).
- **Widening stops at the first rung producing ≥1 survivor** ([[tickets/T18]] §1), superseding
  T10 D6's *"stop the moment ≥2 schemes are speakable."*

### 3.9 The line inventory is stated at the wrong resolution

[[tickets/T23]] §5 settles at **N = 46 lines → 3N+1 = 139 files**, *plus* a bare value-chip family
(one file per box value per language). [[tickets/T15]] separately sizes the chip family at
~200 values × 3 ≈ 600 files (~30 MB) and the whole rendered pool at ~200 MB.

`docs/build-plan` Step 10 says *"the 46 lines from T23 in 3 languages"* and gives the render gate no
number to check. 46 × 3 = 138, not 139 — the +1 is [[tickets/T24]]'s single trilingual greeting,
*"the only audio file in the system that is not per-language."*

### 3.10 Five build gates, presented as four

Each ticket called its own gate "the third" or "the fourth" because they landed on different days.
Reconciled against [[tickets/T07]] (which runs them), the full set is:

| # | Gate | Owner ticket | In docs? |
|---|---|---|---|
| 1 | **Expressibility** — every facet resolves to a closed-set value or `ANY`; `ANY` is the only sentinel | [[tickets/T06]] · [[tickets/T07]] | **missing** |
| 2 | Alias floor ≥3/language, ≥1 code-mixed per non-English, uniqueness gate | [[tickets/T12]] · [[tickets/T24]] | yes |
| 3 | Read-back completeness — all six chunks rendered in all three languages | [[tickets/T15]] | yes |
| 4 | Forbidden phrase, two-tier, `closing_farewell` brand allowlist | [[tickets/T18]] · [[tickets/T23]] | yes |
| 5 | Provenance & freshness — host, `fetched_on` age, `source_sha256` drift | [[tickets/T21]] | yes |

[[tickets/T07]] also fixes the **run order**, which the docs omit: *"Run the gates as a pre-filter,
not a post-check. Order them by cost: alias floor first (cheapest, excludes most), expressibility
second, read-back completeness last, because it is the only one that spends TTS."*

---

## 4 · Deliverables the brain requires that were never written

- **Four module briefs.** [[tickets/T17]] §5 is explicit: the 12 narrative segments are **retired,
  not re-cut**, and what replaces them is *"four module briefs, ~2 pages each, generated from the
  map, each containing only the owner's signature block, the ticket links behind each clause, the
  day-one test, and the not-frozen list."* They do not exist. Supplied here as
  [[briefs/audio|Audio]] · [[briefs/model|Model]] · [[briefs/engine|Engine]] · [[briefs/data|Data]].
- **`make demo-fixture`.** [[tickets/T17]] §4 names it as the one command that runs a whole call
  against four fakes and prints the LOG — *"map rev 3's stated purpose delivered as one command
  rather than as an intention."* The build plan never mentions it.
- **The run drills — *two*, not three.** [[tickets/T19]] specified Wi-Fi-dies, process-dies and
  laptop-dies. **Rev 26 drops the laptop-dies drill by name** — *"T19's spare-laptop drill is
  dropped (no second person, no second machine); the restart loop and hotspot drills stay"* — which
  follows from Adarsh building solo. *(The first draft of this audit demanded the spare laptop back;
  that demand is withdrawn.)* What remains required and is still missing from `docs/build-plan`
  Step 19: the **hotspot drill**, the **30-minute-idle cold-start test**, the
  **no-`git pull`-during-judging freeze**, and the `max_concurrent_measured` reading — which rev 27
  makes load-bearing, since *"one caller at a time"* is a named risk to be **announced before
  judging, not discovered during it.**
- **T04's seven survivable behaviours.** [[tickets/T04]] branch 4 requires that *"at least one call
  in the ten deliberately exercises each."* Neither the PRD's acceptance section nor the build plan
  carries the list.

---

## 5 · Closed by rev 27, and what is still open

### Map source-of-truth rule — **ratified 10 Sep 2026, and it closes two findings**

> **`maps/wayfinder-map.md` — the latest map by name and by time — is the sole source of truth.**
> Everything in `maps/history/` is **supporting version history**, kept so a decision can be traced
> back, and is **not authoritative for anything.**

Two consequences, both applied here rather than left open:

1. **The rev 8 and rev 24 gaps in `maps/history/` are withdrawn as findings** — not deferred,
   withdrawn. A version archive is not a correctness artefact, so its completeness is not a defect.
   **Do not re-raise them.** ([[09-DECISION-LOG]] D9.)
2. **The self-contradicting date inside the map is Adarsh's to edit, and stays open on that basis
   only** — noted below, untouched, because the ruling makes the map authoritative and therefore not
   mine to rewrite. **Rev 26 is later and explicit; every document in this rebuild reads 14 Sep.**


**All three questions the first draft raised are now answered — two by the map, one by Adarsh.**
D1 (provider) and D2 (date) are closed by rev 27 and rev 26. **D3 is closed as of 10 Sep 2026:
minimax on day one, the fixed-order stand-in withdrawn** ([[09-DECISION-LOG]] D3). What is left is
**no decision and one measurement**: [[tickets/T14]]'s 300–500 ms model-call budget, unverified
since the provider changed, which Step 14's bake-off must re-establish.

**One inconsistency inside the map itself, for Adarsh, not for me to edit.** The acceptance-bar
bullet in `Notes` still opens *"on 12 Sep 2026, a live Indian number… takes real calls"*, while the
rev 26 entry twenty lines below moves the ten-call test to 14 Sep. The intent is not in doubt — rev
26 is later and explicit — but **the bar's own sentence still names the old date**, and the bar is
the one line every decision is judged against. It wants a parenthetical amendment in the bullet, in
the same style as rev 25's, so a reader of the bar alone is not misled.

### The demo date — **closed: 14 September 2026**

[[tickets/T04]] and map rev 25 said **12 Sep**. **Rev 26 moved it**, in terms that leave nothing to
interpret: *"architecture and build plan ready by 12 Sep; product working properly by **14 Sep
night**, which moves the ten-call acceptance test from 12 Sep to 14 Sep."*

That is the bar amendment the first draft of this audit asked for — recorded in the map, which is
where a bar amendment belongs. **Every document in this rebuild is written to 14 Sep**, and
[[06-BUILD-PLAN]] is laid out Day 1…Day 5 against it, with **12 Sep held as the internal deadline
for architecture and build plan** — a second date rev 26 sets and which the plan now names.

**Nothing structural changed** in moving from the 12 Sep drafts: the two extra days land as slack
on Days 4–5, where [[07-TEST-PLAN]]'s drills and the acceptance run sit.

### A superseded clause worth re-reading before the demo

[[tickets/T04]] branch 5 requires that *"a scheme is in the 12 Sep corpus only when all four
read-back chunks are **human-verified** in all three languages."* [[tickets/T08]] later suspended
the truth lock and [[tickets/T07]] rev 22 removed the human from the ingest path entirely. The
supersession is real and recorded — but it means **the corpus entering the demo does not satisfy the
acceptance ticket's own branch 5.** That is a named, dated debt, not a defect; it is listed in
[[10-RISK-REGISTER|the risk register]] so nobody rediscovers it on the day.
