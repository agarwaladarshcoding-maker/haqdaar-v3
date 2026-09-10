---
title: "HAQDAAR v1 — Product Requirements"
slug: prd
type: module-note
module: general
status: reviewed
tags: [prd, product, scope, acceptance, staging]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/PRD.md
---

# HAQDAAR v1 — Product Requirements

> **Status: draft, staged, not merged.** Written 10 Sep 2026 against
> [[maps/wayfinder-map|Wayfinder Map rev 27]] and [[tickets/T04]], which owns the acceptance bar.
> **The ten-call acceptance test is 14 September 2026**, moved there by **map rev 26**;
> **architecture and build plan are due 12 September**, the same entry's internal deadline.
> **v1 is rev 26's definition: every feature present in its simplest form, a whole call end to
> end** — *"v1 cuts features, never safety."* §7's v2 list is therefore *improvements*, never
> missing features.

---

## 1 · The problem

Families miss government welfare schemes they could apply for, because finding one currently
requires **a smartphone, literacy in English or Hindi, and knowing a scheme's official name.**
myScheme publishes them, but only as long web pages.

**The people who most need these schemes have a basic keypad phone, speak Hindi or Marathi, and
have never seen that website.**

## 2 · Who calls

A person on a **feature phone**, often in a noisy home, speaking **Hindi, Marathi or English —
often mixed within a single sentence.**

They know their state, gender, rough age, caste category and kind of work. They may not know their
exact income. **They may not want to say their caste** — and the system must never march them onto
a keypad menu to extract it ([[tickets/T11]] §4). They may know a scheme's popular name
(*"PM kisan"*), or only what they need (*"help for farming"*).

## 3 · What the product does

**A phone number. No app, no internet, no reading.**

1. **Choose a language** — press 1 Hindi, 2 Marathi, 3 English. Marathi is second because it is the
   weakest-served caller in the design; clearing them out of the preamble sooner is the cheapest
   kindness on offer ([[tickets/T24]]).
2. **Say what you want.** Two doors, one call, no routing decision:
   - **Name a scheme** (Door A) → read straight back.
   - **Describe yourself or your need** (Door B) → a few short questions, then 2–4 named schemes.
   The caller never chooses a door; the doors are just which fields came back from one model call
   ([[tickets/T12]]).
3. **Hear each scheme** — name, then a ~35-word summary. Then keypad:
   **1** benefits · **2** how to apply · **3** documents · **4** who can apply · **9** next scheme.
   Key 4 exists on purpose: *it is the one section that lets the caller judge for themselves, which
   is the only honest route for a system that never says "you are eligible"* ([[tickets/T23]] §5).
4. **Search again** — *"anything else?"* clears **only** the need, keeping every other confirmed
   fact — **or hang up.**

**Always available:** `#` repeats the last thing said, at any time, in any language, costing nothing.
`*` changes language at any moment and clears nothing. `0` means *don't know / none of these* on
every menu in the system — one meaning everywhere, so the caller learns it once.

## 4 · What it must never do

These are not guidelines. Each is enforced by a build gate, a type boundary or an ordering
assertion — because [[tickets/T08]] leaves no human between a translated string and a citizen.

| Rule | How it is enforced |
|---|---|
| **Never say "you are eligible", "you will get" or anything like it** — in any language | Two-tier forbidden-phrase build gate, per language, with the brand allowlisted only in `closing_farewell` ([[tickets/T18]], [[tickets/T23]]) |
| **Never speak a scheme's name before the bad news** in a non-exact ending | Asserted at build against the `say(sequence)` order. *It is a property of order, not of words, so it survives machine translation* ([[tickets/T18]]) |
| **Never offer a scheme the caller is barred from** by state, gender or caste category | A scheme whose miss-set holds a **hard** box is never spoken — not as a match, not as nearest, not with a label ([[tickets/T09]], [[tickets/T10]]) |
| **Never make up a sentence live** | Zero runtime TTS. Every string is rendered before any call, and the runtime imports no TTS client ([[tickets/T15]]) |
| **Never let the model invent a fact the caller did not state** | Every value carries the transcript span that produced it; code drops any value whose span is not literally in what the caller said ([[tickets/T11]] §3) |
| **Never store the caller's voice or raw number** | Audio destroyed at hangup; number hashed ([[tickets/T16]]) |
| **Never give a helpline, website or phone number** | Nothing in the design verifies such a claim ([[tickets/T18]]) |

> **Why the span guard is load-bearing.** Given *"main kisan hoon"*, a helpful model will also
> return `income_band = low`. Farmers are poor — **and the caller did not say it.** A filled box
> **narrows**, so an inferred value can exclude a scheme the caller actually qualifies for, and the
> LOG records it as though the caller said it. *That is an untruth generated by helpfulness and
> invisible at runtime.*

## 5 · Success on the day — the acceptance bar

Owned by [[tickets/T04]]. Quoted rather than paraphrased, because the previous revision softened it.

> Ten calls are placed to a live number by **people outside the team**, from real handsets, **at
> least three in each of Hindi, English and Marathi.** Each call is judged afterwards **from the LOG
> alone**, pass or fail. **Eight of ten passes.**

**A call fails on exactly three conditions, and nothing else:**

1. The system **said something untrue** — named a scheme the caller does not plausibly qualify for
   *as a match*, stated an unsupported benefit or document, or asserted eligibility in any form.
2. The system **hung up unprompted.**
3. The call **ended before a terminal state.**

**Terminal state** is one of: *read-back started* · *honest dead-end delivered* · *keypad-only
fallback delivered.* Hangup anywhere else is abandonment, and abandonment is a fail.

**Frustration is not the test — structure is.** Audio is destroyed at hangup, so *"the caller
shouted and cancelled"* cannot be adjudicated.

### The two clauses most easily got wrong

**A dead-end is a pass — but only if the ladder ran.**

> *"Zero survivors → mask widened → still zero → says plainly that nothing matched and reads the
> nearest two, labelled as nearest and **not** as matches: **pass**. Zero survivors → dead-end
> delivered **without** the widening step: **fail**. The mechanism is what is being judged, not the
> caller's luck."* — [[tickets/T04]] branch 3

T04 expects dead-ends to be *"the common case, not the edge — plausibly two or three of the ten."*
**This is why the widening ladder is v1 scope and not v2.** Deferring it converts two or three
likely passes into certain fails against a bar of eight.

**Exactly one survivor is a pass.** One named scheme plus an honest statement that it is the only
one beats padding to two with something that does not match — *padding is a lie.*

### Door A's clock

A caller who names a scheme hears the **first word of its name within 20 seconds** of finishing
their sentence. Measured as `t_name`, from Sarvam's `vad.speech_end` to the `playedStream` of a mark
placed immediately before the name — **both ends are provider events, neither is a local guess**
([[tickets/T14]]). `t_end` is recorded too but cannot fail the bar; it exists so Marathi summary
length becomes evidence for free rather than a surprise on the day.

A single breach does not fail the demo. Three do, via the eight-of-ten rule.

### Behaviours at least one call must deliberately exercise

[[tickets/T04]] branch 4. **Survived** means: reaches a terminal state, or issues a *specific*
disambiguating re-ask; never says something untrue; never hangs up unprompted.

| Behaviour | Required response |
|---|---|
| Silence — no keypad, no speech | Replay the question; then the presence line; then a polite delivered ending |
| Wrong / out-of-range keypad press | Named re-ask stating the valid range. Never silently ignored |
| Keypad mash — several digits fast | First valid digit in range wins, remainder discarded. Never an error |
| A scheme that does not exist, or is outside the corpus | Says plainly it does not have that one, then offers Door B. **Never invents, never silently substitutes a similar name** |
| Mixed languages mid-sentence | Handled under the pinned language; a failed parse is a specific re-ask, not a generic error |
| Nothing intelligible | Specific re-ask; second failure drops that box to its keypad menu |
| Answering a different question than the one asked | The `box` field carries it — a value for an earlier box is an ANSWER, not a wrong-slot write |

**Explicitly not counted against the demo:** carrier-side drops, a caller who hangs up after a
terminal state, a caller who hangs up in the first two seconds without speaking, DTMF a handset
never transmitted.

## 6 · v1 scope

| Area | v1 |
|---|---|
| Languages | Hindi, Marathi, English — keypad-pinned at turn 0, `*` re-pins any time |
| Phone | Twilio +1, on Adarsh's laptop behind a fixed ngrok domain. Plivo India is a second adapter behind the same seam if KYC lands |
| Door A | Exact alias match in code first (zero model cost), then model selection over the alias closed set. 1 → read back · 2 → one keypad turn · ≥3 or `0` → Door B, seeded |
| Door B | Opener fills what it can, confirmed once as a bundle. Then question turns: `state` spoken, the rest keypad |
| Planner | Minimax elimination ÷ expected turns; hard boxes first only while they still split the set |
| Stopping | ≤4 survivors · no box splits · **8 turns** · **6 questions** · zero survivors |
| **Widening** | **In scope.** Soft boxes only, one at a time, `income_band → age → occupation → category`, stopping at the first rung with ≥1 survivor |
| Endings | direct match · overflow (top 3) · **widened match** · nearest (≤2, summary only) · empty |
| Help keys | `#` repeat · `*` language · `0` don't-know/none-of-these |
| Failures | Silence ladder 6/6/6 · box-level keypad drop · call-level keypad-only on 2 model failures or 1 unrecovered ASR socket |
| Data | A deliberately small, fully tri-lingual testing corpus, built by an **unattended** pipeline whose cost does not scale with N in human time ([[tickets/T07]]) |
| Proof | One JSONL per call, plus a judge script that marks each call pass/fail from the LOG alone |

**On corpus size.** [[tickets/T04]] branch 5, as corrected: *12 Sep is a **testing-phase** bar, and
the corpus is kept deliberately small **on purpose**, for ease of testing and clean tri-lingual
verification — not because verification is a bottleneck.* [[tickets/T07]] rev 22 makes **N a build
parameter, not a design decision**: no clause of the ingest pass may scale with N in human time.
8–10 schemes is a sensible starting N; it is a dial, not a requirement.

## 7 · v2 — after v1 is tagged

1. Spoken answers with echo-confirm for **every** box, not just `state`.
2. Rephrases wired to the per-box ask-counter on every box.
3. `*` detection-as-hint — a detector whose only power is to *offer* a switch, never to act
   ([[tickets/T24]], designed and costed, switched off).
4. Speech barge-in — one flag, `clearAudio` on `vad.speech_start` ([[tickets/T14]], same shape).
5. Multi-value boxes — *"I farm and I run a shop"* ([[tickets/T09]], deferred because it blurs the
   miss-set the whole fallback rests on).
6. Per-cell hard/soft — `age` is a wall on a pension and blur on a scholarship ([[tickets/T10]]).
7. Human facet audit filling `facets_verified_by` — **rev 26 sets it `null` on every v1 record**
   and calls v2's job *restoring the human read by filling a field* ([[tickets/T21]], [[tickets/T06]]).
8. A **verified** next-step referral for a dead-ended caller — *"the largest piece of unrealised
   value in the fallback path. It needs a source, not a sentence."*
9. Per-DID language default — three numbers, one per language, **costs zero turns**. Ruled out of
   the bar, not out of the design.
10. Plivo adapter · webhook signature validation · cloud host in an Indian region.
11. **A paid model key**, if money appears — which would retire rev 27's *one caller at a time*
    risk and reopen spoken answers on every box. **The provider is a tunable, not a shape.**

## 8 · Out of scope — does not graduate

Cross-call memory · outbound calls · SMS · status lookup (*"where is my money"*) · rejection-cause
prediction · document upload · any app, website or WhatsApp surface · schemes not on myScheme ·
concurrency and autoscaling · corpus maintenance after sale · cost and break-even modelling.

**Outbound is a redrawn destination, not an option** ([[tickets/T04]]): the caller has no need in
mind, Door A cannot exist, the greeting and consent change, the 20-second clock starts from a caller
who is not ready, and Indian outbound to unregistered numbers is a DLT/DND compliance surface this
design has never accounted for.

## 9 · Risks

| Risk | Mitigation | Source |
|---|---|---|
| Judges' handsets cannot dial +1 | Check every caller's phone beforehand. Plivo India if KYC lands | rev 25 |
| **Groq free-tier rate limit (429)** | Ratified with its mitigations, not despite them: **two model moments per call**, alias match in code first, **a 429 is a [[tickets/T18]] model failure** so two per call drop to keypad-only — the worst case is a slower call, never a dead one | **rev 27** |
| **The model-call latency budget is unverified** | [[tickets/T14]]'s 300–500 ms was measured against Gemini Flash-Lite. **Step 14's 30-utterance bake-off must report latency**; if Groq misses, the 1.2 s response budget moves | [[tickets/T14]] · rev 27 |
| Marathi voice unusable at 8 kHz | Day-one listening check. The voice id is inside the render key, so a swap is a re-render, not a redesign | [[tickets/T15]] |
| Machine translation error | Hold-aside check asserts digits, ₹ amounts and dates byte-identical; forbidden-phrase gate catches claims | [[tickets/T08]], [[tickets/T18]] |
| Model-derived facets are wrong | *"Preference shall be given to women"* is not *"for women"*. Named exposure with [[tickets/T21]] over it | [[tickets/T07]] |
| Laptop sleeps or Wi-Fi drops | Lid open, sleep off, 30-minute idle cold-start test; hotspot backup; restart loop. **No spare laptop — rev 26 drops that drill** (solo builder, one machine), so the restart loop is the whole recovery story | [[tickets/T19]] · rev 26 |
| One caller at a time | Measure it, then **announce it before judging, not discover it during**. Rev 27 names this a standing risk of the free tier | [[tickets/T19]] · rev 27 |
| Solo builder runs out of time | Small steps. **The keypad-only call is shippable on its own** and is a T04 pass | [[tickets/T18]] |

## 10 · What the presentation team needs from the build

- §1–§5 of this file, and §1–§2 of [[03-ARCHITECTURE]].
- The call-flow diagram in [[03-ARCHITECTURE]] §5 and the terminal tree in §8.
- One real LOG file from a test call.
- A 60-second screen recording of `tail -f` on a live call's log.

## 11 · Related

[[01-CONTRADICTIONS]] · [[03-ARCHITECTURE]] · [[06-BUILD-PLAN]] · [[07-TEST-PLAN]] ·
[[10-RISK-REGISTER]] · [[tickets/T04]] · [[maps/wayfinder-map]] · [[people/adarsh-agarwala]]

---
**Wayfinder Map:** [[maps/wayfinder-map|Latest Map]] · **Brain Index:** [[glossary|Glossary]]
