#!/usr/bin/env python3
"""
sync_vault.py — Automated Synchronization Engine for HAQDAAR v2 Brain

Synchronizes unaltered source documents from source-docs/ into the
isolated haqdaar-v2-brain/ Obsidian vault, enforcing RULES.md governance,
generating YAML frontmatter, and producing Obsidian-compatible wikilinks.

Usage:
    python3 sync_vault.py             # Run one-shot sync
    python3 sync_vault.py --sync      # Explicit one-shot sync
    python3 sync_vault.py --watch     # Continuous watch daemon
    python3 sync_vault.py --status    # Check status and diff
"""

import os
import sys
import re
import glob
import time
import json
import hashlib
from datetime import datetime
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "source-docs"
VAULT_DIR = BASE_DIR / "haqdaar-v2-brain"
CACHE_FILE = VAULT_DIR / ".obsidian" / ".sync_cache.json"
CHANGELOG_DIR = VAULT_DIR / "changelog"
TICKETS_DIR = VAULT_DIR / "tickets"
MAPS_DIR = VAULT_DIR / "maps"
MAPS_HIST_DIR = MAPS_DIR / "history"
NOTES_DIR = VAULT_DIR / "notes"
DOCS_DIR = VAULT_DIR / "docs"
BRIEFS_SOURCE_DIR = SOURCE_DIR / "briefs"
BRIEFS_DIR = VAULT_DIR / "briefs"

MODULE_MAP = {
    "audio": "audio",
    "model": "model",
    "engine": "engine",
    "data": "data",
    "cross": "architecture",
    "architecture": "architecture",
}

def compute_hash(filepath):
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def load_cache():
    """Load cached file hashes."""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    """Save file hashes to cache."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

def extract_ticket_metadata(content, filename):
    """Extract metadata from raw ticket content."""
    lines = content.splitlines()
    title = ""
    ticket_id = ""
    is_closed = False
    module = "architecture"
    ticket_type = "ticket"
    blocked_by = []
    blocks = []
    
    slug = filename.replace(".md", "")
    ticket_id = slug
    
    # 1. Title and status from first heading
    for line in lines:
        if line.startswith("# "):
            raw_title = line[2:].strip()
            if raw_title.startswith("~~") and raw_title.endswith("~~"):
                is_closed = True
                raw_title = raw_title[2:-2].strip()
            title = raw_title
            break
            
    if not title:
        title = slug

    # 2. Check for resolution / closure anywhere in text
    if re.search(r"##\s*Resolution", content, re.IGNORECASE):
        is_closed = True
    if re.search(r"\bCLOSED\b", content) or re.search(r"\bClosed \d+", content):
        is_closed = True

    # 3. Metadata line: **Type:** ... · **Module:** ... · **Blocked by:** ... · **Blocks:** ...
    for line in lines[:15]:
        if "**Type:**" in line or "**Module:**" in line:
            if "CLOSED" in line or "Closed" in line or "closed" in line:
                is_closed = True
            
            # Module
            mod_match = re.search(r"\*\*Module:\*\*\s*([A-Za-z0-9_-]+)", line)
            if mod_match:
                raw_mod = mod_match.group(1).lower()
                module = MODULE_MAP.get(raw_mod, raw_mod)
                
            # Type
            type_match = re.search(r"\*\*Type:\*\*\s*`?([A-Za-z0-9_:-]+)`?", line)
            if type_match:
                ticket_type = type_match.group(1)
                
            # Blocked by
            bb_match = re.search(r"\*\*Blocked by:\*\*\s*([^\*·\n]+)", line)
            if bb_match:
                raw_bb = bb_match.group(1)
                for t in re.findall(r"T\d+[a-z]?", raw_bb):
                    if t != ticket_id:
                        blocked_by.append(t)
                        
            # Blocks
            b_match = re.search(r"\*\*Blocks:\*\*\s*([^\*·\n]+)", line)
            if b_match:
                raw_b = b_match.group(1)
                for t in re.findall(r"T\d+[a-z]?", raw_b):
                    if t != ticket_id:
                        blocks.append(t)

    status = "closed" if is_closed else "open"
    return {
        "title": title,
        "ticket_id": ticket_id,
        "slug": ticket_id,
        "status": status,
        "module": module,
        "ticket_type": ticket_type,
        "blocked_by": sorted(list(set(blocked_by))),
        "blocks": sorted(list(set(blocks))),
    }

def convert_to_wikilinks(text):
    """Convert relative links, ticket references, and module terms to Obsidian wikilinks."""
    # Convert [Title](tickets/TXX.md) or [Title](TXX.md) -> [[tickets/TXX|Title]]
    text = re.sub(
        r"\[([^\]]+)\]\((?:tickets\/)?(T\d+[a-z]?(?:-[a-z0-9-]+)?)\.md\)",
        r"[[tickets/\2|\1]]",
        text
    )
    # Convert standard [Title](MAP*.md) -> [[maps/wayfinder-map|Title]]
    text = re.sub(
        r"\[([^\]]+)\]\(MAP[^\)]*\.md\)",
        r"[[maps/wayfinder-map|\1]]",
        text
    )
    # Convert docs [Title](DOC.md) -> [[docs/doc|Title]]
    doc_slugs = [
        "ARCHITECTURE", "BUILD-PLAN", "PRD", "REVIEW", "TODAY",
        "INTERFACES", "DATA-CONTRACT", "TEST-PLAN", "TRACEABILITY",
        "DECISION-LOG", "RISK-REGISTER", "CONTRADICTIONS", "README"
    ]
    for dp in doc_slugs:
        text = re.sub(
            rf"\[([^\]]+)\]\((?:docs\/)?{dp}\.md\)",
            rf"[[docs/{dp.lower()}|\1]]",
            text,
            flags=re.IGNORECASE
        )
        text = re.sub(
            rf"`{dp}\.md`",
            rf"[[docs/{dp.lower()}|`{dp}.md`]]",
            text,
            flags=re.IGNORECASE
        )
    return text

def process_doc(source_path):
    """Process and write a documentation note to haqdaar-v2-brain/docs/."""
    filename = source_path.name
    with open(source_path, "r", encoding="utf-8") as f:
        content = f.read()

    slug = filename.replace(".md", "").lower()
    dest_path = DOCS_DIR / f"{slug}.md"
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    stat = source_path.stat()
    created_date = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d")
    updated_date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")

    footer = "\n\n---\n**Wayfinder Map:** [[maps/wayfinder-map|Latest Map]] · **Brain Index:** [[glossary|Glossary]]\n"

    # If source already has YAML frontmatter, preserve it and update status/date
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body_text = parts[2]
            fm_text = re.sub(r"status:\s*[^\n]+", "status: reviewed", fm_text)
            fm_text = re.sub(r"updated:\s*[^\n]+", f"updated: {updated_date}", fm_text)
            body = convert_to_wikilinks(body_text.strip())
            full_content = f"---{fm_text}---\n\n{body}"
            if "Wayfinder Map:" not in full_content:
                full_content += footer
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(full_content)
            return dest_path

    # Otherwise synthesize frontmatter for docs without it
    lines = [line.strip() for line in content.split("\n")]
    title = filename.replace(".md", "")
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    tags = ["doc", "architecture", slug]

    frontmatter = f"""---
title: "{title}"
slug: {slug}
type: doc
module: architecture
status: reviewed
tags: {json.dumps(tags)}
created: {created_date}
updated: {updated_date}
author: Adarsh Agarwala
last_agent_edit: sync_vault.py
source_file: source-docs/{filename}
---

"""
    body = convert_to_wikilinks(content)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + body + footer)

    return dest_path

def process_brief(source_path):
    """Process and write a module brief note to haqdaar-v2-brain/briefs/."""
    filename = source_path.name
    with open(source_path, "r", encoding="utf-8") as f:
        content = f.read()

    dest_path = BRIEFS_DIR / filename
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)

    stat = source_path.stat()
    updated_date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
    footer = "\n\n---\n**Wayfinder Map:** [[maps/wayfinder-map|Latest Map]] · **Brain Index:** [[glossary|Glossary]]\n"

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body_text = parts[2]
            fm_text = re.sub(r"status:\s*[^\n]+", "status: reviewed", fm_text)
            fm_text = re.sub(r"updated:\s*[^\n]+", f"updated: {updated_date}", fm_text)
            body = convert_to_wikilinks(body_text.strip())
            full_content = f"---{fm_text}---\n\n{body}"
            if "Wayfinder Map:" not in full_content:
                full_content += footer
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(full_content)
            return dest_path

    body = convert_to_wikilinks(content)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(body + footer)
    return dest_path

def process_ticket(source_path):
    """Process and write a ticket note to haqdaar-v2-brain/tickets/."""
    filename = source_path.name
    with open(source_path, "r", encoding="utf-8") as f:
        content = f.read()

    meta = extract_ticket_metadata(content, filename)
    slug = meta["slug"]
    dest_path = TICKETS_DIR / f"{slug}.md"
    TICKETS_DIR.mkdir(parents=True, exist_ok=True)

    # Prepare tags
    tags = ["ticket", f"module/{meta['module']}", f"status/{meta['status']}"]
    if meta["ticket_type"]:
        tags.append(f"type/{meta['ticket_type'].replace(':', '-')}")

    # Format blocked_by and blocks
    blocked_by_str = json.dumps(meta["blocked_by"])
    blocks_str = json.dumps(meta["blocks"])

    # Extract or prepare dates
    stat = source_path.stat()
    created_date = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d")
    updated_date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")

    # Frontmatter
    frontmatter = f"""---
title: "{meta['title']}"
slug: {slug}
type: ticket
module: {meta['module']}
status: {meta['status']}
tags: {json.dumps(tags)}
created: {created_date}
updated: {updated_date}
author: Adarsh Agarwala
last_agent_edit: sync_vault.py
source_file: source-docs/{filename}
blocked_by: {blocked_by_str}
blocks: {blocks_str}
---

"""
    # Convert body text links
    body = convert_to_wikilinks(content)

    # Link to parent module note if not already linked
    module_note = f"[[notes/{meta['module']}/overview|{meta['module'].capitalize()} Module]]"
    footer = f"\n\n---\n**Module Overview:** {module_note} · **Wayfinder Map:** [[maps/wayfinder-map|Latest Map]]\n"

    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + body + footer)

    return dest_path, meta

def extract_map_metadata(content, filename):
    """Extract revision number and date from a map file."""
    rev = 0
    date_str = ""
    m = re.search(r"rev\s*(\d+)", content)
    if m:
        rev = int(m.group(1))
    
    m_date = re.search(r"charted\s*(\d+\s*[A-Za-z]+\s*\d{4})", content)
    if m_date:
        date_str = m_date.group(1)
        
    return rev, date_str

def process_maps():
    """Process all MAP*.md files, placing the latest at maps/wayfinder-map.md and archiving all into maps/history/."""
    map_files = sorted(glob.glob(str(SOURCE_DIR / "MAP*")))
    if not map_files:
        return []

    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    MAPS_HIST_DIR.mkdir(parents=True, exist_ok=True)

    latest_rev = -1
    latest_file = None
    all_maps = []

    for f_str in map_files:
        p = Path(f_str)
        with open(p, "r", encoding="utf-8") as fp:
            content = fp.read()
        rev, date_str = extract_map_metadata(content, p.name)
        all_maps.append((rev, p, content))
        if rev > latest_rev:
            latest_rev = rev
            latest_file = (p, content, rev)

    created_paths = []

    # Write history maps
    for rev, p, content in all_maps:
        slug = f"wayfinder-map-rev{rev}" if rev else p.stem.lower()
        hist_dest = MAPS_HIST_DIR / f"{slug}.md"
        
        stat = p.stat()
        mdate = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        
        body = convert_to_wikilinks(content)
        frontmatter = f"""---
title: "HAQDAAR Wayfinder Map (Rev {rev})"
slug: {slug}
type: map
module: architecture
status: {"reviewed" if p == latest_file[0] else "superseded"}
tags: [map, wayfinder, architecture, rev-{rev}]
created: 2026-08-22
updated: {mdate}
author: Adarsh Agarwala
last_agent_edit: sync_vault.py
source_file: source-docs/{p.name}
---

"""
        with open(hist_dest, "w", encoding="utf-8") as fp:
            fp.write(frontmatter + body)
        created_paths.append(hist_dest)

    # Write latest ratified map
    if latest_file:
        p, content, rev = latest_file
        dest = MAPS_DIR / "wayfinder-map.md"
        body = convert_to_wikilinks(content)
        
        stat = p.stat()
        mdate = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        
        frontmatter = f"""---
title: "HAQDAAR Wayfinder Map (Ratified Rev {rev})"
slug: wayfinder-map
type: map
module: architecture
status: reviewed
tags: [map, wayfinder, architecture, ratified]
created: 2026-08-22
updated: {mdate}
author: Adarsh Agarwala
last_agent_edit: sync_vault.py
source_file: source-docs/{p.name}
---

"""
        with open(dest, "w", encoding="utf-8") as fp:
            fp.write(frontmatter + body)
        created_paths.append(dest)

    return created_paths

def log_changelog(created_files, updated_files, reason="Automated sync from source-docs/"):
    """Write an entry to /changelog/ per RULES.md."""
    if not created_files and not updated_files:
        return None

    CHANGELOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{today}-sync-update-{timestamp}.md"
    log_path = CHANGELOG_DIR / filename

    content = f"""# Changelog: {today} Sync Update

## Agent: sync_vault.py
## Date: {today}
## Source: {reason}

### Files Created ({len(created_files)})
"""
    for f in created_files:
        rel = f.relative_to(VAULT_DIR) if VAULT_DIR in f.parents else f.name
        content += f"- `{rel}` — generated with YAML frontmatter and wikilinks\n"

    content += f"\n### Files Updated ({len(updated_files)})\n"
    for f in updated_files:
        rel = f.relative_to(VAULT_DIR) if VAULT_DIR in f.parents else f.name
        content += f"- `{rel}` — synchronized with latest source-docs changes\n"

    with open(log_path, "w", encoding="utf-8") as fp:
        fp.write(content)

    return log_path

def run_sync():
    """Run synchronization and return stats."""
    cache = load_cache()
    new_cache = {}
    
    created_files = []
    updated_files = []

    source_files = sorted(
        list(SOURCE_DIR.glob("*.md")) +
        list(SOURCE_DIR.glob("MAP*")) +
        (list(BRIEFS_SOURCE_DIR.glob("*.md")) if BRIEFS_SOURCE_DIR.exists() else [])
    )
    # Deduplicate paths
    source_files = list({f.resolve(): f for f in source_files}.values())

    maps_need_update = False

    for s_file in source_files:
        current_hash = compute_hash(s_file)
        rel = str(s_file.relative_to(SOURCE_DIR))
        cached_hash = cache.get(rel, cache.get(s_file.name))
        new_cache[rel] = current_hash

        if s_file.name.startswith("MAP"):
            if cached_hash != current_hash:
                maps_need_update = True
        elif re.match(r"^T\d+", s_file.name):
            if cached_hash is None:
                dest, meta = process_ticket(s_file)
                created_files.append(dest)
            elif cached_hash != current_hash:
                dest, meta = process_ticket(s_file)
                updated_files.append(dest)
        elif s_file.parent == BRIEFS_SOURCE_DIR:
            dest = process_brief(s_file)
            if cached_hash is None or not dest.exists():
                created_files.append(dest)
            elif cached_hash != current_hash:
                updated_files.append(dest)
        else:
            # General documentation file (ARCHITECTURE, BUILD-PLAN, PRD, REVIEW, TODAY, etc.)
            dest = process_doc(s_file)
            if cached_hash is None or not dest.exists():
                created_files.append(dest)
            elif cached_hash != current_hash:
                updated_files.append(dest)

    # Clean up any wrongly-categorized tickets/TODAY.md if it exists
    stray_today = TICKETS_DIR / "TODAY.md"
    if stray_today.exists():
        try:
            stray_today.unlink()
        except Exception:
            pass

    if maps_need_update or not (MAPS_DIR / "wayfinder-map.md").exists():
        map_paths = process_maps()
        for p in map_paths:
            if p.exists() and p not in created_files:
                if not cache:
                    created_files.append(p)
                else:
                    updated_files.append(p)

    save_cache(new_cache)

    if created_files or updated_files:
        log_path = log_changelog(created_files, updated_files)
        print(f"[SYNC SUCCESS] Created: {len(created_files)}, Updated: {len(updated_files)}")
        if log_path:
            print(f"[CHANGELOG] Logged to {log_path.relative_to(BASE_DIR)}")
    else:
        print("[SYNC] Everything up to date. Zero changes detected.")

    return len(created_files), len(updated_files)

def watch_mode():
    """Continuously poll source-docs/ for changes and sync in real-time."""
    print(f"[WATCHER STARTED] Monitoring {SOURCE_DIR} for changes (Ctrl+C to stop)...")
    try:
        while True:
            time.sleep(2)
            cache = load_cache()
            source_files = list(SOURCE_DIR.glob("*.md")) + list(SOURCE_DIR.glob("MAP*")) + (list(BRIEFS_SOURCE_DIR.glob("*.md")) if BRIEFS_SOURCE_DIR.exists() else [])
            changed = False
            for f in source_files:
                rel = str(f.relative_to(SOURCE_DIR))
                if rel not in cache and f.name not in cache:
                    changed = True
                    break
                if compute_hash(f) != cache.get(rel, cache.get(f.name)):
                    changed = True
                    break
            
            if changed:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Detected change in source-docs! Syncing...")
                run_sync()
    except KeyboardInterrupt:
        print("\n[WATCHER STOPPED] Exiting cleanly.")

def show_status():
    """Print status of source documents vs vault notes."""
    cache = load_cache()
    source_files = sorted(
        list(SOURCE_DIR.glob("*.md")) +
        list(SOURCE_DIR.glob("MAP*")) +
        (list(BRIEFS_SOURCE_DIR.glob("*.md")) if BRIEFS_SOURCE_DIR.exists() else [])
    )
    source_files = list({f.resolve(): f for f in source_files}.values())
    
    print(f"=== HAQDAAR v2 Brain Sync Status ===")
    print(f"Source Directory: {SOURCE_DIR}")
    print(f"Vault Directory:  {VAULT_DIR}")
    print(f"Total Source Files: {len(source_files)}")
    print(f"Cached Files:       {len(cache)}")
    
    tickets_count = len([f for f in TICKETS_DIR.glob("*.md") if re.match(r"^T\d+", f.name)]) if TICKETS_DIR.exists() else 0
    maps_count = len(list(MAPS_HIST_DIR.glob("*.md"))) if MAPS_HIST_DIR.exists() else 0
    docs_count = len(list(DOCS_DIR.glob("*.md"))) if DOCS_DIR.exists() else 0
    briefs_count = len(list(BRIEFS_DIR.glob("*.md"))) if BRIEFS_DIR.exists() else 0
    print(f"Vault Tickets:      {tickets_count}")
    print(f"Vault Maps:         {maps_count + 1 if (MAPS_DIR / 'wayfinder-map.md').exists() else 0}")
    print(f"Vault Docs:         {docs_count}")
    print(f"Vault Briefs:       {briefs_count}")
    
    out_of_sync = 0
    for f in source_files:
        h = compute_hash(f)
        rel = str(f.relative_to(SOURCE_DIR))
        if cache.get(rel, cache.get(f.name)) != h:
            print(f"  [DIRTY] {rel}")
            out_of_sync += 1
    if out_of_sync == 0:
        print("All source files are synchronized with the vault.")
    else:
        print(f"Files requiring sync: {out_of_sync}")

def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--watch", "-w"):
            watch_mode()
            return
        elif arg in ("--status", "-s"):
            show_status()
            return
        elif arg in ("--sync", "-y"):
            run_sync()
            return
        else:
            print(f"Unknown argument: {arg}")
            print(__doc__)
            sys.exit(1)
            
    # Default is run_sync
    run_sync()

if __name__ == "__main__":
    main()
