---
title: "Test & Acceptance Plan"
slug: test-plan
type: module-note
module: architecture
status: reviewed
tags: [testing, acceptance, fixture, staging]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/T04.md
---

# Test & Acceptance Plan

Three layers, each with a different job: **the fixture** proves the seams on day one, **the sim**
proves the loop without a phone, **the ten calls** are the bar.

---

## 1 · Day-one tests — one per owner, each runnable with the other three faked

[[tickets/T17]] §4. **Fakes are written by each owner for their own interface, from one shared
fixture file. Nobody writes a fake for a dependency.**

| Owner | The test |
|---|---|
| **Audio** | Play a three-file sequence with a terminal mark; take a DTMF mid-play; return `Digit` carrying `discarded_transcript`; report a `playedStream` timestamp |
| **Model** | Return the expected stamps for the nine utterances; **drop the one whose span is not in its transcript** |
| **Engine** | Run P1 to a stop in ≤4 turns; run **P2 through the full ladder to two nearest schemes labelled as non-matches** |
| **Data** | Load the fixture; answer `mask` / `specificity` / `chunks`; **reject S6, the scheme missing its Marathi `summary`, at the build gate** |

**The four tests together are the integration test.** `make demo-fixture` runs a whole call against
four fakes and prints the LOG — *"map rev 3's stated purpose, interfaces fail on day one instead of
day nine, delivered as one command rather than as an intention."*

**Seam disputes are arbitrated by the fixture test.** Whoever's day-one test still passes is not
holding the bug. No adjudication, no meeting.

> **The ~10 audio stubs carry real durations.** That is what makes the turn clock, the silence
> ladder and the whole loop testable **before a phone line exists** — and it is what made
> [[tickets/T05]]'s lateness survivable.

---

## 2 · The fixture — chosen for what it breaks

*"One persona, three schemes is too thin, and specifically so: three arbitrary schemes cannot
exercise the hard-miss/soft-miss distinction, on which the entire fallback ladder and the honest
dead-end both rest."*

| | Role | Proves |
|---|---|---|
| S1 | exact match on P1 | the happy path and the ≤4 stop |
| S2 | soft-miss on `income_band` | speakable-with-a-label; the miss-set |
| S3 | **hard-miss on `state`** | **never-speakable**; the speaking rule |
| S4 | `ANY` on five of seven boxes | **specificity ordering beats tally** |
| S5 | shares one alias with S1 | **Door A's cap of 2** and the disambiguation turn |
| S6 | missing its Marathi `summary` | **the build gate rejects it** |

| | Role |
|---|---|
| **P1** | narrows to **1 survivor** — the happy path |
| **P2** | narrows to **0** and runs the **full widening ladder** to a labelled nearest-two. **This is a PASS** |
| **P3** | **names a scheme at the opener** — Door A |

**Nine utterances**, one per persona per language. **The fixture and [[tickets/T08]]'s offline test
base are the same artifact — do not build two.** [[tickets/T13]]'s dry-run, [[tickets/T12b]]'s
measurement and the context bake-off all run against the thing that exists on day one.

**Curator: Data's owner.** *Any other curator guarantees the fixture and the real snapshot drift in
shape, and the drift shows up as four passing fakes and one failing integration.*

---

## 3 · Property tests that guard the never-mislead rules

These are not nice-to-haves. Each replaces a human that [[tickets/T08]] removed.

| Property | Where asserted |
|---|---|
| **Bad news before names.** In every non-exact terminal, no scheme name appears in the `say()` sequence before the preamble | `tests/test_terminals.py` — Step 5 |
| **Widened order.** `terminal_widened_preamble → drop_* → results_widened_lead → names` | `tests/test_terminals.py` |
| **A hard-miss scheme is never speakable** — not as match, not as nearest, not with a label | `tests/test_filter.py` — Step 3 |
| **UNKNOWN never narrows**, and counts as *not satisfied* for the speaking rule | `tests/test_filter.py` |
| **The span guard drops an inferred value** — *"main kisan hoon"* must not produce an `income_band` stamp | `tests/test_model.py` — Step 14 |
| **Class precedence** — *"Bihar. Aur ye income band kya hota hai?"* is an **ANSWER**, not a CLARIFY | `tests/test_model.py` |
| **No forbidden phrase in any authored line or `summary`**, in any of the three languages | build gate 4 — Step 9 |
| **`section_source_frame` never precedes a `summary`** | `tests/test_terminals.py` |
| **`Log.write` never raises** — feed it a malformed line and assert `invalid: true` is written | `tests/test_log.py` — Step 6 |
| **`Corpus.load` raises on a broken snapshot, and no runtime read ever raises** | `tests/test_corpus.py` — Step 11 |
| **`Model` never raises** and never returns out-of-set | `tests/test_model.py` |
| **The runtime imports no TTS client** | an import test — Step 10 |
| **The word "twilio" appears only under `audio/telephony/`** | a grep test, every step |
| **SILENCE does not increment the cap; NOISE does** | `tests/test_turn.py` — Step 13 |
| **Keypad-only completes a call from an empty vector inside the 8-turn cap** | `tests/test_call_keypad.py` — Step 16 |

---

## 4 · The ten calls

**Ten calls, from people outside the build, on real handsets, unrehearsed, ≥3 per language.
Judged after the fact from the LOG alone. Pass bar: 8 of 10.**

**A call fails on exactly three conditions and nothing else** ([[tickets/T04]] branch 2):
said something untrue · hung up unprompted · ended before a terminal state.

**Terminal state:** read-back started · honest dead-end delivered · keypad-only fallback delivered.

### Coverage — at least one call deliberately exercises each

[[tickets/T04]] branch 4. Track it as a checklist on the day.

| # | Behaviour | Required response | Call |
|---|---|---|---|
| 1 | Silence — no keypad, no speech | Replay → presence line → polite delivered ending | ☐ |
| 2 | Wrong / out-of-range keypad press | **Named re-ask stating the valid range.** Never silently ignored | ☐ |
| 3 | Keypad mash — several digits fast | **First valid digit in range wins**, remainder discarded. Never an error | ☐ |
| 4 | A scheme outside the corpus | Says plainly it does not have that one, then offers Door B. **Never invents, never silently substitutes** | ☐ |
| 5 | Mixed languages mid-sentence | Handled under the pinned language; a failed parse is a **specific** re-ask | ☐ |
| 6 | Nothing intelligible | Specific re-ask; second failure drops that box to its keypad menu | ☐ |
| 7 | Answering a different question than the one asked | The `box` field carries it — **an ANSWER, not a wrong-slot write** | ☐ |

Plus the two the bar names directly:

| | Check | Call |
|---|---|---|
| **Door A** | A caller who names a scheme hears its **first word within 20 s**, measured as `t_name` from the mark's `playedStream` | ☐ |
| **Door B dead-end** | A caller who matches nothing reaches a **laddered, labelled nearest-two** — `ladder_rung` present and non-zero in the LOG | ☐ |

**Not counted against the demo:** carrier-side drops · a caller who hangs up **after** a terminal
state · a caller who hangs up in the first two seconds without speaking · DTMF a handset never
transmitted.

**A dead-end without a ladder rung is a FAIL**, even though the caller heard something honest.
*The mechanism is what is being judged, not the caller's luck.*

**A keypad-only completion is a PASS.** None of the three fail conditions fire.

**Exactly one survivor is a PASS.** Padding to two is a lie.

---

## 5 · Infrastructure checks — before the ten calls

From [[tickets/T19]]. None of these is a code test; all of them can lose the demo.

| Check | Method | Pass | Result |
|---|---|---|---|
| **Cold start** | Leave the laptop **idle 30 minutes**, then dial | The call connects | ______ |
| Public endpoint | `curl https://<dev-domain>/health` **from a phone on mobile data** | 200 | ______ |
| Answer latency | `/answer` returns static XML, no I/O — read the carrier's debug log | well under a second | ______ |
| Restart | Kill process **and** tunnel; restart with one command; dial **with no console edit** | connects, ≤60 s | ______ |
| Credentials | `.env` gitignored; grep history for key prefixes | nothing found | ______ |
| **Concurrency** | Three phones within ten seconds | `max_concurrent_measured` = ______ | ______ |
| Sarvam plan limit | Dashboard — concurrent streaming sessions | recorded beside the measurement | ______ |
| Tunnel data cap | Usage page on the evening before. ~11 kB/s outbound ≈ 40 MB/talking-hour ≈ 25 h on the free 1 GB | if >half gone, **buy a plan — a card, not a redesign** | ______ |
| `keepCallAlive="false"` | The smoke call | no drop at connect | ______ |
| **Marathi at 8 kHz** | Listen to 3 Marathi + 3 Hindi lines, **and one intro+chip pair for a seam at the 120 ms tail** | usable | ______ |
| **Boot memory is flat in corpus size** | Boot against the demo snapshot, then against one whose pool is padded to ~4.5 GB of junk keys; compare RSS | **both ≈ records + ~35 MB pinned** — RSS does not track pool size | ______ |
| **Cold-cache Mouth budget** | Flush the tier-1 LRU, set `AUDIO_PREFETCH_ON_STOP=false`, play an 18-chunk read-back; time first byte per chunk | **≤ 50 ms** every chunk ([[03-ARCHITECTURE]] §10.1) | ______ |
| **Lazy audio did not weaken `load`** | Delete one `.ulaw`; then corrupt one byte of another | **`Corpus.load` raises in both cases** — error rule 1 intact | ______ |
| **No object store on the demo host** | `AUDIO_TIER2=none`; grep the runtime import graph | **no S3/R2 client imported, no network call on any play path** | ______ |

**Drills — two, each run once:** Wi-Fi dies → hotspot, next call works · process dies → restart
loop absorbs it. *([[tickets/T19]]'s third drill, laptop-dies with a named spare, is **dropped by
map rev 26** — solo builder, one machine. **So a dead laptop is a dead demo**, and the cold-start
row above stops being a formality.)*

**On the day (D-day is 14 Sep, map rev 26):** lid open, plugged in, sleep off · **freeze — no
`git pull`, no snapshot flip during judging** · only Adarsh touches the machine · **if concurrency
measured 1, announce it before judging, not during** — which map rev 27 makes the expected case on
a free tier, not the unlucky one.

---

## 6 · What the LOG must let a judge do, with no audio

Walk one file top to bottom and answer, for every call:

1. Did it reach a terminal state? *(a closing line exists, and its content says which)*
2. Who ended it? *(a system hangup follows a closing line's mark; anything else is abandonment)*
3. Was every spoken scheme `speakable` under that snapshot? *(replay the AND instructions against
   the pinned snapshot — survivors are derived, never stored)*
4. If it dead-ended, **did the ladder run?** *(`ladder_rung`)*
5. Why did questioning stop? *(`stop` — and zero-survivors is named separately from
   zero-information)*
6. Was anything untrue said? *(the terminal's line order, and the forbidden-phrase gate that ran at
   build)*

**If the LOG cannot answer these, the LOG is the bug — not the call.**

## 7 · Related

[[02-PRD]] · [[06-BUILD-PLAN]] · [[05-DATA-CONTRACT]] · [[10-RISK-REGISTER]] ·
[[tickets/T04]] · [[tickets/T13]] · [[tickets/T12b]] · [[tickets/T17]] · [[tickets/T19]]
