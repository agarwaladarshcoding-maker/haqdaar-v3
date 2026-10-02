"""tests/test_confirm.py

Unit tests for haqdaar/model/confirm.py (item #10: yes/no word lists out of Engine).
Verifies accept and reject matching across English, Hindi, and Marathi.
"""
import pytest
from haqdaar.model.confirm import match_confirm
from haqdaar.model.router import Model


@pytest.mark.parametrize(
    "text,lang",
    [
        # English accept
        ("yes", "en"),
        ("yeah", "en"),
        ("yep", "en"),
        ("correct", "en"),
        ("right", "en"),
        ("sure", "en"),
        ("1", "en"),
        # Hindi accept
        ("haan", "hi"),
        ("ha", "hi"),
        ("sahi", "hi"),
        ("sahi hai", "hi"),
        ("theek hai", "hi"),
        ("ji haan", "hi"),
        ("1", "hi"),
        # Marathi accept
        ("ho", "mr"),
        ("hoy", "mr"),
        ("barobar", "mr"),
        ("khare", "mr"),
        ("barobar aahe", "mr"),
        ("1", "mr"),
    ],
)
def test_match_confirm_accept_across_languages(text, lang):
    assert match_confirm(text, lang=lang) is True
    # Model.confirm delegation
    model = Model()
    assert model.confirm(text, lang=lang) is True


@pytest.mark.parametrize(
    "text,lang",
    [
        # English reject
        ("no", "en"),
        ("nope", "en"),
        ("wrong", "en"),
        ("incorrect", "en"),
        ("fix", "en"),
        ("change", "en"),
        ("2", "en"),
        # Hindi reject
        ("nahi", "hi"),
        ("na", "hi"),
        ("galat", "hi"),
        ("galat hai", "hi"),
        ("badlo", "hi"),
        ("2", "hi"),
        # Marathi reject
        ("nahi", "mr"),
        ("chuki", "mr"),
        ("chuki che", "mr"),
        ("badla", "mr"),
        ("nako", "mr"),
        ("2", "mr"),
    ],
)
def test_match_confirm_reject_across_languages(text, lang):
    assert match_confirm(text, lang=lang) is False
    model = Model()
    assert model.confirm(text, lang=lang) is False


def test_match_confirm_unclear():
    assert match_confirm("potato", lang="en") is None
    assert match_confirm("kuch bhi", lang="hi") is None
    assert match_confirm("", lang="mr") is None
