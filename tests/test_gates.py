"""Plan item 1.10 — the five gates (D5).

No test here touches the network or the real data_cache. Each gate gets its own
test, and the ones that matter most are the *false alarms*: a gate that fails
honest text is worse than no gate, because it silently drops schemes the caller
should have heard.
"""

import json

import pytest

from haqdaar.contracts import tunables
from haqdaar.data.pipeline import p5_gates
from haqdaar.data.pipeline.p5_gates import (
    SECTION_FIELDS,
    gate_complete,
    gate_forbidden,
    gate_length,
    gate_numbers,
    gate_scheme,
    gate_script,
    run_gates,
)

HI = {
    "name": "पीएम किसान",
    "summary": "छोटे किसानों को हर साल 6000 रुपये तीन किस्तों में मिलते हैं।",
    "benefit_text": "हर साल 6000 रुपये।",
    "who_can_apply": "जिन किसानों के पास खेती की जमीन है।",
    "documents": "आधार कार्ड और बैंक खाता।",
    "how_to_apply": "नजदीकी सीएससी केंद्र पर जाएं।",
}
EN = {
    "name": "PM Kisan",
    "summary": "Small farmers get 6000 rupees each year in 3 equal installments.",
    "benefit_text": "6000 rupees every year.",
    "who_can_apply": "Farmers who own farm land.",
    "documents": "Aadhaar card and a bank account.",
    "how_to_apply": "Visit the nearest CSC centre.",
}
MR = {
    "name": "पीएम किसान",
    "summary": "लहान शेतकऱ्यांना दरवर्षी 6000 रुपये तीन हप्त्यांत मिळतात.",
    "benefit_text": "दरवर्षी 6000 रुपये.",
    "who_can_apply": "ज्या शेतकऱ्यांकडे शेतजमीन आहे.",
    "documents": "आधार कार्ड आणि बँक खाते.",
    "how_to_apply": "जवळच्या सीएससी केंद्रावर जा.",
}


def _scheme(scheme_id="pm-kisan", en=None, hi=None, mr=None):
    return {
        "scheme_id": scheme_id,
        "chunks": {
            "en": dict(en or EN),
            "hi": dict(hi or HI),
            "mr": dict(mr or MR),
        },
    }


def _write_inputs(tmp_path, records):
    derived = tmp_path / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    with (derived / "schemes.jsonl").open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return derived


# --- G1 · numbers ------------------------------------------------------------


def test_g1_passes_when_the_amounts_survive():
    """6000 is in both, so nothing is wrong."""
    assert gate_numbers("6000 rupees a year", "हर साल 6000 रुपये") == []


def test_g1_allows_a_small_number_to_become_a_word():
    """Sarvam writes "3 installments" as "तीन" — seen on the real pm-kisan run.

    If this fails, every scheme trips G1 and no Hindi is ever spoken.
    """
    assert gate_numbers("in 3 equal installments", "तीन किस्तों में") == []


def test_g1_catches_a_missing_amount():
    """An amount is never spelled out, so a lost 6000 is a real fault."""
    reasons = gate_numbers("6000 rupees a year", "हर साल रुपये")
    assert len(reasons) == 1 and "6000" in reasons[0]


def test_g1_catches_an_invented_number():
    """A number nobody wrote is a number nobody can trust, however small."""
    reasons = gate_numbers("rupees each year", "हर साल 9 रुपये")
    assert len(reasons) == 1 and "not in the English" in reasons[0]


def test_g1_reads_an_indian_comma_amount_as_one_number():
    """"5,00,000" is one number, not 5 then 00 then 000."""
    assert p5_gates._numbers("up to 5,00,000") == ["500000"]


# --- G2 · forbidden phrases --------------------------------------------------


def test_g2_catches_a_second_person_promise():
    """The system must never tell a caller they are eligible."""
    reasons = gate_forbidden("आप पात्र हैं", "hi")
    assert len(reasons) == 1 and "forbidden phrase" in reasons[0]


def test_g2_does_not_trip_on_the_honest_word_patrata():
    """D5 names this case: "पात्रता" means "eligibility" and is normal, honest text."""
    assert gate_forbidden("पात्रता की शर्तें नीचे दी गई हैं।", "hi") == []


def test_g2_runs_on_the_english_too():
    """The English is the source of the other two, so it is gated first."""
    assert gate_forbidden("you are eligible for this", "en") != []


# --- G3 · length -------------------------------------------------------------


def test_g3_passes_a_normal_translation():
    assert gate_length(EN["summary"], HI["summary"]) == []


def test_g3_catches_a_padded_translation():
    """Far longer than the English means the translator added things."""
    english = " ".join(["word"] * 20)
    reasons = gate_length(english, " ".join(["बहुत"] * 60))
    assert len(reasons) == 1 and "the English" in reasons[0]


def test_g3_ignores_an_empty_english():
    """Nothing to measure against, so G5 handles it instead of G3 dividing by zero."""
    assert gate_length("", "कुछ पाठ") == []


def test_g3_counts_words_not_characters():
    """pm-kisan's real document list: 1.8x by character, but not by word.

    A terse English list becomes a spoken Hindi sentence. By character that
    looks like padding; by word, which is what the caller hears, it is fine.
    """
    english = "Aadhaar Card.\nLandholding papers.\nSavings Bank Account."
    hindi = (
        "आधार कार्ड, भूमि स्वामित्व के कागजात, बचत बैंक खाते का विवरण। "
        "सीएससी सेंटर आपको कागज़ों की पूरी सूची बताएगा।"
    )
    assert len(hindi) / len(english) > tunables.GATE_LENGTH_RATIO_MAX
    assert gate_length(english, hindi) == []


def test_g3_exempts_a_short_line():
    """A three-item list spoken as a sentence must add words; that is not padding."""
    assert gate_length("Aadhaar Card. Savings Bank Account.", "आधार कार्ड और बचत बैंक खाते का विवरण। सीएससी सेंटर आपको पूरी सूची बताएगा।") == []


# --- G4 · script -------------------------------------------------------------


def test_g4_passes_real_devanagari():
    assert gate_script(EN["summary"], HI["summary"]) == []


def test_g4_catches_untranslated_english():
    reasons = gate_script("Visit the nearest CSC centre.", "Visit the nearest CSC centre.")
    assert any("Devanagari" in r for r in reasons)
    assert any("identical" in r for r in reasons)


def test_g4_ignores_digits_and_spaces_when_measuring_script():
    """A line that is mostly rupee amounts is still honest Hindi."""
    assert gate_script("6000 rupees, 3 times", "6000 रुपये, 3 बार") == []


def test_g4_ignores_a_web_address():
    """A portal name cannot be written in Devanagari and still work.

    This is smam's real how_to_apply line, which failed at 0.77 before the fix.
    """
    assert gate_script(EN["how_to_apply"], MR["how_to_apply"]) == []
    assert gate_script("Visit the portal", "agrimachinery.nic.in पोर्टलला भेट द्या") == []


# --- G5 · complete -----------------------------------------------------------


def test_g5_passes_a_full_scheme():
    assert gate_complete(_scheme()["chunks"]) == []


def test_g5_names_every_empty_section():
    chunks = _scheme()["chunks"]
    chunks["mr"]["documents"] = ""
    chunks["hi"]["name"] = "   "
    reasons = gate_complete(chunks)
    assert "mr.documents is empty" in reasons
    assert "hi.name is empty" in reasons


# --- the whole scheme --------------------------------------------------------


def test_a_good_scheme_passes_every_gate_in_every_language():
    row = gate_scheme(_scheme())
    assert row["ok"] is True
    assert row["lang_ok"] == {"en": True, "hi": True, "mr": True}


def test_one_bad_language_does_not_sink_the_others():
    """Hindi may be wrong while Marathi is fine; only Hindi should be held back."""
    hi = dict(HI, benefit_text="हर साल रुपये।")  # the 6000 is gone
    row = gate_scheme(_scheme(hi=hi))
    assert row["lang_ok"]["hi"] is False
    assert row["lang_ok"]["mr"] is True
    assert row["ok"] is False


def test_an_empty_section_fails_every_language():
    """A scheme missing a section cannot be spoken in any language."""
    mr = dict(MR, documents="")
    row = gate_scheme(_scheme(mr=mr))
    assert row["lang_ok"] == {"en": False, "hi": False, "mr": False}


def test_an_empty_text_is_reported_once_by_g5_not_again_by_g1_to_g4():
    """One problem must not look like five in the report."""
    hi = dict(HI, summary="")
    row = gate_scheme(_scheme(hi=hi))
    assert row["languages"]["hi"]["summary"] == []
    assert "hi.summary is empty" in row["complete"]


def test_every_section_field_appears_in_the_row():
    row = gate_scheme(_scheme())
    for lang in ("en", "hi", "mr"):
        assert set(row["languages"][lang]) == set(SECTION_FIELDS)


# --- the runner --------------------------------------------------------------


def test_run_writes_a_row_per_scheme_and_a_report(tmp_path):
    derived = _write_inputs(tmp_path, [_scheme("a"), _scheme("b")])
    reports = tmp_path / "reports"

    assert run_gates(derived_dir=derived, reports_dir=reports) == 0

    rows = [
        json.loads(line)
        for line in (derived / "gates.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [r["scheme_id"] for r in rows] == ["a", "b"]
    assert all(r["ok"] for r in rows)

    report = json.loads((reports / "gates.json").read_text(encoding="utf-8"))
    assert report["schemes"] == 2
    assert report["ok"] == 2
    assert report["per_language"] == {"en": 2, "hi": 2, "mr": 2}
    assert report["failures"] == []


def test_the_report_lists_only_the_fields_that_failed(tmp_path):
    """A reviewer opening gates.json should see the fault, not 18 empty lists."""
    hi = dict(HI, benefit_text="हर साल रुपये।")
    derived = _write_inputs(tmp_path, [_scheme("bad", hi=hi)])
    reports = tmp_path / "reports"

    run_gates(derived_dir=derived, reports_dir=reports)

    report = json.loads((reports / "gates.json").read_text(encoding="utf-8"))
    failure = report["failures"][0]
    assert failure["scheme_id"] == "bad"
    assert set(failure["languages"]["hi"]) == {"benefit_text"}
    assert failure["languages"]["mr"] == {}


def test_missing_schemes_file_says_so_and_does_not_crash(tmp_path):
    assert run_gates(derived_dir=tmp_path / "nope", reports_dir=tmp_path / "r") == 1


def test_gates_file_is_replaced_not_appended(tmp_path):
    """A second run must not leave yesterday's rows behind it."""
    derived = _write_inputs(tmp_path, [_scheme("a")])
    run_gates(derived_dir=derived, reports_dir=tmp_path / "r")
    run_gates(derived_dir=derived, reports_dir=tmp_path / "r")

    lines = [
        line
        for line in (derived / "gates.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 1


def test_the_number_floor_is_a_tunable(monkeypatch):
    """Drop the floor and a spelled-out 3 becomes a failure, as the knob promises."""
    monkeypatch.setattr(tunables, "GATE_NUMBER_MIN", 1)
    assert gate_numbers("in 3 installments", "तीन किस्तों में") != []
