---
title: "Frozen Interfaces — the four signature blocks"
slug: interfaces
type: module-note
module: architecture
status: reviewed
tags: [interfaces, contracts, frozen, staging]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/T17.md
---

# Frozen Interfaces

> **This file exists so there is exactly one place to check a signature.** It reproduces
> [[tickets/T17]] §2 faithfully rather than paraphrasing it. **If this file and [[tickets/T17]]
> ever disagree, T17 wins** and this file is fixed in the same commit.
>
> The previous `docs/architecture` §5 restated these from memory and got most of the names wrong —
> see [[01-CONTRADICTIONS]] §2. Code written against a paraphrase does not compile against a
> contract.

**Frozen means:** changing any of it needs the owners on **both sides of the changed edge**, plus a
map revision. Adarsh breaks ties. **Numbers are not frozen** — every tunable lives in
`contracts/tunables.py` and changes with no ceremony at all.

**Language frozen with the signatures, because a signature needs one:** Python 3.11, asyncio, one
process, one repo. *"Not a preference — the carrier and Sarvam are both raw WSS, the whole corpus is
~200 MB in RAM, and a single process with no external services is the only shape that survives every
remaining answer."*

> **Amendment, 10 Sep 2026 — the parenthetical, not the ruling.** The *"~200 MB in RAM"* clause was
> a demo-scale observation, not a requirement; at national scale the pool is ~4.5 GB and the clause
> is false. **The ruling stands unchanged** — one process, no external services — because
> [[03-ARCHITECTURE]] §10.1 makes the pool **lazily read off local SSD with a pinned hot set**,
> which needs no service and no second process. **Read the clause as "the corpus *records* are in
> RAM."** No signature below moves.

---

## Audio — used by Engine

```python
Audio.connect(ws)                -> Audio
Audio.select_language()          -> (Lang, LangSource)      # turn 0; two plays then default hi
Audio.say(sequence)              -> None                    # append-only, returns immediately
Audio.repeat()                   -> None                    # re-fires marks
Audio.clear()                    -> None
Audio.on_mark(mark)              -> awaitable[timestamp]    # playedStream — the ONLY completion signal
Audio.next_input(profile)        -> Digit | Speech | Noise | Silence(n) | Hangup
Audio.language                   -> Lang                    # settable; `*` re-pins via config.update
Audio.hangup()                   -> None
```

- `Speech` carries `text` and, where the DTMF flush fired, `discarded_transcript`.
- `profile` selects the silence gap: **4 s at turn 0, 6 s thereafter, no timer during read-back.**
- **`Audio` never terminates a call.** The silence ladder surfaces `Silence(1|2|3)` and **Engine**
  decides: rung 1 → `repeat()`, rung 2 → the presence line, rung 3 → the closing line, await its
  mark, then `hangup()`.
- **`Audio.hangup()` plays nothing.** *Play the closing line, await its `playedStream`, then hang
  up* is **Engine's** rule to obey, because Engine is the module that knows which closing line.
- `Noise` and `Hangup` are members of the union and are not optional — [[tickets/T14]] gives NOISE
  and SILENCE **different turn-accounting behaviour** (NOISE consumes a cap turn, SILENCE does not),
  and collapsing them erases that in the type system.

## Model — used by Engine

```python
Model(corpus)
Model.opener(transcript, lang)                  -> list[Stamp] | Unclear
Model.turn(transcript, box, window, ask_count)  -> Answer | Clarify | Repeat | Meta | Unclear
Model.failures                                  -> int
```

- `Stamp = (box | "scheme", value, span)`. **The opener returns a list**, including the `scheme`
  pseudo-box; **every question turn returns exactly one result.**
- `window` is the bounded **two-turn** verbatim history. `ask_count` is the per-box rephrase counter.
- **Error behaviour, frozen: `Model` never raises and never returns a value outside the closed
  set.** Hard timeout **2.0 s**, **no in-turn retry**; a timeout returns `Unclear(reason="timeout")`
  and increments `failures`. Engine reads `failures` for the two-strikes-to-keypad-only rule.
- **The span guard is Model's, not Engine's.** Model is the only module holding the transcript and
  the candidate value at the same moment, so closed-set validation and span validation both run
  *inside* Model before it returns. **Engine is structurally incapable of receiving an unvalidated
  value** — the guard stops being a discipline and becomes a type boundary.
- **The model may *read* the last two turns; it may only *quote* from the sentence just spoken.**
  One string comparison enforces it. Widening the haystack weakens the guard in exact proportion:
  *the caller says at turn 1 "my brother in Bihar told me about this", mumbles at turn 5, and the
  span check would pass on a state they never claimed.*

## Engine

```python
Engine.run_call(audio, model, corpus, log) -> None          # the loop

Planner.next_action(box_vector, corpus)    -> Ask(box) | Widen(box) | Stop(reason)
Filter.survivors(box_vector, corpus)       -> tuple[int, ...]
Filter.tally(box_vector, corpus)           -> Mapping[int, int]
Filter.miss_set(box_vector, corpus, ix)    -> frozenset[BoxId]
```

- **`Planner` and `Filter` take no Audio, no Model and no Log.** This is the seam that keeps
  [[tickets/T09]]'s purity claim honest after the loop moved into Engine, and it is what makes
  [[tickets/T13]]'s dry-run **an afternoon rather than a week** — the narrowing runs over the
  utterance table with three of four modules absent.
- **`Widen` is part of the frozen signature.** Deferring the widening ladder is an interface change,
  not a scope cut ([[01-CONTRADICTIONS]] §1.2).
- **Engine assembles the LOG line; Data persists it.** Engine holds every field value; Data owns the
  file, the schema and the flush discipline.
- Engine's three pieces of state are **box vector, turn counter, ladder rung** — which is exactly
  what a [[tickets/T16]] line is made of.

## Data — runtime · `Corpus`

```python
Corpus.load(snapshot_id)                  -> Corpus
Corpus.snapshot_id                        -> str
Corpus.mask(box, value)                   -> int
Corpus.values(box)                        -> tuple[ValueCode, ...]
Corpus.specificity(scheme_ix)             -> int
Corpus.scheme_id(scheme_ix)               -> str
Corpus.alias_lookup(text, lang)           -> tuple[str, ...]            # <=2, by the uniqueness gate
Corpus.alias_set(lang)                    -> Mapping[str, tuple[str, ...]]
Corpus.audio(line_id, lang, value=None)   -> RenderKey
Corpus.chunks(scheme_id, lang)            -> tuple[RenderKey, ...]      # 6, ordered
Corpus.gate_notes(scheme_id)              -> tuple[str, ...]
```

**Error behaviour, frozen: `Corpus` raises at `load` and never during a call.** Every runtime read
is total, because the build gate already guaranteed it. *"A runtime `KeyError` would mean the gate
is broken, and deploy is the right place to learn that — not turn four of a judged call."*

**`Corpus.audio` and `Corpus.chunks` return a `RenderKey` — a name, not bytes.** No signature in
this file passes audio bytes across a module edge, which is why the tiered lazy-read pool
([[03-ARCHITECTURE]] §10.1) is **entirely internal to `haqdaar/audio/` and changes nothing here.**
`load` still raises on a missing or corrupt key; it now proves that by **verifying existence and
digest against the pool index** rather than by reading the pool into memory.

`alias_lookup` returns **at most 2** by construction: the uniqueness gate drops any alias appearing
on ≥3 schemes. **Door A's cap of two candidates falls out of the data, not out of code.**

## Data — runtime · `Log`

```python
Log.open(call_id, snapshot_id)  -> Log
Log.write(line: dict)           -> None
Log.close(reason: str)          -> None
```

**Error behaviour, frozen: a LOG write never kills a call.** A line failing the [[tickets/T16]]
schema is written anyway carrying **`invalid: true`**, with a warning to stderr. *"A malformed line
is still evidence; a missing line is nothing."* **This is the one place in the design where we
deliberately persist something known-wrong.**

## Data — build time (an artifact contract, not a call)

```
snapshots/<snapshot_id>/
  schemes.jsonl      one flat row per scheme (five field groups)
  masks.bin          packed (box, value) -> word
  vocab.json         closed value sets + code map
  templates.json     line_id -> {lang -> render_key}, values expanded
  manifest.json      the snapshot IS the manifest
audio/<render_key>.ulaw    one flat pool, shared across snapshots
```

**`render_key = sha256(text ‖ lang ‖ voice_id ‖ tts_model ‖ 8000)`** — frozen verbatim.

**Line ids are strings resolved through the manifest, never an enum.** [[tickets/T17]] §0 made this
choice deliberately so that `N` could move: *"T15 pinned N ≈ 29 from an enumeration, not a
derivation; if authoring moves it to 27 or 34, nothing recompiles and no interface changes."*
It then moved to 38, then to **46** ([[tickets/T23]]) — and nothing recompiled. The decision paid.

---

## What is *not* frozen

Everything inside a module · the **contents** of the closed value sets · the wording and translation
of every fixed line and question form · voice id and TTS vendor · prompt text inside Model, so long
as the output contract holds · the widening ladder's order · the greeting's clause order.

**And every tunable**, in one unowned file:

| Tunable | v1 value | Source |
|---|---|---|
| `ENDPOINT_MS` | 700 | [[tickets/T14]] — *direction derived, number not. The cheapest dial in the system* |
| `RESPONSE_BUDGET_S` | 1.2 | [[tickets/T14]] |
| `MODEL_TIMEOUT_S` | 2.0 | [[tickets/T14]], [[tickets/T17]] |
| `SILENCE_GAP_S` | 6 | [[tickets/T14]] — derived from T10's ~8 s turn model. *If T10's 8 moves, this moves with it* |
| `TURN0_GAP_S` | 4 | [[tickets/T14]] |
| `MAX_TURNS` | **8** | [[tickets/T10]] D4 — *the one number with no derivation; the dial to turn if the demo runs long* |
| `MAX_QUESTIONS` | **6** | [[tickets/T10]] D4 — a hard wall regardless of turn count |
| `STOP_SURVIVORS` | 4 | [[tickets/T10]] D4 |
| `NEAREST_CAP` | 2 | [[tickets/T18]] — *a restraint number, not a delivery shape* |
| `MODEL_FAILURES_TO_KEYPAD` | 2 | [[tickets/T18]] — per call, **not consecutive** |
| `BOX_STRIKES_TO_KEYPAD` | 2 | [[tickets/T11]] — consecutive, per box |
| `KEYPAD_CARDINALITY_MAX` | 9 | [[tickets/T15]] — above this a box goes to UNKNOWN, never to a menu |
| `ALIAS_FLOOR` | 3 | [[tickets/T12]] — *if it bites, lower the floor rather than admit a scheme the caller cannot name* |
| `CALL_CEILING_S` | 600 | [[tickets/T14]] — *a safety net for a wedged socket, not a design parameter. A ceiling that fires during the test is a bug report, not a caller* |
| `MAX_SOURCE_AGE_DAYS` | 14 | [[tickets/T21]] |
| `AUDIO_CACHE_MB` | **512** | §10.1 — tier-1 LRU ceiling. *Above the whole demo pool, so every demo read is a hit* |
| `AUDIO_PREFETCH_ON_STOP` | `true` | §10.1 — warm the read-back's 18 chunks when `Planner` returns `Stop` |
| `AUDIO_TIER2` | `none` | §10.1 — `none` \| `s3` \| `r2`. **`none` on the demo host**; the object store is a large-deployment backing store, never on a call's critical path |
| `AUDIO_WARM_ON_BOOT` | `true` | §10.1 — fill tier 1 to its ceiling at snapshot flip |

## Related

[[03-ARCHITECTURE]] · [[05-DATA-CONTRACT]] · [[08-TRACEABILITY]] · [[tickets/T17]] ·
[[briefs/audio]] · [[briefs/model]] · [[briefs/engine]] · [[briefs/data]]
