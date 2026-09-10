---
title: "Decision Log — supersession chains"
slug: decision-log
type: module-note
module: architecture
status: reviewed
tags: [decisions, supersession, traceability, staging]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/MAP-done.md
---

# Decision Log — what overrode what

**Why this file exists.** [[maps/wayfinder-map|The map]] records decisions in the order they were
made. Several were later **overturned by a ticket that closed after them**, and the override is
recorded inside the *later* ticket — so a reader landing on the earlier one gets a stale answer.
This file is the index of those chains. It stores no new decisions; it points.

Read with [[RULES.md]] §6: *if a decision invalidates an earlier note, the old note is marked
`superseded` with a pointer to the new one.*

---

## 1 · Superseded within the design

| Original | Superseded by | What changed |
|---|---|---|
| map rev 2 — *"widen the last mask and retry once"* | [[tickets/T09]] 5 | **Widening by recency is unsafe** — if the last box was `state`, it manufactures schemes the caller is geographically barred from. Replaced by a **soft-only** ladder |
| [[tickets/T09]] — *"an order T10 supplies"* | [[tickets/T10]] D6 | The order is **`income_band → age → occupation → category`** — least-trusted first |
| [[tickets/T10]] D6 — *"stop the moment ≥2 schemes are speakable"* | [[tickets/T18]] 1 | **Stop at the first rung producing ≥1 survivor.** *Every rung discards a fact the caller stated* |
| [[tickets/T10]] D4 — three stops | [[tickets/T18]] 1 | **Zero survivors is a fourth stop, named separately in the LOG** — a reader must tell *nothing was left* from *no question helped* |
| [[tickets/T06]] — *"a turn is one AND instruction"* | [[tickets/T09]] 2 | **One pass, one word retained per turn.** Masks are kept, not folded |
| [[tickets/T09]] 7 — survivor counts stored as a replay assertion | [[tickets/T16]] 2 | **Struck.** *Storing survivor sets would be a second copy of a derivable fact — redundancy dressed as proof* |
| [[tickets/T11]] — echo-confirm **unconditional** | [[tickets/T12]] | **Narrowed to box values. Door A is exempt** — the read-back is the confirmation |
| [[tickets/T11]] — box drop to keypad on two strikes | [[tickets/T15]] | **Cardinality > 9 → straight to UNKNOWN, never a keypad menu.** `state` has 36 values |
| [[tickets/T11]] — box drop to keypad | [[tickets/T18]] 4 | **Completion:** two more non-ANSWERs on a box *already* on keypad → **UNKNOWN.** There is nowhere else to go |
| [[tickets/T11]] 5 — model timeout 1.5 s | [[tickets/T14]] 1 · [[tickets/T17]] | **2.0 s hard timeout**, no in-turn retry |
| [[tickets/T11]] — *"the model class META is the language route"* | [[tickets/T24]] 3 | **Structurally impossible** — *to hear "can we speak in Marathi?" you must understand a caller you have just established you cannot understand.* The route is `*` on the keypad |
| map rev 2 — speech barge-in *if the provider streams live media* | [[tickets/T14]] 2 | The condition **resolves to yes and is declined anyway.** *Listen always, interrupt only on keypad* |
| earlier ruling — *"audio beats DTMF"* | [[tickets/T14]] 5 | **Overturned.** The turn closes on the **first complete input**; a keypress is complete on arrival |
| charting — *"only short echo fragments render live"* | [[tickets/T15]] | **The live-rendering ceiling drops to zero.** TTS leaves the runtime entirely |
| [[tickets/T15]] — *never carrier-plus-slot* | [[tickets/T23]] 3 | **Narrowed:** chips after a colon pause are fine; slots inside a sentence stay forbidden. This **struck the ~600-file `confirm_<box>_<value>` carrier family** |
| [[tickets/T16]] — *a keypad-only drop is a terminal state* | [[tickets/T18]] 3 | **Correction: keypad-only is a MODE.** The call continues to an ordinary terminal — and that is a pass |
| [[tickets/T18]] — forbidden-phrase gate as a **bare-word ban everywhere** | [[tickets/T23]] 4 | **Two tiers.** A bare-word ban over verbatim sections would exclude nearly every myScheme scheme, because *their own eligibility prose says "eligible"* |
| [[tickets/T23]] first pass — *"compliance: zero occurrences"* | [[tickets/T23]] 5 | **The claim was false — the brand name is the forbidden word.** `closing_farewell` says हकदार. Fixed with a **closing-only allowlist** |
| [[tickets/T06]] — `facets_verified = YES` required, human-read | [[tickets/T07]] rev 22 | **The human is out of the loop.** Replaced by `facets_source: derived`. [[tickets/T21]] keeps `facets_verified_by/on` as **nullable** fields so reinstating means filling a field, not changing a schema |
| [[tickets/T04]] branch 5 — *all chunks human-verified in three languages* | [[tickets/T08]] · [[tickets/T07]] | **Truth lock suspended.** *The corpus entering the demo does not satisfy the acceptance ticket's own branch 5* — a named debt, in [[10-RISK-REGISTER]] |
| [[tickets/T14]] — inventory `3N + 2` | [[tickets/T15]] · [[tickets/T24]] | **`3N + 1`** — the +1 is the single trilingual greeting |
| [[tickets/T15]] — N ≈ 29, ~88 files | [[tickets/T18]] → **[[tickets/T23]] 5** | N moved 29 → ~38 → **46. Final: 139 files.** *Nothing recompiled* — T17 made line ids manifest-resolved strings for exactly this |
| [[tickets/T01]] — **Plivo, India data region** | map **rev 25** | **Suspended for build.** Twilio +1 first, behind the Audio seam; **Plivo becomes a second adapter, not a redesign** |
| [[tickets/T11]] §5 — **Gemini Flash-Lite, paid key, *"turn billing on"*** | map **rev 27** | **Overturned on budget, not on argument.** Groq free tier, with T11's own objection accepted as fact and answered by **spending fewer model calls**: two model moments per call, alias match in code first, **a 429 is a [[tickets/T18]] failure**, no in-turn retry, model id a tunable. *The three-field contract, span guard and closed sets are untouched — the provider changed, not the contract* |
| [[tickets/T04]] · map rev 25 — **the ten-call test on 12 Sep** | map **rev 26** | **Moved to 14 Sep night.** 12 Sep survives as the internal deadline for [[03-ARCHITECTURE]] and [[06-BUILD-PLAN]]. A bar amendment, recorded where bar amendments belong |
| [[tickets/T19]] — **the laptop-dies drill, spare machine, cold switch** | map **rev 26** | **Dropped.** No second person, no second machine — *"Adarsh builds solo; the team works on the presentation."* Restart loop and hotspot drills stay. **A dead laptop is now a dead demo, stated rather than implied** |
| [[tickets/T17]] §6 — **merge the modules if the team is under four** | map **rev 26** | **Not taken.** Four modules and `contracts/` stay: each agent step is scoped to one module, and *the seams are what keep a step small and reviewable* |
| [[tickets/T06]] — human facet check | map **rev 26** | **`facets_verified_by: null` on every v1 record.** The pipeline runs end to end without a human; the debt is **visible in the data**, and the build gates still exclude a bad record |
| [[tickets/T19]] — *"a small cloud instance"* | [[tickets/T19]] rev 24 | **Overturned on the calendar, not on taste.** A laptop behind a stable tunnel domain — *a demo host, written down as one* |
| [[tickets/T15]] — *the runtime holds no TTS credentials* | [[tickets/T19]] | **Weakened to a code rule.** One Sarvam key covers Ear and Mouth, so the credential cannot be withheld. The runtime imports no TTS client, **and a test asserts it** |
| [[tickets/T22]] — recover two myScheme value lists | [[tickets/T22]] · [[tickets/T07]] | **Closed by narrowing.** Five of six items retired with the 18-box rail; the `occupation` cut folded into T07's ingest pass |

## 2 · Dependencies that ran backwards

Recorded because it happened **four times** and is a pattern worth noticing, not an accident.

| Filed as | Actually ran | Ticket |
|---|---|---|
| T12 blocked by T07 | **T12 handed T07 the alias contract** | [[tickets/T12]] |
| T17 blocked by T23 | **T17 froze the id space; T23 fills it.** The edge was **cut, not satisfied** | [[tickets/T17]] 0 |
| T07 blocked by T22 | T22's occupation cut folded **into** T07 | [[tickets/T22]] |
| T18 blocked on *"does a Door A caller reach Door B?"* | **The route already existed** — *"anything else?"* clears only `category`. *"It only needed someone to say so"* | [[tickets/T18]] 6 |

## 3 · Designed, costed, and deliberately switched off

Each is **one flag or one config line.** None is missing work; each is a recorded choice.

| Feature | The dial | Why off | Ticket |
|---|---|---|---|
| **Speech barge-in** | fire `clearAudio` on `vad.speech_start` | *A false trigger on 8 kHz household audio costs the caller the question; a true one saves ~2 s. The asymmetry runs the wrong way and the corpus is noisy* | [[tickets/T14]] 2 |
| **Language detection as a hint** | a detector that only *offers* a switch after disagreeing twice | Determinism, the test table and the trace all survive because it **prompts and never acts.** Costs one line ×3 | [[tickets/T24]] |
| **Per-DID language default** | three numbers, one per language | **Costs zero turns** — the strongest argument anyone made in T24. Loses only because the bar says *a* live number and one poster carries one | [[tickets/T24]] |
| **Input pin ≠ output pin** | one config line: pin input `hi` whenever output is `en` | For the Hinglish caller who presses 3. *Evidence first* — [[tickets/T13]] | [[tickets/T24]] |
| **Multi-value boxes** | OR the two value masks into one turn mask | *Mechanically cheap*, but it **blurs the miss-set, which the whole soft-only fallback rests on** | [[tickets/T09]] |
| **`door_a_downgrade_to_b` courtesy line** | already authored in the inventory | Engine may toggle it if latency allows | [[tickets/T23]] |

## 4 · Numbers with no derivation — the named dials

*"Every other number in T10 came from structure; these came from feel."* Each lives in
`contracts/tunables.py` and changes with no ceremony.

| Number | Set by | First evidence |
|---|---|---|
| **8-turn cap** | [[tickets/T10]] D4 — ~65 s at ~8 s/turn. *The single dial to turn if the demo runs long* | [[tickets/T13]] |
| **700 ms endpoint window** | [[tickets/T14]] 1 — *the direction is derived, the number is not.* Deliberately above the vendor's 250–500 ms: *dead air costs a second; a cut-off costs a turn* | [[tickets/T13]]; tunable **mid-demo on a live stream** |
| **Alias floor of 3** | [[tickets/T12]] — *a wrong floor silently shrinks the corpus.* **If it bites, lower the floor rather than admit a scheme the caller cannot name** | [[tickets/T12b]] |
| **2-turn context window** | [[tickets/T11]] 6 — settled by argument, **prediction recorded rather than measured** | [[tickets/T13]]'s three-way bake-off |
| **Nearest cap of 2** | [[tickets/T18]] 2 — *a restraint number, not a delivery-shape number* | — |

## 5 · Deviations introduced by *this* rebuild — each needs Adarsh's ratification

**Nothing below is a decision I made. Each is a question the brain leaves open or a place where the
current docs departed from it.** They are listed so they get ratified rather than absorbed.

**Updated after map rev 27 reached the vault: D1 and D2 are closed by the map itself.**
**Updated again 10 Sep 2026: D3 is ratified — minimax, day one.** No decision in this table is
open; D7 is a measurement Step 14 produces, not a decision.

| # | Item | Status |
|---|---|---|
| D1 | **LLM provider.** | **Closed by map rev 27 — Groq free tier.** No ticket amendment is owed: a map revision outranks a ticket, and rev 27 *is* the amendment. See §1 |
| D2 | **Demo date.** | **Closed by map rev 26 — 14 Sep** for the ten-call run, 12 Sep for architecture and build plan |
| D3 | **Minimax planner vs a fixed question order.** [[tickets/T10]] D2 ratified minimax | **Closed — minimax, day one. Ratified by Adarsh, 10 Sep 2026.** Rev 26's *"every feature present in its simplest form"* is the ratified feature simplified, not replaced; minimax is ~15 lines over an existing `Filter` and is what lets the LOG reproduce a call exactly. **The fixed-order stand-in is withdrawn** — no deviation is recorded, because none is taken. Built in [[06-BUILD-PLAN]] Step 4; stated in [[03-ARCHITECTURE]] §7.3 |
| D7 | **[[tickets/T14]]'s 300–500 ms model-call budget is unverified** after the provider change — it was measured against Gemini Flash-Lite, and the 1.2 s response clock rests on it | **Open, but it is a measurement, not a decision.** Step 14's bake-off reports p50/p95; if Groq misses, the clock moves, not the provider |
| D4 | **The widening ladder is v1, not v2.** Restored here, because `Widen` is a frozen signature and [[tickets/T04]] branch 3 makes it a pass/fail condition | **Restored — no ratification needed; the deferral was the deviation** |
| D5 | **`*` mid-call re-pin is v1.** Restored — [[tickets/T24]] costed it at zero in every module and [[tickets/T23]] implemented it with no new audio | **Restored** |
| D6 | **Both caps present** (`MAX_TURNS=8`, `MAX_QUESTIONS=6`). The docs carried only the second | **Restored** |
| D8 | **The audio pool is read lazily, not preloaded.** [[tickets/T15]]'s *"~200 MB fits in RAM"* is a demo-scale observation that becomes false at ~2,500 schemes (~4.5 GB); [[tickets/T17]] leaned on it when freezing the language | **Ratified by Adarsh, 10 Sep 2026 — no ticket amendment owed and no signature moves.** `Corpus.audio`/`chunks` return a **`RenderKey`, not bytes**, so the tiering is internal to `haqdaar/audio/`. Tier 0 pins the bounded ~35 MB (fixed lines + chips); the growth term (scheme chunks) is `mmap` + LRU off SSD, prefetched when `Planner` returns `Stop`. **The demo host warms the whole pool, so its behaviour is byte-identical to preloading.** [[03-ARCHITECTURE]] §10.1, [[06-BUILD-PLAN]] Steps 11 & 17 |
| D9 | **`maps/wayfinder-map.md` is the sole source of truth; `maps/history/` is version support only.** The history set skips rev 8 and rev 24 | **Ratified by Adarsh, 10 Sep 2026.** The latest map by name/time is the only authoritative artefact; historical revisions are supporting versions and **their completeness is not a correctness property.** The rev 8/24 gaps are **withdrawn as findings**, not deferred. See [[01-CONTRADICTIONS]] §5 |

## Related
[[01-CONTRADICTIONS]] · [[08-TRACEABILITY]] · [[10-RISK-REGISTER]] · [[maps/wayfinder-map]]

---
**Wayfinder Map:** [[maps/wayfinder-map|Latest Map]] · **Brain Index:** [[glossary|Glossary]]
