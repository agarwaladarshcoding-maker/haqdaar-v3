"""tests/test_scrape.py

Unit and invariant tests for Step 7 myScheme scraper (p1_scrape.py).
"""
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from haqdaar.data.pipeline.p1_scrape import (
    MYSCHEME_HOST,
    compute_source_sha256,
    is_cache_valid,
    load_scheme_slugs,
    scrape_scheme,
)


def test_compute_source_sha256_deterministic():
    b = "Assistance of Rs 6000"
    e = "Landholding farmer"
    x = "Institutional landholder"
    d = "Aadhaar, Land records"
    a = "Apply online via PM-KISAN portal"

    hash1 = compute_source_sha256(b, e, x, d, a)
    hash2 = compute_source_sha256(b, e, x, d, a)
    assert hash1 == hash2
    assert len(hash1) == 64

    # Drift in any block changes hash
    hash_drifted = compute_source_sha256(b + " modified", e, x, d, a)
    assert hash1 != hash_drifted


def test_load_scheme_slugs(tmp_path: Path):
    yaml_file = tmp_path / "schemes.yaml"
    yaml_file.write_text(
        """
schemes:
  - slug: pm-kisan # comment
  - slug: kcc # comment
  - slug: pm-kisan # duplicate
  - slug: smam
"""
    )
    slugs = load_scheme_slugs(yaml_file)
    assert slugs == ["pm-kisan", "kcc", "smam"]


def test_is_cache_valid_checks_required_blocks_and_hash(tmp_path: Path):
    cache_dir = tmp_path / "raw"
    cache_dir.mkdir(parents=True)
    slug = "test-scheme"

    b = "benefits text"
    e = "eligibility text"
    x = ""  # exclusions can be empty
    d = "documents text"
    a = "apply text"
    sha = compute_source_sha256(b, e, x, d, a)

    record = {
        "myscheme_slug": slug,
        "source_url": f"https://www.{MYSCHEME_HOST}/schemes/{slug}",
        "fetched_on": "2026-09-12",
        "benefits": b,
        "eligibility": e,
        "exclusions": x,
        "documents": d,
        "apply": a,
        "source_sha256": sha,
    }

    # Valid cache
    (cache_dir / f"{slug}.json").write_text(json.dumps(record))
    (cache_dir / f"{slug}.html").write_text("<html>content</html>")
    assert is_cache_valid(slug, cache_dir=cache_dir) is True

    # Bad host must fail
    record["source_url"] = "https://thirdparty.com/schemes/test-scheme"
    (cache_dir / f"{slug}.json").write_text(json.dumps(record))
    assert is_cache_valid(slug, cache_dir=cache_dir) is False

    # Restore host, but tamper hash -> must fail
    record["source_url"] = f"https://www.{MYSCHEME_HOST}/schemes/{slug}"
    record["source_sha256"] = "tampered"
    (cache_dir / f"{slug}.json").write_text(json.dumps(record))
    assert is_cache_valid(slug, cache_dir=cache_dir) is False

    # Empty required block (e.g. eligibility) -> must fail
    record["eligibility"] = "   "
    record["source_sha256"] = compute_source_sha256(b, "   ", x, d, a)
    (cache_dir / f"{slug}.json").write_text(json.dumps(record))
    assert is_cache_valid(slug, cache_dir=cache_dir) is False


def test_scrape_scheme_anti_fabrication_on_error(tmp_path: Path):
    cache_dir = tmp_path / "raw"
    mock_page = MagicMock()
    mock_page.goto.return_value = MagicMock(status=404)
    mock_page.url = f"https://www.{MYSCHEME_HOST}/schemes/invalid-slug"
    mock_page.title.return_value = "Page not found"
    mock_page.content.return_value = "<html>404 Page not found</html>"

    with pytest.raises(RuntimeError, match="Writing nothing"):
        scrape_scheme("invalid-slug", mock_page, cache_dir=cache_dir, force=True)

    # Assert nothing was written to cache dir
    assert not (cache_dir / "invalid-slug.json").exists()
    assert not (cache_dir / "invalid-slug.html").exists()


def test_pipeline_not_imported_by_runtime():
    """Verify runtime contracts and engine modules do not import pipeline scraper."""
    import haqdaar.contracts.tunables
    import haqdaar.contracts.types
    import haqdaar.data.corpus
    import haqdaar.engine.filter
    import haqdaar.engine.planner
    import haqdaar.engine.terminals
    import sys

    assert "haqdaar.data.pipeline.p1_scrape" not in sys.modules or (
        # It's imported in this test, but ensure engine/contracts didn't import it
        not hasattr(haqdaar.engine.filter, "scrape_scheme")
        and not hasattr(haqdaar.engine.planner, "scrape_scheme")
        and not hasattr(haqdaar.engine.terminals, "scrape_scheme")
    )
