"""haqdaar/data/door_a_sources.py

Build Door A scheme entries from repo pipeline sources (AUDIT #5).

Disk I/O lives here (Data owns I/O), not in haqdaar/engine/door_a.py.
Used by tools/door_a_check.py and tests; the live call path uses
DoorA.from_corpus() (snapshot-scoped, no disk reads).
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from haqdaar.contracts.types import SchemeEntry
from haqdaar.engine.door_a import (
    GENERIC_STOP_WORDS,
    devanagari_to_latin,
    normalize_text,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

_MANUAL_ALIASES_CACHE: dict[str, dict[str, list[str]]] | None = None


def load_manual_aliases(base_dir: Path = BASE_DIR) -> dict[str, dict[str, list[str]]]:
    global _MANUAL_ALIASES_CACHE
    if _MANUAL_ALIASES_CACHE is not None:
        return _MANUAL_ALIASES_CACHE
    path = base_dir / "haqdaar/data/manual_aliases.json"
    if path.exists():
        try:
            _MANUAL_ALIASES_CACHE = json.loads(path.read_text(encoding="utf-8"))
            return _MANUAL_ALIASES_CACHE
        except Exception as exc:
            logger.warning("Failed to load manual aliases from %s: %s", path, exc)
            return {}
    return {}


def quarantined_slugs(base_dir: Path = BASE_DIR) -> set[str]:
    """Slugs quarantined at scrape or derive (p1/p2 reports; missing = none)."""
    quarantined: set[str] = set()
    for report_name in ("scrape.json", "derive.json"):
        try:
            report = json.loads((base_dir / "data_cache/reports" / report_name).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        for q in report.get("quarantined", []):
            if isinstance(q, dict) and q.get("slug"):
                quarantined.add(q["slug"])
    return quarantined


def load_repo_scheme_entries(base_dir: Path = BASE_DIR) -> list[SchemeEntry]:
    """Load the schemes.yaml roster enriched with derived jsonl + candidates.csv.

    Quarantined slugs are skipped: they are unservable (no snapshot row), so
    the matcher must not present them — same as the from_corpus path in prod.
    """
    schemes_yaml_path = base_dir / "haqdaar/data/pipeline/schemes.yaml"
    if not schemes_yaml_path.exists():
        logger.error("Door A: schemes.yaml not found at %s", schemes_yaml_path)
        return []
    quarantined = quarantined_slugs(base_dir)

    schemes_yaml = yaml.safe_load(schemes_yaml_path.read_text(encoding="utf-8")).get("schemes", [])

    derived_map: dict[str, Any] = {}
    derived_path = base_dir / "data_cache/derived/schemes.jsonl"
    if derived_path.exists():
        for line in derived_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                derived_map[item["scheme_id"]] = item

    candidates_map: dict[str, Any] = {}
    cand_path = base_dir / "data_cache/derived/candidates.csv"
    if cand_path.exists():
        with open(cand_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                candidates_map[r["slug"]] = r

    manual_aliases = load_manual_aliases(base_dir)
    entries: list[SchemeEntry] = []
    for sc in schemes_yaml:
        slug = sc["slug"]
        if slug in quarantined:
            logger.info("Door A: skipping quarantined slug '%s'", slug)
            continue
        priority = sc.get("priority", 2)
        d = derived_map.get(slug, {})
        c = candidates_map.get(slug, {})

        aliases: set[str] = set()
        aliases.add(slug)
        aliases.add(slug.replace("-", " "))
        aliases.add(slug.replace("-", ""))

        if c.get("short_title"):
            st = c["short_title"].lower()
            aliases.add(st)
            aliases.add(st.replace("-", " "))
            aliases.add(st.replace("-", ""))
        if c.get("name"):
            aliases.add(c["name"].lower())

        names = {}
        for f in ["scheme_name_en", "scheme_name_hi", "scheme_name_mr"]:
            if d.get(f):
                names[f.replace("scheme_name_", "")] = d[f]
                aliases.add(d[f].lower())

        for f in ["aliases_en", "aliases_hi", "aliases_mr"]:
            for a in d.get(f, []):
                aliases.add(a.lower())

        if slug in manual_aliases:
            for lang_aliases in manual_aliases[slug].values():
                for a in lang_aliases:
                    aliases.add(a.lower())

        # Expand common prefixes: "pradhan mantri" <-> "pm" and Devanagari forms.
        expanded: set[str] = set(aliases)
        for a in aliases:
            if a.startswith("pradhan mantri "):
                expanded.add("pm " + a[15:])
            elif a.startswith("pm "):
                expanded.add("pradhan mantri " + a[3:])
            if a.startswith("प्रधानमंत्री "):
                expanded.add("पीएम " + a[12:])
            elif a.startswith("पंतप्रधान "):
                expanded.add("पीएम " + a[10:])
            elif a.startswith("पीएम "):
                expanded.add("प्रधानमंत्री " + a[5:])
                expanded.add("पंतप्रधान " + a[5:])

        alias_entries: list[str] = []
        distinctive_tokens: set[str] = set()
        for a in expanded:
            norm = normalize_text(a)
            if norm:
                alias_entries.append(norm)
                words = [w for w in norm.split() if w not in GENERIC_STOP_WORDS and len(w) > 1]
                distinctive_tokens.update(words)

                lat = normalize_text(devanagari_to_latin(a))
                if lat and lat != norm:
                    alias_entries.append(lat)
                    lat_words = [w for w in lat.split() if w not in GENERIC_STOP_WORDS and len(w) > 1]
                    distinctive_tokens.update(lat_words)

        entries.append(SchemeEntry(
            slug=slug,
            priority=priority,
            names=names,
            aliases=alias_entries,
            distinctive_tokens=distinctive_tokens,
        ))
    return entries
