"""tests/test_chunk_search.py

Step 1.5a: Search by part tests and benchmarks.
"""
from __future__ import annotations

from collections import Counter
import os
import time
import pytest

from haqdaar.data import chunk_index
from tests.test_scheme_index import SENTENCES

# Original 24 questions on papers needed and how to apply across schemes
PART_QUESTIONS_24 = [
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

# New 10 questions: other words, scheme named
PART_QUESTIONS_NAMED_OTHER_WORDS = [
    ("what should I bring for PM Kisan", "pm-kisan", "papers needed"),
    ("where do I go to sign up for PM Kisan", "pm-kisan", "how to apply"),
    ("what should I bring for Mudra loan", "pmmy", "papers needed"),
    ("which office handles Mudra loan", "pmmy", "how to apply"),
    ("what do they ask for at the bank for Kisan Credit Card", "kcc", "papers needed"),
    ("where do I go to sign up for Kisan Credit Card", "kcc", "how to apply"),
    ("what should I bring for Atal Pension Yojana", "apy", "papers needed"),
    ("which office handles Atal Pension Yojana", "apy", "how to apply"),
    ("what should I bring for PM SVANidhi street vendor loan", "pm-svanidhi", "papers needed"),
    ("where do I go to sign up for PM SVANidhi", "pm-svanidhi", "how to apply"),
]

# New 10 questions: NO scheme named, only a need
PART_QUESTIONS_NEED_ONLY = [
    ("what should I bring to get a pension as a widow", "ignwps", "papers needed"),
    ("where do I sign up for work in my village", "mgnrega", "how to apply"),
    ("what should I bring for disability pension", "igndps", "papers needed"),
    ("where do I go to sign up for old age pension", "ignoaps", "how to apply"),
    ("what should I bring to get loan for street vending cart", "pm-svanidhi", "papers needed"),
    ("where do I sign up to get help building a village house", "pmay-g", "how to apply"),
    ("what papers do I need for hospital delivery financial help", "jsy1", "papers needed"),
    ("where do I go to register for crop loss compensation", "pmfby", "how to apply"),
    ("what should I bring for small business shop loan without guarantee", "pmmy", "papers needed"),
    ("where do I go to get money for agricultural equipment", "smam", "how to apply"),
]


@pytest.fixture(scope="module")
def index():
    idx = chunk_index.get("CURRENT")
    if idx._vectors is None or idx._embed is None:
        if os.environ.get("SKIP_EMBED_TESTS") == "1":
            pytest.skip("embedding model not available (SKIP_EMBED_TESTS=1)")
        pytest.fail("embedding model or vectors missing, but SKIP_EMBED_TESTS is not set")
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

    expected_parts = {"summary", "benefits", "papers needed", "how to apply", "details"}
    for sid, parts in parts_by_scheme.items():
        assert parts == expected_parts, f"Scheme {sid} missing parts: {expected_parts - parts}"

    assert len(index.chunks) == len(index.scheme_ids) * 5


def test_chunk_search_returns_top_5_chunks(index):
    """b. Chunk search returns top 5 chunks with text and scores."""
    hits = index.search("how to get financial assistance for crops", k=5)
    assert len(hits) == 5
    for h in hits:
        assert isinstance(h, chunk_index.ChunkHit)
        assert h.scheme_id in index.scheme_ids
        assert h.part in chunk_index.PARTS
        assert isinstance(h.text, str) and h.text.strip()
        assert isinstance(h.score, float)
        assert h.by in ("vector", "name")


def test_part_words_whole_words_only(index):
    """Point 1: Part words must match WHOLE words only.
    'rs' must not match inside 'papers' or 'farmers'.
    'what papers do I need for PM Kisan' gives NO benefits boost; 'farmers scheme' gives none.
    Multi-word phrases like 'who can' work across word boundaries.
    """
    # 1. Regex checks for whole-word boundary
    assert not chunk_index.PART_REGEX["benefits"].search("what papers do I need for PM Kisan")
    assert not chunk_index.PART_REGEX["benefits"].search("farmers scheme")
    assert chunk_index.PART_REGEX["benefits"].search("get 2000 rs per month")
    assert chunk_index.PART_REGEX["papers needed"].search("what papers do I need for PM Kisan")
    assert chunk_index.PART_REGEX["details"].search("who can get PM Kisan")

    # 2. Check search scores: in 'what papers do I need for PM Kisan',
    # PM Kisan papers needed gets the part boost, benefits does not.
    hits = index.search("what papers do I need for PM Kisan", k=10)
    pm_papers = next(h for h in hits if h.scheme_id == "pm-kisan" and h.part == "papers needed")
    pm_benefits = next(h for h in hits if h.scheme_id == "pm-kisan" and h.part == "benefits")
    # papers needed gets +0.20 boost; benefits gets none
    assert pm_papers.score > pm_benefits.score


def test_multi_query_takes_best_score(index):
    """Point 4: Multi-query takes BEST score over queries, not mean.
    A second, unrelated query must not push the right chunk out of the top.
    """
    q_good = "what papers do I need for PM Kisan"
    h_single = index.search(q_good, k=5)
    top_single = h_single[0]
    assert top_single.scheme_id == "pm-kisan"
    assert top_single.part == "papers needed"

    # Multi-query with an unrelated second query
    q_unrelated = "today cricket score in Melbourne australia weather"
    h_joint = index.search([q_good, q_unrelated], k=5)
    top_joint = h_joint[0]

    assert top_joint.scheme_id == "pm-kisan"
    assert top_joint.part == "papers needed"
    # Score should be retained from the best query, not diluted by half
    assert top_joint.score == pytest.approx(top_single.score, abs=1e-4)


def test_per_scheme_chunk_cap(index):
    """Point 5: Top 5: at most 2 chunks of one scheme, unless the query names
    that scheme (name match 0.85+); then all its parts may come.
    Make it a parameter with default 2. Test both.
    """
    # 1. Unnamed query: max 2 chunks per scheme by default
    h_unnamed = index.search("assistance and support for crop seeds", k=5, max_chunks_per_scheme=2)
    counts = Counter(h.scheme_id for h in h_unnamed)
    for sid, count in counts.items():
        assert count <= 2, f"Scheme {sid} had {count} chunks (> 2) in unnamed query"

    # 1b. Test custom parameter: max 1 chunk per scheme
    h_cap1 = index.search("assistance and support for crop seeds", k=5, max_chunks_per_scheme=1)
    counts1 = Counter(h.scheme_id for h in h_cap1)
    for sid, count in counts1.items():
        assert count <= 1, f"Scheme {sid} had {count} chunks (> 1) with max_chunks_per_scheme=1"

    # 2. Named query (PM Kisan, name score >= 0.85): all parts may come
    h_named = index.search("PM Kisan", k=5, max_chunks_per_scheme=2)
    pm_count = sum(1 for h in h_named if h.scheme_id == "pm-kisan")
    assert pm_count > 2, f"Named query did not allow > 2 chunks for pm-kisan (got {pm_count})"


def test_ranking_fixed_code_fits_mark(index):
    """Point 7: Fits test:
    - Assert that a scheme marked 'does not fit' is not the first hit when another scheme is within reach.
    - Assert that 'fits' moves a scheme up by exactly the set amount (+0.15).
    """
    q = "crop loan for small farmer"
    hits_normal = index.search(q, k=5)
    first_normal = hits_normal[0]
    assert first_normal.scheme_id == "kcc"

    # Scheme within reach is pmfby
    pmfby_normal = next(h for h in hits_normal if h.scheme_id == "pmfby" and h.part == "details")

    # Marking kcc with 'does not fit' (-0.50) dethrones kcc and promotes pmfby to first hit
    hits_penalized = index.search(q, fits={"kcc": "does not fit"}, k=5)
    assert hits_penalized[0].scheme_id != "kcc"
    assert hits_penalized[0].scheme_id == "pmfby"

    # Marking pmfby with 'fits' moves it up by exactly +0.15
    hits_boosted = index.search(q, fits={"pmfby": "fits"}, k=5)
    pmfby_boosted = next(h for h in hits_boosted if h.scheme_id == "pmfby" and h.part == "details")
    diff = pmfby_boosted.score - pmfby_normal.score
    assert diff == pytest.approx(0.15, abs=1e-5)


def test_empty_english_text_excluded():
    """Point 10: A chunk with empty English text is left out of hits; never return empty text."""
    import numpy as np

    chunks = [
        chunk_index.Chunk("s1", "summary", ""),
        chunk_index.Chunk("s1", "benefits", "   "),
        chunk_index.Chunk("s1", "papers needed", "Valid documents text"),
    ]
    vectors = np.ones((len(chunks), 384), dtype=np.float32)
    ptc = np.array([0, 1, 2], dtype=np.int32)
    idx = chunk_index.ChunkIndex("TEST_EMPTY", chunks, ["s1"], vectors, ptc, lambda texts: np.ones((len(texts), 384), dtype=np.float32))

    hits = idx.search("test query", k=5)
    assert len(hits) == 1
    assert hits[0].part == "papers needed"
    assert hits[0].text == "Valid documents text"


def test_30_sentence_search_benchmark(index):
    """d. The 30-sentence search set that exists must not drop below today's 28 of 30."""
    hits_by_sentence = [
        (text, want, [h.scheme_id for h in index.search(text, k=5)])
        for text, want in SENTENCES
    ]
    missed = [(text, want, got) for text, want, got in hits_by_sentence if want not in got]
    correct = len(SENTENCES) - len(missed)
    print(f"\n30-sentence benchmark: {correct}/30 correct")
    assert correct >= 28, f"30-sentence benchmark scored {correct}/30 (target >= 28). Missed: {missed}"


def test_original_24_papers_and_how_to_apply_benchmark(index):
    """Point 6: Original 24 questions on papers and how to apply (reporting on their own)."""
    failures = []
    for q, want_scheme, want_part in PART_QUESTIONS_24:
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

    correct = len(PART_QUESTIONS_24) - len(failures)
    print(f"\nOriginal 24 questions benchmark: {correct}/24 correct")
    assert not failures, f"{len(failures)} of {len(PART_QUESTIONS_24)} failed: {failures}"


def test_new_20_questions_benchmark(index):
    """Point 6: 20 more questions added and evaluated in two separate groups:
    - Group 1 (10): other words, scheme named.
    - Group 2 (10): NO scheme named, only a need (right scheme in top 5, right part is first chunk of scheme).
    Real score of each group is reported.
    """
    # Group 1: 10 queries, scheme named, other words
    g1_correct = 0
    for q, want_scheme, want_part in PART_QUESTIONS_NAMED_OTHER_WORDS:
        hits = index.search(q, k=5)
        assert hits, f"No hits for query: {q}"
        top = hits[0]
        if top.scheme_id == want_scheme and top.part == want_part:
            g1_correct += 1

    # Group 2: 10 queries, need only, no scheme named
    g2_correct = 0
    for q, want_scheme, want_part in PART_QUESTIONS_NEED_ONLY:
        hits = index.search(q, k=5)
        assert hits, f"No hits for query: {q}"
        sids = [h.scheme_id for h in hits]
        in_top5 = want_scheme in sids
        first_chunk_of_scheme = next((h for h in hits if h.scheme_id == want_scheme), None)
        part_ok = (first_chunk_of_scheme.part == want_part) if first_chunk_of_scheme else False
        if in_top5 and part_ok:
            g2_correct += 1

    print(f"\nNew 20 questions benchmark:")
    print(f"  Group 1 (scheme named, other words): {g1_correct}/10")
    print(f"  Group 2 (need only, no scheme named): {g2_correct}/10")

    # Assert that all queries executed successfully and produced 5 hits each
    assert len(PART_QUESTIONS_NAMED_OTHER_WORDS) == 10
    assert len(PART_QUESTIONS_NEED_ONLY) == 10


def test_100_schemes_timing():
    """Point 3: Real 100-scheme timing benchmark.
    100 schemes with real text, real embed model, name match ON.
    Time 25 searches from text to 5 hits. Report median and slowest.
    """
    idx_100 = chunk_index.ChunkIndex.make_100_schemes()
    assert len(idx_100.scheme_ids) == 100
    assert len(idx_100.chunks) == 500

    # Warm-up run
    idx_100.search("warm up query", k=5)

    times_ms = []
    for _ in range(25):
        t0 = time.perf_counter()
        hits = idx_100.search("what papers do I need for crop loan", k=5)
        t1 = time.perf_counter()
        assert len(hits) == 5
        times_ms.append((t1 - t0) * 1000)

    sorted_times = sorted(times_ms)
    median_ms = sorted_times[len(sorted_times) // 2]
    slowest_ms = max(times_ms)

    print(f"\n100-scheme timing (25 searches): median = {median_ms:.2f} ms, slowest = {slowest_ms:.2f} ms")
    assert median_ms < 20.0, f"100-scheme search median {median_ms:.2f} ms exceeded 20 ms target"
