"""Marathi paused (owner, 4 Oct 2026): offered languages are Hindi (key 1) and English (key 2)."""
from __future__ import annotations

from haqdaar.audio.lines import load_lines
from haqdaar.contracts import tunables
from haqdaar.engine.call import _next_lang


def test_default_offer_is_hindi_then_english(monkeypatch):
    monkeypatch.setattr(tunables, "LANGS_OFFERED", ("hi", "en"))
    assert tunables.turn0_keys() == {"1": "hi", "2": "en"}


def test_star_skips_the_paused_language(monkeypatch):
    monkeypatch.setattr(tunables, "LANGS_OFFERED", ("hi", "en"))
    assert _next_lang("hi") == "en" and _next_lang("en") == "hi"
    assert _next_lang("mr") == "hi"  # a language that is not offered falls back to the first


def test_all_three_still_work_when_offered(monkeypatch):
    monkeypatch.setattr(tunables, "LANGS_OFFERED", ("hi", "mr", "en"))
    assert tunables.turn0_keys() == {"1": "hi", "2": "mr", "3": "en"}
    assert [_next_lang(l) for l in ("hi", "mr", "en")] == ["mr", "en", "hi"]


def test_each_greeting_part_names_only_its_own_language():
    """The owner's complaint: the English part read out all three choices again."""
    g = load_lines()["greeting_trilingual"]
    assert "Hindi" not in g["en"] and "Marathi" not in g["en"]
    assert g["en"].count("press") == 1 and "1" in g["hi"]
    assert g["mr"].strip()  # Marathi text is kept


def test_a_greeting_key_for_a_language_not_offered_gives_the_default(monkeypatch):
    monkeypatch.setattr(tunables, "LANGS_OFFERED", ("hi", "en"))
    assert "3" not in tunables.turn0_keys()
