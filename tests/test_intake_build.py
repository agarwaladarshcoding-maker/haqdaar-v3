"""N7 builder half: tools/intake_build.py and the p6 age rule for talk-only schemes. Tiny made-up source, index and annot
files under tmp_path (never the real ones). No model, no network."""
import copy
import json

import pytest

from haqdaar.contracts import tunables
from haqdaar.data.corpus import Corpus
from haqdaar.data.pipeline.p6_snapshot import build_range_bands, build_snapshot
from tools import intake_build as ib

SOURCE = """### **Ministry of Tests**

# **Test Scheme**

### Details

The scheme **helps** farmers.​ It runs in  all states, see [the page](https://example.org/a/very/long/path/that/goes/on/and/on/and/on/forever/and/ever).

### Benefits

1\\)	Rs. 3,00,000 loan at low rate
2\\)	Training

### Eligibility

The applicant must be a woman aged 18 to 40 years.

### Exclusions

* Government employees are not eligible.

### Documents Required

* Aadhaar card

### Application Process

Apply at the bank.
"""
LINES = SOURCE.split("\n")


def good_annot(**over):
    a = {
        "slug": "test-scheme", "name_en": "Test Scheme", "name_hi": "टेस्ट योजना",
        "aliases_en": ["test", "test yojana", "ts"], "aliases_hi": ["टेस्ट", "टेस्ट योजना", "टीएस"],
        "category": "business_loans", "category_why": "a loan", "gender": "female", "social_category": "ANY",
        "age": {"min": 15, "max": 29}, "income_max_inr": 300000, "occupation": "ANY", "state": "ANY",
        "home_state": "ANY", "gives": ["loan"], "sub_kind": "ANY", "for_organisation": False,
        "facts": {"govt_employee": {"role": "bars", "quote": "Government employees are not eligible"}},
        "gate_notes": ["Apply at the bank"],
        "evidence": {"gender": "must be a woman", "age": "aged 18 to 40 years", "income_max_inr": "Rs. 3,00,000 loan"},
        "confidence": "high",
    }
    a.update(over)
    return a


def problems(**over):
    return ib.check_annot(good_annot(**over), "test-scheme", LINES)


# --- the quote check ----------------------------------------------------------------------------------------------

def test_a_good_annot_has_no_problem():
    assert problems() == []


def test_quote_matches_through_markdown_zero_width_and_spaces():
    ev = {"gender": "must be a WOMAN", "age": "aged 18 to 40 years", "income_max_inr": "Rs. 3,00,000 loan"}
    assert problems(evidence=ev) == []
    assert problems(facts={"govt_employee": {"role": "bars", "quote": "Government   employees​ are not eligible"}}) == []
    # markdown in the source, a plain quote; the link text and a backslash escape count as plain text
    ev = {**ev, "gender": "the scheme helps farmers. it runs in all states, see the page"}
    assert problems(evidence=ev) == []
    assert problems(evidence={**ev, "age": "1) Rs. 3,00,000 loan"}) == []


def test_a_changed_word_is_refused():
    bad = problems(evidence={"gender": "must be a man", "age": "aged 18 to 40 years", "income_max_inr": "Rs. 3,00,000 loan"})
    assert any("evidence gender: quote not found" in p for p in bad)
    assert any("fact govt_employee: quote not found" in p
               for p in problems(facts={"govt_employee": {"role": "bars", "quote": "Government employees are eligible"}}))


@pytest.mark.parametrize("over, expect", [
    ({"extra": 1}, "unknown key 'extra'"),
    ({"category": "sport"}, "category 'sport' is not in the vocab"),
    ({"gender": "robot"}, "gender: 'robot' is not in the vocab"),
    ({"social_category": ["GEN", "XX"]}, "social_category: 'XX'"),
    ({"occupation": "king"}, "occupation: 'king'"),
    ({"state": "KERALA"}, "state 'KERALA' must be ANY or OTHER"),
    ({"home_state": "ATLANTIS"}, "home_state: 'ATLANTIS'"),
    ({"gives": ["magic"]}, "gives: 'magic'"),
    ({"gives": []}, "gives must be a non-empty list"),
    ({"sub_kind": "Bad Kind"}, "sub_kind 'Bad Kind'"),
    ({"aliases_en": ["a", "b"]}, "aliases_en: 2 usable aliases"),
    ({"aliases_hi": ["", "", "x"]}, "aliases_hi: 1 usable aliases"),
    ({"name_en": " "}, "name_en is empty"),
    ({"age": {"min": 40, "max": 18}}, "age min 40 is above max 18"),
    ({"slug": "other"}, "slug 'other' is not 'test-scheme'"),
    ({"facts": {"moon_card": {"role": "needs", "quote": "Aadhaar card"}}}, "fact 'moon_card' is not in the vocab"),
    ({"facts": {"widow": {"role": "maybe", "quote": "Aadhaar card"}}}, "fact widow: role must be needs or bars"),
    ({"evidence": {"gender": "must be a woman"}}, "evidence age: the value has no quote"),
    ({"evidence": {"gender": "must be a woman", "age": "aged 18 to 40 years", "income_max_inr": "Rs. 3,00,000 loan",
                   "occupation": "farmers"}}, "evidence occupation: there is no value for it"),
    ({"evidence": {"colour": "x", "gender": "must be a woman", "age": "aged 18 to 40 years",
                   "income_max_inr": "Rs. 3,00,000 loan"}}, "evidence key 'colour'"),
])
def test_each_refusal_reason(over, expect):
    assert any(expect in p for p in problems(**over)), problems(**over)


def test_all_problems_are_collected_not_just_the_first():
    got = problems(category="sport", gender="robot", aliases_en=[])
    assert len(got) == 3


def test_missing_key_is_named():
    a = good_annot()
    del a["gives"]
    assert "missing key 'gives'" in ib.check_annot(a, "test-scheme", LINES)


# --- the chunks ---------------------------------------------------------------------------------------------------

def test_chunks_are_cut_from_the_sections_and_cleaned():
    chunks, cuts, falls = ib.make_chunks("Test Scheme", LINES)
    assert list(chunks) == ["name", "summary", "benefit_text", "who_can_apply", "documents", "how_to_apply"]
    assert chunks["name"] == "Test Scheme"
    assert chunks["summary"] == "The scheme helps farmers. It runs in all states, see the page."   # link text kept, long url gone
    assert chunks["benefit_text"] == "1) Rs. 3,00,000 loan at low rate. 2) Training."              # amounts exact
    assert chunks["who_can_apply"] == "The applicant must be a woman aged 18 to 40 years. Exclusions: Government employees are not eligible."
    assert chunks["documents"] == "Aadhaar card." and chunks["how_to_apply"] == "Apply at the bank."
    assert cuts == [] and falls == []
    for text in chunks.values():
        assert not any(c in text for c in "*_#>\\​") and "http" not in text


def test_a_long_chunk_is_cut_at_a_sentence_end_and_rs_is_not_one():
    body = " ".join(f"Rs. {n} is paid in year {n}." for n in range(1, 60))
    lines = ["### Details", body, "### Benefits", "Money."]
    chunks, cuts, _ = ib.make_chunks("N", lines)
    assert len(chunks["summary"]) <= ib.CHUNK_CAP and chunks["summary"].endswith(" paid in year 12.")
    assert cuts and cuts[0].startswith("summary (")


def test_a_scheme_with_no_eligibility_heading_still_gets_a_chunk():
    lines = ["### Details", "It helps.", "### Benefits", "Cash.", "### Frequently Asked Questions",
             "**Q) Who?**", "**A)Any adult can apply**"]
    chunks, _, falls = ib.make_chunks("N", lines)
    assert chunks["who_can_apply"] == "Any adult can apply."
    assert chunks["documents"] == "Any adult can apply."
    assert "who_can_apply from faq" in falls
    none, _, falls2 = ib.make_chunks("N", ["### Details", "It helps."])
    assert none["benefit_text"] == "It helps." and none["documents"] == ib.NOT_LISTED
    assert all(none[c] for c in none)


# --- the row ------------------------------------------------------------------------------------------------------

LIVE_KEYS = ["scheme_id", "myscheme_slug", "source_url", "level", "priority", "state", "department", "fetched_on",
             "source_sha256", "facets_source", "facets_verified_by", "some_future_key", "chunks"]


def test_row_has_every_live_key_and_the_n6_shape():
    row = ib.make_row(good_annot(for_organisation=True), LINES, "Ministry of Tests", LIVE_KEYS, "2026-10-06")
    assert set(LIVE_KEYS) <= set(row) and row["some_future_key"] is None
    assert row["scheme_id"] == row["myscheme_slug"] == "test-scheme" and row["source_url"] == "intake:test-scheme"
    assert row["talk_only"] is True and row["facets_source"] == "intake" and row["income_band"] == "ANY"
    assert row["facts"] == {"govt_employee": "bars"} and row["gives"] == ["loan"] and row["age"] == {"min": 15, "max": 29}
    assert row["gate_notes"] == ["Apply at the bank", "Yearly family income must be up to Rs 3,00,000.",
                                 "This scheme is for organisations, not for a person."]
    assert row["evidence_quotes"]["gender"] == "must be a woman" and row["evidence_quotes"]["income_band"] == "Rs. 3,00,000 loan"
    assert set(row["chunks"]) == {"en"}
    assert ib.make_row(good_annot(age={"min": 18, "max": 120}), LINES, "", [], "d")["age"] == {"min": 18, "max": None}


def test_the_real_live_row_keys_are_all_covered():
    from pathlib import Path
    cur = Path("snapshots/CURRENT")
    if not cur.exists():
        pytest.skip("no live snapshot here")
    live = json.loads((cur.parent / cur.read_text().strip() / "schemes.jsonl").read_text().splitlines()[0])
    keys = [k for k in live if k not in ("bit", "chunk_keys")]
    row = ib.make_row(good_annot(), LINES, "", keys, "2026-10-06")
    assert set(keys) <= set(row)


def test_inr_groups_like_india():
    assert [ib.inr(n) for n in (500, 5000, 300000, 12345678)] == ["500", "5,000", "3,00,000", "1,23,45,678"]


# --- the run: missing, refused, ok --------------------------------------------------------------------------------

def test_check_all_reports_ok_refused_and_missing(tmp_path):
    index = {"schemes": [{"slug": s, "name": s, "start": 1, "end": len(LINES)} for s in ("test-scheme", "bad", "gone")]}
    annot = tmp_path / "annot"
    annot.mkdir()
    (annot / "test-scheme.json").write_text(json.dumps(good_annot()), encoding="utf-8")
    (annot / "bad.json").write_text("{not json", encoding="utf-8")
    (annot / "stray.json").write_text("{}", encoding="utf-8")
    rows, report, cuts, falls, counts = ib.check_all(index, LINES, annot, LIVE_KEYS, "2026-10-06")
    assert counts == {"OK": 1, "REFUSED": 1, "MISSING": 1} and [r["scheme_id"] for r in rows] == ["test-scheme"]
    text = "\n".join(report)
    assert "test-scheme  OK" in text and "gone  MISSING (no annot file)" in text
    assert "bad  REFUSED" in text and "not valid JSON" in text and "stray  NOT IN THE INDEX" in text


# --- p6: the age rule for talk-only rows --------------------------------------------------------------------------

def _row(sid, age, **kw):
    chunks = {lang: {n: f"{sid} {n} {lang}" for n in ("name", "summary", "benefit_text", "who_can_apply", "documents",
                                                      "how_to_apply")} for lang in ("en", "hi", "mr")}
    return {"scheme_id": sid, "category": "farming", "aliases_en": [f"alias {sid}"], "chunks": chunks, "age": age, **kw}


LIVE = [_row("a", {"min": 18, "max": 40}), _row("b", {"min": 41, "max": None}), _row("c", "ANY")]
NEW = _row("t", {"min": 15, "max": 29}, talk_only=True, gives=["loan"])


def test_talk_only_age_does_not_move_the_bands():
    assert build_range_bands(LIVE, "age") == build_range_bands([s for s in LIVE + [NEW] if not s.get("talk_only")], "age")


def test_a_talk_only_scheme_is_found_for_every_band_it_touches(tmp_path):
    snaps, audio = tmp_path / "snaps", tmp_path / "audio"
    bands_without = [b["code"] for b in build_range_bands(LIVE, "age")]
    build_snapshot(copy.deepcopy(LIVE) + [copy.deepcopy(NEW)], snapshot_id="s", snapshots_dir=snaps, audio_dir=audio,
                   render_stubs=True)
    vocab = json.loads((snaps / "s" / "vocab.json").read_text())
    assert vocab["boxes"]["age"]["values"] == bands_without == ["0-17", "18-40", "41+"]
    old = (tunables.SNAPSHOTS_DIR, tunables.AUDIO_DIR)
    tunables.SNAPSHOTS_DIR, tunables.AUDIO_DIR = str(snaps), str(audio)
    try:
        corpus = Corpus.load("s")
    finally:
        tunables.SNAPSHOTS_DIR, tunables.AUDIO_DIR = old
    ids = [corpus.scheme_id(i) for i in range(3 + 1)]
    holders = lambda band: {ids[i] for i in range(len(ids)) if corpus.mask("age", band) >> i & 1}
    assert "t" in holders("0-17") and "t" in holders("18-40") and "t" not in holders("41+")   # 15-29 touches two bands
    assert "a" not in holders("0-17") and "a" in holders("18-40")                          # the old rule for live rows


# --- the isolated snapshot ----------------------------------------------------------------------------------------

def test_the_isolated_snapshot_loads_and_leaves_the_live_one_alone(tmp_path):
    live_snaps, live_audio, out = tmp_path / "live_snaps", tmp_path / "live_audio", tmp_path / "out"
    build_snapshot(copy.deepcopy(LIVE), snapshot_id="live1", snapshots_dir=live_snaps, audio_dir=live_audio, render_stubs=True)
    before = {p.name: p.read_bytes() for p in (live_snaps / "live1").iterdir()}
    index_before = (live_audio / "index.json").read_bytes()
    row = ib.make_row(good_annot(), LINES, "", [], "2026-10-06")
    snap_id = ib.build_isolated([row], live_snaps, live_audio, out)
    assert (out / "snaps" / "CURRENT").read_text().strip() == snap_id
    assert (live_snaps / "CURRENT").read_text().strip() == "live1"
    assert {p.name: p.read_bytes() for p in (live_snaps / "live1").iterdir()} == before
    assert (live_audio / "index.json").read_bytes() == index_before
    got = ib.verify(live_snaps, live_audio, out / "snaps", out / "audio", snap_id, len(LIVE) + 1)
    assert not [g for g in got if g.startswith("FAIL")], got
    assert any("schemes: 4 (expected 4)" in g for g in got)
    assert any("new boxes p6 wrote:" in g and "gives" in g and "f_govt_employee" in g for g in got)
    assert (tunables.SNAPSHOTS_DIR, tunables.AUDIO_DIR) != (str(out / "snaps"), str(out / "audio"))
