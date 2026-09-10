---
title: "HAQDAAR v1 — Build Plan"
slug: build-plan
type: module-note
module: architecture
status: reviewed
tags: [build, plan, execution, staging]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/BUILD-PLAN.md
---

# HAQDAAR v1 — Build Plan

> **Status: draft, staged, not merged.** Two dates, both from **map rev 26**:
> **this plan and [[03-ARCHITECTURE]] are due 12 Sep**, and **D-day — the ten-call acceptance run —
> is 14 Sep 2026**, moved there from 12 Sep by that same entry. Days 1–5 below run to 14 Sep.
> **21 steps, 0–20**, as rev 27 names them; `v1-keypad` at Step 12 is a demoable product on its own.

## How to run a step

Each step sits in one module where possible and carries a test that proves it.

**To the implementing agent:**
> Implement **Step N** of `brain/docs/build-plan`. Follow `AGENTS.md`. Read
> `brain/docs/architecture`, `brain/docs/interfaces` and **every ticket the step names** before
> writing code. Work on branch `step-NN`. Do nothing outside this step. Finish by running the step's
> **Done when** command and pasting its real output.

**To the reviewing agent:** `brain/docs/review` with the step number. **Merge only on a passing
review.**

```bash
git checkout main && git pull
git checkout -b step-NN
# implement, then review, then:
git checkout main && git merge --no-ff step-NN -m "step NN: <name>" && git push
```

**Milestone tags:** `v1-skeleton` (Step 2) · `v1-keypad` (Step 12) · `v1-voice` (Step 16) ·
`v1` (Step 20).

**If time runs short: `v1-keypad` is a complete, honest, demoable call on its own**, and
[[tickets/T18]] proved it end to end — *keypad-only completes a whole call and scores a
[[tickets/T04]] pass.* Everything after it adds speech.

**Standing review checks, every step:** the word "twilio" appears only under
`haqdaar/audio/telephony/` · `filter.py`, `planner.py`, `terminals.py` import only `contracts/` ·
the runtime never imports `data/pipeline/` · signatures match [[04-INTERFACES]] (and if that
disagrees with [[tickets/T17]], **T17 wins**) · no key or token in code, tests, fixtures or this
branch's history · numbers live in `contracts/tunables.py`, not inline.

---

## Day 1 — skeleton and a real call

### Step 0 · Repo and rules
- **Files:** `pyproject.toml` (Python 3.11; fastapi, uvicorn[standard], websockets, httpx, pydantic,
  python-dotenv, pyyaml, pytest, pytest-asyncio) · `Makefile` with `run · sim · test · demo-fixture ·
  pipeline · smoke` · `.env.example` · `.gitignore` (`.env`, `logs/`, `audio/`, `.venv/`,
  `data_cache/`, `brain/.obsidian/workspace*.json`) · empty package tree per [[03-ARCHITECTURE]] §4.
- **Also in this step, from map rev 27:** vendor the vault into the repo at **`brain/`** — this map
  and every ticket — with **`brain/docs/`** holding ARCHITECTURE, PRD, BUILD-PLAN, REVIEW and TODAY,
  so *"a decision lives in the brain or nowhere"* and every agent reads it before acting. Write root
  **`AGENTS.md`** (Antigravity reads it) with **`CLAUDE.md` importing it**, so the two agents cannot
  drift on rules.
- **Done when:** `make test` → 1 passed, and `brain/docs/build-plan` opens from inside the repo.
- **Review focus:** tree matches §4 **exactly**, including `audio/` as a **top-level flat pool**,
  not nested under `snapshots/`.

### Step 1 · Telephony smoke call
- **Tickets:** [[tickets/T19]], [[tickets/T14]], [[tickets/T05]].
- **Files:** `server.py` (`/health`, `/answer` returning the Stream XML as `text/xml`, `/stream`
  accepting the WS) · `audio/telephony/twilio.py` (parse `connected`/`start`/`media`/`dtmf`/
  `mark`/`stop`; build outbound `media`, `mark`, `clear`) · `tools/tone.py`.
- **Behaviour:** on `start`, send a 1 s 440 Hz tone as one `media`, then a `mark` named `tone_end`.
  Print inbound marks and digits. Digit `9` closes the socket.
- **Done when:** a real dial produces `mark tone_end` and `dtmf 1` in the terminal and the call
  ends; `tests/test_twilio_codec.py` passes.
- **Review focus:** outbound media carries **no WAV header**. Stream URL takes **no query string**.
- **Ratify on this call** ([[tickets/T14]]): **`keepCallAlive="false"`.** If it drops calls at
  connect, flip to `true` and bound the strand with `streamTimeout="600"`. **Write the result into
  the step's commit message.**
- **Measure and record:** seconds from dial to tone · three phones within ten seconds, how many
  reach the opener ([[tickets/T19]]).

### Step 2 · Contracts, tunables, fixture
- **Tickets:** [[tickets/T17]], [[tickets/T16]], [[tickets/T10]], [[tickets/T06]].
- **Files:** `contracts/types.py` — every name in [[04-INTERFACES]], the seven-box enum **plus the
  `scheme` pseudo-box**, `UNASKED`/`UNKNOWN` markers, and the input union
  **`Digit | Speech | Noise | Silence(n) | Hangup`** · `contracts/tunables.py` — the full table in
  [[04-INTERFACES]], **including both `MAX_TURNS=8` and `MAX_QUESTIONS=6`** ·
  `contracts/log_schema.py`.
- **Fixture** ([[tickets/T17]] §4) — **curated by Data's owner**, because the fixture is a miniature
  snapshot and Data's build already emits snapshots:

  | | Role | Proves |
  |---|---|---|
  | S1 | exact match on P1 | the happy path and the ≤4 stop |
  | S2 | soft-miss on `income_band` | speakable-with-a-label; the miss-set |
  | S3 | hard-miss on `state` | never-speakable; the speaking rule |
  | S4 | `ANY` on five of seven boxes | specificity ordering beats tally |
  | S5 | shares one alias with S1 | Door A's cap of 2 and the disambiguation turn |
  | S6 | missing its Marathi `summary` | **must be REJECTED at the build gate** |

  **Three personas: P1** narrows to 1 survivor · **P2** narrows to 0 and must run the **full
  widening ladder** to a labelled nearest-two · **P3** names a scheme at the opener.
  **Nine utterances** — one per persona per language. **~10 audio stubs**: correct-duration silence
  named by render key, *so the turn clock is testable before a phone line exists.*
- **Done when:** `make test` loads every fixture record into the record type with no validation
  error, and the S6 row is rejected.
- **Review focus:** no logic in `contracts/`. **The fixture and [[tickets/T08]]'s offline test base
  are the same artifact — do not build two.**
- **Tag:** `v1-skeleton`.

---

## Day 2 — the pure engine, and data starts flowing

### Step 3 · Filter (pure)
- **Tickets:** [[tickets/T09]], [[tickets/T10]], [[tickets/T18]].
- **Spec:** build masks from records (`ANY` sets the bit in **every** mask for that column);
  **retain turn masks, do not fold them**; `survivors` = AND of answered masks; `tally`; `miss_set`.
  `speakable(scheme)` is **False** if any hard box (`state`, `gender`, `social_category`) is non-`ANY`
  on the scheme and is UNASKED, UNKNOWN or mismatched in the vector. `nearest(vector)` keeps schemes
  whose miss-set is **soft-only**, ranks by **tally** then specificity, returns **at most 2**.
- **Done when:** `pytest tests/test_filter.py` passes; the hard-miss scheme S3 is **never** speakable
  for P1; **UNKNOWN never narrows**.
- **Review focus:** zero imports beyond `contracts/`. **No NOT masks anywhere. No numbers, no
  comparisons** — the Filter sees categorical codes only.

### Step 4 · Planner (pure)
- **Tickets:** [[tickets/T10]], [[tickets/T11]], [[tickets/T15]], [[tickets/T18]].
- **Spec:** `next_action(box_vector, corpus) -> Ask(box) | Widen(box) | Stop(reason)`.
  - **Score:** minimax elimination ÷ expected turns (keypad 1, spoken 2). Ties break on **snapshot
    order**. **Day one, not deferrable** — ratified 10 Sep 2026 ([[09-DECISION-LOG]] D3). The
    fixed-order stand-in is withdrawn; do not implement it, do not leave a flag for it.
  - Skip answered boxes; **skip UNKNOWN boxes permanently** — UNASKED stays askable, UNKNOWN does
    not. Skip any box where every survivor holds the same value.
  - **Four stops:** ≤4 survivors · **8 turns OR 6 questions** · no splitting box · **zero survivors,
    named separately in the LOG.**
  - **The speaking-rule exception:** do **not** stop on "≤4" while an unasked hard box is non-`ANY`
    on any survivor. **Ask that box first**, or the call stops holding schemes it is not allowed to
    speak.
  - **`Widen`:** soft boxes only, one at a time, **`income_band → age → occupation → category`**,
    skipping rungs over UNASKED/UNKNOWN boxes (they appended no mask, so there is nothing to widen),
    **stopping at the first rung producing ≥1 survivor.**
- **Done when:** `pytest tests/test_planner.py` covers **all four stops** and the full ladder,
  including a rung that is skipped rather than counted.
- **Review focus:** pure. Stop reason strings match the LOG schema. **Hard boxes are never widened.**

### Step 5 · Terminals (pure)
- **Tickets:** [[tickets/T18]], [[tickets/T23]], [[tickets/T21]].
- **Spec:** survivors + state → an ordered `say()` sequence of line ids, chips and marks, for **all
  five delivery shapes** in [[03-ARCHITECTURE]] §8. `state_unknown_disclaimer` first when `state` is
  UNKNOWN. A `name:<scheme_id>` mark **immediately before each name**; `end:<scheme_id>` after its
  summary. **Nearest = `summary` only, no `section_menu`, auto-advance.**
  **`section_source_frame` never before a `summary`.**
- **Done when:** `pytest tests/test_terminals.py` includes an **ordering test**: in every non-exact
  ending, **no scheme name appears before the preamble**, and in the widened ending the order is
  `preamble → drop_* → results_widened_lead → names`.
- **Review focus:** **bad-news-first is asserted, not assumed.** This is the assertion that replaces
  the human verifier [[tickets/T08]] removed.

### Step 6 · Log, call loop and console sim (keypad-only)
- **Tickets:** [[tickets/T16]], [[tickets/T17]], [[tickets/T24]], [[tickets/T14]].
- **Files:** `data/log.py` · `engine/call.py` (keypad path: turn 0 → consent → questions → terminal
  → read-back menu → anything_else → closing) · `sim.py` with a `FakeAudio` that prints line ids and
  reads typed digits · `make sim` · **`make demo-fixture`** ([[tickets/T17]] §4 names this command:
  a whole call against four fakes, printing the LOG).
- **Done when:** all three personas run to `closing_farewell`; `logs/<id>.jsonl` has a call-open
  line, **one line per turn including NOISE and SILENCE lines**, and a closing line carrying `stop`
  and `ladder_rung`; **P2 reaches a labelled nearest-two through the full ladder.**
- **Review focus:** **`Log.write` never raises — test it with a deliberately bad line and assert
  `invalid: true` is written.** Engine imports no telephony. **Turn 0 writes a line and does not
  count against the cap. A SILENCE line carries the current `turn_n` unchanged plus `silence_n`.**

### Step 7 · Scraper
- **Tickets:** [[tickets/T02]], [[tickets/T21]], [[tickets/T22]], [[tickets/T07]].
- **Files:** `data/pipeline/schemes.yaml` (the slug list — **verify each slug resolves; replace any
  that do not and note the substitution**) · `p1_scrape.py`, Playwright headless (myScheme renders
  client-side).
- **Output per scheme:** `data_cache/raw/<slug>.json` with `source_url`, `fetched_on`, the five
  English blocks (benefits, eligibility, exclusions, documents, apply), and **`source_sha256` over
  those five blocks**; plus `raw/<slug>.html`.
- **Done when:** `make pipeline-scrape` produces ≥8 files, each on a `myscheme.gov.in` host with
  non-empty blocks (exclusions may be empty).
- **Review focus:** polite delays; cached (no refetch under 1 day); **no third-party datasets** —
  [[tickets/T02]] found one that **fabricates eligibility rules and Hindi text on fetch failure**.

### Step 8 · Derivation (facets, aliases, summary)
- **Tickets:** [[tickets/T06]], [[tickets/T07]], [[tickets/T10]], [[tickets/T11]], [[tickets/T12]],
  [[tickets/T24]].
- **Spec:** one model call per scheme per task, throttled and **cached to `data_cache/extract/`** so
  re-runs are free. **Nothing in this pass may scale with N in human time.** *(The throttle is not
  hygiene: map rev 27 puts this pass and the runtime on the same org-wide free-tier limit, so an
  unthrottled re-run during a call is a self-inflicted 429.)*
  - **Facets:** each box gets a closed-list value or `ANY`, **with the quoted sentence that justifies
    it**. A value with no quote becomes `ANY`, and the quote goes to `gate_notes`. Set
    `facets_source: derived` and **`facets_verified_by: null`** — map rev 26 automates this pass
    end to end and makes the missing human read **visible in the data** ([[tickets/T21]]'s own
    pattern) rather than an unwritten assumption. v2 fills the field; the gates still run, so a
    machine-filled record that fails one still does not enter the snapshot.
  - **Aliases:** ≥3 per language, **≥1 code-mixed per non-English language**; uniqueness resolved
    over the whole table afterwards.
  - **Summary:** generated in English, ~35 words, then translated. Tier-1 forbidden words banned.
  - **Occupation vocabulary is cut from the corpus's own eligibility prose in this same pass**, in
    three languages, **with its cardinality recorded** — it must stay ≤9 to keep its keypad menu.
- **Done when:** `make pipeline-extract` writes a valid record per scraped scheme, with **every
  non-`ANY` facet carrying an evidence quote found verbatim in the eligibility text.**
- **Review focus:** the evidence-quote check is **in code**. The model is told to **select, never to
  invent**, and the closed set is enforced **after** the model returns — *a prompt is not a guard.*

---

## Day 3 — snapshot, real audio, keypad call on the phone

### Step 9 · Translate and the five gates
- **Tickets:** [[tickets/T08]], [[tickets/T18]], [[tickets/T21]], [[tickets/T23]], [[tickets/T12]],
  [[tickets/T15]].
- **Spec:** Sarvam Translate for sections and summary. **Hold-aside check:** every digit, ₹ amount
  and date string in the English must appear **unchanged** in the translation, or the record fails.
  `p4_gates.py` runs all five gates **in the pre-filter order** of [[05-DATA-CONTRACT]] §3 and prints
  a scheme × gate table with the failing clause.
- **Done when:** `make pipeline-gates` prints the table and ≥6 schemes pass everything.
- **Review focus:** the brand allowlist is scoped to **`closing_farewell` only**; tier 2 checks
  **second-person claims only**; the gates run **cheapest-first as a pre-filter**, and read-back
  completeness runs **last** because it is the only one that spends TTS.

### Step 10 · Render audio
- **Tickets:** [[tickets/T15]], [[tickets/T23]], [[tickets/T24]].
- **Spec:** `lines.yaml` = **the 46 lines from [[tickets/T23]] → 139 files (3N+1)**, the +1 being
  `greeting_trilingual`. Plus **one bare chip per (box, value, language)** ≈ 600 files. Plus six
  chunks × schemes × 3 languages. Render key = `sha256(text ‖ lang ‖ voice ‖ model ‖ 8000)`; **skip
  existing files.** Bulbul → `ffmpeg` → raw μ-law 8 kHz mono, **loudness-normalised, 120 ms tail.**
- **Done when:** `make pipeline-render` reports **0 missing against a count of 139 + chips + chunks**,
  and `python tools/play.py <line_id> mr` writes a WAV.
- **Adarsh listens:** 3 Marathi and 3 Hindi lines, **and one `bundle_confirm_intro` + chip pair to
  check it does not sound seamed at the 120 ms tail.** If a voice is unusable, change the voice id in
  tunables and re-render — *the key makes it a re-render, not a redesign.*
- **Review focus:** render is idempotent; **the runtime imports no TTS client, and a test asserts
  it** ([[tickets/T19]] weakened this from a credential rule to a code rule — honour the code rule).

### Step 11 · Snapshot build and Corpus
- **Tickets:** [[tickets/T15]], [[tickets/T17]], [[tickets/T21]], map rev 3.
- **Spec:** `p6_snapshot.py` writes `schemes.jsonl`, `masks.bin`, `vocab.json` (with `vocab_source`
  per box), `templates.json` and `manifest.json`, **derives the keypad age and income band edges
  from the snapshot's own cutoffs (≤9 bands)**, and flips `CURRENT`. `corpus.py` loads the **records**
  into memory and **raises if any line id lacks audio** — proven by **verifying existence and digest
  of every declared `render_key` against the pool index**, not by reading the pool
  ([[03-ARCHITECTURE]] §10.1). Also build `audio/pool.py`: **tier 0 pinned** (139 fixed lines +
  ~600 chips), **tier 1 `mmap` + byte-bounded LRU** at `AUDIO_CACHE_MB`, optional **tier 2
  read-through** behind `AUDIO_TIER2` (**`none` for the demo — do not wire a bucket**), and
  `warm()` / `prefetch(keys)`.
- **Done when:** `make pipeline` runs Steps 7–11 end to end; `Corpus.load(CURRENT)` succeeds; the sim
  from Step 6 runs against the **real** snapshot; **a corrupted `.ulaw` and a deleted `.ulaw` each
  make `load` raise**; **boot RSS is flat when the pool is doubled with junk keys** — the test that
  proves the growth term left memory.
- **Review focus:** `schemes.jsonl` and `manifest.json` are **committed** (they must outlive the logs
  that name them); **`audio/` is a flat top-level pool and is gitignored** — **still one flat
  namespace at every tier, nothing nested per snapshot**; `pool.py` is imported only by
  `haqdaar/audio/`, never by `corpus.py`, and **a test asserts the runtime imports no TTS client and
  no object-store client when `AUDIO_TIER2=none`.**

### Step 12 · Mouth over the wire → keypad-only call on a real phone
- **Tickets:** [[tickets/T14]], [[tickets/T15]], [[tickets/T23]], [[tickets/T24]].
- **Files:** `audio/mouth.py` — `say`/`repeat`/`clear`/`on_mark`, with mark tracking that **ignores
  marks cleared after a `clear`** · `audio/turn.py` — keypad only for now; a silence timer started
  from each **`playedStream`**, never from send · wire the real `Audio` into `server.py` ·
  `Audio.select_language()`.
- **Engine additions:** the 6/6/6 silence ladder (replay → presence → closing) · `#` repeat ·
  `*` re-pin replaying `greeting_trilingual` and **clearing nothing** · **any keypress resets the
  ladder** · `#` at turn 0 **not** consuming one of the two greeting plays · the 10-minute ceiling.
- **Done when:** one call per language, keypad only, reaching a read-back and `closing_farewell`, and
  each LOG shows the closing line.
- **Review focus:** **hang up only after the closing line's mark returns** — *nothing may hang up on
  a queued buffer.* `*` and `#` never close a turn; digits 0–9 do.
- **Tag:** `v1-keypad` — **this is already a demoable, T04-passing product.**

---

## Day 4 — voice

### Step 13 · Ear and the settled turn
- **Tickets:** [[tickets/T03]], [[tickets/T14]], [[tickets/T24]].
- **Spec:** forward the carrier's 20 ms μ-law frames to Sarvam **unbatched** — *the largest single
  saving in the chain, and it costs nothing.* Config: `endpointing=vad`,
  **`stream_type="fast"` (not optional — `balanced` buffers ~1000 ms and puts a full second in front
  of every turn, invisibly)**, `silence_duration_ms=700`, `min_speech_duration_ms=250`,
  `mode="codemix"`, `audioTrack="inbound"`.
  - **First complete input wins:** a key is complete on arrival, speech only at endpoint.
  - On a key during speech: send `flush`, act on the digit, log the finalised text as
    `discarded_transcript`.
  - **`vad.speech_start` with an empty or span-less final = NOISE (consumes a cap turn). No
    `speech_start` at all = SILENCE (does not).**
  - **Check Sarvam's current docs** for exact message names and whether the English hop comes from
    the same stream or needs a translate call. **Write the answer into the commit message.**
- **Done when:** `tests/test_turn.py` replays recorded event sequences covering the DTMF race, the
  flush and both NOISE/SILENCE branches; a live call prints transcripts for three spoken sentences
  in each language.
- **Review focus:** **Audio still imports nothing from Engine, Model or Data.**

### Step 14 · Model router
- **Tickets:** [[tickets/T11]], [[tickets/T12]], [[tickets/T14]], [[tickets/T17]].
- **Spec:** `opener()` returns a list of `(box, value, span)` including the `scheme` pseudo-box;
  `turn()` returns exactly one result and takes `ask_count`. JSON-only prompts, **temperature 0**,
  structured output, **no streaming**, closed sets from `Corpus`, **span guard inside Model**,
  **2.0 s hard timeout, no in-turn retry.** A timeout, transport error, malformed output, out-of-set
  value or span drop returns a typed failure and increments `Model.failures`. **Never raises.**
  Context is the **two-turn verbatim window plus `ask_count`** — the model may *read* the window but
  may only *quote* from the current utterance.
  **Class precedence: `META > ANSWER > CLARIFY > REPEAT > UNCLEAR`.**
- **Provider: Groq, free tier** — ratified by **map rev 27**, overturning [[tickets/T11]] §5
  *"on budget, not on argument."* The model id is a **tunable**, not a constant: pick it with a
  **30-utterance bake-off** — 30 real-shaped utterances across the three languages, scored on
  class accuracy, closed-set validity and **span survival**, and **timed**. Record the winner and
  the runner-up in [[09-DECISION-LOG]].
- **The 429 path is part of this step, not an afterthought.** A 429 returns the same typed failure
  as a timeout and increments `Model.failures`, so [[tickets/T18]]'s two-per-call drop to
  keypad-only handles it. **No in-turn retry.** Test it with a mocked 429.
- **Latency is an output of this step.** [[tickets/T14]] priced the model call at 300–500 ms
  against Gemini Flash-Lite; that number is now unverified. **The bake-off reports p50 and p95.**
  If the winner misses the budget, raise it in [[09-DECISION-LOG]] — the 1.2 s response clock moves,
  the provider does not.
- **Done when:** `pytest tests/test_model.py` passes with a mocked provider, including
  **a span-guard test — "farmer" must not produce an `income_band` stamp** — and a precedence test
  for *"Bihar. Aur ye income band kya hota hai?"* returning **ANSWER**, not CLARIFY.
- **Review focus:** **no free text ever reaches Engine.** The system prompt is byte-identical across
  calls, so provider-side caching can apply.

### Step 15 · Door A and the opener bundle
- **Tickets:** [[tickets/T12]], [[tickets/T23]], [[tickets/T11]].
- **Spec:** after `opener_prompt` — **exact alias match in code first**, then `Model.opener`.
  1 candidate → read-back with the `t_name` mark · 2 → keypad pick **with `door_a_option_none` on
  `0`** · ≥3 or `0` → `door_a_downgrade_to_b`, seeded. Box stamps → `bundle_confirm_intro` + chips +
  `confirm_yn_suffix`; **`2` drops every opener box back to UNASKED** and the ladder re-asks at
  normal price.
- **Done when:** sim tests cover **all four candidate counts (0, 1, 2, ≥3)**, and a live call saying
  *"PM kisan"* records **`t_name` < 20 s** in the LOG.
- **Review focus:** **Door A has no confirm turn** — the read-back is the confirmation.
  **`t_name` comes from the mark's `playedStream`, not a local clock.**

### Step 16 · Spoken state, and the failure ladders
- **Tickets:** [[tickets/T11]], [[tickets/T15]], [[tickets/T18]], [[tickets/T23]].
- **Spec:** `q_state` → Speech → `Model.turn` → chip echo + yes/no. **Two consecutive non-ANSWERs on
  `state` → UNKNOWN** (`unknown_source: dropped`), **never a keypad menu — 36 values fail the
  cardinality rule.** `CLARIFY` → `rephrase_state`. **UNKNOWN is accepted first time, never re-asked,
  and declining does not count as a failed turn.**
  **Call-level keypad-only** on **2 model failures (not consecutive)** *or* **1 unrecovered ASR
  socket after one free reconnect**: play `keypad_only_mode`, turn Door A off, force `state` to
  UNKNOWN. **Written once, consumes no turn. An UNCLEAR is not a failure.**
- **Done when:** sim tests pass for the UNKNOWN-state path (**disclaimer spoken first**), the
  keypad-only switch, and **the binding worst case — a drop at turn 1 completing five keypad boxes
  inside the 8-turn cap**; plus one live call per language completing Door B with spoken state.
- **Tag:** `v1-voice`.

---

## Day 5 — harden and accept

### Step 17 · Anything-else loop and read-back sections
- **Tickets:** [[tickets/T18]], [[tickets/T23]], map rev 2.
- **Spec:** `anything_else` `1` clears **only `category`** and returns to the opener — *a Door A
  caller answering yes starts Door B from a near-empty vector at normal price.* Section menu 1–4,
  **each behind `section_source_frame`**, key 4 = who can apply. `9` → `next_scheme_intro` /
  `no_more_schemes`.
- **Engine addition:** when `Planner.next_action` returns `Stop(reason)`, **call
  `pool.prefetch(corpus.chunks(...))` for the read-back before assembling the LOG line**
  (`AUDIO_PREFETCH_ON_STOP`). This is the one place the tiering touches the call loop, and it is
  fire-and-forget — **a prefetch that has not landed falls back to a blocking `mmap` read**, which
  is still inside the 50 ms Mouth budget on local SSD ([[03-ARCHITECTURE]] §10.1).
- **Done when:** a sim test covers **two searches in one call with every non-category box retained**;
  **a cold-cache read-back (LRU flushed, prefetch disabled) still meets the 50 ms Mouth budget** for
  all 18 chunks.

### Step 18 · Judge script
- **Tickets:** [[tickets/T04]], [[tickets/T16]].
- **Goal:** `python tools/judge.py logs/` prints each call PASS or FAIL with a reason, **from the LOG
  alone.**
- **FAIL when:** no closing line · a hangup not initiated by the system · a scheme spoken that failed
  `speakable` under its snapshot · **a dead-end delivered with `ladder_rung` absent or 0 when
  survivors reached zero** ([[tickets/T04]] branch 3 — *the mechanism is what is being judged*).
- **Done when:** it runs on the sim logs and on Step 12's real logs, and correctly passes P2's
  laddered dead-end and a keypad-only completion.

### Step 19 · Run hardening and the drills
- **Tickets:** [[tickets/T19]].
- **Spec:** `make run` restarts on crash · `/health` reports the snapshot id · startup prints the
  snapshot id and audio count · `make smoke` prints the manual checklist.
- **The four checks, each runnable by anyone:**
  1. `curl https://<dev-domain>/health` **from a phone on mobile data**, not the laptop's Wi-Fi → 200.
  2. `/answer` returns static XML with no I/O — read the latency in the carrier's debug log.
  3. Kill the process **and** the tunnel; restart both with one command; call again **with no carrier
     console edit** → connects, ≤60 s from kill.
  4. `.env` gitignored; grep this branch's history for key prefixes → nothing.
- **The two drills, each run once before D-day** *(rev 26 dropped the third — see below)*:
  - **Wi-Fi dies** → phone hotspot; the tunnel reconnects and the domain does not change. The
    in-flight call is lost; **the next call must work.**
  - **The process dies** → the restart loop costs one call, not a person noticing.
  - ~~**The laptop dies**~~ → **dropped by map rev 26**: *"T19's spare-laptop drill is dropped (no
    second person, no second machine); the restart loop and hotspot drills stay."* Adarsh builds
    solo and the team is on the presentation, so there is no second machine to switch to.
    **Consequence to state plainly rather than leave implicit: a dead laptop is a dead demo.** The
    restart loop and the cold-start check below are the entire recovery story, which is why the
    *"lid open, sleep off"* item under them is not optional.
- **The one that is not deferrable:** plugged in, **lid open**, OS sleep off. **Leave it idle 30
  minutes, then call. That call is the cold-start test and it is the only one that counts.**
- **Also record:** `max_concurrent_measured` from three phones dialling within ten seconds, beside
  Sarvam's concurrent-stream plan limit. **If it is 1, judges call one at a time and that is
  announced before judging, not discovered during it.**

### Step 20 · Acceptance run
- **Before starting:** check each caller's handset can dial the number. Sequential calls only if
  concurrency measured 1. **Freeze: no `git pull`, no snapshot pointer flip during judging.**
- **Run:** 10 calls from people outside the build, **≥3 per language**, unrehearsed, **with at least
  one call deliberately exercising each of [[tickets/T04]]'s seven behaviours** ([[07-TEST-PLAN]]).
- **Judge:** `tools/judge.py` → **≥8 PASS.**
- **Tag `v1`.** Copy 2–3 LOG files to `brain/docs/evidence/` for the presentation team.

---

## v2 backlog — only after `v1` is tagged

Ordered as [[02-PRD]] §7. Nothing here is started before the tag.

## Related

[[02-PRD]] · [[03-ARCHITECTURE]] · [[04-INTERFACES]] · [[05-DATA-CONTRACT]] · [[07-TEST-PLAN]] ·
[[08-TRACEABILITY]] · [[09-DECISION-LOG]] · [[10-RISK-REGISTER]]
