---
title: "HAQDAAR Wayfinder Map (Rev 12)"
slug: wayfinder-map-rev12
type: map
module: architecture
status: superseded
tags: [map, wayfinder, architecture, rev-12]
created: 2026-08-22
updated: 2026-09-02
author: Adarsh Agarwala
last_agent_edit: sync_vault.py
source_file: source-docs/MAP-t9.md
---

# HAQDAAR — Wayfinder Map

`wayfinder:map` · local-markdown tracker · charted 22 Aug 2026 · rev 12 (1 Sep)

## Destination

A HAQDAAR system design that is complete, trusted and sharp enough to be **cut into four owned modules and handed to other people to build** — target ~1 Sep 2026.

The map is done when nothing is left to decide before someone goes and builds.

## Notes

- **Domain:** inbound IVR for Indian government scheme discovery. Feature-phone caller, keypad primary, voice on top, 5–6 questions maximum, never says "you are eligible".
- **Acceptance bar (not a ticket — the standing test every decision is judged against):** on 12 Sep 2026, a live Indian number takes real calls in Hindi, English and Marathi; a caller who names a scheme gets it read back in under 20 s; a caller who describes themselves gets 2–4 named schemes; the LOG can prove why each was chosen. *(Tested against and held unchanged by T08, 1 Sep — see 'How a language gets added' below.)*
- **Build is out of the map.** This map produces decisions. Execution is tracked separately.
- **Every session:** grill-me + domain modelling. One ticket per session, except research tickets which run in parallel.
- **The existing 12 segments are evidence, not authority.** Every "lock" in them is provisional until it comes back through a ticket and Adarsh ratifies it. Mine them; don't inherit them.
- **Standing preference:** every question carries a default so nothing stalls. Verdicts, not option menus. Bullets, not paragraphs.
- **Ownership seam = the nine stages, grouped into four modules** — Audio (Telephony/Mouth/Ear), Model (Router+Reader), Engine (Checker/Filter/Planner), Data (Corpus+LOG). A person owns a module and its interface, not a document. Docs get re-cut to match.
- **Corpus source today is the scrape.** A government data feed is assumed to replace it after sale; nothing in the design may depend on that feed existing.
- **English myScheme content is the only source of truth** (rev 5). Hindi and Marathi text from myScheme is drafting material, never read-back material.
- **The truth lock is suspended for 12 Sep** (rev 11, T08): no human verifies translated strings before they are spoken. This is a recorded debt, not a repeal. Nothing built for the demo may assume it stays suspended.

## Decisions so far

- **Destination named** (charting, 22 Aug): the design package, not the running system; 12 Sep is the acceptance bar.
- **Segments demoted to evidence** (charting, 22 Aug): nothing in 01–12 is final until re-ratified.
- **Ownership by module, not by segment** (charting, 22 Aug): segments are documentation slices and give two people the same code with no interface between them.
- **Mouth is TTS + an ingest-time cache** (charting, 22 Aug): one `say(text, language)` path; all repeated lines and all scheme read-back audio rendered once at ingest and served as files; only short echo fragments render live. Text always comes from code templates, never the model.
- **Barge-in policy** (rev 2, 22 Aug): keypad interrupts everything always; speech barge-in only if the provider streams live media (T01); an interrupt discards the remainder of the line; the final read-back is keypad-interruptible only.
- **LOG retention split** (rev 2, 22 Aug): audio destroyed at hangup; the decision trace persists because it *is* the proof the acceptance bar demands; caller number hashed or not stored. Overrides "everything deleted after the call", which would have made the success bar unprovable.
- **Dead-end ladder** (rev 2, 22 Aug; **widening clause superseded by T09, rev 12**): if nothing matches, say plainly that nothing matched and read the nearest two, labelled as nearest and not as matches. Model or ASR unavailable drops the call into keypad-only mode, which costs zero model calls. *"Widens the last mask and retries once" is replaced by T09's soft-only ladder — widening by recency can speak a scheme the caller is geographically barred from.*
- **"Anything else?" keeps caller facts** (rev 2, 22 Aug): a second question in the same call clears only the need box; state, age, occupation and other confirmed boxes survive.
- **Scale deferred, hosting not** (rev 2, 22 Aug): concurrency, autoscaling and cold-start behaviour are out of scope; a minimal deploy target for 12 Sep is a task ticket (T19).
- **Corpus snapshots are immutable and pinned per call** (rev 3, 22 Aug): the audio cache is content-addressed, so changed content simply produces a new file and nothing is ever invalidated. A call binds to one numbered corpus snapshot at connect and holds it to hangup; deploy builds a new snapshot, renders its missing audio, then flips a pointer. In-flight calls finish on the old snapshot. Orphaned audio is swept between deploys, never during a call.
- **Telephony is Plivo, India data region** ([[tickets/T01|Pick the telephony provider]], 23 Aug): decided by paperwork, not features — Plivo accepts a Udyam (MSME) certificate as business proof, obtainable in an afternoon with Aadhaar + PAN, where Exotel wants a Certificate of Incorporation we don't have. Twilio sells no Indian local DIDs at all; Ozonetel and Knowlarity are sales-led with nothing public to design against. Bidirectional WSS, μ-law 8 kHz, DTMF on the same socket. **The India data region binds to an organization and cannot be changed after that organization is created** — but a wrong pick is recovered by creating a new organization from the console switcher, not by re-signing up (corrected 28 Aug, T05 session; the original 'chosen at signup, cannot be changed' overstated it). No trial path exists — a paid, KYC'd account is required from day one. **Udyam alone satisfies KYC**; it is one of three accepted documents and no second document is required, though the first application must be sealed and signed. 022/080 review is now automated at ~5 minutes, not up to a business day.
- **[[tickets/T02|What myScheme actually gives us per scheme]]** (rev 5, 23 Aug): eligibility is prose and every filter value is ours to derive at ingest — the long pole is confirmed long. Only three fields arrive structured: level, application mode, tags. The four read-back chunks arrive pre-separated by section anchor, and **exclusions** arrives as a fifth separate block the Checker should use as negative rules. Segment 05's 18 boxes are confirmed as a real myScheme facet rail, not an invention — but the rail lives in the search wizard, never on the scheme record, so a scheme's position on any box is derived by us. Hindi and Marathi content exists and is disclaimed by the platform itself, so English is the source of truth and every spoken non-English line is human-verified by us. Third-party myScheme datasets must be spot-checked: at least one public one fabricates eligibility rules and Hindi text on fetch failure.
- **Sarvam is the ear, and the confidence ladder loses its number** ([[tickets/T03|Which ASR can hear Hindi, English and Marathi on a phone line]], rev 6, 23 Aug): Sarvam `saaras:v3-realtime` over an 8 kHz WebSocket, μ-law, language pinned per call. Matches Plivo's leg exactly — no transcode between telephony and Ear. **No shippable ASR returns a per-utterance transcript confidence**, so the 0.50 / 0.85 gates have no source and are replaced by a match score our own code computes against the closed set for the slot — a number we own, tune, and can put in the LOG as proof. Deepgram Nova-3 named as fallback **provisionally: it is US-hosted and may not survive T20.**
- **Module owners write their own fakes first** (rev 3, 22 Aug): every owner's day-one commit is a fake implementation of their own interface returning deterministic values from one shared fixture file (one persona, three schemes). Consumers never write fakes for dependencies they don't own. All four modules are runnable against each other from day one, so interfaces fail on day one instead of day nine.
- **[[tickets/T04|What "working properly on 12 Sep" means]]** (rev 7, 25 Aug): ten calls, from outside the team, real handsets, ≥3 per language, judged after the fact from the LOG alone — eight of ten must pass. A call fails only on an untruth, an unprompted hangup, or ending before a terminal state; abandonment is read structurally off the LOG, never off tone. A correctly-executed dead-end (full widening ladder run, nearest-two honestly labelled) **is a pass** — this resolves the standing contradiction with "gets 2–4 named schemes." Outbound calling is ruled out of the map entirely, not a T04 option. **The 12 Sep scheme corpus is deliberately small, for testing ease** — not a shortfall against 50 or 100, which is a later-stage, post-bar decision against the full corpus. All spoken content, fixed lines and every in-corpus scheme, is tri-lingual at parity; no per-language subsetting. The LOG gains a second job: prove the scheme choice, and let a call's pass/fail be reconstructed without audio.

- **Provisioning is parked behind the design work** ([[tickets/T05|Get an Indian inbound number in hand]], 28 Aug): T05 blocks nothing — its body claimed T14, but T14 is blocked by T24 alone — and the automated ~5 minute Plivo review removed the queue-time risk that put it on the frontier. It also proves nothing worth demonstrating: that an inbound IVR can take a call is not in question. **Latest safe start 5 Sep**, ratified 28 Aug: two to three days of work against seven days of runway, deliberately clear of the ~1 Sep design-package week so the two do not collide. The acceptance bar's live Indian number is held, not amended; if 5 Sep passes unstarted, amending the bar to allow the Twilio +1 becomes an explicit decision rather than a silent slip. Parking is safe only while the Audio module's provider seam stays honest — Twilio assumptions leaking past it turn a parked errand into a September rewrite.

- **The scheme record is facets, not rules** ([[tickets/T06|What one scheme record contains]], 29 Aug): one flat row per scheme, five field groups — identity/provenance, matching, filtration, negative rules, read-back. Each facet column holds a value from a closed list or `ANY`; the build expands every (column, value) pair into a scheme bitmask, so a turn is one AND instruction and there is no rule engine and no database in the call. Numerics are stored **exact** and become closed sets only at build — no banding, since the mask table is precomputed anyway. **Box 0 `category` is load-bearing**: a property of the scheme, read off the opening sentence, applied before question one, costing zero questions. **Aliases are a first-class field** in all three languages — a caller never speaks the official title. Exclusions subtract from a column's admitted set at capture where they can; where they cannot they become **`gate_notes`, a list, never spoken and never filtered on, carried into the LOG as declared blind spots.** One sentinel only, `ANY`; a second UNKNOWN was rejected because the build gate does that job better — a row that cannot be fully expressed **does not enter the snapshot at all**. `facets_verified` is tightened to mean a human read the eligibility prose and confirmed each `ANY` is real silence. **A sixth read-back chunk, `summary`, is added**: the bar wants a named scheme back in under 20 s, verbatim `benefit_text` is not 20 s in Marathi, and paraphrase of captured text is forbidden — so one authored ~35-word line per language, with the four verbatim sections offered by keypad after it. The record stores text only; audio stays derivative and content-addressed. No column may be deleted on the 16 Aug test numbers, which were measured against the dropped inferred corpus and are shape, not fact.

- **Three languages, no verifier, and the two legs stop sharing a rule** ([[tickets/T08|How verified content survives three languages]], 1 Sep): the ticket's 600-string arithmetic was stale on both terms — T06 made read-back five chunks (`summary` authored natively, not translated; aliases heard, never spoken; fixed lines a one-time block) and T04 already shrank N. **Design N = 100**, demo runs a small subset. **All three languages stay** — Marathi was briefly dropped for want of a verifier and restored the moment the verifier went, because that was the only thing making it expensive. **Inbound and outbound stop obeying the same rule**, because their failure costs differ: inbound goes caller's language → English internally → the model **selects one value from a fixed keyword list** → that keyword is echoed back in the caller's language from cache → confirm. The English hop is safe precisely because the exit is a closed set — the worst achievable error is the wrong item from a known list, recoverable by the ladder and visible in the LOG. **Outbound read-back stays pre-translated and cached, no runtime generation**, because an outbound error speaks a falsehood about money and is unrecoverable. **The keyword list is the test base** — ~150–200 values per language, frozen, making the inbound leg testable offline against a table of utterances; T22 now feeds Model as well as Data. **No human verifier is staffed**: translation ships naive, the truth lock is suspended as debt, and the system prompt forcing selection-from-database becomes the only remaining guard — which makes T11 load-bearing on the inbound path, not just read-back. The hold-aside check (names, amounts, dates byte-identical through translation) survives as a machine assertion, since it needs no language skill and catches the worst failure. Every staffing question in the ticket body is void with the verifier.

- **The masks are kept, not folded** ([[tickets/T09|The filter table and what a survivor mask means]], 1 Sep): `survivors = survivors AND mask` was the wrong shape — correct and insufficient. A set has no notion of *near*, so the dead-end ladder's "nearest two" and the bar's "2–4 named schemes" both had nothing to run on. A bare tally is also insufficient: a scheme missing **category** is worth reading with a label, a scheme missing **state** can never be had. So **turn masks are retained rather than ANDed away** — six answered boxes is six machine words, and from them derive **survivors** (AND, the truth claim), **tally** (how many masks hold the bit, ranks the near) and **miss-set** (*which* masks lack it, decides what may be spoken). Vector search is ruled out: it cannot produce a trace, and proving the choice is the LOG's second job. This amends T06's "one AND instruction" to **one pass, one word retained per turn.** A box holds a code, UNASKED or UNKNOWN — **UNASKED and UNKNOWN are the same instruction to the filter** (no mask appended) and differ only in the LOG and to T10; **UNKNOWN always widens, never narrows.** `category` is **box 0 in the same table**, not a pre-filter, because *"anything else?"* must be able to clear it. **There is no undo stack** — the box vector is the only state and everything derives, so a correction overwrites one box and re-derives; the ticket's recompute-vs-reverse question had a false premise. At zero survivors, **a scheme whose miss-set contains a hard box is never spoken**, and widening drops **soft boxes only**, one at a time in an order T10 supplies. The Engine is **pure code, language-blind, with no runtime negation and no numerics** — Model selects a keyword, Data owns the list and the code map, and the code is the interface. **The snapshot id plus the ordered box vector reconstruct the entire call**, so the LOG stores no survivor sets. One code per box for 12 Sep. The single thing handed to T10 is the **hard/soft classification of every box.**

## How a language gets added

Written plainly, because this is the thing that decides whether three languages is ambitious or routine. It is routine.

**Nothing in the system is written per language.** There is no Hindi code path and no Marathi code path. There is one path, and the language is a setting the call carries.

A language is two lists and a batch job:

1. **The keyword list** — about 150–200 words: the states, the occupations, the categories, the caste and income groups. Written once in that language.
2. **The scheme text** — every scheme's four sections plus the fixed lines the system says on every call, machine-translated and turned into audio files ahead of time.

Both are done before anyone calls. Neither touches the code. That is why **adding a language is roughly a day**, and why dropping one buys almost nothing.

**Inside a call it works like this:**

- The caller's language is set when the call connects
- They speak, and Sarvam writes down what they said in that language
- We turn it into English inside the system, where all the thinking happens
- The system is only allowed to answer by **picking a word off our list** — it may not write its own
- That picked word is played back to the caller in their own language, from a file we made earlier, so they hear exactly what got ticked and can correct it
- When we finally read a scheme out, the audio was made and stored days ago — nothing is written or translated while the caller is on the line

**The one rule that holds all of this up:** the system chooses from a list going in, and reads from a file going out. It never makes up a sentence. That is what stops a wrong translation from becoming a false promise about money, and it is also what lets us test the whole thing offline without making a phone call.

**What we are knowingly skipping for 12 Sep:** nobody reads the translations before they go out. On a real system a person would. For the hackathon the machine's word is taken as-is. This is written down as a debt, not forgotten.

## Not yet specified

- **What the eventual production scheme count is (50, 100, or otherwise).** Settled by T04 (25 Aug) as **out of the 12 Sep bar** — the demo runs on a deliberately small, fully tri-lingual testing corpus, and the production count is a later-stage decision made against the full corpus once it exists. Still genuinely open, just no longer urgent against 1 Sep; T07 sizes the small testing set, not this.

- **Multi-value boxes.** Deferred by T09 (1 Sep): "I farm and I run a shop" is a real caller, and mechanically it is cheap — OR the two value masks into one turn mask. It is deferred because it blurs the miss-set, which the whole soft-only fallback rests on, and because it hands T10 a harder question-selection problem. For 12 Sep the ladder forces a pick. Revisit against the full corpus, not before.

- **Who eventually verifies spoken content, and at what rate.** Deferred with the truth lock by T08. The number that comes out of this sets the ceiling on production corpus size forever — T07's resolution record still wants it, just not before 12 Sep.

New fog goes here as it surfaces. It will.

## Out of scope

Ruled beyond this destination. Does not graduate.

- **Cross-call memory** — phone number as identity, returning-caller recall. Dropped 22 Aug.
- **The caller-facing consent line** — deferred to build, not designed here. One recorded sentence at greeting. Low-risk only because the LOG holds no audio and no raw number.
- **Concurrency and scale** — simultaneous call capacity, autoscaling, cold starts. Industrial concern, handled after 12 Sep.
- **Corpus maintenance after sale** — the government updates scheme data once integrated; we do not design an update workflow.
- SMS delivery pack — separate workstream, PRD only.
- Status lookup ("where is my money") — no PM-KISAN API access.
- Rejection-cause prediction, document upload and ambiguity detection.
- Any web/app UI, WhatsApp, or smartphone surface.
- Schemes not listed on myScheme.
- Cost and break-even modelling — owned by a teammate with sourced figures.
- Anything after 12 Sep: productionisation, monitoring, the government data integration itself.

## Frontier (open, unblocked, takeable now)

T09 closing opened four at once. Order below is the order to take them.

- [[tickets/T10|How the next question is chosen and when to stop]] — grilling *(unblocked by T09)* ← **next session.** Inherits exactly one thing from T09: it must classify every box **hard or soft**, because the widening ladder and the never-speak rule both run on that classification. Also owns survivor ordering when more than four survive.
- [[tickets/T11|The closed set the model is allowed to say]] — grilling *(unblocked by T09)* · **load-bearing on the inbound leg after T08.** T09 fixed its output side: the Model emits a code, the Engine is language-blind, out-of-set is treated as UNKNOWN.
- [[tickets/T16|What the LOG must prove]] — grilling *(unblocked by T09)*. T09 hands it a contract to ratify: snapshot id + ordered box vector reconstructs the call, so no survivor sets are stored.
- [[tickets/T23|What the confirmation ladder runs on now that there is no ASR confidence]] — grilling *(unblocked by T09)*
- [[tickets/T21|What the record says about provenance and freshness]] — grilling *(unblocked by T06)*
- [[tickets/T22|Recover the two missing myScheme value lists]] — task *(blocks T07; after T08 it also supplies the inbound keyword base, so it now feeds Model as well as Data)*
- [[tickets/T20|Whether call audio may leave India]] — research *(unblocked by T03; run in parallel)*
- [[tickets/T24|How the call's language is chosen, and whether it can change mid-call]] — grilling *(from T03)*

[[tickets/T05|Get an Indian inbound number in hand]] is **parked** — takeable, but blocks nothing and earns no session time until **5 Sep**, its latest safe start.

[[tickets/T18|The fallback ladder]] lost T09 as a blocker but still waits on T11. [[tickets/T19|Where it runs on 12 Sep]] still waits on T20. [[tickets/T15|How Mouth gets its audio]] still waits on T14 and T24.

## All tickets

| # | Name | Type | Module | Blocked by |
|---|------|------|--------|-----------|
| ~~T01~~ | ~~[[tickets/T01|Pick the telephony provider]]~~ | research | Audio | — · **closed 23 Aug** |
| ~~T02~~ | ~~[[tickets/T02|What myScheme actually gives us per scheme]]~~ | research | Data | — · **closed 23 Aug** |
| ~~T03~~ | ~~[[tickets/T03|Which ASR can hear Hindi, English and Marathi on a phone line]]~~ | research | Audio | — · **closed 23 Aug** |
| ~~T04~~ | ~~[[tickets/T04|What "working properly on 12 Sep" means]]~~ | grilling | cross | — · **closed 25 Aug** |
| T05 | [[tickets/T05|Get an Indian inbound number in hand]] | task | Audio | T01 · **parked 28 Aug — start by 5 Sep, blocks nothing** |
| ~~T06~~ | ~~[[tickets/T06|What one scheme record contains]]~~ | grilling | Data | — · **closed 29 Aug** |
| T07 | [[tickets/T07|Choose and structure the 50 schemes]] | task | Data | ~~T06~~, T22 |
| ~~T08~~ | ~~[[tickets/T08|How verified content survives three languages]]~~ | grilling | Data | ~~T06~~ · **closed 1 Sep** |
| ~~T09~~ | ~~[[tickets/T09|The filter table and what a survivor mask means]]~~ | grilling | Engine | ~~T06~~ · **closed 1 Sep** |
| T10 | [[tickets/T10|How the next question is chosen and when to stop]] | grilling | Engine | ~~T09~~ · **owns the hard/soft box classification** |
| T11 | [[tickets/T11|The closed set the model is allowed to say]] | grilling | Model | ~~T09~~ · **load-bearing on the inbound leg after T08** |
| T12 | [[tickets/T12|Door A: matching a spoken scheme name]] | prototype | Model | T07 |
| T13 | [[tickets/T13|Dry-run the narrowing on real schemes]] | prototype | Engine | T07, T10 |
| T14 | [[tickets/T14|The turn clock: silence, barge-in and call length]] | grilling | Audio | T24 |
| T15 | [[tickets/T15|How Mouth gets its audio]] | grilling | Audio | ~~T08~~, T14, T24 |
| T16 | [[tickets/T16|What the LOG must prove]] | grilling | Data | ~~T09~~ |
| T17 | [[tickets/T17|Module boundaries and frozen interfaces]] | grilling | cross | ~~T09~~, T11, T14, T15, T16, T23, T24 |
| T18 | [[tickets/T18|The fallback ladder: nothing fits, or nothing works]] | grilling | cross | ~~T09~~, T11 |
| T19 | [[tickets/T19|Where it runs on 12 Sep]] | task | cross | T20 |
| T20 | [[tickets/T20|Whether call audio may leave India]] | research | Audio | — |
| T21 | [[tickets/T21|What the record says about provenance and freshness]] | grilling | Data | ~~T06~~ |
| T22 | [[tickets/T22|Recover the two missing myScheme value lists]] | task | Data+Model | — |
| T23 | [[tickets/T23|What the confirmation ladder runs on now that there is no ASR confidence]] | grilling | Model | ~~T09~~ |
| T24 | [[tickets/T24|How the call's language is chosen, and whether it can change mid-call]] | grilling | Audio | — |

T17 is the destination gate. When it closes, the map is done.
