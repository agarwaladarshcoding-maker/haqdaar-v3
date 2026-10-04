"""Step 7.5a: which language did the caller say? Plain lookup, no model."""
from __future__ import annotations

import pytest

from haqdaar.audio.lang_words import language_from_words
from haqdaar.contracts import tunables


@pytest.fixture(autouse=True)
def _three_languages(monkeypatch):
    monkeypatch.setattr(tunables, "LANGS_OFFERED", ("hi", "mr", "en"))


@pytest.mark.parametrize("text,lang", [
    ("Hindi", "hi"), ("hindi please", "hi"), ("हिंदी", "hi"), ("हिन्दी।", "hi"), ("हिंदी में", "hi"),
    ("Marathi", "mr"), ("मराठी", "mr"), ("मराठीत बोला", "mr"),
    ("English", "en"), ("english, please.", "en"), ("अंग्रेज़ी", "en"), ("अंग्रेजी", "en"), ("इंग्रजी", "en"),
    ("one", "hi"), ("number two", "mr"), ("3", "en"), ("तीन", "en"), ("दो दबाओ", "mr"), ("ek", "hi"),
])
def test_a_named_language_or_key_number_is_picked(text, lang):
    assert language_from_words(text) == lang


@pytest.mark.parametrize("text", [
    "", "   ", "hello", "hello hello can you hear me", "kisan ke baare mein", "हाँ",
    "hindi english",              # two languages: unclear
    "मराठी हिंदी",
    "what do you do about one thing",   # a number word inside a sentence is only a word
    "do",                         # Latin "do" is English, not the key number
])
def test_anything_unclear_picks_nothing(text):
    assert language_from_words(text) is None


def test_a_language_the_greeting_does_not_offer_is_never_picked(monkeypatch):
    monkeypatch.setattr(tunables, "LANGS_OFFERED", ("hi", "en"))   # the default: no Marathi
    assert language_from_words("Marathi") is None
    assert language_from_words("two") == "en"      # numbers follow the keys the greeting gave
    assert language_from_words("three") is None    # there is no third key
    assert language_from_words("Hindi") == "hi"
