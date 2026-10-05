"""Review faults 5, 6, 7: the plain-code word spotters. No model, no network."""
import pytest

from haqdaar.data import scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.engine import talk_words, words_tell_me

_IDX = scheme_index.SchemeIndex.load("CURRENT", embed=lambda texts: 1 / 0)


def _named(text):
    return [h.scheme_id for h in _IDX.search(text, 4) if h.by == "name" and h.score > 0]


@pytest.mark.parametrize("text,sid", [
    ("पीएम किसान", "pm-kisan"),
    ("पीएम किसान योजना के बारे में बताइए", "pm-kisan"),
    ("मनरेगा", "mgnrega"),
    ("केसीसी", "kcc"),
    ("pm awas", "pmay-g"),
    ("स्वनिधि", "pm-svanidhi"),
    ("मुद्रा लोन", "pmmy"),
    ("mudra loan", "pmmy"),
    ("pm kisan", "pm-kisan"),
    ("किसान क्रेडिट कार्ड", "kcc"),
    ("अटल पेंशन योजना", "apy"),
])
def test_scheme_named(text, sid):
    assert sid in _named(text)


@pytest.mark.parametrize("text", [
    "किसी से पूछो", "कैसे सीखूं", "मुद्रा लेना है", "समुद्र के पास रहता हूँ",
    "मुद्रा की कमी है", "मेरी आजीविका चली गई", "my family benefit from farming",
    "किसानों को हर साल पैसा मिलता है वो योजना",
])
def test_scheme_not_named(text):
    assert _named(text) == []


def _spot(text):
    return talk_words.spot(text, Corpus.load("CURRENT"))


def test_marathi_no_words():
    assert "occupation" not in _spot("मी शेतकरी नाही")
    assert _spot("मला कर्ज नको").get("category") != "business_loans"
    assert _spot("mala karj nako").get("category") != "business_loans"


@pytest.mark.parametrize("text,need", [
    ("घर नहीं है", "housing"),
    ("नौकरी नहीं है मेरे पास", "jobs_skills"),
    ("मुझे पेंशन नहीं मिलती", "pension"),
    ("mere paas ghar nahi hai", "housing"),
])
def test_lack_is_need(text, need):
    assert _spot(text).get("category") == need


def test_latin_relation_not_caller_work():
    assert "occupation" not in _spot("mera bhai kisan hai")


@pytest.mark.parametrize("text", [
    "bas bata do", "बस बताइए", "seedha batao", "सीधे बताइए", "बस योजना बता दो",
    "फक्त योजना सांगा", "no more questions please", "कोई भी योजना बता दो",
    "नहीं नहीं, बस योजना बता दो", "just tell me",
])
def test_just_tell_me(text):
    assert words_tell_me.is_just_tell_me(text)


@pytest.mark.parametrize("text", [
    "मुझे किसान योजना बता दो", "शेतकरी योजना सांगा", "I have no questions",
    "कोई किसान योजना बता दो", "कोणती पेन्शन योजना सांगा",
])
def test_not_just_tell_me(text):
    assert not words_tell_me.is_just_tell_me(text)
