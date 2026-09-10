---
title: Adarsh Agarwala
slug: adarsh-agarwala
type: person
module: architecture
status: reviewed
tags: [lead, architecture, governance]
created: 2026-09-06
updated: 2026-09-06
author: Adarsh Agarwala
last_agent_edit: Antigravity
---

# Adarsh Agarwala

**Role:** Lead Architect & Decision Ratifier  
**System:** [[projects/haqdaar/overview|HAQDAAR v2]]

---

## Focus Areas & Responsibilities

- **System Governance:** Final ratification of all Wayfinder map revisions and ticket closures.
- **Architectural Seams:** Defining the four module boundaries ([[notes/audio/overview|Audio]], [[notes/model/overview|Model]], [[notes/engine/overview|Engine]], [[notes/data/overview|Data]]).
- **Acceptance Bar:** Enforcing the 12 Sep 2026 acceptance bar (inbound Hindi/English/Marathi under 20s read-back).
- **Turn-Loop Integrity:** Validating latency budgets, barge-in policies, and dead-end ladders.

---

## Key Ratified Decisions

- **Destination Named:** The design package complete enough to cut into four owned modules.
- **Door A & Door B Architecture:** [[tickets/T12|T12 matching spoken scheme names]] fails into Door B discovery.
- **LOG Retention:** Caller audio destroyed at hangup; caller phone number hashed; decision trace persisted for audit.
- **Module Fake Implementations:** Every module owner writes a fake implementation returning deterministic fixtures from day one.
- **Corpus Snapshot Pinning:** Calls bind to an immutable corpus snapshot from connect to hangup.

---

## Linked Tickets

- [[tickets/T01]] — Telephony provider selection
- [[tickets/T02]] — myScheme source extraction
- [[tickets/T08]] — Language addition protocol
- [[tickets/T12]] — Spoken scheme name matching (Door A)
- [[tickets/T19]] — Minimal deployment target
