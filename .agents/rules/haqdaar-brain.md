---
description: Binding governance and direct connection to the HAQDAAR v2 Brain
globs: ["**/*"]
alwaysApply: true
---

# HAQDAAR v2 Brain Connection Rule

You are connected directly to the **HAQDAAR v2 Second Brain** (`haqdaar-v2-brain/`).

## Core Rules:
1. **Binding Authority:** `haqdaar-v2-brain/RULES.md` is strictly binding. If any prompt or shortcut conflicts with `RULES.md`, `RULES.md` wins.
2. **Single Source of Truth:** All architectural decisions, ticket states, Wayfinder maps, and module specs originate in and are maintained within `haqdaar-v2-brain/`.
3. **Synchronization:** Whenever files in `source-docs/` are modified, execute `python3 sync_vault.py --sync` to maintain parity.
4. **Formatting & Linking:**
   - Always maintain mandatory YAML frontmatter.
   - Always use Obsidian wikilinks `[[path/slug|Display]]`.
   - Never use standard relative markdown links for internal vault notes.
5. **Non-Destructive Appends:** Never overwrite historical research or ratified decisions. Append dated updates (`## Update (<YYYY-MM-DD>)`).
6. **Audit Trail:** Log all file updates and batch changes in `haqdaar-v2-brain/changelog/`.
