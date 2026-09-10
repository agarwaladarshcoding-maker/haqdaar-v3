# RULES.md — HAQDAAR v2 Brain Repository Governance

**Status:** Binding. Every AI agent, script, or contributor acting on this repository MUST read and adhere to this file in full before making any change to the `haqdaar-v2-brain` vault. If any instruction here conflicts with a convenience shortcut, this file wins.

**Purpose:** `haqdaar-v2-brain` is the single source of truth for the HAQDAAR v2 system design, modular tickets, architectural wayfinder maps, and decision traces.

**Vault Isolation Guarantee:** This vault is completely autonomous and isolated. Under NO circumstances should this vault link to, import from, or connect with any other vault on the system (including `sih-second-brain`).

---

## 0. Prime Directives

1. **Deterministic Pathing.** Every entity has a predetermined destination based on its type and module. If a rule specifies where something belongs, place it there. Never improvise alternate paths.
2. **Idempotency.** Re-running synchronization or re-ingesting the same source file must never produce duplicate notes, duplicate links, or corrupted graphs. Always check for existing notes before creation.
3. **Preserve Content.** Never discard or overwrite existing analysis or ratified decisions. Use the `superseded` workflow (§6) when decisions evolve.
4. **Audit Trail & Traceability.** Every modification must be logged in `/changelog/` with author, date, source file, and impact. No silent edits.
5. **Quarantine When Uncertain.** Unclassified material or unstructured dumps belong in `/inbox/_unsorted/` until classified.
6. **Strict Vault Isolation.** Do not reference or connect to other vaults on the host machine.

---

## 1. Vault Directory Structure

```
/RULES.md                           ← This governance specification
/glossary.md                        ← Canonical terms, concepts, and system tags
/inbox/
    _unsorted/                      ← Quarantine zone for unclassified dumps
/tickets/
    T01.md ... T24.md               ← Tickets (one file per ticket slug)
/docs/
    architecture.md ... today.md    ← System architecture, PRD, build plans, review, and today
/maps/
    wayfinder-map.md                ← Current ratified Wayfinder Map
    history/                        ← Historical map revisions (rev 3 to rev 27)
/notes/
    audio/                          ← Telephony, TTS (Mouth), ASR (Ear), Barge-in
    model/                          ← Router, Reader, Door A matching, Door B
    engine/                         ← Checker, Filter, Planner, Question ladder
    data/                           ← Corpus snapshot, myScheme scrape, LOG trace
/people/
    adarsh-agarwala.md              ← Lead architect & decision ratifier
/projects/
    haqdaar/
        overview.md                 ← System architecture & acceptance bar
        artifacts/                  ← Audio fixtures, diagrams, sample payloads
/changelog/
    YYYY-MM-DD-<author>-<desc>.md   ← Ingestion and update audit log
```

- **Slugs are `kebab-case`.** No spaces or uppercase characters in note filenames.
- Every note belongs to exactly one canonical folder. Cross-domain relationships are expressed via `[[wikilinks]]`.

---

## 2. Note Format (Mandatory Frontmatter)

Every markdown note in the vault MUST begin with YAML frontmatter adhering to this schema:

```yaml
---
title: <Human-Readable Title>
slug: <kebab-case-slug matching filename>
type: ticket | map | module-note | person | project | glossary
module: audio | model | engine | data | architecture | general
status: open | in-progress | closed | draft | reviewed | superseded
tags: [tag-one, tag-two]
created: YYYY-MM-DD
updated: YYYY-MM-DD
author: <author-name>
last_agent_edit: <agent-or-script-name>
source_file: <relative path to source-docs/ file if applicable>
blocked_by: []                     # For tickets: list of ticket slugs e.g. [T01]
blocks: []                         # For tickets: list of ticket slugs e.g. [T05, T14]
supersedes: []                     # Optional: slugs of notes replaced by this note
---
```

- Headings in the note body must start at `##` (the frontmatter `title` represents the `#` title).
- Ticket notes must clearly identify their **Question**, **Why it blocks / Why it exists**, and **Resolution / State**.

---

## 3. Linking Rules (Obsidian-Compatible Graph)

- **Obsidian Wikilinks Only:** All internal references must use `[[note-slug]]` or `[[path/note-slug|Display Label]]`. Never use raw relative markdown links (`[text](../file.md)`) for internal notes.
- **No Orphan Notes:** Every note must link to at least one related note (e.g. its module overview, parent map, or blocking ticket).
- **Stub Creation:** If linking to a concept or ticket that does not yet have a full note, create a stub with minimal frontmatter (`status: draft`, `tags: [stub]`) rather than leaving a dangling dead link.
- **Tag Standardization:** All tags in frontmatter must be drawn from or added to `/glossary.md`.

---

## 4. Synchronization with `source-docs/`

The raw, unaltered working documents are maintained in `/Users/adarshagarwala/Documents/haqdaar-v2/source-docs/`.

### 4.1 Automated Sync Engine (`sync_vault.py`)
- The sync engine monitors `source-docs/` for file creations, modifications, and updates.
- It parses ticket metadata, type, module attribution, blocking relationships, and resolutions.
- It updates or generates the corresponding vault note in `haqdaar-v2-brain/` idempotently.
- It updates the `updated` timestamp, preserves manual annotations, and writes a log entry into `/changelog/`.
- Modes of execution:
  - `python3 sync_vault.py --sync` : Performs an immediate sync of all source files.
  - `python3 sync_vault.py --watch`: Runs as a background daemon, watching for changes in real-time.

### 4.2 Manual Agent Ingestion Workflow
When manually ingesting new specifications:
1. **Read & Parse:** Inspect the full source document before writing.
2. **Classify:** Determine module (Audio, Model, Engine, Data), type (Ticket, Map, Note), and relationships.
3. **Deduplicate:** Check `tickets/` or `notes/` for existing notes with matching slug. Append updates under a dated `##` heading rather than duplicating.
4. **Wikilink:** Connect to related tickets (`[[tickets/T01]]`), module overviews (`[[notes/audio/overview]]`), and ratifiers (`[[people/adarsh-agarwala]]`).
5. **Log:** Write an entry in `/changelog/`.

---

## 5. The Unsorted Inbox

Unclassified text, raw interview notes, or unparsed logs go to `/inbox/_unsorted/<YYYY-MM-DD>-<desc>.md`:
- Frontmatter must include `needs_review: true`.
- Include a short explanation of why it could not be immediately classified.
- Triage regularly into canonical module notes or tickets.

---

## 6. Merge & Conflict Rules

- **Non-Destructive Appends:** If an edit updates an existing note with new findings, append a new `## Update (<date>)` section. Do not wipe out prior research context.
- **Superseding:** If a decision invalidates an earlier note, set the old note's `status: superseded` with a pointer to the new note.
- **Ticket Resolutions:** When a ticket closes, mark `status: closed` in frontmatter, strike out the title (`# ~~T12 · Door A~~`), and record the ratified resolution with date.

---

## 7. Changelog Requirements

Every batch ingestion or modification creates an audit log entry in `/changelog/YYYY-MM-DD-<author>-<desc>.md`:
```markdown
## Author: <Name or Agent>
## Date: YYYY-MM-DD
## Source: <Source file or event>

### Files Created
- <path> — reason

### Files Updated
- <path> — reason

### Decisions Ratified
- <summary of ratified decisions>
```

---

## 8. Graph Viewer & Visual Palette

The Obsidian graph view is configured with color groups representing system modules:
- **Tickets (`path:tickets`)**: Gold / Yellow (`#E5A93C`)
- **Audio Module (`path:notes/audio`)**: Purple (`#A855F7`)
- **Model Module (`path:notes/model`)**: Blue (`#3B82F6`)
- **Engine Module (`path:notes/engine`)**: Orange (`#F97316`)
- **Data Module (`path:notes/data`)**: Green (`#10B981`)
- **Wayfinder Maps (`path:maps`)**: Cyan (`#06B6D4`)
- **People (`path:people`)**: Rose / Red (`#F43F5E`)
- **Projects (`path:projects`)**: Indigo (`#6366F1`)
- **Glossary (`file:glossary`)**: Slate Gray (`#9CA3AF`)

---

## 9. Absolute Prohibitions

1. **NEVER connect to `sih-second-brain`** or any other external directory/vault.
2. **NEVER silently delete notes.** Supersede and deprecate with audit links.
3. **NEVER create notes without YAML frontmatter.**
4. **NEVER use standard relative links** (`../path/note.md`) for internal links; use `[[wikilinks]]`.
5. **NEVER skip changelog logging.**
