"""tests/test_lines.py

Step 1.13 (plan 1.11) — the fixed lines load, cover every id, and obey the house rules.
"""
import re

import pytest
import yaml

from haqdaar.audio import lines as lines_mod
from haqdaar.audio.lines import (
    LINES_PATH,
    TRILINGUAL_LINE_ID,
    line_text,
    load_lines,
    untranslated,
)
from haqdaar.contracts import vocab
from haqdaar.contracts.types import FIXED_LINE_IDS


def test_every_fixed_line_id_is_present_exactly_once():
    loaded = load_lines()
    assert set(loaded) == set(FIXED_LINE_IDS)
    raw = yaml.safe_load(LINES_PATH.read_text(encoding="utf-8"))["lines"]
    assert len(raw) == len(FIXED_LINE_IDS), "a duplicate key would be silently dropped by yaml"


def test_every_line_has_english():
    for line_id, texts in load_lines().items():
        assert texts.get("en"), line_id


def test_no_line_promises_the_caller_anything():
    """The call reads out what a scheme says; it never tells a caller they will get it."""
    for line_id, texts in load_lines().items():
        for lang, text in texts.items():
            found = vocab.find_forbidden(text, lang)
            assert found is None, f"{line_id}/{lang} says {found!r}"


def test_lines_stay_short_enough_to_speak():
    """A fixed line is a prompt, not a paragraph. The section menu is the longest by design."""
    for line_id, texts in load_lines().items():
        words = len(texts["en"].split())
        assert words <= 40, f"{line_id} is {words} words"


def _english_only(tmp_path):
    """lines.yaml as it was before p4 filled in Hindi and Marathi, and before any line was pinned."""
    path = tmp_path / "lines.yaml"
    text = LINES_PATH.read_text(encoding="utf-8")
    path.write_text(re.sub(r"(?m)^    (hi|mr|pinned): .*\n", "", text), encoding="utf-8")
    return path


def test_line_text_falls_back_to_english_before_translation(tmp_path):
    path = _english_only(tmp_path)
    assert line_text("closing_farewell", "en", path).startswith("Thank you")
    # hi is not written yet, so the English is what plays rather than nothing at all.
    assert line_text("closing_farewell", "hi", path) == line_text("closing_farewell", "en", path)


def test_untranslated_lists_the_work_left_for_p4(tmp_path):
    todo = untranslated(_english_only(tmp_path))
    ids = {line_id for line_id, _ in todo}
    assert TRILINGUAL_LINE_ID not in ids, "the trilingual greeting is one recording"
    # Every other line still needs hi and mr; this is what the build gate will watch shrink.
    assert len(todo) == (len(FIXED_LINE_IDS) - 1) * 2


def test_a_missing_id_is_an_error(tmp_path):
    bad = tmp_path / "lines.yaml"
    bad.write_text("lines:\n  greeting_trilingual:\n    en: Hello\n", encoding="utf-8")
    load_lines.cache_clear()
    with pytest.raises(ValueError, match="missing fixed lines"):
        load_lines(bad)


def test_an_unknown_id_is_an_error(tmp_path):
    body = "lines:\n" + "".join(
        f"  {line_id}:\n    en: Text here\n" for line_id in FIXED_LINE_IDS
    ) + "  not_a_real_line:\n    en: Text here\n"
    bad = tmp_path / "lines.yaml"
    bad.write_text(body, encoding="utf-8")
    load_lines.cache_clear()
    with pytest.raises(ValueError, match="unknown line ids"):
        load_lines(bad)


@pytest.fixture(autouse=True)
def _clear_cache():
    load_lines.cache_clear()
    yield
    load_lines.cache_clear()


def test_keypad_lines_are_backed_by_chips_in_all_three_languages():
    """A keypad line is useless without its chips, and chips come from vocab, not from here."""
    for box in ("gender", "social_category", "occupation"):
        assert f"keypad_{box}" in load_lines()
        for value in vocab.KEYPAD_LISTS[box]:
            label = vocab.LABELS.get(value)
            if label is None:
                continue
            for lang in ("en", "hi", "mr"):
                assert label.get(lang), f"chip {value} has no {lang}"


def test_band_labels_come_from_a_template():
    from haqdaar.audio.lines import band_label

    assert band_label("age", 18, 40) == "18 to 40 years"
    assert band_label("age", 60, None) == "60 years and above"
    assert band_label("income_band", 0, 100000) == "0 to 100000 rupees a year"
    assert band_label("income_band", 250000, None, "hi").endswith("और उससे ऊपर")
    assert band_label("age", 18, 40, "mr") == "18 ते 40 वर्षे"


def test_band_label_rejects_a_box_with_no_template():
    from haqdaar.audio.lines import band_label

    with pytest.raises(ValueError, match="no band template"):
        band_label("gender", 1, 2)
