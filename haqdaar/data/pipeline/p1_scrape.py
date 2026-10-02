"""haqdaar/data/pipeline/p1_scrape.py

myScheme headless scraper (Step 7, 05-DATA-CONTRACT.md §1, T02, T07, T21, T22).
Pipeline build tool — NEVER imported by runtime code.

Hard rules:
  - Source of truth: only myscheme.gov.in. No third-party datasets, ever.
  - Fail loudly: on failed fetch or missing required blocks, raise and write nothing.
  - Cache: never refetch a scheme fetched less than one day ago.
  - Polite delays: delay between fetches; do not hammer the site.
  - Output per scheme:
      data_cache/raw/<slug>.json
      data_cache/raw/<slug>.html
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

import yaml

from haqdaar.contracts import tunables

try:
    from playwright.sync_api import Browser, Page, sync_playwright
except ImportError:
    sync_playwright = None  # type: ignore

logger = logging.getLogger("haqdaar.pipeline.p1_scrape")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
RAW_CACHE_DIR = BASE_DIR / "data_cache" / "raw"
REPORTS_DIR = BASE_DIR / tunables.REPORTS_DIR
DEFAULT_SCHEMES_FILE = Path(__file__).resolve().parent / "schemes.yaml"

MYSCHEME_HOST = "myscheme.gov.in"
MYSCHEME_SCHEME_BASE = f"https://www.{MYSCHEME_HOST}/schemes"

DEFAULT_POLITE_DELAY_SEC = 2.0
BROWSER_TIMEOUT_MS = 30000

# Headings to strip from raw section innerText
SECTION_HEADINGS = {
    "benefits": {"benefits"},
    "eligibility": {"eligibility"},
    "exclusions": {"exclusions"},
    "documents": {"documents required", "documents", "document required"},
    "apply": {"application process", "apply", "how to apply"},
}


def compute_source_sha256(
    benefits: str, eligibility: str, exclusions: str, documents: str, apply: str
) -> str:
    """Compute deterministic SHA-256 digest over the five English blocks."""
    payload = "\n".join([benefits, eligibility, exclusions, documents, apply])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_scheme_slugs(yaml_path: Path = DEFAULT_SCHEMES_FILE) -> List[str]:
    """Load verified scheme slugs from schemes.yaml."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Schemes configuration file not found: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("schemes", [])
    else:
        raise ValueError(f"Unexpected data format in {yaml_path}: expected list or dict")

    slugs: List[str] = []
    for item in items:
        if isinstance(item, str):
            slug = item.strip()
        elif isinstance(item, dict) and "slug" in item:
            slug = str(item["slug"]).strip()
        else:
            continue
        if slug and slug not in slugs:
            slugs.append(slug)

    if not slugs:
        raise ValueError(f"No scheme slugs found in {yaml_path}")

    return slugs


DEFAULT_PRIORITY = 2


def load_scheme_priorities(yaml_path: Path = DEFAULT_SCHEMES_FILE) -> Dict[str, int]:
    """Load per-scheme priority (1-3, default DEFAULT_PRIORITY) from schemes.yaml.

    A scheme with no `priority` key gets DEFAULT_PRIORITY. A `priority` present but not
    an int in 1..3 (bool does not count as an int here) raises, naming the slug.
    """
    if not yaml_path.exists():
        raise FileNotFoundError(f"Schemes configuration file not found: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("schemes", [])
    else:
        raise ValueError(f"Unexpected data format in {yaml_path}: expected list or dict")

    priorities: Dict[str, int] = {}
    for item in items:
        if not (isinstance(item, dict) and "slug" in item):
            continue
        slug = str(item["slug"]).strip()
        if not slug:
            continue
        if "priority" not in item:
            priorities[slug] = DEFAULT_PRIORITY
            continue
        p = item["priority"]
        if isinstance(p, bool) or not isinstance(p, int) or not (1 <= p <= 3):
            raise ValueError(f"{slug}: priority must be an int in 1..3, got {p!r}")
        priorities[slug] = p

    return priorities


def compute_roster_accounting(
    kept_slugs: Sequence[str],
    yaml_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Compute roster accounting: roster_size, quarantined_count, quarantined_slugs, kept_count.

    Guarantees: roster_size - quarantined_count == kept_count.
    """
    yaml_file = yaml_path if yaml_path is not None else DEFAULT_SCHEMES_FILE
    if yaml_file.exists():
        roster = load_scheme_slugs(yaml_file)
    else:
        roster = list(kept_slugs)

    roster_set = set(roster)
    kept_set = set(kept_slugs)
    quarantined = sorted(roster_set - kept_set)

    return {
        "roster_size": len(roster),
        "quarantined_count": len(quarantined),
        "quarantined_slugs": quarantined,
        "kept_count": len(kept_slugs),
    }


def is_cache_valid(slug: str, cache_dir: Path = RAW_CACHE_DIR) -> bool:
    """Check if cache exists and was fetched less than one day ago."""
    json_path = cache_dir / f"{slug}.json"
    html_path = cache_dir / f"{slug}.html"

    if not json_path.exists() or not html_path.exists():
        return False

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate required fields
        required_fields = (
            "myscheme_slug",
            "source_url",
            "fetched_on",
            "benefits",
            "eligibility",
            "exclusions",
            "documents",
            "apply",
            "source_sha256",
        )
        if not all(field in data for field in required_fields):
            return False

        # Host check
        parsed_url = urlparse(data["source_url"])
        if MYSCHEME_HOST not in parsed_url.netloc:
            return False

        # Check required non-empty blocks (exclusions may be empty)
        for req in ("benefits", "eligibility", "documents", "apply"):
            if not str(data[req]).strip():
                return False

        # Verify hash integrity
        expected_sha = compute_source_sha256(
            data["benefits"],
            data["eligibility"],
            data["exclusions"],
            data["documents"],
            data["apply"],
        )
        if data["source_sha256"] != expected_sha:
            return False

        # Check age (< 1 day = 86400 seconds)
        fetched_on_str = data["fetched_on"]
        try:
            fetched_date = datetime.strptime(fetched_on_str, "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            days_old = (today - fetched_date).days
            if days_old < 1:
                return True
        except ValueError:
            pass

        # Fallback to file modification time if date parsing doesn't match
        mtime = json_path.stat().st_mtime
        age_seconds = time.time() - mtime
        return age_seconds < 86400

    except Exception:
        return False


def _extract_section_text(page: Page, section_ids: List[str], block_name: str) -> str:
    """Extract section text from page DOM, stripping header line if present."""
    for sec_id in section_ids:
        loc = page.locator(f"#{sec_id}")
        if loc.count() > 0:
            text = loc.inner_text().strip()
            if not text:
                continue
            lines = text.splitlines()
            if lines and lines[0].strip().lower() in SECTION_HEADINGS.get(block_name, set()):
                text = "\n".join(lines[1:]).strip()
            return text
    return ""


def load_listing(path: Optional[Path] = None) -> Dict[str, Dict[str, str]]:
    """Plan 3.3: level and ministry for each slug, from p0_discover's candidates.csv (the site's
    own search index). Empty if p0 has not run; the caller then leaves them out."""
    import csv

    path = path or Path(__file__).resolve().parents[3] / tunables.DERIVED_DIR / "candidates.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        return {r["slug"]: r for r in csv.DictReader(f)}


def scrape_scheme(
    slug: str,
    page: Page,
    cache_dir: Path = RAW_CACHE_DIR,
    force: bool = False,
) -> Dict[str, Any]:
    """Scrape a single scheme from myscheme.gov.in using Playwright headless.

    Fails loudly and writes nothing if the fetch fails or if required blocks are missing.
    """
    if not force and is_cache_valid(slug, cache_dir):
        json_path = cache_dir / f"{slug}.json"
        logger.info("Using cached data for slug '%s' (<1 day old)", slug)
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    url = f"{MYSCHEME_SCHEME_BASE}/{slug}"
    logger.info("Fetching %s", url)

    response = page.goto(url, wait_until="networkidle", timeout=BROWSER_TIMEOUT_MS)

    # Validate response status and host
    final_url = page.url
    parsed_final = urlparse(final_url)
    if MYSCHEME_HOST not in parsed_final.netloc:
        raise ValueError(
            f"Host validation failed for slug '{slug}': redirected to {final_url} (must be on {MYSCHEME_HOST})"
        )

    if response is not None and response.status >= 400:
        raise RuntimeError(
            f"Failed fetch for slug '{slug}': HTTP {response.status} at {url}. Writing nothing."
        )

    page_content = page.content()
    page_title = page.title()

    # Detect 404 or missing scheme page
    if "404" in final_url or "Page not found" in page_title or "Scheme Not Found" in page_content:
        raise RuntimeError(
            f"Scheme not found on myscheme.gov.in for slug '{slug}' (title: '{page_title}'). Writing nothing."
        )

    # Wait briefly to ensure dynamic elements have fully rendered
    page.wait_for_timeout(1000)

    # Extract the 5 English blocks
    benefits = _extract_section_text(page, ["benefits"], "benefits")
    eligibility = _extract_section_text(page, ["eligibility"], "eligibility")
    exclusions = _extract_section_text(page, ["exclusions"], "exclusions")
    documents = _extract_section_text(page, ["documents-required", "documents"], "documents")
    apply = _extract_section_text(page, ["application-process", "apply", "how-to-apply"], "apply")

    # Required blocks assertion: benefits, eligibility, documents, apply must be non-empty
    # Exclusions may be empty.
    missing_blocks = []
    if not benefits:
        missing_blocks.append("benefits")
    if not eligibility:
        missing_blocks.append("eligibility")
    if not documents:
        missing_blocks.append("documents")
    if not apply:
        missing_blocks.append("apply")

    if missing_blocks:
        raise ValueError(
            f"Failed to extract required non-empty blocks {missing_blocks} for slug '{slug}' from {url}. Writing nothing."
        )

    # Deterministic SHA-256 over the five captured blocks
    source_sha256 = compute_source_sha256(benefits, eligibility, exclusions, documents, apply)
    fetched_on = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    record: Dict[str, Any] = {
        "myscheme_slug": slug,
        "source_url": url,
        "fetched_on": fetched_on,
        "benefits": benefits,
        "eligibility": eligibility,
        "exclusions": exclusions,
        "documents": documents,
        "apply": apply,
        "source_sha256": source_sha256,
    }
    listed = load_listing().get(slug)
    if listed:
        record["level"] = listed["level"].upper()  # "Central" -> "CENTRAL"
        record["department"] = listed["ministry"]

    # Atomic write to cache
    cache_dir.mkdir(parents=True, exist_ok=True)
    json_path = cache_dir / f"{slug}.json"
    html_path = cache_dir / f"{slug}.html"

    temp_json = cache_dir / f"{slug}.json.tmp"
    temp_html = cache_dir / f"{slug}.html.tmp"

    try:
        with open(temp_json, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        with open(temp_html, "w", encoding="utf-8") as f:
            f.write(page_content)

        os.replace(temp_json, json_path)
        os.replace(temp_html, html_path)
    finally:
        if temp_json.exists():
            temp_json.unlink(missing_ok=True)
        if temp_html.exists():
            temp_html.unlink(missing_ok=True)

    logger.info("Successfully scraped and cached slug '%s' (sha256: %s)", slug, source_sha256[:12])
    return record


def scrape_all_slugs(
    slugs: List[str],
    page: Page,
    cache_dir: Path = RAW_CACHE_DIR,
    polite_delay: float = DEFAULT_POLITE_DELAY_SEC,
) -> "tuple[List[Dict[str, Any]], List[Dict[str, str]]]":
    """Scrape every slug against one already-open page (D2: quarantine, don't crash).

    A per-slug failure is set aside with its reason and the loop moves on; scrape_scheme
    writes nothing to cache on error, and any stale raw file from an earlier run is
    deleted, so a quarantined slug leaves no raw file for p2 to re-derive (AUDIT #2).
    """
    results: List[Dict[str, Any]] = []
    quarantined: List[Dict[str, str]] = []

    for idx, slug in enumerate(slugs):
        if idx > 0 and not is_cache_valid(slug, cache_dir):
            logger.info("Polite delay of %.1fs before next fetch...", polite_delay)
            time.sleep(polite_delay)

        try:
            rec = scrape_scheme(slug, page, cache_dir=cache_dir)
            results.append(rec)
        except Exception as e:
            logger.error("Error scraping slug '%s': %s", slug, e)
            quarantined.append({"slug": slug, "reason": str(e)})
            for suffix in (".json", ".html"):
                stale = cache_dir / f"{slug}{suffix}"
                if stale.exists():
                    stale.unlink()
                    logger.warning("Deleted stale raw file for quarantined slug '%s': %s", slug, stale.name)

    return results, quarantined


def finalize_scrape_report(
    results: List[Dict[str, Any]],
    quarantined: List[Dict[str, str]],
    reports_dir: Path = REPORTS_DIR,
    min_required_schemes: int = tunables.MIN_SCHEMES,
) -> Path:
    """Write data_cache/reports/scrape.json and enforce the survival floor (D2).

    The run fails only if fewer than min_required_schemes schemes survive quarantine.
    """
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "scrape.json"
    temp_report = reports_dir / "scrape.json.tmp"
    with open(temp_report, "w", encoding="utf-8") as f:
        json.dump(
            {
                "stage": "scrape",
                "kept": [rec["myscheme_slug"] for rec in results],
                "quarantined": quarantined,
            },
            f, indent=2, ensure_ascii=False,
        )
    os.replace(temp_report, report_path)

    if len(results) < min_required_schemes:
        raise RuntimeError(
            f"Pipeline scrape produced {len(results)} schemes, but at least {min_required_schemes} are required."
        )
    return report_path


def run_pipeline_scrape(
    schemes_file: Path = DEFAULT_SCHEMES_FILE,
    cache_dir: Path = RAW_CACHE_DIR,
    polite_delay: float = DEFAULT_POLITE_DELAY_SEC,
    min_required_schemes: int = tunables.MIN_SCHEMES,
    reports_dir: Path = REPORTS_DIR,
) -> List[Dict[str, Any]]:
    """Main pipeline scrape runner.

    Reads schemes.yaml, executes polite Playwright scraping, caches to data_cache/raw/,
    and verifies that at least min_required_schemes valid schemes are produced.
    """
    if sync_playwright is None:
        raise ImportError(
            "playwright is not installed. Run 'pip install playwright && playwright install chromium'."
        )

    slugs = load_scheme_slugs(schemes_file)
    logger.info("Loaded %d slugs from %s", len(slugs), schemes_file)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel=tunables.SCRAPE_BROWSER_CHANNEL,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        results, quarantined = scrape_all_slugs(slugs, page, cache_dir=cache_dir, polite_delay=polite_delay)

        browser.close()

    if quarantined:
        logger.warning(
            "Quarantined %d of %d schemes: %s",
            len(quarantined), len(slugs),
            ", ".join(f"{q['slug']} ({q['reason']})" for q in quarantined),
        )

    # Write the quarantine report and enforce the survival floor (D2)
    finalize_scrape_report(results, quarantined, reports_dir, min_required_schemes)

    for rec in results:
        parsed = urlparse(rec["source_url"])
        assert MYSCHEME_HOST in parsed.netloc, f"Host not myscheme.gov.in: {rec['source_url']}"
        assert rec["benefits"], f"Empty benefits for {rec['myscheme_slug']}"
        assert rec["eligibility"], f"Empty eligibility for {rec['myscheme_slug']}"
        assert rec["documents"], f"Empty documents for {rec['myscheme_slug']}"
        assert rec["apply"], f"Empty apply for {rec['myscheme_slug']}"
        assert rec["source_sha256"], f"Missing sha256 for {rec['myscheme_slug']}"

    print(f"\nPipeline scrape complete: {len(results)} schemes successfully processed and verified.")
    for rec in results:
        print(
            f"  - {rec['myscheme_slug']}: url={rec['source_url']} | sha256={rec['source_sha256'][:12]}... | "
            f"b={len(rec['benefits'])} e={len(rec['eligibility'])} x={len(rec['exclusions'])} "
            f"d={len(rec['documents'])} a={len(rec['apply'])}"
        )

    return results


if __name__ == "__main__":
    try:
        run_pipeline_scrape()
    except Exception as exc:
        print(f"FATAL: Pipeline scrape failed: {exc}", file=sys.stderr)
        sys.exit(1)
