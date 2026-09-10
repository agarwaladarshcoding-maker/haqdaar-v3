---
title: "Risk Register and Debt Ledger"
slug: risk-register
type: module-note
module: general
status: reviewed
tags: [risk, debt, staging]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/MAP-done.md
---

# Risk Register and Debt Ledger

Two different things, kept apart on purpose.

- **A debt** is a decision already taken, with the exposure named and dated. It does not need
  managing; it needs **not being forgotten**, and nothing built for v1 may assume it stays acceptable.
- **A risk** is something that can still go wrong before the demo, with an owner and a check.

---

## 1 · Debts — named, dated, accepted

| # | Debt | Named in | Why accepted | Never assume |
|---|---|---|---|---|
| B1 | **No human verifies any translated string before a caller hears it** | [[tickets/T08]], rev 11 | Machine-checkable gates are the whole defence | …that the truth lock stays suspended. Reinstating it must mean **filling a field, not changing a schema** ([[tickets/T21]]) |
| B2 | **Facets are model-derived, not human-read** | [[tickets/T07]] rev 22 | Nothing may scale with N in human time | *"Preference shall be given to women" is not "for women", and the model may flatten it.* [[tickets/T21]] owns the audit |
| B3 | **The generated `summary` is machine-authored and machine-translated** | [[tickets/T07]] | Native authoring was a quality choice made when N was assumed small | It is under **tier 1** of the forbidden-phrase gate — the strict one |
| B4 | **The LOG persists caller-descriptive transcripts past hangup** | [[tickets/T16]] §5 | *A redacted transcript cannot evidence a CLARIFY or an UNCLEAR — which is the entire reason the field exists* | *"Scheduled Caste farmer in Bihar earning under ₹50,000"* is **more identifying as persisted text than the hashed number beside it** |
| B5 | **Transcript text crosses a border to reach the model** | [[tickets/T11]] · [[tickets/T20]] | A data-protection question, not a carrier rule; it cannot produce a dead number | Audio never approaches the model — **the transcript does** |
| B6 | **Caller audio transits a foreign carrier** while Twilio is the number | rev 25 | Bar amended explicitly | The laptop is in Bengaluru, which is why the rest of T20's edge was cut |
| B7 | **One machine, one uplink, no monitoring beyond the LOG** | [[tickets/T19]] | Scale ruled out at rev 2; this is its concrete shape | It is a **demo host, written down as one.** Nothing here is a production decision |
| B8 | **No webhook signature validation on `/stream`** | [[tickets/T19]] | Low odds over two days | Anyone who finds the URL can open a socket and spend our credit. **First thing after the demo** |
| B9 | **Personal data at rest on a personal laptop** | [[tickets/T19]] | Full-disk encryption is the whole control | — |
| B10 | **The runtime holds a key that can also do TTS** | [[tickets/T19]] | One Sarvam key covers Ear and Mouth | [[tickets/T15]]'s credential rule **weakened to a code rule**: the runtime imports no TTS client, **and a test asserts it** |
| B11 | **Door A is silently unavailable in keypad-only** | [[tickets/T18]] §4 | Explaining a lost capability the caller may never have wanted costs a line and buys nothing | A caller who named a scheme and hit a model failure **will be asked a question instead, and will feel unheard** |
| B12 | **A dead-ended caller is sent away empty-handed** — no helpline, office or website | [[tickets/T18]] | Nothing in the design verifies such a claim, and [[tickets/T08]] staffs no verifier | *The largest piece of unrealised value in the fallback path. **It needs a source, not a sentence*** |
| B13 | **The v1 corpus does not satisfy [[tickets/T04]] branch 5** (all chunks human-verified) | [[tickets/T04]] vs [[tickets/T08]] · [[tickets/T07]] | The supersession is real and recorded | Do not rediscover this on the day. See [[09-DECISION-LOG]] §1 |
| B14 | **The runtime depends on a free-tier LLM quota shared org-wide with the corpus pipeline** | map **rev 27** | *"There is no money for a paid LLM"* — answered by spending fewer calls, not by hoping: two model moments per call, alias match first, **429 = a [[tickets/T18]] failure**. Worst case is a slower call | …that a pipeline re-run is harmless during a call. **Throttle and cache are load-bearing**, not hygiene ([[06-BUILD-PLAN]] Step 8) |
| B15 | **One caller at a time** | map **rev 27** | Accepted, with an obligation attached: it is **announced before judging, not discovered during it** | Measure `max_concurrent_measured` in Step 19 and say the number out loud. Do not let a judge dial second |
| B16 | **No spare machine** — rev 26 dropped [[tickets/T19]]'s laptop-dies drill | map **rev 26** | Solo builder, one machine; there is no second person to hold a warm copy | **A dead laptop is a dead demo.** Which is why *lid open, sleep off, plugged in* and the 30-minute cold-start test are not optional |

## 2 · Risks — before the demo

| # | Risk | Mitigation | Owner | Check |
|---|---|---|---|---|
| R1 | **Judges' handsets cannot dial the number** | Check **every** caller's phone beforehand. Plivo India if KYC lands | Adarsh | before Step 20 |
| R2 | **Marathi at 8 kHz is unusable** — *unheard by anyone so far* | Day-one listening check. **The voice id is inside the render key, so a swap is a re-render** | Audio | Step 10 |
| R3 | **A chip sounds seamed after `bundle_confirm_intro`** at the 120 ms tail | Listen to one intro + chip pair | Audio | Step 10 |
| R4 | **`keepCallAlive="false"` drops calls at connect** | The one ratify-on-hardware ruling. If it does, flip to `true` and bound with `streamTimeout="600"` | Audio | **Step 1, the smoke call** |
| R5 | **Concurrency is 1** | Measure it with three phones. **If it is 1, announce it before judging — not discover it during** | Adarsh | Step 19 |
| R6 | **The laptop sleeps** | Lid **open**, plugged in, sleep off. **Idle 30 min then dial — that call is the only cold-start test that counts** | Adarsh | Step 19 |
| R7 | **Wi-Fi drops** | Hotspot backup; the tunnel reconnects and the domain does not change. Run the drill once | Adarsh | Step 19 |
| R8 | **The laptop dies** | **Unmitigated by ruling** — map rev 26 dropped the spare-machine drill (solo builder). What is left: plugged in, lid open, sleep off, and the restart loop for everything short of hardware death. See B16 | Adarsh | Step 19 |
| R9 | **Tunnel data cap** — free plan, 1 GB/month ≈ 25 talking hours | Check usage the evening before. If over half is gone, **buy a plan — a card, not a redesign** | Adarsh | eve of demo |
| R10 | **Machine translation drops a number or a date** | **Hold-aside check** — every digit, ₹ amount and date must appear **unchanged**, or the record fails | Data | Step 9 |
| R11 | **A gate silently shrinks the corpus below a demoable size** | The gate table prints the failing clause per scheme. **If the alias floor bites, lower the floor rather than admit a scheme the caller cannot name** | Data | Step 9 |
| R12 | **Source drift between scrape and demo** | Re-fetch and re-hash **once, the evening before the freeze.** No auto-accept. If it knocks out a fixture coverage scheme, **hand re-read that one — ~20 minutes** | Data | eve of demo |
| R13 | **`occupation`'s value list exceeds 9** and loses its keypad menu | Record its cardinality in the ingest pass and keep it ≤9 | Data | Step 8 |
| R14 | **The 700 ms window cuts off hesitant callers** | *The direction is derived; the number is not.* **Tunable mid-demo on a live stream** — the cheapest dial in the system | Audio | [[tickets/T13]] |
| R15 | **The 8-turn cap makes calls feel long** | *The single dial to turn if the demo runs long* | Engine | [[tickets/T13]] |
| R16 | **Solo builder runs out of time** | Small steps. **`v1-keypad` is a complete, honest, T04-passing product on its own** | Adarsh | Step 12 |
| R18 | **The pool outgrows the host.** `6 × schemes × 3` is linear in the corpus: ~200 MB at 100 schemes, **~4.5 GB at ~2,500**. A preloading boot step makes corpus size a machine requirement | **Closed by design, not by mitigation** ([[09-DECISION-LOG]] D8): tier 0 pins the bounded ~35 MB, the growth term is lazily `mmap`-read with an LRU. **The regression test is boot RSS being flat when the pool is padded** ([[07-TEST-PLAN]] §5) | Data | Step 11 |
| R19 | **A cold read misses the 50 ms Mouth budget**, adding a felt gap inside the 1.2 s clock | The read-back is **announced a full turn ahead** — prefetch on `Stop` gives ~2 s of headroom against a ~0.5 MB NVMe read. **Fallback is a blocking `mmap`, still inside 50 ms locally.** Fixed lines and chips are pinned and can never miss. Verified cold-cache in [[07-TEST-PLAN]] §5 | Audio | Step 17 |
| R20 | **Tier 2 (S3/R2) drags a network call onto a call path** on a large deployment, breaking the demo host's *no external services* shape | **`AUDIO_TIER2=none` on the demo host and a test asserts no object-store client is imported.** Where enabled, tier 2 is **read-through at snapshot flip via `warm()`, never at play time** | Audio | Step 11 |
| R17 | **The LLM provider question is unresolved** | [[09-DECISION-LOG]] D1. A free tier reintroduces a failure mode [[tickets/T11]] deleted for *"less than a bus fare"* | Adarsh | **before Step 14** |

## 3 · Open questions the map still carries

Not risks and not debts — genuinely open, and each recorded with what would close it.

| Question | Closed by |
|---|---|
| Does Sarvam return the original transcript alongside the English hop? | An Audio integration check. If yes it becomes a **second LOG field, never a replacement** |
| Does the 2-turn context window beat four fields? | [[tickets/T13]]'s three-way bake-off. **Prediction on record; if the numbers disagree, take the numbers** |
| Do feature-phone callers recognise *हैश* / *हॅश* for `#`? | [[tickets/T13]] |
| Do Hinglish callers transcribe badly on the English pin? | [[tickets/T13]]. The fix is **one config line** |
| Should plural agreement in count-sensitive lines be fixed? | *The false numeral is gone; the plural is a grammar wobble, not a claim.* Revisit only if the dry-run hears it as wrong |
| What is the eventual production scheme count? | Out of the v1 bar. **N is a build parameter** |
| Who verifies spoken content in production, and at what rate? | Deferred with the truth lock. **The number sets the ceiling on production corpus size forever** |
| Should hard/soft be per (scheme, box)? | Correct, and it reopens [[tickets/T06]]. Not for v1 |

## Related
[[02-PRD]] §9 · [[03-ARCHITECTURE]] §15 · [[07-TEST-PLAN]] §5 · [[09-DECISION-LOG]] ·
[[maps/wayfinder-map]]

---
**Wayfinder Map:** [[maps/wayfinder-map|Latest Map]] · **Brain Index:** [[glossary|Glossary]]
