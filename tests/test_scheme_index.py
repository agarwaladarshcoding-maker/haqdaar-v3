"""Step 7.13 B2: scheme search (vector + name) and the fixed question picker over its hits."""
import pytest

from haqdaar.contracts.types import SEVEN_BOXES, UNASKED
from haqdaar.data import scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.engine import talk_pick

# caller sentence -> the scheme that must be in the top 3 (Hindi + English, owner's change C6)
SENTENCES = [
    ("मुझे खेती के लिए कोई योजना चाहिए", "pm-kisan"),
    ("किसानों को हर साल पैसा मिलता है वो योजना", "pm-kisan"),
    ("PM Kisan ke bare mein batao", "pm-kisan"),
    ("मेरी फसल खराब हो गई, बीमा मिलेगा क्या", "pmfby"),
    ("I want insurance for my crops", "pmfby"),
    ("किसान क्रेडिट कार्ड कैसे बनता है", "kcc"),
    ("I am a farmer and I need a loan for seeds", "kcc"),
    ("ट्रैक्टर खरीदने पर सब्सिडी", "smam"),
    ("subsidy to buy farm machines", "smam"),
    ("मेरे पति नहीं रहे, विधवा पेंशन चाहिए", "ignwps"),
    ("pension for a widow", "ignwps"),
    ("मैं विकलांग हूँ, कोई पेंशन है क्या", "igndps"),
    ("pension for a disabled person", "igndps"),
    ("घर के कमाने वाले की मौत हो गई, कोई मदद मिलेगी", "nfbs"),
    ("the earning member of our family died", "nfbs"),
    ("गाँव में पक्का घर बनाने के लिए मदद चाहिए", "pmay-g"),
    ("I need help to build a house in my village", "pmay-g"),
    ("गाँव में काम चाहिए, सौ दिन का रोजगार", "mgnrega"),
    ("मनरेगा जॉब कार्ड", "mgnrega"),
    ("बुढ़ापे के लिए पेंशन में पैसा जमा करना है", "apy"),
    ("Atal Pension Yojana", "apy"),
    ("मैं ठेला लगाता हूँ, लोन चाहिए", "pm-svanidhi"),
    ("loan for a street vendor", "pm-svanidhi"),
    ("मुद्रा लोन चाहिए दुकान के लिए", "pmmy"),
    ("I want to start a small business and need a loan", "pmmy"),
    ("नया उद्योग लगाने के लिए सब्सिडी", "pmegp"),
    ("अस्पताल में डिलीवरी पर पैसा मिलता है क्या", "jsy1"),
    ("money for a pregnant woman for hospital delivery", "jsy1"),
    ("अप्रेंटिस ट्रेनिंग में स्टाइपेंड", "naps"),
    ("महिला स्वयं सहायता समूह", "day-nrlm"),
]


@pytest.fixture(scope="module")
def index():
    idx = scheme_index.get("CURRENT")
    if idx._vectors is None:
        pytest.skip("embedding model not on this machine")
    return idx


@pytest.fixture(scope="module")
def corpus():
    return Corpus.load("CURRENT")


def test_search_finds_the_scheme_in_the_top_3(index):
    missed = [
        (text, want, [h.scheme_id for h in index.search(text, 3)])
        for text, want in SENTENCES
        if want not in [h.scheme_id for h in index.search(text, 3)]
    ]
    assert len(SENTENCES) == 30
    assert len(missed) <= 3, missed          # target: 27 of 30


def test_a_said_name_wins_by_name_search(index):
    top = index.search("kisan credit card ke bare mein batao", 4)[0]
    assert (top.scheme_id, top.by) == ("kcc", "name")


def test_search_never_raises_and_empty_words_give_nothing(index):
    assert index.search("", 4) == []
    assert index.search("   ?? ", 4) == []
    assert len(index.search("x", 4)) == 4


def test_name_search_alone_works_with_no_model():
    idx = scheme_index.SchemeIndex.load("CURRENT", embed=lambda texts: 1 / 0)
    assert idx._vectors is None
    assert idx.search("जननी सुरक्षा योजना", 2)[0].scheme_id == "jsy1"


def _blank():
    return {b: UNASKED for b in SEVEN_BOXES}


def test_vague_need_gets_the_pickers_question(index, corpus):
    """C1: a vague caller is asked the ONE box the fixed picker names, with its allowed values."""
    hits = [h.scheme_id for h in index.search("मुझे कोई योजना चाहिए", 10)]
    got = talk_pick.narrow(hits, _blank(), corpus)
    assert len(got.left) == 10
    assert got.ask in SEVEN_BOXES
    assert got.values == tuple(corpus.values(got.ask))
    assert got.order[0] == got.ask


def test_three_turns_of_facts_narrow_to_three_or_fewer(index, corpus):
    hits = [h.scheme_id for h in index.search("I need some help from the government", 10)]
    bv = _blank()
    answers = {"category": "farming", "occupation": "farmer", "gender": "male", "age": "18-35"}
    for _ in range(3):
        got = talk_pick.narrow(hits, bv, corpus)
        if got.ask is None:
            break
        bv[got.ask] = answers.get(got.ask, corpus.values(got.ask)[0])
    got = talk_pick.narrow(hits, bv, corpus)
    assert 1 <= len(got.left) <= talk_pick.TALK_STOP_SCHEMES
    assert got.ask is None


def test_subcorpus_filter_matches_the_full_filter(corpus):
    ids = ["pm-kisan", "ignwps", "jsy1", "kcc"]
    bv = {**_blank(), "gender": "male"}
    got = talk_pick.narrow(ids, bv, corpus)
    assert got.left == ("pm-kisan", "kcc")


def test_marks(corpus):
    bv = _blank()
    assert talk_pick.mark("ignwps", bv, corpus) == talk_pick.NOT_KNOWN
    assert talk_pick.mark("pmay-g", bv, corpus) == talk_pick.FITS
    assert talk_pick.mark("ignwps", {**bv, "gender": "male"}, corpus) == talk_pick.DOES_NOT_FIT
    assert talk_pick.mark("ignwps", {**bv, "gender": "female", "age": "41-79", "category": "pension"},
                          corpus) == talk_pick.FITS
    assert talk_pick.mark("no-such-scheme", bv, corpus) == talk_pick.NOT_KNOWN
