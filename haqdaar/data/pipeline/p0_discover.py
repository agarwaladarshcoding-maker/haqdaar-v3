"""haqdaar/data/pipeline/p0_discover.py

Plan 3.1 — find every central scheme on myscheme.gov.in, so 3.2 can choose from the full list.

The search page fetches its results from the site's own endpoint
`/api/apisetu/search/schemes` (found by watching the page load, 30 Sep). It answers plain HTTP
with JSON, 100 schemes a page, so no browser is needed. The filter is the same one the
"Central Schemes" tab sends: level = Central (owner, 30 Sep: central schemes only).

    make pipeline-discover     # writes data_cache/derived/candidates.csv and prints the counts

One caller at a time, 2 s between pages (tunables.DISCOVER_PAGE_GAP_S).
"""
from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from haqdaar.contracts import tunables

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
SEARCH_URL = "https://www.myscheme.gov.in/api/apisetu/search/schemes"
CANDIDATES_FILE = BASE_DIR / Path(tunables.DERIVED_DIR) / "candidates.csv"
COLUMNS = (
    "slug", "name", "short_title", "level", "scheme_for", "categories", "ministry",
    "close_date", "tags", "brief",
)


def _get_page(start: int, size: int) -> dict[str, Any]:
    params = {
        "lang": "en",
        "q": json.dumps([{"identifier": "level", "value": "Central"}]),
        "keyword": "",
        "sort": "",
        "from": start,
        "size": size,
    }
    r = httpx.get(
        SEARCH_URL, params=params, timeout=tunables.DISCOVER_TIMEOUT_S,
        headers={"User-Agent": "Mozilla/5.0 (HAQDAAR scheme research; one request at a time)"},
    )
    r.raise_for_status()
    return r.json()["data"]["hits"]


def _row(item: dict[str, Any]) -> dict[str, str]:
    f = item.get("fields") or {}
    return {
        "slug": f.get("slug") or "",
        "name": (f.get("schemeName") or "").strip(),
        "short_title": (f.get("schemeShortTitle") or "").strip(),
        "level": f.get("level") or "",
        "scheme_for": f.get("schemeFor") or "",
        "categories": "; ".join(f.get("schemeCategory") or []),
        "ministry": f.get("nodalMinistryName") or "",
        "close_date": f.get("schemeCloseDate") or "",
        "tags": "; ".join(f.get("tags") or []),
        "brief": " ".join((f.get("briefDescription") or "").split()),
    }


def discover(
    get_page: Callable[[int, int], dict[str, Any]] = _get_page,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, str]]:
    """Every central scheme, one row each, in the site's order. Slugs are de-duplicated."""
    size = tunables.DISCOVER_PAGE_SIZE
    rows: dict[str, dict[str, str]] = {}
    start, total = 0, None
    while total is None or start < total:
        if start:
            sleep(tunables.DISCOVER_PAGE_GAP_S)
        hits = get_page(start, size)
        total = int(hits["page"]["total"])
        items = hits.get("items") or []
        if not items:
            break  # the site said there was more, but sent nothing: stop, do not loop
        for item in items:
            row = _row(item)
            if row["slug"]:
                rows.setdefault(row["slug"], row)
        start += len(items)
        print(f"  {len(rows)}/{total}", flush=True)
    return list(rows.values())


def write_candidates(rows: list[dict[str, str]], path: Path = CANDIDATES_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for row in sorted(rows, key=lambda r: r["slug"]):
            w.writerow(row)


def print_counts(rows: list[dict[str, str]]) -> None:
    print(f"central schemes: {len(rows)}")
    print(f"  for individuals: {sum(1 for r in rows if r['scheme_for'] == 'Individual')}")
    print(f"  with a close date: {sum(1 for r in rows if r['close_date'])}")
    cats: Counter[str] = Counter()
    for r in rows:
        for c in filter(None, (x.strip() for x in r["categories"].split(";"))):
            cats[c] += 1
    print("  by category:")
    for c, n in cats.most_common():
        print(f"    {n:4d}  {c}")


def main(argv: Optional[list[str]] = None) -> int:
    rows = discover()
    write_candidates(rows)
    print_counts(rows)
    print(f"written: {CANDIDATES_FILE.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
