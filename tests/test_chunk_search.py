"""tests/test_chunk_search.py

Step 1.5a: Search by part.
Tests:
1. Chunks: each scheme is cut into 5 parts:
   - summary, benefits, papers needed, how to apply, details.
   - 'papers needed' and 'how to apply' added to index.
   - Each chunk retains scheme_id, part, and text.
2. Chunk search function: English query in, top 5 chunks out.
3. Multi-query support: more than one query for one need, results joined.
4. Fixed-code ranking: vector score, name match, caller's fits mark.
5. 30-sentence regression benchmark (must achieve >= 28 of 30).
6. New benchmark of 24 questions on papers and how to apply (first chunk matches scheme & part).
7. 100+ schemes scalability benchmark (< 20 ms).
"""
from __future__ import annotations

import time
import pytest

from haqdaar.data import chunk_index
from tests.test_scheme_index import SENTENCES

# 24 questions on papers needed and how to apply across schemes
PART_QUESTIONS = [
    ("what papers do I need for PM Kisan", "pm-kisan", "papers needed"),
    ("how do I apply for PM Kisan", "pm-kisan", "how to apply"),
    ("how do I apply for a Mudra loan", "pmmy", "how to apply"),
    ("what documents are required for Mudra loan", "pmmy", "papers needed"),
    ("what papers do I need for Kisan Credit Card", "kcc", "papers needed"),
    ("how do I apply for Kisan Credit Card", "kcc", "how to apply"),
    ("what documents do I need for PM Awas Yojana Gramin", "pmay-g", "papers needed"),
    ("how do I apply for rural housing under PMAY-G", "pmay-g", "how to apply"),
    ("what papers are needed for widow pension", "ignwps", "papers needed"),
    ("how do I apply for Indira Gandhi widow pension", "ignwps", "how to apply"),
    ("what documents do I need for disability pension", "igndps", "papers needed"),
    ("how to apply for disability pension", "igndps", "how to apply"),
    ("what papers are required for MGNREGA job card", "mgnrega", "papers needed"),
    ("how do I apply for MGNREGA work", "mgnrega", "how to apply"),
    ("what documents are needed for Atal Pension Yojana", "apy", "papers needed"),
    ("how do I apply for Atal Pension Yojana", "apy", "how to apply"),
    ("what papers do I need for PM SVANidhi street vendor loan", "pm-svanidhi", "papers needed"),
    ("how do I apply for PM SVANidhi loan", "pm-svanidhi", "how to apply"),
    ("what documents are needed for crop insurance under PMFBY", "pmfby", "papers needed"),
    ("how do I apply for PM Fasal Bima crop insurance", "pmfby", "how to apply"),
    ("what papers do I need for Janani Suraksha Yojana", "jsy1", "papers needed"),
    ("how do I apply for Janani Suraksha Yojana hospital delivery", "jsy1", "how to apply"),
    ("what papers are required for SMAM farm machine subsidy", "smam", "papers needed"),
    ("how do I apply for SMAM tractor subsidy", "smam", "how to apply"),
]


@pytest.fixture(scope="module")
def index():
    idx = chunk_index.get("CURRENT")
    if idx._vectors is None:
        pytest.skip("embedding model not available on this machine")
    return idx


def test_chunks_cut_into_five_parts(index):
    """a. Each scheme is cut into 5 parts: summary, benefits, papers needed, how to apply, details."""
    parts_by_scheme: dict[str, set[str]] = {}
    for c in index.chunks:
        assert isinstance(c, chunk_index.Chunk)
        assert c.scheme_id in index.scheme_ids
        assert c.part in chunk_index.PARTS
        assert c.text.strip(), f"Empty text for {c.scheme_id} {c.part}"
        parts_by_scheme.setdefault(c.scheme_id, set()).add(c.part)

    # Every scheme has all 5 parts
    expected_parts = {"summary", "benefits", "papers needed", "how to apply", "details"}
    for sid, parts in parts_by_scheme.items():
        assert parts == expected_parts, f"Scheme {sid} missing parts: {expected_parts - parts}"

    assert len(index.chunks) == len(index.scheme_ids) * 5


def test_chunk_search_returns_top_5_chunks(index):
    """b. Chunk search returns top 5 chunks (not whole cards)."""
    hits = index.search("how to get financial assistance for crops", k=5)
    assert len(hits) == 5
    for h in hits:
        assert isinstance(h, chunk_index.ChunkHit)
        assert h.scheme_id in index.scheme_ids
        assert h.part in chunk_index.PARTS
        assert isinstance(h.text, str) and h.text
        assert isinstance(h.score, float)
        assert h.by in ("vector", "name")


def test_multi_query_search_joins_results(index):
    """b. More than one query for one need is allowed; the results are joined."""
    # Single query searches
    h1 = index.search("PM Kisan", k=5)
    h2 = index.search("papers needed", k=5)

    # Joint query search
    h_joint = index.search(["PM Kisan", "papers needed"], k=5)
    assert len(h_joint) == 5
    top = h_joint[0]
    assert top.scheme_id == "pm-kisan"
    assert top.part == "papers needed"


def test_ranking_fixed_code_fits_mark(index):
    """c. Ranking by fixed code: fits mark passed by caller boosts or penalizes."""
    q = "what papers do I need for PM Kisan"
    hits_normal = index.search(q, k=3)
    assert hits_normal[0].scheme_id == "pm-kisan"

    # Penalizing pm-kisan with 'does not fit' moves other relevant schemes up
    hits_penalized = index.search(q, fits={"pm-kisan": "does not fit"}, k=3)
    assert hits_penalized[0].scheme_id != "pm-kisan" or hits_penalized[0].score < hits_normal[0].score

    # Boosting kcc with 'fits' elevates kcc
    hits_boosted = index.search("crop loan for seeds", fits={"kcc": "fits"}, k=3)
    assert hits_boosted[0].scheme_id == "kcc"


def test_search_never_raises_and_empty_returns_nothing(index):
    assert index.search("") == []
    assert index.search("   ??  ") == []
    assert index.search([]) == []
    assert len(index.search("farmer")) <= 5


def test_30_sentence_search_benchmark(index):
    """d. The 30-sentence search set that exists must not drop below today's 28 of 30."""
    hits_by_sentence = [
        (text, want, [h.scheme_id for h in index.search(text, k=5)])
        for text, want in SENTENCES
    ]
    missed = [(text, want, got) for text, want, got in hits_by_sentence if want not in got]
    correct = len(SENTENCES) - len(missed)
    assert correct >= 28, f"30-sentence benchmark scored {correct}/30 (target >= 28). Missed: {missed}"


def test_new_papers_and_how_to_apply_benchmark(index):
    """d. A new set of at least 20 questions on papers and how to apply,
    each with the scheme and the part that must come first."""
    assert len(PART_QUESTIONS) >= 20

    failures = []
    for q, want_scheme, want_part in PART_QUESTIONS:
        hits = index.search(q, k=1)
        assert hits, f"No hits returned for query: '{q}'"
        top = hits[0]
        if top.scheme_id != want_scheme or top.part != want_part:
            failures.append({
                "query": q,
                "wanted": (want_scheme, want_part),
                "got": (top.scheme_id, top.part),
                "score": top.score,
            })

    assert not failures, f"{len(failures)} of {len(PART_QUESTIONS)} failed: {failures}"


def test_100_schemes_timing():
    """e. It must hold for 100+ schemes: time one search on a made-up index of 100 schemes (aim: under 20 ms)."""
    idx_100 = chunk_index.ChunkIndex.make_synthetic(n_schemes=100)
    assert len(idx_100.chunks) == 500

    # Warm-up run
    idx_100.search("warm up query", k=5)

    # Time single search
    times_ms = []
    for _ in range(25):
        t0 = time.perf_counter()
        hits = idx_100.search("what papers do I need for crop loan", k=5)
        t1 = time.perf_counter()
        assert len(hits) == 5
        times_ms.append((t1 - t0) * 1000)

    median_ms = sorted(times_ms)[len(times_ms) // 2]
    assert median_ms < 20.0, f"Search time {median_ms:.2f} ms exceeded 20 ms target"
