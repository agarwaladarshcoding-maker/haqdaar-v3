# HAQDAAR v2 — Architecture & Second Brain Vault

This repository contains the architecture, Wayfinder decision maps, and tickets for **HAQDAAR v2** (an inbound Interactive Voice Response system for Indian government scheme discovery).

It is organized into two primary directories, coupled by an automated synchronization engine:

```
/Users/adarshagarwala/Documents/haqdaar-v2/
├── source-docs/                       # Original working markdown files as-is
│   ├── MAP.md ... MAP.-t12amd         # Wayfinder decision maps
│   └── T01.md ... T24.md              # Modular tickets across Audio, Model, Engine, Data
│
├── haqdaar-v2-brain/                  # Dedicated, self-contained Obsidian Vault
│   ├── .obsidian/                     # Pre-configured graph colors, appearance & core plugins
│   ├── RULES.md                       # Vault governance, note schema, linking rules & prohibitions
│   ├── glossary.md                    # Canonical definitions & system tags
│   ├── tickets/                       # Structured ticket notes with wikilinks & metadata
│   ├── maps/                          # Current ratified Wayfinder Map & history
│   ├── notes/                         # Module overviews (audio, model, engine, data)
│   ├── people/                        # Contributor profiles (adarsh-agarwala.md)
│   ├── projects/                      # System overview & acceptance bar
│   ├── inbox/_unsorted/               # Quarantine zone for raw dumps
│   └── changelog/                     # Timestamped ingestion & update audit logs
│
├── sync_vault.py                      # Automated synchronization engine (sync & watch daemon)
└── README.md                          # Quickstart guide
```

---

## Opening the Vault in Obsidian

1. Launch **Obsidian**.
2. Click **Open folder as vault** (or the vault switcher icon in the lower-left corner).
3. Browse to and select:
   ```
   /Users/adarshagarwala/Documents/haqdaar-v2/haqdaar-v2-brain
   ```
4. The vault opens immediately with:
   - **Pre-configured Graph View**: Node colors automatically group tickets, maps, audio, model, engine, and data notes.
   - **Wikilinks & Backlinks**: Bidirectional navigation across all 24 tickets, Wayfinder maps, and module specs.
   - **100% Vault Isolation**: This vault operates completely autonomously and is never connected to any other vault on your system.

---

## Keeping the Vault Updated

Whenever files in `source-docs/` are created or modified, `sync_vault.py` updates the Obsidian vault idempotently and records an entry in `haqdaar-v2-brain/changelog/`.

### Commands

- **One-shot sync:**
  ```bash
  python3 sync_vault.py
  # or
  python3 sync_vault.py --sync
  ```
- **Continuous watch daemon:**
  ```bash
  python3 sync_vault.py --watch
  ```
  *Monitors `source-docs/` in real time and automatically propagates changes as soon as you save any file.*
- **Check sync status:**
  ```bash
  python3 sync_vault.py --status
  ```

---

## Vault Governance & Guidelines

All notes in `haqdaar-v2-brain` adhere strictly to [RULES.md](file:///Users/adarshagarwala/Documents/haqdaar-v2/haqdaar-v2-brain/RULES.md):
- Mandatory YAML frontmatter (`title`, `slug`, `type`, `module`, `status`, `tags`, `blocked_by`, `blocks`).
- Obsidian wikilink syntax (`[[tickets/T01]]`, `[[notes/audio/overview]]`).
- Non-destructive updates and traceable changelog entries.
