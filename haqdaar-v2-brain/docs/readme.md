---
title: "Staged Rebuild — read me first"
slug: staging-readme
type: module-note
module: general
status: reviewed
tags: [staging, index, readme]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
---

# Staged Rebuild — read me first

> ## NOT MERGED
> Everything in `_staging/v2-rebuild/` is a **draft held outside the vault and outside
> `source-docs/`, on Adarsh's instruction.** Nothing here has touched `haqdaar-v2-brain/`.
> No changelog entry has been written, because [[RULES.md]] §7 logs **ingestion**, and nothing has
> been ingested. **Merge only on Adarsh's explicit say-so** — the procedure is in §4 below.

## 0.5 · Third pass, 10 Sep 2026 — two rulings applied

**Ruling 1 — the map's source of truth.** `maps/wayfinder-map.md` (latest by name and by time) is
**the only authoritative map**; `maps/history/` is supporting version history. **The rev 8 / rev 24
gaps are withdrawn as findings**, and the map's internal date inconsistency stays with Adarsh
because the ruling makes the map his to edit. [[01-CONTRADICTIONS]] §5, [[09-DECISION-LOG]] D9.

**Ruling 2 — the audio pool no longer preloads.** [[tickets/T15]]'s *"~200 MB fits in RAM"* is true
of the 100-scheme demo corpus and false at national scale (~2,500 schemes ≈ **4.5 GB**), and
[[tickets/T17]] leaned on that clause when freezing the language. **Fixed by
[[03-ARCHITECTURE]] §10.1 with no frozen signature moving** — `Corpus.audio` and `Corpus.chunks`
return a **`RenderKey`, not bytes**, so storage is entirely internal to `haqdaar/audio/`:

- **tier 0 pinned in RAM** — the 139 fixed lines + ~600 chips, ~35 MB, **bounded by frozen numbers,
  so it is the same size at 2,500 schemes as at 100**;
- **tier 1 local SSD** — `mmap` + byte-bounded LRU for scheme chunks, **the only term that grows**,
  and the one family the Planner announces a full turn ahead;
- **tier 2 S3/R2** — read-through, large deployments only, **off on the demo host**.

**Zero-runtime-TTS is strengthened, not weakened:** lazy means *read later*, never *synthesise
later*. **The 50 ms Mouth budget is unchanged**, and now has a cold-cache test behind it. On Adarsh's
laptop the whole pool is warmed at boot, so **the demo behaves byte-identically to preloading.**
Touches [[03-ARCHITECTURE]] §2/§10/§10.1/§13 · [[04-INTERFACES]] · [[05-DATA-CONTRACT]] §2 ·
[[06-BUILD-PLAN]] Steps 11 & 17 · [[07-TEST-PLAN]] §5 · [[09-DECISION-LOG]] D8 ·
[[10-RISK-REGISTER]] R18–R20.

## 1 · Why the rebuild

> **Corrected 10 Sep, second pass.** The first version of this rebuild was written against a vault
> whose newest map was rev 25, and reported that the *"MAP rev 27"* the docs cite did not exist.
> **Rev 27 is real** — it had been ratified but not yet placed in the vault. It is now
> `maps/wayfinder-map.md`. **Two findings are withdrawn and one reverses; the rest stand.** Every
> document here has been rewritten against rev 27. The adjudication is [[01-CONTRADICTIONS]] §0.

`docs/architecture`, `docs/prd` and `docs/build-plan` disagree with **closed tickets that map
rev 27 never touched**, in ways that change what gets built and whether the
[[tickets/T04|acceptance bar]] can be met. Rev 26 and rev 27 are three entries — who builds, by
when, and which LLM. They settle the provider and the date; they say nothing about the ladder, the
caps, the frozen signatures, the audio pool, class precedence or the gates.

**What rev 27 settles, and this rebuild now follows:**

- **Groq free tier is ratified**, overturning [[tickets/T11]] §5 *"on budget, not on argument"* —
  together with the five mitigations rev 27 attaches to it: **two model moments per call (the
  opener and spoken `state`), exact alias match in code first, a 429 counted as a [[tickets/T18]]
  model failure, no in-turn retry, model id chosen by a 30-utterance bake-off.** The docs carried
  the provider and left four of the five out; they are restored.
- **The bar is 14 Sep**, moved explicitly by rev 26, with **12 Sep held as the internal deadline for
  architecture and build plan** — also rev 26's.

**What still contradicts a live ticket — and one of these can fail the demo outright:**

- **The widening ladder was deferred to v2.** [[tickets/T04]] branch 3 makes it a **pass/fail
  condition**: *"a dead-end is a pass **if and only if** the widening ladder ran first."* T04 expects
  dead-ends in *"two or three of the ten"* calls. Deferring converts those into **certain fails**
  against a bar of eight, and removes a **frozen** signature, `Planner.next_action`'s `Widen`
  branch. **Rev 26 argues against the deferral, not for it:** *"v1 = every feature present in its
  simplest form… v1 cuts features, never safety."*
- **~10 frozen signatures restated with wrong names**, the audio pool nested inside snapshots, the
  **8-turn cap dropped**, the SILENCE-vs-NOISE turn rule absent, class precedence never stated, the
  ASR keypad-only trigger missing, one build gate unlisted. All with citations in
  [[01-CONTRADICTIONS]].

**One thing worth saying plainly:** the vault's own module notes — [[notes/engine/overview]],
[[notes/audio/overview]], [[notes/model/overview]], [[notes/data/overview]] — **are accurate.** They
carry the 8-turn cap, the three terminals, the widening ladder and the ASR failure trigger
correctly. The drift is specific to `docs/`.

Full evidence, with citations: **[[01-CONTRADICTIONS]]**.

## 2 · What is here

| File | Job | Replaces |
|---|---|---|
| [[01-CONTRADICTIONS]] | The audit. Every disagreement, with the ticket that governs | *(new)* |
| [[02-PRD]] | Product scope and the acceptance bar | `docs/prd` |
| [[03-ARCHITECTURE]] | The shape, **with 11 flow diagrams** | `docs/architecture` |
| [[04-INTERFACES]] | The four frozen signature blocks, faithful to [[tickets/T17]] | *(new — was a wrong paraphrase inside `docs/architecture` §5)* |
| [[05-DATA-CONTRACT]] | Record, snapshot, five gates, 46 lines, LOG schema | *(new — was scattered)* |
| [[06-BUILD-PLAN]] | 21 steps, each traced to tickets | `docs/build-plan` |
| [[07-TEST-PLAN]] | Day-one tests, fixture, property tests, the ten calls, the drills | *(new)* |
| [[08-TRACEABILITY]] | Ticket → design → build step, one row per ticket | *(new)* |
| [[09-DECISION-LOG]] | Supersession chains — what overrode what, and the open deviations | *(new)* |
| [[10-RISK-REGISTER]] | Debts (decided, named) vs risks (still open, with owners) | *(new)* |
| [[briefs/audio]] · [[briefs/model]] · [[briefs/engine]] · [[briefs/data]] | **The four module briefs [[tickets/T17]] §5 required and that were never written** | *(new)* |

`docs/review` and `docs/today` are **unchanged and still correct** — `review` already states the
precedence rule this rebuild applies (*"if ARCHITECTURE and T17 disagree, T17 wins"*).

### On the diagrams

11 mermaid diagrams, which Obsidian renders natively: system context · module graph · call
lifecycle · Door A decision tree · box-vector dataflow · stop conditions · terminal tree · the turn
sequence with both clocks · the three failure ladders · the build pipeline · the language path.
They live in [[03-ARCHITECTURE]] §2, §3, §5, §6, §7, §8, §9, §10 and §11.

## 3 · Decisions — all three closed

| # | Question | Status |
|---|---|---|
| **D1** | **Groq free tier, or Gemini paid?** | **Closed — Groq.** Rev 27 records the supersession. No ticket amendment is owed; the amendment *is* the map entry. Steps 8, 14 and 15 are written to it, and to its five mitigations |
| **D2** | **12 Sep or 14 Sep?** | **Closed — 14 Sep**, moved by rev 26. Everything here is rewritten to it. **12 Sep survives as the internal deadline for architecture and build plan**, which is also rev 26's |
| **D3** | **Minimax planner on day one, or a fixed order?** | **Closed — minimax, day one. Ratified by Adarsh, 10 Sep 2026.** *"Every feature present in its simplest form"* means the ratified feature simplified, not replaced; minimax is ~15 lines over a `Filter` that already exists, and it is what makes the LOG reproduce a call exactly. Built in [[06-BUILD-PLAN]] Step 4, stated in [[03-ARCHITECTURE]] §7.3. **The fixed-order stand-in is withdrawn** — it is not a fallback and no deviation is recorded |

**One open item the provider change created**, and it is measurement, not a decision:
[[tickets/T14]]'s **300–500 ms** model-call budget was measured against Gemini Flash-Lite and is now
unverified. Step 14's bake-off must report latency, not just accuracy — if Groq misses the budget,
the 1.2 s second clock moves, not the provider.

**D4–D6 I restored without asking**, because in each case the *deferral* was the deviation, not the
feature — and rev 26's own v1 definition backs each: the widening ladder (a frozen signature and a
pass/fail condition, restored in its **simplest form — fixed rung order**), `*` mid-call re-pin
(costed at zero in every module, no new audio), and both caps (`MAX_TURNS=8` alongside
`MAX_QUESTIONS=6`). Say the word if you disagree with any of them.

## 4 · How to merge, when you say so

[[RULES.md]] is explicit that `source-docs/` is the edit target and the vault is generated —
*"whenever files in `source-docs/` are modified, execute `python3 sync_vault.py --sync`."*
**Editing `haqdaar-v2-brain/docs/` directly would be overwritten by the next sync.**

```bash
cd /Users/adarshagarwala/Documents/haqdaar-v2

# 1 · new docs → source-docs/ (the vault regenerates from here)
cp _staging/v2-rebuild/02-PRD.md            source-docs/PRD.md
cp _staging/v2-rebuild/03-ARCHITECTURE.md   source-docs/ARCHITECTURE.md
cp _staging/v2-rebuild/06-BUILD-PLAN.md     source-docs/BUILD-PLAN.md
cp _staging/v2-rebuild/04-INTERFACES.md     source-docs/INTERFACES.md
cp _staging/v2-rebuild/05-DATA-CONTRACT.md  source-docs/DATA-CONTRACT.md
cp _staging/v2-rebuild/07-TEST-PLAN.md      source-docs/TEST-PLAN.md
cp _staging/v2-rebuild/08-TRACEABILITY.md   source-docs/TRACEABILITY.md
cp _staging/v2-rebuild/09-DECISION-LOG.md   source-docs/DECISION-LOG.md
cp _staging/v2-rebuild/10-RISK-REGISTER.md  source-docs/RISK-REGISTER.md
cp _staging/v2-rebuild/01-CONTRADICTIONS.md source-docs/CONTRADICTIONS.md
mkdir -p source-docs/briefs && cp _staging/v2-rebuild/briefs/*.md source-docs/briefs/

# 2 · flip status: draft → reviewed, in the frontmatter of each

# 3 · sync, then verify
python3 sync_vault.py --sync
python3 sync_vault.py --status

# 4 · changelog — REQUIRED by RULES.md §7, no silent edits
#     haqdaar-v2-brain/changelog/2026-09-10-adarsh-docs-rebuild-rev27.md
#     must record: D8 (lazy tiered audio pool) and D9 (map source-of-truth rule)
```

**One layout note from rev 27.** The map now says *"the brain is the Obsidian vault of this map and
every ticket, **placed at `brain/` inside the git repo**"*, with `brain/docs/` holding ARCHITECTURE,
PRD, BUILD-PLAN, REVIEW and TODAY. That describes the **build repo**, which does not exist yet
([[06-BUILD-PLAN]] Step 0 creates it and vendors the vault in). It does **not** change this
repository's `source-docs/` → `sync_vault.py` → `haqdaar-v2-brain/` flow, which is still where these
files are authored. **Both prompts in the build plan already reference `brain/docs/...`.**

**Before merging, three things [[RULES.md]] requires that this staging area cannot do for you:**

1. **Non-destructive appends (§6).** The old `docs/` are being **replaced**, not appended to. If any
   analysis in them is worth keeping, either append it here under a dated `## Update` heading, or
   mark the old note `status: superseded` with a pointer rather than deleting it.
2. **`sync_vault.py` may not know about new filenames.** The five new docs and the `briefs/` folder
   are files the sync engine has never seen. **Run `--status` and read it** before trusting the sync.
3. **The changelog entry is not optional** — §9 lists *"NEVER skip changelog logging"* among the
   absolute prohibitions.

**Vault isolation holds throughout:** nothing here references or links to any other vault.

## 5 · What I did not do

- **Nothing was written to `haqdaar-v2-brain/` or `source-docs/`.** The only files touched outside
  this folder are `.agent/TASK.md` and `.agent/NOTES.md`, per `AGENTS.md`.
- **No ticket was edited.** Where a ticket and the docs disagreed, I recorded it in
  [[01-CONTRADICTIONS]] and wrote the docs to follow the ticket. Amending a closed ticket is yours.
- **No new decisions.** Where the brain was silent or self-contradictory I surfaced it in
  [[09-DECISION-LOG]] §5 rather than picking. After rev 27 one was left open — §3's D3 — and
  **Adarsh ratified it on 10 Sep 2026: minimax, day one.** Nothing in §3 is open now.
- **No ticket amendment was written for Groq.** None is owed: rev 27 *is* the amendment, and a map
  revision outranks a ticket. [[08-TRACEABILITY]] and [[09-DECISION-LOG]] record the supersession
  chain instead.
- **The 12 retired segments were not re-cut.** [[tickets/T17]] §5 forbids it: *"a re-cut segment is a
  fourth document restating the map at a different resolution."* The four briefs are zoomed from the
  map, as that ticket specified.

---
**Wayfinder Map:** [[maps/wayfinder-map|Latest Map]] · **Brain Index:** [[glossary|Glossary]]
