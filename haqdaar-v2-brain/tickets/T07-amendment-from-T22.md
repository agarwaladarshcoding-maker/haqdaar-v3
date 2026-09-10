---
title: "T07 — amendment from T22 (10 Sep 2026, MAP rev 21)"
slug: T07-amendment-from-T22
type: ticket
module: architecture
status: open
tags: ["ticket", "module/architecture", "status/open", "type/ticket"]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: sync_vault.py
source_file: source-docs/T07-amendment-from-T22.md
blocked_by: []
blocks: []
---

# T07 — amendment from T22 (10 Sep 2026, MAP rev 21)

> Splice this into `tickets/T07.md`. I do not have the current T07 body, so this is an amendment block rather than a rewritten file — paste it under the existing amendments from T12, T24 and T15, and change the header line as noted.

---

## Header change

**Blocked by:** ~~T06~~, ~~T22~~ — **T22 closed 10 Sep; T07 is fully unblocked.**

---

## Amendment: the occupation vocabulary is now T07's to cut

T22 was going to hand T07 an occupation value list recovered from the myScheme wizard. It closed instead by narrowing: the wizard's rail is the retired 18-box one, and the portal was never going to be authoritative anyway, because T02 established that eligibility is prose and every filter value is derived by us at ingest. **The cut moves inside T07.**

**It is a step in the ingest pass, not a phase in front of it.** The pass already opens every scheme's eligibility prose to derive its facets; the occupation vocabulary falls out of that same read. Doing it first as a separate pass would read the prose twice.

### The rule the list must satisfy

**A value earns a place only if at least one scheme in the corpus discriminates on it.** Not "the occupations Indian citizens have" — the occupations *these schemes distinguish between*. Two consequences:

- The list is **closed over the corpus by construction**, which is what T06's build gate wants (a row that cannot be fully expressed does not enter the snapshot) and what T08's offline test base wants (~150–200 values per language, frozen, testable against a table of utterances).
- The list **grows with the corpus and that is correct**, not drift. Adding schemes may add values; the mask table is rebuilt at build time anyway (T06), so this costs a rebuild and nothing else.

### Cardinality is a live constraint, not a footnote

**T15 (rev 19): a box with more than nine values cannot be keypad-dropped.** `occupation` is a **soft** box (T10) and sits third in the widening ladder, so it is one of the boxes most likely to be reached by the fallback path with a caller who has already failed twice on it.

- **At ≤9 values, `occupation` keeps its keypad menu** and T11's two-non-ANSWER drop works normally.
- **Above 9, it falls straight to UNKNOWN**, and T09's widening takes it from there — safe, but it costs a box the ladder was counting on.

**So the count is a design decision, not an outcome.** Cut for ≤9 if the corpus allows it; if the honest count runs over, record the number and the reason rather than trimming to fit, and note that `occupation` has lost its keypad form.

### Three languages, same rule as every other keyword

The list is part of T08's keyword list, so it ships in all three languages: **written once per language, one audio file per value** (T15 — never a carrier sentence with a slot dropped in, because a joined-in inflection error in Hindi or Marathi reads as broken). Naive translation, truth lock suspended (rev 11), debt recorded.

**Code-mixing applies here as it does to aliases.** T24 required at least one code-mixed alias per non-English language on the grounds that scheme names are proper nouns nobody translates. Occupation words are the opposite case — *farmer*, *student*, *labourer* have real Hindi and Marathi forms callers actually use — but **the English word is often spoken inside a Marathi sentence anyway**. The span guard compares the span against the transcript, not against a vocabulary, so this is handled; but the **utterance table for the offline test base must contain the code-mixed forms**, or the test base tests a caller who does not exist.

### What was lost, and where it is recorded

We can no longer say the occupation vocabulary came from the portal. **Provenance, not correctness** — [[tickets/T21|T21]] owns it. If anyone later runs the optional 20-minute wizard errand, the portal list is a **cross-check**, and a divergence is evidence for T21 rather than a defect in T07.

---

## Standing amendments already on T07 (unchanged, listed for one place to look)

- **T12 (rev 15) — alias contract:** ≥3 aliases per language per scheme, stored as spoken, build-time uniqueness gate. An alias on ≥3 schemes is a category word and is dropped from all of them; an alias on exactly 2 *is* the disambiguation pair, which is where Door A's cap of 2 candidates comes from. A scheme below the floor does not enter the snapshot.
- **T24 (rev 17) — code-mixed aliases:** at least one alias per non-English language must be the code-mixed form.
- **T15 (rev 19) — read-back gate:** a scheme missing any of its six read-back chunks rendered in any of the three languages does not enter the snapshot. Same shape as the alias floor.
- **T17 (rev 20) — fixture curation:** Data's owner curates the five-scheme fixture (match / soft-miss / hard-miss / near-`ANY` generic / alias-sharing pair) plus three personas, and the fixture *is* T08's offline test base — one artifact, not two.

---

**Amendment recorded 10 Sep 2026 · MAP rev 21 · source: T22 close**


---
**Module Overview:** [[notes/architecture/overview|Architecture Module]] · **Wayfinder Map:** [[maps/wayfinder-map|Latest Map]]
