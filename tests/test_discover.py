"""Plan 3.1 — discovery pages through the search, keeps one row per slug, and stops safely."""
from __future__ import annotations

from haqdaar.data.pipeline import p0_discover as D


def _item(slug: str, **f) -> dict:
    return {"fields": {"slug": slug, "schemeName": f"Scheme {slug}", "level": "Central",
                       "schemeFor": f.get("for", "Individual"), "schemeCategory": ["Agriculture"],
                       "tags": ["a", "b"], "briefDescription": "  one\n two ",
                       "schemeCloseDate": f.get("close")}}


def test_pages_until_total_with_a_gap_and_no_duplicates(monkeypatch):
    monkeypatch.setattr(D.tunables, "DISCOVER_PAGE_SIZE", 2)
    pages = {0: ["a", "b"], 2: ["b", "c"], 4: ["d"]}
    calls, slept = [], []

    def get_page(start, size):
        calls.append(start)
        return {"page": {"total": 5}, "items": [_item(s) for s in pages[start]]}

    rows = D.discover(get_page=get_page, sleep=slept.append)
    assert calls == [0, 2, 4]
    assert slept == [D.tunables.DISCOVER_PAGE_GAP_S] * 2
    assert [r["slug"] for r in rows] == ["a", "b", "c", "d"]
    assert rows[0]["brief"] == "one two" and rows[0]["tags"] == "a; b"


def test_an_empty_page_stops_instead_of_looping():
    rows = D.discover(get_page=lambda s, n: {"page": {"total": 99}, "items": []}, sleep=lambda s: None)
    assert rows == []


def test_csv_round_trip(tmp_path):
    import csv

    path = tmp_path / "c.csv"
    D.write_candidates([D._row(_item("z", close="2026-12-31")), D._row(_item("a"))], path)
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert [r["slug"] for r in rows] == ["a", "z"] and rows[1]["close_date"] == "2026-12-31"
    assert tuple(rows[0]) == D.COLUMNS
