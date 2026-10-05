"""Step 1.3a (e): the picker limits + (f) 30 situations and minimax on 100 schemes. No model."""
import pytest
from types import SimpleNamespace

from haqdaar.contracts import tunables
from haqdaar.contracts.log_schema import STOP_LE_4_SURVIVORS
from haqdaar.contracts.types import SEVEN_BOXES, UNASKED, UNKNOWN, Ask, Stop
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.data.scheme_text import SchemeText
from haqdaar.engine import planner, talk_pick
from haqdaar.engine.filter import Filter
from haqdaar.engine.talk import _Talk
from haqdaar.engine import talk_words
from tests.test_talk import Index


@pytest.fixture(scope="module")
def corpus():
    return Corpus.load("CURRENT")


def _blank(**known):
    return {b: UNASKED for b in SEVEN_BOXES} | known


def _all(corpus):
    return [corpus.scheme_id(i) for i in range(17)]


# --- 1.3a talk limits --------------------------------------------------------

def test_talk_stops_at_two_left_but_asks_at_three_or_four(corpus):
    assert talk_pick.narrow(["pm-kisan", "kcc"], _blank(), corpus).ask is None
    # Three schemes that a box still splits get a question (age splits the pensions).
    assert talk_pick.narrow(["apy", "nps-tsep", "ignwps"], _blank(), corpus).ask == "age"
    # Three schemes no box splits stop too (nothing left to ask).
    assert talk_pick.narrow(["pm-kisan", "pmfby", "kcc"], _blank(), corpus).ask is None
    got = talk_pick.narrow(["pm-kisan", "pmfby", "kcc", "smam"],
                           _blank(category="farming"), corpus)
    assert got.ask is not None  # a farming situation gets its question


def test_keys_keep_stopping_at_four(corpus):
    bv = _blank(category="farming")
    assert len(Filter.survivors(bv, corpus)) == 4
    act = planner.next_action(bv, corpus)  # no stop_survivors: the keys path
    assert isinstance(act, Stop) and act.reason == STOP_LE_4_SURVIVORS


def test_at_most_three_questions_a_call(corpus, tmp_path):
    log = Log.open("maxq", corpus.snapshot_id, logs_dir=str(tmp_path))
    t = _Talk(SimpleNamespace(), None, corpus, log, "en", Index())
    t.asked = {"category": 1, "occupation": 1}
    assert t._state(Index().ids)[0].ask is not None  # two asked: may ask on
    t.asked = {"category": 1, "occupation": 1, "age": 1}
    assert t._state(Index().ids)[0].ask is None      # three asked: show schemes


def test_unknown_box_is_never_asked_again(corpus):
    got = talk_pick.narrow(_all(corpus), _blank(category="farming", age=UNKNOWN), corpus)
    assert got.ask != "age"


def test_asked_box_is_never_without_a_dependent_scheme(corpus):
    """Relevance: never a box no remaining scheme depends on."""
    cases = [(_all(corpus), _blank()),
             (_all(corpus), _blank(category="farming")),
             (_all(corpus), _blank(category="pension")),
             (_all(corpus), _blank(category="business_loans")),
             (_all(corpus), _blank(occupation="farmer")),
             (_all(corpus), _blank(gender="female")),
             (_all(corpus), _blank(category="farming", occupation="farmer"))]
    for ids, bv in cases:
        got = talk_pick.narrow(ids, bv, corpus)
        if got.ask is None:
            continue
        sub = talk_pick.SubCorpus(corpus, [corpus._scheme_ids.index(s) for s in ids])
        surv = Filter.survivors(bv, sub)
        assert planner._box_splits_survivors(got.ask, surv, bv, sub), (ids, bv, got.ask)


def test_tie_worst_then_average_then_easy_first(corpus):
    """business_loans: occupation and age tie at worst 0 and on average, so the
    fixed easy-first order asks occupation (work before age)."""
    got = talk_pick.narrow(_all(corpus), _blank(category="business_loans"), corpus)
    assert got.ask == "occupation"
    got = talk_pick.narrow(_all(corpus), _blank(category="pension"), corpus)
    assert got.ask == "age"  # age wins outright here: worst 2 left vs gender's 3


# --- an answer to another question -------------------------------------------

class _Client:
    def __init__(self, replies):
        self.replies = list(replies)

    def call(self, messages, task="", timeout=None, model=None):
        return SimpleNamespace(success=True, data=self.replies.pop(0))


def _decide(corpus, tmp_path, name, words, reply, **known):
    log = Log.open(name, corpus.snapshot_id, logs_dir=str(tmp_path))
    t = _Talk(SimpleNamespace(), SimpleNamespace(client=_Client([reply])), corpus, log, "en", Index())
    t.heard = [words]
    t.stage = {}
    t.bv.update(known)
    t._decide(words)
    return t


def test_answer_to_another_question_does_not_count(corpus, tmp_path):
    """Asked age, told the state: the state is taken, the age ask is free. The new question
    counts (the read of 1.3b: before, the new ask was the one left out, so the cap never fired)."""
    log = Log.open("otherbox", corpus.snapshot_id, logs_dir=str(tmp_path))
    reply = {"action": "ask", "say": "What kind of help do you need?",
             "ask_box": "category", "facts": {"state": "MAHARASHTRA"}, "scheme": ""}
    t = _Talk(SimpleNamespace(), SimpleNamespace(client=_Client([reply])), corpus, log, "en", Index())
    t.heard, t.stage = ["I am from Maharashtra"], {}
    t.asked, t.last_asked = {"age": 1}, "age"
    t._decide("I am from Maharashtra")
    assert t.bv["state"] == "MAHARASHTRA"
    assert t.asked == {"category": 1}


def test_answer_to_the_asked_box_counts(corpus, tmp_path):
    """The category is known from before; the caller says nothing new; the
    occupation ask counts."""
    t = _decide(corpus, tmp_path, "samebox", "hmm, tell me",
                {"action": "ask", "say": "What work do you do?",
                 "ask_box": "occupation", "facts": {}, "scheme": ""},
                category="farming")
    assert t.asked == {"occupation": 1}


def test_question_count_rule(corpus, tmp_path):
    """1.3 (A): every question the line asks counts. One is given back when the
    caller answered another box than the one asked last (asked age, told the state)."""
    from haqdaar.engine.talk import _free_ask
    assert not _free_ask("", {"state"})             # nothing was asked
    assert not _free_ask("age", set())              # no answer at all: the ask counts
    assert not _free_ask("age", {"age"})            # answered: the ask counts
    assert not _free_ask("age", {"age", "state"})
    assert _free_ask("age", {"state"})              # asked age, told the state


def test_three_unanswered_questions_then_schemes(corpus, tmp_path):
    """1.3b (A): three turns with no usable answer use up the questions;
    then the line shows schemes and asks nothing."""
    from types import SimpleNamespace
    from haqdaar.data.log import Log
    from haqdaar.engine.talk import _Talk
    log = Log.open("threeq", corpus.snapshot_id, logs_dir=str(tmp_path))
    t = _Talk(SimpleNamespace(), None, corpus, log, "en", Index())
    t.stage = {}
    for _ in range(3):
        nar, _cards = t._state(t._found() or Index().ids)
        t.heard = ["hmm"]
        assert nar.ask is not None
        wrong = "gender" if nar.ask != "gender" else "age"
        t.model = SimpleNamespace(client=_Client([
            {"action": "ask", "say": "What kind of help do you need?",
             "ask_box": wrong, "facts": {}, "scheme": ""},
            {"action": "ask", "say": "What kind of help do you need?",
             "ask_box": wrong, "facts": {}, "scheme": ""}]))
        t._decide("hmm")
    assert sum(t.asked.values()) == 3
    assert t._state(t._found() or Index().ids)[0].ask is None


def test_dont_know_first_turn_sets_nothing(corpus, tmp_path):
    """1.3b (C): "I don't know which scheme is for me" on turn 1 is no answer
    to nothing: no box is set to not known."""
    t = _decide(corpus, tmp_path, "dontknowfirst", "I don't know which scheme is for me",
                {"action": "not_for_me", "say": "", "facts": {}, "scheme": ""})
    assert t.bv["category"] == UNASKED


def test_dont_know_after_a_question_sets_unknown(corpus, tmp_path):
    """1.3b (C): "do not know" sets the box the line just asked about."""
    from types import SimpleNamespace
    from haqdaar.data.log import Log
    from haqdaar.engine.talk import _Talk
    log = Log.open("dontknowask", corpus.snapshot_id, logs_dir=str(tmp_path))
    t = _Talk(SimpleNamespace(), None, corpus, log, "en", Index())
    t.stage = {}
    t.heard = ["I need some scheme"]
    t.model = SimpleNamespace(client=_Client([
        {"action": "ask", "say": "What kind of help do you need?",
         "ask_box": "category", "facts": {}, "scheme": ""}]))
    t._decide("I need some scheme")
    t.heard = ["I do not know"]
    t.model = SimpleNamespace(client=_Client([{"action": "not_for_me"}]))
    t._decide("I do not know")
    assert t.bv["category"] == UNKNOWN


# --- (f) minimax on a made-up set of 100 schemes -------------------------------

class FakeCorpus:
    """75 schemes: 5 kinds x 5 works x 3 ages. state/gender/group are open for
    all, income has no values, so neither can ever be asked."""

    def __init__(self, n=75):
        self._n = n
        self._ids = tuple(f"s{i:03d}" for i in range(n))

    @property
    def snapshot_id(self):
        return "fake-100"

    def scheme_id(self, i):
        return self._ids[i] if 0 <= i < self._n else ""

    def specificity(self, i):
        return 0

    def values(self, box):
        return {"category": tuple(f"c{k}" for k in range(5)),
                "occupation": tuple(f"o{k}" for k in range(5)),
                "age": tuple(f"a{k}" for k in range(3)),
                "state": ("MAHARASHTRA", "OTHER"),
                "gender": ("female", "male"),
                "social_category": ("GEN", "OBC"),
                "income_band": ()}[box]

    def _facet(self, i, box):
        if box == "category":
            return f"c{(i // 15) % 5}"
        if box == "occupation":
            return f"o{i % 5}"
        if box == "age":
            return f"a{i % 3}"
        return None  # ANY: every value's mask holds the scheme

    def mask(self, box, value):
        if box == "income_band":
            return 0
        out = 0
        for i in range(self._n):
            facet = self._facet(i, box)
            if facet is None or facet == value:
                out |= 1 << i
        return out


def test_minimax_100_blank_asks_the_kind():
    fake = FakeCorpus()
    act = planner.next_action(_blank(), fake)
    assert isinstance(act, Ask) and act.box == "category"


def test_minimax_100_talk_asks_down_to_two():
    """stop_survivors=2 (talk): 4 left still asks; 2 left stops. Default (keys): stops at 4."""
    fake = FakeCorpus()
    bv = _blank(category="c0", occupation="o0")  # 0, 5, 10 -> 3... see below
    assert len(Filter.survivors(bv, fake)) == 3
    assert isinstance(planner.next_action(bv, fake), Stop)  # keys: 3 <= 4
    act = planner.next_action(bv, fake, stop_survivors=2)
    assert isinstance(act, Ask) and act.box == "age"  # talk: age splits 1/1/1
    bv2 = _blank(category="c0", occupation="o0", age="a0")
    assert len(Filter.survivors(bv2, fake)) == 1
    assert isinstance(planner.next_action(bv2, fake, stop_survivors=2), Stop)


def test_minimax_100_never_asks_open_or_empty_boxes():
    fake = FakeCorpus()
    for bv in (_blank(), _blank(category="c0"), _blank(category="c0", occupation="o1"),
               _blank(category="c2", age="a1"), _blank(occupation="o3", age="a2")):
        act = planner.next_action(bv, fake, stop_survivors=2)
        assert not isinstance(act, Ask) or act.box in ("category", "occupation", "age"), act


def test_minimax_100_reaches_two_in_three_questions():
    """Answer each question with the value keeping the most schemes: 75 -> 15
    -> 3 -> 1, three questions, then stop."""
    fake = FakeCorpus()
    bv, asked = _blank(), 0
    while True:
        act = planner.next_action(bv, fake, stop_survivors=2)
        if not isinstance(act, Ask):
            break
        asked += 1
        assert asked <= 6
        vals = fake.values(act.box)
        bv[act.box] = max(vals, key=lambda v: len(Filter.survivors({**bv, act.box: v}, fake)))
    assert len(Filter.survivors(bv, fake)) <= 2
    assert asked <= 3


# --- (f) 30 situations -> the first question expected --------------------------

# situation -> expected first question (None = show schemes, ask nothing).
# Candidates are all 17 schemes; the box values come from the word spotter.
SITUATIONS = [
    ("मेरी फसल खराब हो गई", "occupation"),
    ("पैसे की तंगी है", "category"),
    ("बुज़ुर्ग हूँ, कोई सहारा नहीं", "category"),
    ("मुझे पेंशन चाहिए", "age"),
    ("मैं ठेला लगाता हूँ", "category"),
    ("मुझे घर बनाना है", None),
    ("मेरी डिलीवरी अस्पताल में होगी", "category"),  # delivery + hospital name two kinds: ask
    ("मुझे इलाज के लिए मदद चाहिए", None),          # health holds nothing: say so plainly
    ("मेरे बच्चे की पढ़ाई के लिए", None),           # education holds nothing: say so plainly
    ("मैं विकलांग हूँ", None),                      # 2 left: show them
    ("गाँव में रोज़गार चाहिए", None),               # jobs are 2: show them
    ("मुझे लोन चाहिए दुकान के लिए", "occupation"),
    ("मैं बुनकर हूँ", "category"),
    ("मुझे दुकान खोलने के लिए पैसे चाहिए", "occupation"),
    ("बारिश नहीं हुई, फसल सूख गई", "occupation"),
    ("मुझे ट्रैक्टर खरीदना है", "category"),
    ("मैं गर्भवती हूँ", None),                      # jsy1 + day-nrlm: show them
    ("मुझे पढ़ाई के लिए स्कॉलरशिप चाहिए", None),
    ("मुझे मकान बनाने के लिए पैसे चाहिए", None),
    ("मुझे अपना छोटा कारोबार बढ़ाना है", "occupation"),
    ("I need some help", "category"),
    ("i need a scheme for farming", "occupation"),
    ("my crops died", "occupation"),
    ("I am sixty years old", "category"),
    ("I am a widow", "category"),
    ("my husband died", "category"),
    ("I am a street vendor", "category"),
    ("I drive a cart in the city", "category"),
    ("मला शेतीसाठी मदत हवी आहे", "occupation"),
    ("मला पेन्शन हवी आहे", "age"),
]


def test_thirty_situations_ask_the_expected_first_question(corpus):
    assert len(SITUATIONS) == 30
    wrong = []
    for said, want in SITUATIONS:
        bv = _blank()
        bv.update(talk_words.spot(said, corpus))
        got = talk_pick.narrow(_all(corpus), bv, corpus)
        if got.ask != want:
            wrong.append((said, want, got.ask))
    assert not wrong, wrong
