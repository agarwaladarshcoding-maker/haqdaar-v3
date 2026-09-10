---
title: "Module Brief — Data"
slug: brief-data
type: module-note
module: data
status: reviewed
tags: [brief, data, corpus, log, owner, staging]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/T17.md
---

# Module Brief — Data

> One of the four module briefs [[tickets/T17]] §5 requires.

**Owns:** Corpus + LOG — a **build-time half** (scrape → derive → translate → gates → render →
snapshot) and a **runtime half** (read the snapshot, append the trace).

> **The pairing looked arbitrary and is not.** [[tickets/T16]] made the trace unreadable without the
> snapshot id and the box vector, so **LOG and Corpus share a reader, and splitting them would split
> that reader.**

**Also owns the renderer** — *a Data build tool wearing Mouth's name.* Audio owns only what runs
during a call.

**Also curates the fixture**, because the fixture is a miniature snapshot and Data's build already
emits snapshots. *Any other curator guarantees the fixture and the real snapshot drift in shape, and
the drift shows up as four passing fakes and one failing integration.*

**Day-one test:** load the fixture; answer `mask` / `specificity` / `chunks`; **reject the sixth
scheme, missing its Marathi `summary`, at the build gate.**

## Signature block

```python
Corpus.load(snapshot_id) -> Corpus     # raises HERE and only here
Corpus.mask(box, value) · values(box) · specificity(ix) · scheme_id(ix)
Corpus.alias_lookup(text, lang) · alias_set(lang)
Corpus.audio(line_id, lang, value=None) · chunks(scheme_id, lang) · gate_notes(scheme_id)

Log.open(call_id, snapshot_id) · Log.write(line) · Log.close(reason)
```

Full artifact contract in [[05-DATA-CONTRACT]].

## The clauses, and the ticket behind each

| Clause | Ticket |
|---|---|
| **Eligibility is facets, not rules.** One flat row per scheme, five field groups | [[tickets/T06]] |
| **One sentinel: `ANY`.** Card silence maps to it, faithfully — *myScheme's own search returns a facet-silent scheme for every value of that facet.* **A second UNKNOWN sentinel was rejected: it would let a half-captured row enter the corpus wearing a disclaimer. The build gate does that job better** | [[tickets/T06]] |
| **A row that cannot be fully expressed does not enter the snapshot at all** — dropped, never spoken with a caveat | [[tickets/T06]] |
| **`facets_verified_by: null` on every v1 record.** The pipeline runs end to end with no human; the missing read is **visible in the data**, not assumed. The gates still exclude a bad record | map **rev 26** |
| **Numerics stored exact, collapsed to closed sets only at build.** No banding at capture — it would lose precision to buy nothing | [[tickets/T06]] |
| **Exclusions are pre-folded into a column's admitted set at capture**; what cannot be folded becomes `gate_notes` — **a list, never spoken, never filtered on.** *[[tickets/T16]] cannot prove a choice is clean without it* | [[tickets/T06]] |
| **`summary` resolves a real collision:** the 20 s bar vs verbatim `benefit_text` in Marathi. *Without this field Door A misses the bar by construction* | [[tickets/T06]] |
| **The record stores text, never audio.** There is no audio column | [[tickets/T06]] |
| **The mask table is built once per snapshot, frozen with it, never computed during a call.** `ANY` sets the bit in **every** mask for that column | [[tickets/T09]] |
| **The snapshot IS the manifest**, not a directory. **`audio/<render_key>.ulaw` is one flat pool, shared across snapshots**, never nested | [[tickets/T15]] |
| **`render_key = sha256(text ‖ lang ‖ voice_id ‖ tts_model ‖ 8000)`.** *Text alone is wrong — a voice change would silently make every cached caller hear last month's read-back* | [[tickets/T15]] |
| **A call binds to one snapshot at connect and holds it to hangup.** Deploy renders missing keys, writes the manifest, flips a pointer. **In-flight calls finish on the old snapshot** | map rev 3 · [[tickets/T15]] |
| **Zero live rendering.** Every string the system can ever speak is enumerable at build time, so **TTS is a build tool, not a runtime dependency** | [[tickets/T15]] |
| **Composition rule:** compose from separate files **only where the pieces must be independently addressable at runtime.** **Chips after a colon pause are allowed; slots inside a sentence are forbidden** — *a slot inside a clause has agreement to break in Hindi and Marathi; a bare noun chip after a colon has none* | [[tickets/T15]] · [[tickets/T23]] 3 |
| **One loudness pass, 120 ms fixed tail, every file.** Load-bearing — *the read-back concatenates six files, and a level mismatch sounds like a fault on a phone line* | [[tickets/T15]] |
| **Five build gates, run as a pre-filter ordered by cost:** alias floor (cheapest, excludes most) → expressibility → forbidden phrase → provenance → **read-back completeness last, the only one that spends TTS** | [[tickets/T07]] · [[05-DATA-CONTRACT]] §3 |
| **Alias uniqueness is a gate, not authored code.** ≥3 schemes → dropped from all (it is a category word); **exactly 2 → kept, and those two ARE the Door A disambiguation pair.** *No ambiguity list is ever written by hand* | [[tickets/T12]] · [[tickets/T07]] |
| **Provenance lives on the record, not on the snapshot number** — *"a snapshot's number says when it was built, not when its text was read."* `source_url` · `fetched_on` · **`source_sha256`, which makes drift a comparison instead of a reading** | [[tickets/T21]] 1 |
| **Host check on `source_url`.** [[tickets/T02]] found a third-party dataset that **fabricates eligibility rules and Hindi text on fetch failure.** *The cheapest defence against inheriting it* | [[tickets/T21]] 1 |
| **A null `verified_by` must mean "no human touched this", never "someone forgot".** If either origin is `human`, `verified_by` and `verified_on` are required | [[tickets/T21]] 2 |
| **The caller never hears a date.** *"As of 11 September" sounds like a guarantee and isn't one*, and a feature-phone caller cannot check it. **Freshness is a gate, not a sentence** | [[tickets/T21]] 3 |
| **Drift: re-fetch and re-hash once, the evening before the freeze. A changed hash excludes the record until its owner re-reads it. No auto-accept** — the hash tells *that* the text changed, not *whether it matters* | [[tickets/T21]] 4 |
| **Snapshot records and manifests outlive any LOG that names them** — committed to the repo. **The sweep may delete audio, never records** | [[tickets/T21]] 5 |
| **`Corpus.load` raises, and only there.** *A runtime `KeyError` would mean the gate is broken, and deploy is the right place to learn that — not turn four of a judged call* | [[tickets/T17]] 2 |
| **`Log.write` never kills a call.** A schema-failing line is written anyway with `invalid: true`. *A malformed line is still evidence; a missing line is nothing.* **The one place we deliberately persist something known-wrong** | [[tickets/T17]] 2 |
| **The trace explains; it does not replay.** Audio dies at hangup, so text reconstruction is the whole requirement | [[tickets/T16]] 1 |
| **Derive, don't store.** Snapshot id + ordered box vector reconstruct the call. **The only exceptions — `stop` and `ladder_rung` — are written once**, because *they are not properties of the state; they are which branch the code took* | [[tickets/T16]] 2 |
| **One file, two readers. No summary object** — *if it is trustworthy it is derivable, and if it is derivable it should not be stored* | [[tickets/T16]] 6 |
| **NOISE writes a line** though it never reaches the model — without it, *an 8-turn cap that fired after three visible turns reads as a bug* | [[tickets/T16]] 3 |

## The rule that governs the whole ingest pass

> **No clause of the pass may scale with N in human time. 50, 100 or 5,000 must cost the same number
> of people, which is zero.** ([[tickets/T07]] rev 22)

**The only human in HAQDAAR is the caller.** Facets are model-derived with `facets_source: derived`;
`summary` is generated in English and translated; verifier initials are dropped.

**What this costs, recorded rather than absorbed:** *"prose that says 'preference shall be given to
women' is not the same as 'for women', and the model may flatten it."* Named exposure, with
[[tickets/T21]] over it — **not a defect discovered later.**

## Yours to change without asking

Everything inside `data/` · **the contents of the closed value sets** (changed daily) · the wording
and translation of every fixed line · the voice id and TTS vendor · every tunable, including
`ALIAS_FLOOR` and `MAX_SOURCE_AGE_DAYS`.

## Open, and yours to close

- **The alias floor of three was set from feel**, and a wrong floor **silently shrinks the corpus.**
  Named as the dial: *if it bites, lower the floor rather than admit a scheme the caller cannot
  name.* [[tickets/T12b]] is its first evidence.
- **[[tickets/T07]] is the head of the execution frontier** — it derives the keypad band edges, the
  value-chip list and the `occupation` vocabulary (**keep its cardinality ≤9** or it loses its
  keypad menu).
- **Occupation's `vocab_source` is `corpus_prose_cut`**, not the portal. Recorded at snapshot level.
- **The eventual production scheme count** — out of the v1 bar by [[tickets/T04]]; N is a build
  parameter.

## Related
[[03-ARCHITECTURE]] · [[04-INTERFACES]] · [[05-DATA-CONTRACT]] · [[notes/data/overview]] ·
[[tickets/T02]] · [[tickets/T06]] · [[tickets/T07]] · [[tickets/T08]] · [[tickets/T15]] ·
[[tickets/T16]] · [[tickets/T21]] · [[tickets/T22]]
