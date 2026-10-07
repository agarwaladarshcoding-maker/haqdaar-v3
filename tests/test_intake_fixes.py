"""Intake fixes (7 Oct): a tie between name hits goes to the longest name; a scheme for an organisation is not
offered to a person unless named or the caller speaks for an organisation. No model, no network."""
from types import SimpleNamespace

from haqdaar.contracts.types import UNASKED
from haqdaar.data import scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.engine.talk import _Talk
from tests.test_ask_first import Synth, _blank
from tests.test_intake_build import LINES, good_annot
from tools import intake_build as ib


def _names_only(ids, names):
    return scheme_index.SchemeIndex("t", ids, names, None, [], None)


# --- the name tie ------------------------------------------------------------------

def test_the_longest_matched_name_wins_a_tie():
    idx = _names_only(["pmay-g", "pmay-urban"], [["pmay", "pm awas"], ["pmay urban", "शहरी आवास योजना"]])
    assert [h.scheme_id for h in idx.search("PMAY Urban", 2)] == ["pmay-urban", "pmay-g"]
    assert idx.search("PMAY Urban", 1)[0].by == "name"
    assert idx.search("pmay", 1)[0].scheme_id == "pmay-g"            # the short name alone: the rural one, as before
    assert idx.search("शहरी आवास योजना चाहिए", 1)[0].scheme_id == "pmay-urban"


def test_an_equal_tie_keeps_the_snapshot_order():
    idx = _names_only(["a", "b"], [["pm awas"], ["pm awas"]])
    assert [h.scheme_id for h in idx.search("pm awas", 2)] == ["a", "b"]


# --- the row and the corpus --------------------------------------------------------

def test_the_builder_writes_for_organisation_only_when_true():
    assert ib.make_row(good_annot(for_organisation=True), LINES, "", [], "d")["for_organisation"] is True
    assert "for_organisation" not in ib.make_row(good_annot(for_organisation=False), LINES, "", [], "d")


def test_the_corpus_keeps_the_org_schemes_private():
    rows = [{"category": ("farming",)}] * 3
    masks = {("category", "farming"): 0b111}
    c = Corpus("t", masks, {"category": ("farming",)}, ("a", "b", "c"), (0, 0, 0), {}, {}, {}, {},
               for_org=frozenset({"b"}))
    assert c._for_org == frozenset({1})
    assert not any(n.startswith("for_org") or n == "is_for_org" for n in dir(Corpus) if not n.startswith("_"))


# --- the talk ----------------------------------------------------------------------

class OrgCorpus(Synth):
    """s0, s1: farming schemes for a person; s2 (RKVY startups) and s3 (ODOP awards): for an organisation."""

    def __init__(self):
        super().__init__([{"category": ("farming",)}] * 2 + [{"category": ("business_loans",)}] * 2)
        self._scheme_ids = ("pm-kisan", "pmfby", "rkvy-agri-startups", "odop-awards")
        self._for_org = frozenset({2, 3})


class Idx:
    """The search: every scheme in the same order, vector hits; a named scheme (odop) is a name hit."""
    ids = ["rkvy-agri-startups", "odop-awards", "pm-kisan", "pmfby"]

    def search(self, text, k=4):
        out = [SimpleNamespace(scheme_id=s, by="vector", score=0.5) for s in self.ids]
        if "odop" in text.lower():
            out.insert(0, SimpleNamespace(scheme_id="odop-awards", by="name", score=1.0))
            out = [out[0]] + [h for h in out[1:] if h.scheme_id != "odop-awards"]
        return out[:k]


def _talk(tmp_path, words, **known):
    log = Log.open("orgfix", "synth", logs_dir=str(tmp_path))
    t = _Talk(SimpleNamespace(), None, OrgCorpus(), log, "en", Idx())
    t.stage = {}
    t.heard.append(words)
    t.bv.update(_blank(**known))
    return t


def test_a_farmer_asking_for_farming_is_not_offered_an_org_scheme(tmp_path):
    t = _talk(tmp_path, "I am a farmer, I need help with farming", category="farming")
    ids = t._found()
    assert set(ids) >= {"pm-kisan", "pmfby"} and not {"rkvy-agri-startups", "odop-awards"} & set(ids)
    assert not {"rkvy-agri-startups", "odop-awards"} & set(t._state(ids)[0].left)


def test_a_named_org_scheme_still_opens(tmp_path):
    t = _talk(tmp_path, "tell me about ODOP awards")
    ids = t._found()
    assert "odop-awards" in ids and t.named and t.focus == "odop-awards"
    assert "rkvy-agri-startups" not in ids


def test_a_caller_who_runs_a_startup_gets_the_org_scheme(tmp_path):
    for words in ("I run a startup, any agri scheme", "हमारी कंपनी के लिए कोई योजना", "my NGO needs a grant"):
        t = _talk(tmp_path, words, category=UNASKED)
        assert "rkvy-agri-startups" in t._found(), words


def test_the_rebuilt_list_after_a_fixed_fact_leaves_them_out_too(tmp_path):
    t = _talk(tmp_path, "farming please", category="farming")
    kind = [s for s in t._found() if s in ("pm-kisan", "pmfby")]
    assert kind == ["pm-kisan", "pmfby"] or set(kind) == {"pm-kisan", "pmfby"}
    assert t._drop_org(list(Idx.ids), "farming please", set()) == ["pm-kisan", "pmfby"]
