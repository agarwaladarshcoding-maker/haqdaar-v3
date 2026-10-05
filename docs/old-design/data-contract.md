---
title: "Data Contract — record, snapshot, gates, lines, trace"
slug: data-contract
type: module-note
module: data
status: reviewed
tags: [data, corpus, snapshot, gates, log, staging]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/T06.md
---

# Data Contract

Field-level detail behind [[03-ARCHITECTURE]] §10. Sources: [[tickets/T06]] (the record),
[[tickets/T21]] (provenance), [[tickets/T15]] (audio + manifest), [[tickets/T23]] (line inventory),
[[tickets/T16]] (the trace), [[tickets/T07]] (the pass that builds it all).

---

## 1 · One scheme record

Five field groups, one flat row per scheme. **Eligibility is facets, not rules.**

### A · Identity and provenance

| Field | Rule |
|---|---|
| `scheme_id` | capture order, never reused |
| `bit` | **assigned at build from row order, not captured.** Word width derives from row count |
| `myscheme_slug`, `source_url` | validator cross-checks slug against URL; **host must be `myscheme.gov.in`** |
| `level` | `STATE` · `CENTRAL` |
| `state`, `department` | the implementing body |
| `fetched_on` | date **our own scraper** read the page — *the only honest freshness fact we own* |
| `source_sha256` | hash of the five captured English blocks as fetched — **makes drift a comparison instead of a reading** |
| `facets_source` | `derived` (v1) · `audited` |
| `facets_verified_by` / `_on` | a name and date, or **null in v1** |
| `{lang}_sections_origin` | `source` · `machine` · `human`. v1: EN `source`, HI/MR `machine` |
| `{lang}_summary_origin` | `human` · `machine`. v1: `machine` |
| `{lang}_verified_by` / `_on` | a name and date, or **null in v1** |

**One rule makes a null mean something:** if either origin is `human`, `verified_by` and
`verified_on` are **required**. So a null can only ever mean *"no human touched this"* — it can
never mean *"someone forgot to fill it in"* ([[tickets/T21]]).

> **Why store a field that is null on every non-English row?** Two reasons ([[tickets/T21]]).
> Reinstating [[tickets/T08]]'s truth lock should mean **filling a field, not changing a schema**.
> And a null **puts the debt in the data itself**, where anyone reading the snapshot sees it —
> otherwise the debt lives only in the map, where no reader of the data will look.

### B · Matching (Door A)

| Field | Rule |
|---|---|
| `scheme_name_{en,hi,mr}` | the card title in each language |
| `aliases_{lang}` | **≥3 per language, stored as spoken**, lowercased and whitespace-normalised at build. **≥1 code-mixed form per non-English language** |

Honorifics and filler are kept in the stored alias, **never stripped at query time.** The official
title is stored separately and does not count toward the three.

**Aliases are a first-class field, not an enhancement:** *"nobody speaks a twelve-word official
title, and matching against the title alone fails the caller who says half of it."*

### C · Filtration — the mask columns

The seven boxes ([[03-ARCHITECTURE]] §7.2), plus `welfare_board` and `benefit_type`.

- **Numerics are stored exact** (`age_min`, `age_max`, `disability_min_pct`) and **collapse to
  closed sets only at build**, one mask per year / per point. **No banding at capture** — banding
  would lose precision to buy nothing, since the mask table is precomputed anyway.
- **The Engine sees categorical codes only — never a number, never a comparison** ([[tickets/T09]]).
- Conditional rules (`disability_min_pct` given `disabled = YES`) are the **validator's**; the
  Filter never sees a conditional.
- Keypad **band edges** for `age` and `income_band` are **derived by the pipeline from the
  snapshot's own cutoffs**, at most nine bands, and those two lines render per snapshot
  ([[tickets/T23]]). *A band that straddles a scheme's cutoff — a 38-year-old pressing "36 to 59"
  against an 18–40 scheme — cannot be filtered honestly.*

### D · Negative rules

- An exclusion landing on an existing column is **subtracted from that column's admitted set at
  capture.** No second mechanism, no second code path, **no runtime negation** — *the Engine applies
  no NOT masks, ever.*
- An exclusion landing on no column becomes an entry in **`gate_notes`** — a **list**, not a single
  free-text field (a scheme routinely carries several).
- **`gate_notes` is never spoken and never filtered on.** It exists so the LOG can carry a scheme's
  declared blind spots — *[[tickets/T16]] cannot prove a choice is clean without it.*

### E · Read-back — six chunks, three languages

`name` · `summary` · `benefit_text` · `who_can_apply` · `documents` · `how_to_apply`

All verbatim from the card **except `summary`**, which resolves a real collision: the bar wants a
named scheme read back in under 20 seconds, and `benefit_text` verbatim off a myScheme card is not
20 seconds in Marathi, while the capture rule forbids paraphrase. **Both cannot hold.** So one
~35-word one-breath summary per language, generated in English at ingest and translated.
*Without this field Door A misses the bar by construction* ([[tickets/T06]]).

**The record stores text, never audio.** Audio is derivative and content-addressed. There is no
audio column.

### Sentinel semantics

**One sentinel: `ANY`.** It means the scheme does not gate on this dimension, and **card silence
maps to `ANY`** — faithful to the source, since myScheme's own search returns a facet-silent scheme
for every value of that facet.

**A second `UNKNOWN` sentinel was considered and rejected:** it would let a half-captured row enter
the corpus wearing a disclaimer. **The build gate does that job better — a row that cannot be fully
expressed does not enter the snapshot at all.**

> `UNKNOWN` exists **at runtime** as a reserved value in every box's closed set ([[tickets/T11]]),
> but it describes a **caller**, never a scheme. The two never meet.

---

## 2 · The snapshot

```
snapshots/<snapshot_id>/
  schemes.jsonl      one flat row per scheme
  masks.bin          packed (box, value) -> word
  vocab.json         closed value sets + code map + `vocab_source` per box
  templates.json     line_id -> {lang -> render_key}, values expanded
  manifest.json      the snapshot IS the manifest
audio/<render_key>.ulaw    ONE FLAT POOL, shared across snapshots
```

- **`render_key = sha256(text ‖ lang ‖ voice_id ‖ tts_model ‖ 8000)`.** Text alone is wrong — *"a
  voice change would silently make every cached caller hear last month's read-back."*
- **A call binds to one snapshot at connect and holds it to hangup.** Deploy renders missing keys
  into the shared pool, writes the manifest, then flips a pointer. **In-flight calls finish on the
  old snapshot.**
- **`vocab_source` per box** records where each closed set came from ([[tickets/T21]] branch 6).
  v1: `occupation` is `corpus_prose_cut`; boxes authored from the roster are `authored`.
- **Retention obligation:** *derive-don't-store only works while the thing you derive from outlives
  the log that cites it.* **Snapshot records and manifests are kept at least as long as any LOG that
  names them** — committed to the repo, since they are small text. **The orphan sweep may delete
  audio, never records.**

### The mask table

Built once per snapshot, frozen with it, **never computed during a call.**

For every `(box, value)` pair, one word with one bit per scheme. A scheme's bit is set **if its
value matches, or if its value is `ANY`.**

```
mask[category   = agriculture] = 10100000
mask[state      = karnataka]   = 11011101
mask[occupation = farmer]      = 11101110
```

**`ANY` sets a scheme's bit in every mask for that column**, so a scheme silent on a dimension
survives every mask for it. Stated explicitly, because it decides whether questions narrow anything
at all.

### Audio inventory

| Family | Count | Source |
|---|---|---|
| Fixed lines | **N = 46 → 3N + 1 = 139 files** | [[tickets/T23]] §5 |
| Value chips — one bare chip per (box, value, language) | ≈ 200 values × 3 ≈ **600 files, ~30 MB** | [[tickets/T15]], [[tickets/T23]] |
| Scheme chunks | 6 × schemes × 3 languages | [[tickets/T06]], [[tickets/T15]] |
| **Whole rendered pool — 100-scheme demo corpus** | **~200 MB** | [[tickets/T15]] |
| **Whole rendered pool — national scale (~2,500 schemes)** | **~4.5 GB — does *not* fit in RAM** | [[03-ARCHITECTURE]] §10.1 |

**The +1 is the trilingual greeting** — *"the only audio file in the system that is not per-language"*
([[tickets/T24]]). That is why the formula is 3N+1 and not 3N.

**Composition rule** ([[tickets/T15]], amended by [[tickets/T23]] §3):

> Compose from separately-addressable files **only where the pieces must be independently
> addressable at runtime.** Everywhere else, render the whole sentence.

- Fixed lines → one file, whole sentence.
- **Chips after a colon pause are allowed; slots inside a sentence stay forbidden.** *A slot inside
  a clause has agreement to break in Hindi and Marathi; a bare noun chip after a colon has none.*
  This is T23's narrowing of T15's blanket ban, and it is what struck the ~600-file
  `confirm_<box>_<value>` carrier family — **one chip family now serves both single and bundle
  confirm.**
- Scheme audio → **concatenated from its six chunks**, because the sections are individually
  keypad-addressable and a mark must sit immediately before the name.

**Only one row above grows with the corpus.** Fixed lines are `3N + 1` and value chips are
`~200 × 3` — **both bounded by frozen numbers.** Scheme chunks are `6 × schemes × 3`, which is the
entire growth term. That split is what [[03-ARCHITECTURE]] §10.1 tiers on: **the bounded ~35 MB is
pinned in RAM, the unbounded remainder is read lazily off SSD** and is announced a full turn ahead
by `Planner.next_action` returning `Stop`. *"Fits in RAM" was a true observation about the demo
corpus, never a property of the design.*

**Storage tiers — a caching decision, not a layout one.** `audio/<render_key>.ulaw` remains **one
flat namespace shared across snapshots** at every tier; nothing is nested and nothing is renamed.

| Tier | Where | Contents | On the demo host |
|---|---|---|---|
| **0** | RAM, pinned | 139 fixed lines + ~600 chips (~35 MB) | same |
| **1** | Local SSD, `mmap` + byte-bounded LRU (`AUDIO_CACHE_MB`) | scheme chunks, on demand | **ceiling exceeds the whole pool — every read is a hit** |
| **2** | S3 / R2, read-through into tier 1 | large deployments only | **off (`AUDIO_TIER2=none`)** |

**Tier 2 is never on a call's critical path.** It populates tier 1 at snapshot flip via `warm()`,
not at play time. **`Corpus.load` verifies existence and digest against the pool index** — a
directory listing locally, a `ListObjectsV2` page at tier 2 — so a missing or corrupt key is still
a deploy-time failure and error rule 1 is untouched.

**Zero-runtime-TTS is unchanged.** Lazy means *read later*, never *synthesise later*: every byte
still comes from a build-time render under the frozen `render_key`, and the runtime still imports
no TTS client.

**Render pipeline:** TTS → WAV → `ffmpeg` → 8 kHz mono μ-law, stored as `.ulaw`. **One
loudness-normalise pass and a trim-then-pad to a fixed 120 ms tail on every file** — load-bearing,
because the read-back concatenates six files and *"a level mismatch between them sounds like a fault
on a phone line."* **One file per play call. No slicing.**

---

## 3 · The five build gates

**A record failing any gate does not enter the snapshot.** No partial record, no warning flag, no
degraded read. **Run them as a pre-filter, not a post-check, ordered by cost** ([[tickets/T07]]).

| # | Gate | Check | Owner |
|---|---|---|---|
| 1 | **Alias floor** *(cheapest, excludes most — run first)* | ≥3 aliases per language; ≥1 code-mixed per non-English language; **uniqueness**: an alias on **≥3 schemes is dropped from all of them** (it is a category word — *yojana*, *sarkari*), an alias on **exactly 2 is kept** and those two **are** the Door A disambiguation pair | [[tickets/T12]] · [[tickets/T24]] |
| 2 | **Expressibility** | Every facet column resolves to a closed-set value or `ANY`. `ANY` is the only sentinel | [[tickets/T06]] · [[tickets/T07]] |
| 3 | **Read-back completeness** *(runs last — the only gate that spends TTS)* | All six chunks present **and rendered** in all three languages — 18 manifest entries per row | [[tickets/T15]] |
| 4 | **Forbidden phrase — two tiers** | See below | [[tickets/T18]] · [[tickets/T23]] |
| 5 | **Provenance & freshness** | Host is `myscheme.gov.in`; `fetched_on` within `MAX_SOURCE_AGE_DAYS`; **`source_sha256` re-check before the demo snapshot freezes** | [[tickets/T21]] |

### Gate 4 in detail — the only mechanical defence of *never mislead*

[[tickets/T08]] removed the human verifier, so nothing else checks a translated string for an
eligibility claim before it is spoken to a citizen.

| Tier | Applies to | Test |
|---|---|---|
| **1 · our authored voice** | every fixed line and every `summary` | **bare words** banned: "eligible", "qualify", "entitled", "you will get", "you can get" · पात्र, हकदार, मिलेगा, पा सकते हैं · पात्र, हक्क, मिळेल, मिळू शकते |
| **2 · verbatim source sections** | benefits, who-can-apply, documents, how-to-apply | **second-person claims only**: EN *"you are eligible / you will get / you can get"* · HI *"आप पात्र / आपको मिलेगा"* · MR *"तुम्ही पात्र / तुम्हाला मिळेल"* |

**Why two tiers.** A bare-word ban over verbatim sections would exclude nearly every myScheme
scheme, because *myScheme's own eligibility prose says "eligible" in almost all of them* — and gate
3 would then take out the whole corpus. Tier 2 targets **the failure machine translation actually
produces.** Source sections are always spoken behind `section_source_frame`.

**Brand allowlist:** the exact token HAQDAAR / हकदार and its Marathi inflection is exempt **in
`closing_farewell` only.** *The first pass's compliance claim was false — the brand name is the
forbidden word.* Thanking someone for calling a service is not a claim about the caller.

### Drift

Before the demo snapshot freezes, **one command re-fetches every page and re-hashes.** A changed
`source_sha256` **excludes the record until its owner re-reads it** — re-confirm the facets,
re-author the summary, re-run the other gates. **There is no auto-accept**, because the hash can
tell *that* the text changed but not *whether it matters*.

If drift knocks out one of the fixture's five coverage schemes, **hand re-read that one** rather
than lose the coverage role — about 20 minutes. Any other drifted scheme simply leaves the snapshot.
**After the snapshot freezes, drift is not our problem for that session**: the call is pinned.

---

## 4 · The 46 fixed lines

Ids are the identity; row order is display-only ([[tickets/T17]]).

| Group | Lines | Ids |
|---|---|---|
| 1 · Greeting | 1 | `greeting_trilingual` *(the one non-per-language file; plays hi → mr → en)* |
| 1b · Consent | 1 | `consent_notice` *(after selection, before the opener — never at the greeting, where it would be trilingual and triple the one preamble every caller pays for)* |
| 2 · Opener, disambiguation, controls | 6 | `opener_prompt` · `unclear_prompt` · `anything_else` · `door_a_option_1` · `door_a_option_2` · `door_a_option_none` · `door_a_downgrade_to_b` |
| 3 · Question forms | 6 | `q_state` · `q_gender` · `q_social_category` · `q_age` · `q_income_band` · `q_occupation` |
| 4 · Rephrase forms | 6 | `rephrase_*` for the same six boxes |
| 5 · Keypad menus | 5 | `keypad_gender` · `keypad_social_category` · `keypad_age` · `keypad_income_band` · `keypad_occupation` · plus `keypad_unknown_suffix`. **`state` has no menu — 36 values** |
| 6 · Confirmation frames | 3 | `bundle_confirm_intro` · `confirm_bundle_opener` · `confirm_yn_suffix` |
| 7 · Silence ladder | 1 | `silence_presence` |
| 8 · Read-back controls | 4 | `section_menu` · `section_source_frame` · `next_scheme_intro` · `no_more_schemes` |
| 9 · Mode & carve-out | 2 | `keypad_only_mode` · `state_unknown_disclaimer` |
| 10 · Fallback & terminals | 8 | `results_exact_preamble` · `results_overflow` · `terminal_widened_preamble` · `drop_income_band` · `drop_age` · `drop_occupation` · `drop_category` · `results_widened_lead` · `terminal_nearest_preamble` · `terminal_empty` |
| 11 · Closing | 1 | `closing_farewell` |

**Sequencing rules Engine must obey** ([[tickets/T23]] handoffs, [[tickets/T21]] branch 3):

- Widened terminal order is **`terminal_widened_preamble → drop_<box> (each) → results_widened_lead
  → names`** — *bad news first, and every clause lands where its punctuation points.*
- Echo-confirm is assembled as **`bundle_confirm_intro + chip(s) + confirm_yn_suffix`**.
- **`section_source_frame` goes before every verbatim section and NEVER before `summary`.** The
  summary is our compression in our voice — *attributing it to "the official page" would itself be
  an untruth.* Nearest reads `summary` only, so it never meets the frame at all.
- **The caller never hears a date.** `fetched_on` says when we read the page, not that the page is
  still true; *"as of 11 September" sounds like a guarantee and isn't one*, and a feature-phone
  caller cannot check it against anything. **Freshness is a gate, not a sentence.**
- `0` = *none of these / don't know* on **every** menu. `#` repeats. **Any keypress resets the
  silence ladder to rung 0** — the ladder measures presence, and a keypress is presence.
- Nearest terminals **auto-advance** and never play `section_menu`.

**Authoring constraint:** Hindi and Marathi lines are written **impersonal**. Gendered first-person
verbs (*पाया, सकता हूँ, बताऊंगा*, Marathi *शकतो*) **bind the render to a male voice and defeat the
cheap voice swap** the render key was designed to buy ([[tickets/T23]] §5).

---

## 5 · The trace

**One JSONL per call, one line per turn, every turn, whatever its class.**

```jsonc
// call open
{ "call_id": "...", "snapshot_id": "...", "caller_hash": "...", "lang": "mr",
  "lang_source": "keypad", "t0": 0.0 }

// every turn
{ "turn_n": 3, "class": "ANSWER", "transcript": "<full English-hop utterance>" }

// ANSWER adds
{ "box": "state", "value": "BIHAR", "span": "in Bihar" }

// UNKNOWN value adds
{ "unknown_source": "declined" }          // declined | keypad_dropped

// a DTMF flush adds
{ "discarded_transcript": "..." }

// Door A adds
{ "t_name": 3.4, "t_end": 17.9, "candidate_count": 1 }

// NOISE is thin — but it IS written
{ "turn_n": 4, "class": "NOISE" }

// SILENCE carries the CURRENT turn_n unchanged — the turn is still open
{ "turn_n": 4, "class": "SILENCE", "silence_n": 2 }

// closing
{ "stop": "zero_survivors", "ladder_rung": 2, "mode": "keypad_only" }
```

`class` ∈ **ANSWER · CLARIFY · REPEAT · META · UNCLEAR · NOISE**. The first five are model classes
([[tickets/T11]]); **NOISE is a code branch upstream of the model** and still writes a line.

**Kept, and why each earns its place:**

- **`transcript` — the full utterance, not just the span.** This is what makes the four non-stamping
  classes provable instead of invisible: *"CLARIFY, REPEAT, UNCLEAR and NOISE write no box and no
  value; without the transcript, a judge sees a turn that consumed budget and left no evidence of
  why. The span alone cannot do this — a CLARIFY has no span."* Pinned to **the English-hop text,
  the text the model was actually handed**, because that is what the span was checked against. If
  the original-language transcript is also available it becomes a **second field, never a
  replacement.**
- **`unknown_source`** — `declined` vs `keypad_dropped`. *Same value, different story, and only the
  LOG can tell them apart.*
- **`ladder_rung` and `stop`** — **the only exceptions to derive-don't-store.** Written once, at the
  moment they are true, because *"they are not properties of the state; they are which branch the
  code took, and re-running the algorithm months later to find out is trusting the thing under audit
  to testify about itself."* `ladder_rung` stays a single integer — the ladder is monotone, so k plus
  the box vector plus the fixed order reconstructs the dropped set.

**Struck, and why:**

- **`confidence`** — has no source. [[tickets/T03]] found the ASR returns none, and [[tickets/T11]]
  struck the model's own: *"a model self-reporting confidence on a selection it just made is not
  evidence, it is a second generation."* **There is no confidence number anywhere in this system.**
- **`mask`, `survivors_before/after`** — the snapshot id plus the ordered box vector reconstruct the
  entire call. *"Storing survivor sets would be a second copy of a derivable fact, which is
  redundancy dressed as proof."* A reader wanting the survivors at turn 4 replays four AND
  instructions against a pinned snapshot and gets them exactly.
- **`terminal_state`** — struck deliberately. A call reaching a terminal writes a closing line whose
  content says which one; a call that does not simply stops mid-file, and [[tickets/T04]] reads that
  structurally. *"A flag that disagrees with the trace is worse than no flag."*
- **No summary object** — *if it is trustworthy it is derivable, and if it is derivable it should
  not be stored.*

**Never stored:** audio · the caller's raw number (hashed) · masks · survivor sets · tally ·
specificity · confidence.

**One file, two readers.** A judge walks it top to bottom for terminal state, turn count and spoken
names; an engineer reads the same lines for class, box, value and span. **No second format** — *a
judge-only summary would be a second artifact that [[tickets/T04]]'s own audit is not allowed to
trust.*

**The named debt** ([[tickets/T16]] §5): *"'Scheduled Caste farmer in Bihar earning under ₹50,000'
is a caste, an income band and a state in one sentence, and it is more identifying as persisted text
than the hashed number sitting beside it."* Kept anyway, because **a redacted transcript cannot
evidence a CLARIFY or an UNCLEAR, which is the entire reason the field exists.** Recorded on the
same footing as the suspended truth lock.

## 6 · Related

[[03-ARCHITECTURE]] · [[04-INTERFACES]] · [[06-BUILD-PLAN]] · [[briefs/data]] ·
[[notes/data/overview]] · [[tickets/T06]] · [[tickets/T07]] · [[tickets/T15]] · [[tickets/T16]] ·
[[tickets/T21]] · [[tickets/T23]]

---
**Wayfinder Map:** [[maps/wayfinder-map|Latest Map]] · **Brain Index:** [[glossary|Glossary]]
