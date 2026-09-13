"""tests/test_derive.py

Unit, invariant, and integration tests for Step 8 derivation pipeline (p2_derive.py).
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import ANY, SEVEN_BOXES
from haqdaar.data.pipeline.p2_derive import (
    CATEGORIES,
    GENDERS,
    OCCUPATIONS,
    SOCIAL_CATEGORIES,
    STATES,
    TIER1_FORBIDDEN_EN,
    TIER1_FORBIDDEN_HI,
    TIER1_FORBIDDEN_MR,
    apply_alias_uniqueness_gate,
    check_evidence_quote,
    check_forbidden_words,
    derive_facets_task,
    derive_aliases_task,
    derive_summary_task,
    get_cache_path,
    normalize_text,
    read_from_cache,
    run_pipeline_extract,
    write_to_cache,
)


def test_check_evidence_quote_verbatim():
    eligibility = (
        "All landholding farmers' families, which have cultivable land holding in their names "
        "are eligible to get benefit under the scheme."
    )
    # Exact match
    assert check_evidence_quote("All landholding farmers' families", eligibility) is True
    # Quote with punctuation/quotes stripped
    assert check_evidence_quote('"cultivable land holding"', eligibility) is True
    # Normalized whitespace match
    assert check_evidence_quote("farmers'  families,   which have", eligibility) is True
    # Hallucinated or non-verbatim quote must fail
    assert check_evidence_quote("Urban wage laborers earning under 10000", eligibility) is False
    assert check_evidence_quote("women only", eligibility) is False
    assert check_evidence_quote("", eligibility) is False
    assert check_evidence_quote(None, eligibility) is False


def test_check_forbidden_words():
    # English
    assert check_forbidden_words("You are eligible for Rs 6000", TIER1_FORBIDDEN_EN) == "eligible"
    assert check_forbidden_words("You will get 3 installments", TIER1_FORBIDDEN_EN) == "you will get"
    assert check_forbidden_words("All farmers qualify for this", TIER1_FORBIDDEN_EN) == "qualify"
    assert check_forbidden_words("The scheme provides annual support to farmers.", TIER1_FORBIDDEN_EN) is None

    # Hindi
    assert check_forbidden_words("किसान इस योजना के पात्र हैं", TIER1_FORBIDDEN_HI) == "पात्र"
    assert check_forbidden_words("किसानों को 6000 रुपये मिलेगा", TIER1_FORBIDDEN_HI) == "मिलेगा"
    assert check_forbidden_words("यह योजना किसानों को सहायता देती है।", TIER1_FORBIDDEN_HI) is None

    # Marathi
    assert check_forbidden_words("शेतकरी या योजनेसाठी पात्र आहेत", TIER1_FORBIDDEN_MR) == "पात्र"
    assert check_forbidden_words("शेतकऱ्यांना अनुदान मिळेल", TIER1_FORBIDDEN_MR) == "मिळेल"
    assert check_forbidden_words("ही योजना शेतकऱ्यांना आर्थिक मदत देते.", TIER1_FORBIDDEN_MR) is None


def test_alias_uniqueness_gate():
    schemes = [
        {
            "scheme_id": "S1",
            "aliases_en": ["kisan credit", "farmer loan", "yojana", "kcc"],
            "aliases_hi": ["किसान क्रेडिट", "केसीसी", "योजना", "kcc loan"],
            "aliases_mr": ["किसान क्रेडिट", "शेतकरी कर्ज", "योजना", "kcc loan"],
        },
        {
            "scheme_id": "S2",
            "aliases_en": ["tractor subsidy", "farmer loan", "yojana", "tractor yojana"],
            "aliases_hi": ["ट्रैक्टर सब्सिडी", "योजना", "tractor subsidy"],
            "aliases_mr": ["ट्रॅक्टर सबसिडी", "योजना", "tractor subsidy"],
        },
        {
            "scheme_id": "S3",
            "aliases_en": ["weaver aid", "handloom support", "yojana", "kcc"],
            "aliases_hi": ["बुनकर सहायता", "योजना", "केसीसी"],
            "aliases_mr": ["विणकर सहाय्य", "योजना", "केसीसी"],
        },
    ]

    apply_alias_uniqueness_gate(schemes)

    # "yojana" appears on 3 schemes -> must be dropped from all of them
    for s in schemes:
        assert "yojana" not in s["aliases_en"]
        assert "योजना" not in s["aliases_hi"]
        assert "योजना" not in s["aliases_mr"]

    # "kcc" appears on exactly 2 schemes (S1 and S3) -> kept as Door A disambiguation pair
    assert "kcc" in schemes[0]["aliases_en"]
    assert "kcc" in schemes[2]["aliases_en"]

    # "farmer loan" appears on 2 schemes (S1 and S2) -> kept
    assert "farmer loan" in schemes[0]["aliases_en"]
    assert "farmer loan" in schemes[1]["aliases_en"]

    # Unique aliases kept
    assert "tractor subsidy" in schemes[1]["aliases_en"]
    assert "weaver aid" in schemes[2]["aliases_en"]


def test_cache_roundtrip(tmp_path: Path):
    cache_dir = tmp_path / "extract"
    sha = "test_sha_256_hash_12345"
    task = "facets"
    data = {"facets": {"category": {"value": "agriculture", "quote": "All farmers"}}}

    # Initially empty
    assert read_from_cache(sha, task, cache_dir) is None

    # Write and read back
    write_to_cache(sha, task, data, cache_dir)
    cached = read_from_cache(sha, task, cache_dir)
    assert cached == data

    # Verify atomic tmp file was removed
    cache_file = get_cache_path(sha, task, cache_dir)
    assert cache_file.exists()
    assert not cache_file.with_suffix(".tmp").exists()


def test_evidence_quote_in_code_drops_unverified_facet_to_any(tmp_path: Path):
    """If model suggests a value but the quote is not in eligibility text, value becomes ANY."""
    raw_dir = tmp_path / "raw"
    extract_dir = tmp_path / "extract"
    derived_dir = tmp_path / "derived"
    raw_dir.mkdir(parents=True)

    eligibility = "Only registered small scale artisanal handloom weavers."
    raw_scheme = {
        "myscheme_slug": "test-scheme",
        "source_url": "https://www.myscheme.gov.in/schemes/test-scheme",
        "fetched_on": "2026-09-12",
        "benefits": "Financial assistance of Rs 10000.",
        "eligibility": eligibility,
        "exclusions": "Large factories.",
        "documents": "Weaver ID.",
        "apply": "Apply at district office.",
        "source_sha256": "fake_sha_for_test",
    }
    (raw_dir / "test-scheme.json").write_text(json.dumps(raw_scheme))
    (raw_dir / "test-scheme.html").write_text("<html><title>Test Weaver Scheme</title></html>")

    # Mock client returns:
    # 1. occupation: weaver, with verbatim quote -> should KEEP
    # 2. gender: female, with fabricated quote "women only" -> should DROP to ANY
    # 3. social_category: SC, with no quote -> should DROP to ANY
    mock_client = MagicMock()
    mock_client.call.side_effect = [
        # facets call
        {
            "facets": {
                "category": {"value": "handloom", "quote": "handloom weavers"},
                "state": {"value": "ANY", "quote": ""},
                "gender": {"value": "female", "quote": "women only"},  # Not in text!
                "social_category": {"value": "SC", "quote": ""},        # No quote!
                "age": {"value": "ANY", "quote": ""},
                "income_band": {"value": "ANY", "quote": ""},
                "occupation": {"value": "weaver", "quote": "artisanal handloom weavers"}, # Verbatim!
            },
            "gate_notes": [],
        },
        # aliases call
        {
            "scheme_name_hi": "परीक्षण बुनकर योजना",
            "scheme_name_mr": "चाचणी विणकर योजना",
            "aliases_en": ["test weaver", "handloom grant", "weaver scheme", "test craft"],
            "aliases_hi": ["बुनकर योजना", "हथकरघा अनुदान", "test weaver", "कारीगर मदद"],
            "aliases_mr": ["विणकर योजना", "हातमाग मदत", "test weaver", "कारागीर सहाय्य"],
        },
        # summary call
        {
            "summary_en": "Provides ten thousand rupees financial assistance directly to traditional artisanal handloom weavers.",
            "summary_hi": "पारंपरिक हथकरघा बुनकरों को दस हजार रुपये की सीधी वित्तीय सहायता प्रदान की जाती है।",
            "summary_mr": "पारंपरिक हातमाग विणकरांना दहा हजार रुपयांची थेट आर्थिक मदत दिली जाते.",
        },
    ]

    results = run_pipeline_extract(
        raw_dir=raw_dir,
        extract_cache_dir=extract_dir,
        derived_dir=derived_dir,
        client=mock_client,
    )

    assert len(results) == 1
    res = results[0]

    # Validated facets:
    assert res["occupation"] == "weaver"
    assert res["evidence_quotes"]["occupation"] == "artisanal handloom weavers"
    assert res["category"] == "handloom"
    assert res["evidence_quotes"]["category"] == "handloom weavers"

    # Fabricated / missing quote facets MUST be ANY:
    assert res["gender"] == ANY
    assert res["evidence_quotes"]["gender"] == ""
    assert res["social_category"] == ANY
    assert res["evidence_quotes"]["social_category"] == ""

    # Gate notes should carry the unverified quote
    assert any("Unverified quote for gender=female: women only" in note for note in res["gate_notes"])

    # Provenance fields:
    assert res["facets_source"] == "derived"
    assert res["facets_verified_by"] is None
    assert res["facets_verified_on"] is None


def test_zero_network_calls_on_second_run(tmp_path: Path):
    """Second run must make ZERO calls when cache is populated."""
    raw_dir = tmp_path / "raw"
    extract_dir = tmp_path / "extract"
    derived_dir = tmp_path / "derived"
    raw_dir.mkdir(parents=True)

    raw_scheme = {
        "myscheme_slug": "test-zero-call",
        "source_url": "https://www.myscheme.gov.in/schemes/test-zero-call",
        "fetched_on": "2026-09-12",
        "benefits": "Benefits text.",
        "eligibility": "Farmers cultivating land.",
        "exclusions": "",
        "documents": "Aadhaar.",
        "apply": "Online.",
        "source_sha256": "sha_zero_call_123",
    }
    (raw_dir / "test-zero-call.json").write_text(json.dumps(raw_scheme))

    mock_client = MagicMock()
    mock_client.call.side_effect = [
        # facets
        {
            "facets": {
                "category": {"value": "agriculture", "quote": "Farmers cultivating land"},
                "state": {"value": "ANY", "quote": ""},
                "gender": {"value": "ANY", "quote": ""},
                "social_category": {"value": "ANY", "quote": ""},
                "age": {"value": "ANY", "quote": ""},
                "income_band": {"value": "ANY", "quote": ""},
                "occupation": {"value": "farmer", "quote": "Farmers cultivating land"},
            },
            "gate_notes": [],
        },
        # aliases
        {
            "scheme_name_hi": "शून्य कॉल योजना",
            "scheme_name_mr": "शून्य कॉल योजना",
            "aliases_en": ["zero call scheme", "test zero", "farmer zero", "zero grant"],
            "aliases_hi": ["शून्य कॉल योजना", "किसान सहायता", "test zero", "शून्य मदद"],
            "aliases_mr": ["शून्य कॉल योजना", "शेतकरी मदत", "test zero", "शून्य सहाय्य"],
        },
        # summary
        {
            "summary_en": "Offers direct assistance to practicing farmers cultivating agricultural land.",
            "summary_hi": "कृषि भूमि पर खेती करने वाले किसानों को प्रत्यक्ष सहायता प्रदान की जाती है।",
            "summary_mr": "शेती करणाऱ्या शेतकऱ्यांना थेट मदत दिली जाते.",
        },
    ]

    # First run spends 3 calls
    run_pipeline_extract(raw_dir, extract_dir, derived_dir, client=mock_client)
    assert mock_client.call.call_count == 3

    # Second run with a client that would raise if called
    fail_client = MagicMock()
    fail_client.call.side_effect = AssertionError("Groq API was called on a cached pass!")

    run_pipeline_extract(raw_dir, extract_dir, derived_dir, client=fail_client)
    # Passed with 0 calls to fail_client
    assert fail_client.call.call_count == 0


def _one_scheme_run(tmp_path: Path, facets: dict, aliases: dict, summary_en: str):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    eligibility = "Women farmers of all social categories cultivating land."
    raw_scheme = {
        "myscheme_slug": "review-scheme",
        "source_url": "https://www.myscheme.gov.in/schemes/review-scheme",
        "fetched_on": "2026-09-13",
        "benefits": "Support.",
        "eligibility": eligibility,
        "exclusions": "",
        "documents": "Aadhaar.",
        "apply": "Online.",
        "source_sha256": "sha_review",
    }
    (raw_dir / "review-scheme.json").write_text(json.dumps(raw_scheme))
    base_facets = {b: {"value": "ANY", "quote": ""} for b in SEVEN_BOXES}
    base_facets.update(facets)
    client = MagicMock()
    client.call.side_effect = [
        {"facets": base_facets, "gate_notes": []},
        aliases,
        {"summary_en": summary_en, "summary_hi": "सहायता दी जाती है।", "summary_mr": "मदत दिली जाते."},
    ]
    return run_pipeline_extract(raw_dir, tmp_path / "extract", tmp_path / "derived", client=client)


GOOD_ALIASES = {
    "aliases_en": ["review one", "review two", "review three"],
    "aliases_hi": ["समीक्षा एक", "समीक्षा दो", "review yojana"],
    "aliases_mr": ["समीक्षा एक", "समीक्षा दोन", "review yojana"],
}


def test_all_is_not_a_sentinel_and_level_matches_contract(tmp_path: Path):
    """One sentinel only (ANY). 'ALL' on a hard box is outside the closed set and becomes ANY."""
    assert "ALL" not in GENDERS | SOCIAL_CATEGORIES | STATES
    res = _one_scheme_run(
        tmp_path,
        {"social_category": {"value": "ALL", "quote": "of all social categories"}},
        GOOD_ALIASES,
        "Offers support to farmers.",
    )[0]
    assert res["social_category"] == ANY
    assert res["level"] in ("CENTRAL", "STATE")


def test_alias_floor_fails_loudly_instead_of_padding(tmp_path: Path):
    """A scheme under the alias floor is not padded with made-up slug aliases."""
    thin = dict(GOOD_ALIASES, aliases_mr=["समीक्षा एक", "review yojana"])
    with pytest.raises(ValueError, match="aliases in mr"):
        _one_scheme_run(tmp_path, {}, thin, "Offers support to farmers.")
    assert not (tmp_path / "derived" / "review-scheme.json").exists()


def test_missing_code_mixed_alias_fails_loudly(tmp_path: Path):
    no_mix = dict(GOOD_ALIASES, aliases_hi=["समीक्षा एक", "समीक्षा दो", "समीक्षा तीन"])
    with pytest.raises(ValueError, match="code-mixed alias in hi"):
        _one_scheme_run(tmp_path, {}, no_mix, "Offers support to farmers.")


def test_summary_over_word_cap_fails_in_code(tmp_path: Path):
    too_long = " ".join(["word"] * (tunables.SUMMARY_WORD_TARGET + tunables.SUMMARY_WORD_TOLERANCE + 1))
    with pytest.raises(ValueError, match="word cap"):
        _one_scheme_run(tmp_path, {}, GOOD_ALIASES, too_long)


def test_numeric_range_is_min_max_with_numbers_in_the_quote():
    from haqdaar.data.pipeline.p2_derive import check_numeric_range

    q = "Subscribers aged between 18 and 40 years can join."
    assert check_numeric_range({"min": 18, "max": 40}, q) == {"min": 18, "max": 40}
    assert check_numeric_range({"min": None, "max": 40}, q) == {"min": None, "max": 40}
    # a number not in the quote is invented -> ANY
    assert check_numeric_range({"min": 18, "max": 60}, q) == ANY
    # a bare number has no direction -> ANY
    assert check_numeric_range(18, q) == ANY
    assert check_numeric_range({"min": None, "max": None}, q) == ANY
    assert check_numeric_range({"min": 40, "max": 18}, q) == ANY
    assert check_numeric_range({"min": True, "max": 40}, q) == ANY
    assert check_numeric_range({"min": None, "max": 150000}, "income below Rs 1,50,000") == {"min": None, "max": 150000}


def test_age_range_stored_as_min_max_in_record(tmp_path: Path):
    res = _one_scheme_run(
        tmp_path,
        {"age": {"value": {"min": None, "max": 60}, "quote": "Women farmers"}},  # 60 not in quote
        GOOD_ALIASES,
        "Offers support to farmers.",
    )[0]
    assert res["age"] == ANY
    assert any("Unusable age range" in n for n in res["gate_notes"])
