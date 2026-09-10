---
title: "HAQDAAR Wayfinder Map (Rev 5)"
slug: wayfinder-map-rev5
type: map
module: architecture
status: superseded
tags: [map, wayfinder, architecture, rev-5]
created: 2026-08-22
updated: 2026-08-24
author: Adarsh Agarwala
last_agent_edit: sync_vault.py
source_file: source-docs/MAP-t2.md
---

# HAQDAAR — Wayfinder Map

`wayfinder:map` · local-markdown tracker · charted 22 Aug 2026 · rev 5

## Destination

A HAQDAAR system design that is complete, trusted and sharp enough to be **cut into four owned modules and handed to other people to build** — target ~1 Sep 2026.

The map is done when nothing is left to decide before someone goes and builds.

## Notes

- **Domain:** inbound IVR for Indian government scheme discovery. Feature-phone caller, keypad primary, voice on top, 5–6 questions maximum, never says "you are eligible".
- **Acceptance bar (not a ticket — the standing test every decision is judged against):** on 12 Sep 2026, a live Indian number takes real calls in Hindi, English and Marathi; a caller who names a scheme gets it read back in under 20 s; a caller who describes themselves gets 2–4 named schemes; the LOG can prove why each was chosen.
- **Build is out of the map.** This map produces decisions. Execution is tracked separately.
- **Every session:** grill-me + domain modelling. One ticket per session, except research tickets which run in parallel.
- **The existing 12 segments are evidence, not authority.** Every "lock" in them is provisional until it comes back through a ticket and Adarsh ratifies it. Mine them; don't inherit them.
- **Standing preference:** every question carries a default so nothing stalls. Verdicts, not option menus. Bullets, not paragraphs.
- **Ownership seam = the nine stages, grouped into four modules** — Audio (Telephony/Mouth/Ear), Model (Router+Reader), Engine (Checker/Filter/Planner), Data (Corpus+LOG). A person owns a module and its interface, not a document. Docs get re-cut to match.
- **Corpus source today is the scrape.** A government data feed is assumed to replace it after sale; nothing in the design may depend on that feed existing.
- **English myScheme content is the only source of truth** (rev 5). Hindi and Marathi text from myScheme is drafting material, never read-back material.

## Decisions so far

- **Destination named** (charting, 22 Aug): the design package, not the running system; 12 Sep is the acceptance bar.
- **Segments demoted to evidence** (charting, 22 Aug): nothing in 01–12 is final until re-ratified.
- **Ownership by module, not by segment** (charting, 22 Aug): segments are documentation slices and give two people the same code with no interface between them.
- **Mouth is TTS + an ingest-time cache** (charting, 22 Aug): one `say(text, language)` path; all repeated lines and all scheme read-back audio rendered once at ingest and served as files; only short echo fragments render live. Text always comes from code templates, never the model.
- **Barge-in policy** (rev 2, 22 Aug): keypad interrupts everything always; speech barge-in only if the provider streams live media (T01); an interrupt discards the remainder of the line; the final read-back is keypad-interruptible only.
- **LOG retention split** (rev 2, 22 Aug): audio destroyed at hangup; the decision trace persists because it *is* the proof the acceptance bar demands; caller number hashed or not stored. Overrides "everything deleted after the call", which would have made the success bar unprovable.
- **Dead-end ladder** (rev 2, 22 Aug): zero survivors widens the last mask and retries once; if still nothing, say plainly that nothing matched and read the nearest two, labelled as nearest and not as matches. Model or ASR unavailable drops the call into keypad-only mode, which costs zero model calls.
- **"Anything else?" keeps caller facts** (rev 2, 22 Aug): a second question in the same call clears only the need box; state, age, occupation and other confirmed boxes survive.
- **Scale deferred, hosting not** (rev 2, 22 Aug): concurrency, autoscaling and cold-start behaviour are out of scope; a minimal deploy target for 12 Sep is a task ticket (T19).
- **Corpus snapshots are immutable and pinned per call** (rev 3, 22 Aug): the audio cache is content-addressed, so changed content simply produces a new file and nothing is ever invalidated. A call binds to one numbered corpus snapshot at connect and holds it to hangup; deploy builds a new snapshot, renders its missing audio, then flips a pointer. In-flight calls finish on the old snapshot. Orphaned audio is swept between deploys, never during a call.
- **Telephony is Plivo, India data region** ([[tickets/T01|Pick the telephony provider]], 23 Aug): decided by paperwork, not features — Plivo accepts a Udyam (MSME) certificate as business proof, obtainable in an afternoon with Aadhaar + PAN, where Exotel wants a Certificate of Incorporation we don't have. Twilio sells no Indian local DIDs at all; Ozonetel and Knowlarity are sales-led with nothing public to design against. Bidirectional WSS, μ-law 8 kHz, DTMF on the same socket. **The India data region is chosen at signup and cannot be changed.** No trial path exists — a paid, KYC'd account is required from day one.
- **[[tickets/T02|What myScheme actually gives us per scheme]]** (rev 5, 23 Aug): eligibility is prose and every filter value is ours to derive at ingest — the long pole is confirmed long. Only three fields arrive structured: level, application mode, tags. The four read-back chunks arrive pre-separated by section anchor, and **exclusions** arrives as a fifth separate block the Checker should use as negative rules. Segment 05's 18 boxes are confirmed as a real myScheme facet rail, not an invention — but the rail lives in the search wizard, never on the scheme record, so a scheme's position on any box is derived by us. Hindi and Marathi content exists and is disclaimed by the platform itself, so English is the source of truth and every spoken non-English line is human-verified by us. Third-party myScheme datasets must be spot-checked: at least one public one fabricates eligibility rules and Hindi text on fetch failure.
- **Module owners write their own fakes first** (rev 3, 22 Aug): every owner's day-one commit is a fake implementation of their own interface returning deterministic values from one shared fixture file (one persona, three schemes). Consumers never write fakes for dependencies they don't own. All four modules are runnable against each other from day one, so interfaces fail on day one instead of day nine.

## Not yet specified

- **Whether the corpus is 50 schemes or 100.** The destination and T07 say 50; segment 05's filter arithmetic and bit layout assume 100. Nobody has ruled. It changes the mask table, the ingest workload and the three-language verification bill, so it needs settling inside T07 or before it.

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

- [[tickets/T03|Which ASR can hear Hindi, English and Marathi on a phone line]] — research
- [[tickets/T04|What "working properly on 12 Sep" means]] — grilling
- [[tickets/T05|Get an Indian inbound number in hand]] — task *(unblocked by T01)*
- [[tickets/T06|What one scheme record contains]] — grilling *(unblocked by T02)*
- [[tickets/T22|Recover the two missing myScheme value lists]] — task *(new, from T02)*

[[tickets/T19|Where it runs on 12 Sep]] has left the frontier — it now waits on T20.

## All tickets

| # | Name | Type | Module | Blocked by |
|---|------|------|--------|-----------|
| ~~T01~~ | ~~[[tickets/T01|Pick the telephony provider]]~~ | research | Audio | — · **closed 23 Aug** |
| ~~T02~~ | ~~[[tickets/T02|What myScheme actually gives us per scheme]]~~ | research | Data | — · **closed 23 Aug** |
| T03 | [[tickets/T03|Which ASR can hear Hindi, English and Marathi on a phone line]] | research | Audio | — |
| T04 | [[tickets/T04|What "working properly on 12 Sep" means]] | grilling | cross | — |
| T05 | [[tickets/T05|Get an Indian inbound number in hand]] | task | Audio | T01 |
| T06 | [[tickets/T06|What one scheme record contains]] | grilling | Data | — |
| T07 | [[tickets/T07|Choose and structure the 50 schemes]] | task | Data | T06 |
| T08 | [[tickets/T08|How verified content survives three languages]] | grilling | Data | T06 |
| T09 | [[tickets/T09|The filter table and what a survivor mask means]] | grilling | Engine | T06 |
| T10 | [[tickets/T10|How the next question is chosen and when to stop]] | grilling | Engine | T09 |
| T11 | [[tickets/T11|The closed set the model is allowed to say]] | grilling | Model | T03, T09 |
| T12 | [[tickets/T12|Door A: matching a spoken scheme name]] | prototype | Model | T07 |
| T13 | [[tickets/T13|Dry-run the narrowing on real schemes]] | prototype | Engine | T07, T10 |
| T14 | [[tickets/T14|The turn clock: silence, barge-in and call length]] | grilling | Audio | T01, T03 |
| T15 | [[tickets/T15|How Mouth gets its audio]] | grilling | Audio | T08, T14 |
| T16 | [[tickets/T16|What the LOG must prove]] | grilling | Data | T09 |
| T17 | [[tickets/T17|Module boundaries and frozen interfaces]] | grilling | cross | T09, T11, T14, T15, T16 |
| T18 | [[tickets/T18|The fallback ladder: nothing fits, or nothing works]] | grilling | cross | T09, T11 |
| T19 | [[tickets/T19|Where it runs on 12 Sep]] | task | cross | T20 |
| T20 | [[tickets/T20|Whether call audio may leave India]] | research | Audio | T03 |
| T21 | [[tickets/T21|What the record says about provenance and freshness]] | grilling | Data | T06 |
| T22 | [[tickets/T22|Recover the two missing myScheme value lists]] | task | Data | — |

T17 is the destination gate. When it closes, the map is done.
