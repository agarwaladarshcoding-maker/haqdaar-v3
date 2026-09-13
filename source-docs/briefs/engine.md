---
title: "Module Brief — Engine"
slug: brief-engine
type: module-note
module: engine
status: reviewed
tags: [brief, engine, planner, filter, owner, staging]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/T17.md
---

# Module Brief — Engine

> One of the four module briefs [[tickets/T17]] §5 requires.

**Owns:** Checker · Filter · Planner — **and the call loop.**

> **The loop was never charted.** Something receives an Ear event, decides NOISE vs SILENCE vs
> keypress, calls Model, calls Engine, calls Mouth, writes the LOG line, counts turns, runs the
> silence ladder, and holds the box vector. *"The nine stages never named it and no ticket ever
> assigned it. It was invisible because every ticket resolved a decision the loop makes, and none
> resolved the loop."* [[tickets/T17]] assigned it here — **the one place that ticket did more than
> its title.**

**Why Engine and not Audio** — the near miss: Audio already owns the turn *clock*, and a turn is a
clock construct. But **the loop's state is the box vector**, and putting the box vector inside the
language-pinned module makes the language-blind Engine a subroutine of it, **inverting the
dependency [[tickets/T09]] established on purpose.** Engine's three pieces of state — box vector,
turn counter, ladder rung — *are already Engine's, and are exactly what a [[tickets/T16]] line is
made of.* Nothing moved; something nameless acquired a name.

**Price paid honestly:** *"the Engine is pure code"* narrows to **Planner and Filter are pure; the
loop is not.**

**Day-one test:** run P1 to a stop in ≤4 turns, and **P2 through the full ladder to two nearest
schemes labelled as non-matches.**

## Signature block

```python
Engine.run_call(audio, model, corpus, log) -> None

Planner.next_action(box_vector, corpus)    -> Ask(box) | Widen(box) | Stop(reason)
Filter.survivors(box_vector, corpus)       -> tuple[int, ...]
Filter.tally(box_vector, corpus)           -> Mapping[int, int]
Filter.miss_set(box_vector, corpus, ix)    -> frozenset[BoxId]
```

**`Planner` and `Filter` take no Audio, no Model and no Log.** That seam is what makes
[[tickets/T13]]'s dry-run **an afternoon rather than a week.**

## The clauses, and the ticket behind each

### State

| Clause | Ticket |
|---|---|
| **Masks are retained, not folded.** `survivors = survivors AND mask` is *correct and insufficient* — a set has no notion of *near*, and a bare tally cannot tell a health scheme that missed `category` from a Maharashtra scheme that missed `state` | [[tickets/T09]] 2 |
| **The box vector is the only state.** Survivors, tally and miss-set are **always derived, never maintained.** Cost: six machine words per call | [[tickets/T09]] 2 |
| **There is no undo stack, because there is nothing to undo.** A correction overwrites one box and everything re-derives | [[tickets/T09]] 4 |
| **A correction does not discard other boxes**, even ones asked because of the corrected value. Planner decides whether any are worth re-asking | [[tickets/T09]] 4 |
| **`UNASKED` and `UNKNOWN` are the same instruction to the filter — no mask appended.** They differ only in the LOG and to the Planner. **The only real difference: UNASKED is still askable; UNKNOWN is removed from the pool and never revisited** | [[tickets/T09]] 3 · [[tickets/T11]] 4 |
| **UNKNOWN always widens, never narrows** — and counts as **not satisfied** for the speaking rule, identically to UNASKED | [[tickets/T09]] · [[tickets/T11]] |
| **Engine is language-blind.** No language tag ever crosses its boundary; the box vector holds **codes** | [[tickets/T09]] 6 |
| **No runtime negation, ever. No numerics at runtime** — categorical codes only, never a number, never a comparison | [[tickets/T09]] 6 |
| **Out-of-set code:** impossible by construction, hardened anyway — treat as UNKNOWN, append no mask, log it, re-ask | [[tickets/T09]] 6 |

### Choosing and stopping

| Clause | Ticket |
|---|---|
| **Minimax elimination ÷ expected turns.** Score by the **worst** answer; lowest wins; keypad 1 turn, spoken 2; ties on **snapshot order**, so the LOG reproduces the call exactly | [[tickets/T10]] D2 |
| **Information gain was rejected** — it needs a caller prior we do not have, and a uniform prior makes entropy a proxy for *how many values a box has*, so `state` (36) outranks `gender` (2) every turn of every call. *"Minimax puts a guarantee in the LOG instead of an expectation"* | [[tickets/T10]] D2 |
| **No mandatory questions.** Hard boxes first **only while they still split the survivor set** — *asking gender when every survivor is `ANY` on gender is pure annoyance* | [[tickets/T10]] D3 |
| **The speaking rule carries the guarantee instead:** a scheme non-`ANY` on an **unasked hard box** may not be spoken. Same shape as the never-speak rule, so no new machinery — and it closes the hole **without spending four turns up front** | [[tickets/T10]] D3 |
| **Four stops:** ≤4 survivors · **8 turns, with a hard wall at 6 questions** · no box splits the survivors · **zero survivors, named separately in the LOG** | [[tickets/T10]] D4 · [[tickets/T18]] 1 |
| **Do not stop on ≤4 while an unasked hard box is non-`ANY` on any survivor.** Ask it first, or the call stops holding schemes it may not speak | [[tickets/T10]] D3 |
| **Stop at 1 survivor and speak it.** Do not widen upward to manufacture a second — *padding is a lie* | [[tickets/T10]] D4 · [[tickets/T04]] |
| **Turn 0 writes a line and does not count against the cap.** *The cap is a predicate on the counter, not a claim that every line is a cap turn* | [[tickets/T24]] 5 |
| **SILENCE does not consume a cap turn; NOISE does** | [[tickets/T14]] |
| **The opener costs 2 turns if it fills anything, 1 if it fills nothing**, and the ladder starts **from what the opener filled and the caller confirmed** — not an empty vector | [[tickets/T11]] 3 · amendment to T10 |

### Speaking

| Clause | Ticket |
|---|---|
| **Specificity, not tally, orders survivors.** Every survivor holds every answered box by construction, so their tallies are **identical** — tally only works at zero survivors. **Specificity = the count of non-`ANY` boxes matched on.** Without it, *the top of every list is the most generic scheme in the corpus, on every call* | [[tickets/T10]] D5 |
| **Widening: soft boxes only, one at a time, `income_band → age → occupation`** — least-trusted first. **`category` is never widened** (amended 13 Sep 2026): the caller's stated need is not a constraint to relax. **A trust order, not an efficiency one** | [[tickets/T10]] D6 · [[tickets/T18]] 1 |
| **Stop at the first rung producing ≥1 survivor.** *Every rung discards a fact the caller stated; discarding more than necessary is a larger misstatement of what was matched on* | [[tickets/T18]] 1 |
| **Rungs over UNASKED/UNKNOWN soft boxes are skipped, not counted** — they appended no mask, so there is nothing to widen. At most 4 rungs; typically 1–2 run | [[tickets/T18]] 1 |
| **Widening can never reintroduce a hard-box violation**, by construction | [[tickets/T18]] 1 |
| **Three terminals, and they must not share wording:** widened match (a real match on a stated-smaller set) · nearest (**not a match at all**, cap 2, `summary` only, no section menu) · empty. **This distinction is the whole of T18** | [[tickets/T18]] 2 |
| **Bad-news-first is an ordering rule, not a phrasing** — asserted at build against the `say(sequence)` order, and *it survives translation because it is a property of order, not of words* | [[tickets/T18]] 2 |
| **Every dropped box is named, never summarised** — *"some of what you told me" is the softening that lets a caller believe more was matched than was* | [[tickets/T18]] 2 · [[tickets/T10]] D8 |
| **>4 survivors at the cap: top 3 by specificity, spoken as matches** — they *are* true matches — plus one line saying more matched than could be read | [[tickets/T10]] D7 |
| **`section_source_frame` never before a `summary`** | [[tickets/T21]] 3 |
| **Nearest terminals auto-advance and never play `section_menu`** | [[tickets/T23]] |

### Failing

| Clause | Ticket |
|---|---|
| **Two ladders, kept apart.** Box-level: 2 consecutive non-ANSWER on a box → its keypad menu (or straight to UNKNOWN if cardinality > 9). Call-level: keypad-only for the rest of the call | [[tickets/T11]] · [[tickets/T15]] · [[tickets/T18]] 3 |
| **Call-level triggers: 2 model failures per call, NOT consecutive** (*consecutive would let an alternating pattern burn eight turns*) **or 1 unrecovered ASR socket** after one free reconnect | [[tickets/T18]] 3 |
| **An UNCLEAR is not a failure** — *"it is a successful model turn reporting that it could not hear."* Counting it *"would drop healthy calls on a noisy line"* | [[tickets/T18]] 3 |
| **Two non-ANSWERs on a box already on the keypad drop it to UNKNOWN** — there is nowhere else to go. An out-of-menu digit is one such non-ANSWER; replay the question once | [[tickets/T18]] 4 |
| **Keypad-only is a mode, not a terminal state** — the call continues to an ordinary terminal, and that is a **pass.** *This corrects [[tickets/T16]].* Written once, consumes no turn | [[tickets/T18]] 3 |
| **The binding worst case:** a drop at turn 1 with an empty vector — five keypad boxes at 1 turn each = **5 against a cap of 8. It fits** | [[tickets/T18]] 4 |
| **Silence ladder: rung 1 replays the question**, not a presence check — *"on this corpus silence means didn't follow, not walked away."* Rung 2 presence, rung 3 closing + hangup. ~30 s of grace | [[tickets/T14]] 3 |
| **Any keypress resets the ladder to rung 0** — the ladder measures presence, and a keypress is presence | [[tickets/T23]] 1 |
| **Every self-initiated ending uses the same closing line**, and hangup waits on its mark. **No per-terminal goodbye variants** — that tells the caller which failure they hit, which is information for us and is already in the LOG | [[tickets/T18]] 5 |
| **"Anything else?" clears only `category`** — so a Door A caller reaches Door B from a near-empty vector at normal price, after `t_end`, leaving the 20 s bar untouched | [[tickets/T18]] 6 · map rev 2 |

**Engine assembles the LOG line; Data persists it.** Engine holds every field value; Data owns the
file, the schema and the flush discipline.

## Yours to change without asking

Everything inside `engine/` · the widening ladder's **order** · every tunable, including both caps.

## Open, and yours to close

- **The 8-turn cap has no derivation** — ~65 s of questioning at ~8 s/turn, set by feel.
  **Named as the single dial to turn if the demo runs long.** [[tickets/T13]] is its first evidence.
- **[[tickets/T13]] — dry-run the narrowing on real schemes.** Blocked only on a snapshot.
- **Multi-value boxes** — deferred, because they blur the miss-set the whole fallback rests on.
- **Per-cell hard/soft** — `age` is a wall on a pension and blur on a scholarship. Correct, and it
  reopens [[tickets/T06]]. Not for v1.

## Related
[[03-ARCHITECTURE]] · [[04-INTERFACES]] · [[notes/engine/overview]] · [[tickets/T09]] ·
[[tickets/T10]] · [[tickets/T13]] · [[tickets/T16]] · [[tickets/T17]] · [[tickets/T18]]
