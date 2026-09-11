---
title: "T16 — amendment: SILENCE is the seventh turn class (11 Sep 2026)"
slug: T16-amendment-silence-class
type: ticket
module: architecture
status: open
tags: ["ticket", "module/architecture", "status/open", "type/ticket"]
created: 2026-09-11
updated: 2026-09-11
author: Adarsh Agarwala
last_agent_edit: sync_vault.py
source_file: source-docs/T16-amendment-silence-class.md
blocked_by: []
blocks: []
---

# T16 — amendment: SILENCE is the seventh turn class (11 Sep 2026)

> Splice this into `tickets/T16.md`. It resolves a contradiction found in the Step 2 code review,
> not a new question. T16 §2 enumerates six classes; [[docs/architecture|`ARCHITECTURE.md`]] assumes SILENCE lines are
> written in two places. One of them had to lose. **T16 loses.**

---

## The contradiction

- **T16 §2** — "`turn_n`, `class` — one of ANSWER / CLARIFY / REPEAT / META / UNCLEAR / NOISE." Six.
- **[[docs/architecture|`ARCHITECTURE.md`]] §Audio** — "Audio never terminates a call. It surfaces `Silence(n)` and Engine
  decides ... **every SILENCE line T16 wants is written** where every other line is written."
- **[[docs/architecture|`ARCHITECTURE.md`]] §Always-on table** — the silence ladder is a logged event and
  "**SILENCE is not a cap turn**".

The architecture was written against a T16 that wants SILENCE lines. T16's own enumeration does not
list one. The implementer wrote seven classes and was following the architecture, not inventing.

## The resolution

**SILENCE is a turn class. The LOG has seven.**

ANSWER · CLARIFY · REPEAT · META · UNCLEAR · NOISE · **SILENCE**

T16 §2's own argument for NOISE decides this. NOISE earns a line despite never reaching the model
because "without the line, turn-count accounting is not auditable from the LOG alone: an 8-turn cap
that fired after three visible turns reads as a bug rather than as five turns of a bad line." The
silence ladder has exactly the same shape: three rungs of wall-clock time and a replayed question,
all of it invisible in the trace unless a line is written. A call that ended at
`closing_farewell` after two visible turns must read as a caller who went quiet, not as a bug.

**It is a non-cap line.** This is what separates it from NOISE and is the whole reason the
distinction is worth a class rather than a flag:

| | counts a turn | field that moves | what ends it |
|---|---|---|---|
| NOISE | **yes** — toward the 8-turn cap and the two-strike box drop | `turn_n` | next turn |
| SILENCE | **no** | `silence_n` (the ladder rung: 1, 2, 3) | rung 3 → `closing_farewell` → hangup |

A SILENCE line carries `silence_n` and **leaves `turn_n` unchanged**. Any keypress resets the ladder
to rung 0, per the always-on table. The turn clock and the LOG's `turn_n` still agree —
[[tickets/T14]]'s requirement is preserved, because SILENCE was never on the turn clock.

## What changes

- **`tickets/T16.md` §2** — the class enumeration reads seven, not six. SILENCE is added.
- **[[docs/architecture|`ARCHITECTURE.md`]]** — unchanged. Both existing lines were already correct.
- **`haqdaar/contracts/log_schema.py`** — unchanged. `TurnClass` and `TURN_CLASSES` already hold
  seven, and `tests/test_step2.py` already asserts all seven round-trip.

**Nothing in the code moves.** The spec was wrong and the spec is what got amended.

## Handed downstream

- **T17** — the frozen line schema is seven classes wide. `log_schema.py` is already conformant.
- **T14** — reinforced, not amended: SILENCE never counted against the 8-turn cap, so the turn
  clock and `turn_n` still agree. T14's cap arithmetic does not change.
- **Step 6** (build plan) — writes the LOG. It inherits seven classes and the `silence_n` field.


---
**Module Overview:** [[notes/architecture/overview|Architecture Module]] · **Wayfinder Map:** [[maps/wayfinder-map|Latest Map]]
