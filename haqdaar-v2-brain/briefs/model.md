---
title: "Module Brief — Model"
slug: brief-model
type: module-note
module: model
status: reviewed
tags: [brief, model, router, owner, staging]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/T17.md
---

# Module Brief — Model

> One of the four module briefs [[tickets/T17]] §5 requires.

**Owns:** the Router — one opener call, one call per question turn, and the validation standing in
front of both. **Charted as Router + Reader; the Reader no longer exists** — [[tickets/T15]] removed
live rendering and [[tickets/T06]] made read-back six chunks addressed by id, so **nothing composes
text while a caller is on the line.**

**Depends on:** Data (the closed sets). **Never imports Engine.**
**Day-one test:** return the expected stamps for the nine fixture utterances, and **drop the one
whose span is not in its transcript.**

## Signature block

```python
Model(corpus)
Model.opener(transcript, lang)                  -> list[Stamp] | Unclear
Model.turn(transcript, box, window, ask_count)  -> Answer | Clarify | Repeat | Meta | Unclear
Model.failures                                  -> int
```

`Stamp = (box | "scheme", value, span)`.

## The one line that describes the whole module

> **Choose from a list going in, read from a file going out, never write a sentence.**

## The clauses, and the ticket behind each

| Clause | Ticket |
|---|---|
| **Three fields: `class`, `box`, `value`** — plus the span. **No `confidence` anywhere in this system**: *"a model self-reporting confidence on a selection it just made is not evidence, it is a second generation."* **No per-turn `language`** — the pin is a call property | [[tickets/T11]] 1 |
| **Five classes**, by the test *two labels are one label if the system does the same thing after both*: `ANSWER` · `CLARIFY` · `REPEAT` · `META` · `UNCLEAR`. CORRECTION is an ANSWER pointing at an earlier box; NOISE is a code branch upstream | [[tickets/T11]] 2 |
| **`CLARIFY` and `REPEAT` are NOT merged** — *"'kya matlab?' needs different words; a barking dog needs the same words."* Collapsing them is designing for the caller we wish we had | [[tickets/T11]] 2 |
| **Precedence: `META > ANSWER > CLARIFY > REPEAT > UNCLEAR`.** ANSWER beats CLARIFY because *losing a value is worse than delaying an explanation*; META beats everything because it is *the only class where carrying on is actively harmful* | [[tickets/T11]] 2 |
| **The opener returns a list; a question turn returns exactly one.** The box may be any of the seven — *that is how a correction lands* | [[tickets/T11]] 3 |
| **The span guard.** Every value returns with the transcript span that produced it, and **code drops any pair whose span is not literally present.** String containment, no judgement | [[tickets/T11]] 3 |
| **The guard is provenance, not a score.** *Given "main kisan hoon", a model will reasonably also return `income_band = low`. Farmers are poor — and the caller did not say it.* A filled box **narrows**, so the invention excludes a scheme the caller qualifies for, and the LOG records it as though claimed | [[tickets/T11]] 3 |
| **Closed-set validation runs in code after the model returns.** *A prompt is not a guard* | [[tickets/T11]] 1 |
| **Both guards run inside Model, before it returns** — so **Engine is structurally incapable of receiving an unvalidated value.** The guard becomes a type boundary, not a discipline | [[tickets/T17]] 2 |
| **Context is a two-turn verbatim window plus `ask_count`.** The model may **read** the window; it may only **quote** from the current utterance. Full history was rejected because *it guts the span rule* — a state mentioned at turn 1 would pass the check at turn 5 — and because it breaks the offline test base, turning a list into a tree | [[tickets/T11]] 6 |
| **`UNKNOWN` is a reserved value in every box's closed set, not a sixth class.** Accepted first time, **never re-asked, never pushed to keypad** — *"a declining caller must not be marched onto a keypad menu for caste"* — and declining **does not count as a failed turn.** The opener never emits it | [[tickets/T11]] 4 |
| **Door A is a pseudo-box, not a stage.** `scheme` never enters the filter table, never gets a mask, is never asked, cannot be widened; it exists in the box vector for LOG reconstruction only | [[tickets/T12]] |
| **Exact alias match runs in code before the model.** Zero cost, and it is the offline test base | [[tickets/T12]] |
| **Two searches, not four.** Fuzzy matching *is what the model is for* — it was never a stage. *When the ASR writes "PM kissan", the span passes and the model still selects PMKISAN* | [[tickets/T12]] |
| **Door A is exempt from echo-confirm.** *The read-back is the confirmation.* A wrong box stamp is silent and compounds; a wrong scheme is loud and self-correcting | [[tickets/T12]] |
| **Never raises. Never returns out-of-set.** 2.0 s hard timeout, **no in-turn retry** — *"a retry doubles the wait to buy a second draw from the same distribution."* Timeout returns `Unclear(reason="timeout")` and increments `failures` | [[tickets/T14]] · [[tickets/T17]] |
| **Temperature 0, structured output, no streaming** (a 30-token response is useless partially) | [[tickets/T11]] 5 |
| **The system prompt is byte-identical across calls**, so provider-side caching can apply | [[tickets/T11]] 5 |
| **No second model provider.** *"The fallback is the keypad — already designed, already deterministic, already a pass. The keypad is a better fallback than any model because it cannot be wrong"* | [[tickets/T11]] 5 |

## Prompt size is asymmetric — the finding that makes the maths survivable

A **question call** knows its box and needs only that box's list (`gender` 2 values, `state` 36):
a few hundred tokens. **The opener needs all seven: ~1,500 tokens.** So the opener is the expensive
call and every question after it is cheap. **A full call ≈ 4,000 tokens.**

## Safety property that makes five classes affordable without a verifier

**No class error can produce an untruth.** A mislabelled CLARIFY→UNCLEAR yields a repeat instead of
a rephrase: annoying, recoverable. The only path to an untruth runs through a **wrong value**, which
the closed-set gate bounds to the wrong item off a known list, which echo-confirm catches.
**The cost of a class error is degraded politeness, never a false statement about money.**

## Yours to change without asking

Prompt text, so long as the output contract holds · everything inside `model/` · the tunables.

## Open, and yours to close

- **The provider is settled: Groq, free tier** (map **rev 27**, overturning [[tickets/T11]] §5
  *"on budget, not on argument"*). **What is yours is the model id and the shape of the call:**
  - **The model is called at two moments only — the opener and spoken `state`.** Every other box is
    keypad. A typical call spends one to three model calls; keep it that way.
  - **Exact alias match runs in code before `opener()`.** A cleanly named scheme must cost zero.
  - **A 429 returns the same typed failure as a timeout** and increments `failures`, so
    [[tickets/T18]]'s two-per-call drop handles it. **No in-turn retry.**
  - **Pick the model id with a 30-utterance bake-off** across the three languages — class accuracy,
    closed-set validity, **span survival**, and **latency p50/p95.** Record winner and runner-up in
    [[09-DECISION-LOG]].
- **[[tickets/T14]]'s 300–500 ms model-call budget is now unverified** — it was measured against
  Gemini Flash-Lite. The bake-off is what re-establishes it; if the chosen model misses, **the 1.2 s
  response clock moves, not the provider.**
- **The three-way context bake-off** — four fields vs four + two turns vs full history, ~50
  utterances, count wrong stamps. **Prediction on record:** the window beats four fields on
  corrections; full history loses on invented values. *If the numbers disagree, take the numbers.*
  Attached to [[tickets/T13]].
- **Door A's `t_name` prediction of 3–5 s** — [[tickets/T12b]] measures it.

## Related
[[03-ARCHITECTURE]] · [[04-INTERFACES]] · [[notes/model/overview]] · [[tickets/T03]] ·
[[tickets/T11]] · [[tickets/T12]] · [[tickets/T12b]] · [[tickets/T13]] · [[tickets/T23]]

---
**Wayfinder Map:** [[maps/wayfinder-map|Latest Map]] · **Brain Index:** [[glossary|Glossary]]
