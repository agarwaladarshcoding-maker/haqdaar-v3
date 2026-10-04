"""tests/test_qa_search.py

Step 7.3: scheme search (E1), Door A English names (E7), 429 safety (E8). Fakes only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from haqdaar.contracts import tunables
from haqdaar.data.scheme_search import find_schemes
from haqdaar.model.client import GroqModelClient, ModelClientResponse
from haqdaar.model.router import Model

CARDS = {
    "S1": "[S1]\nsummary: Low interest institutional credit for farmers.\nbenefit_text: Up to Rs 3 lakh loan at 4% interest rate.",
    "S5": "[S5]\nsummary: Working capital loan at subsidized interest for weavers.\nbenefit_text: Working capital up to Rs 2 lakh.",
    "S6": "[S6]\nsummary: Insurance protection for unexpected crop yield failure.",
}


# --- E1 ------------------------------------------------------------------------------------

def test_search_picks_best_card_first():
    assert find_schemes("working capital loan with low interest for weavers", CARDS, 2) == ["S5", "S1"]


def test_search_needs_two_shared_words():
    assert find_schemes("tell me about weavers", CARDS, 4) == []
    assert find_schemes("what is the weather today", CARDS, 4) == []
    assert find_schemes("", CARDS, 4) == []


def test_search_caps_at_k_and_ignores_field_labels():
    assert len(find_schemes("working capital loan with low interest", CARDS, 1)) == 1
    assert find_schemes("summary benefit_text", CARDS, 4) == []


def test_search_works_on_devanagari():
    cards = {"A": "[A]\nsummary: किसानों के लिए कम ब्याज पर क्रेडिट।", "B": "[B]\nsummary: बीमा सुरक्षा।"}
    assert find_schemes("किसानों को कम ब्याज पर क्रेडिट चाहिए", cards, 4) == ["A"]


# --- E7 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("said,slug", [
    ("Mudra", "pmmy"),
    ("Mudra loan", "pmmy"),
    ("Mudra Yojana", "pmmy"),
    ("Pradhan Mantri Awaas Yojana", "pmay-g"),
    ("Pradhan Mantri Awas Yojana Gramin", "pmay-g"),
    ("Pradhan Mantri Awaas Yojana Gramin", "pmay-g"),
    ("Agriculture Mechanization", "smam"),
    ("Atal Pension Yojana", "apy"),
    ("Pradhan Mantri Fasal Bima Yojana", "pmfby"),
])
def test_door_a_english_names_read_the_right_scheme(said, slug):
    from haqdaar.data.corpus import Corpus
    from haqdaar.engine.door_a import DoorA
    root = Path(__file__).resolve().parent.parent
    snap = root / "snapshots"
    if not (snap / "CURRENT").exists():
        pytest.skip("no real snapshot in this checkout")
    corpus = Corpus.load(str((snap / "CURRENT").read_text().strip()))
    res = DoorA.from_corpus(corpus).match(said, lang="en")
    assert res.action == "read" and res.scheme_ids == (slug,), res


# --- E8 ------------------------------------------------------------------------------------

class R429Client(GroqModelClient):
    def __init__(self):
        super().__init__(api_key="fake_key")
        self.calls = 0

    def call(self, messages, task="model_router", timeout=None, model=None):
        self.calls += 1
        return ModelClientResponse(success=False, data=None, error="http_429", is_429=True)


def test_429_on_sort_and_answer_never_raises_never_counts_never_sleeps(monkeypatch):
    import time

    def no_sleep(_s):
        raise AssertionError("a live call must not sleep on a 429")

    monkeypatch.setattr(time, "sleep", no_sleep)
    client = R429Client()
    model = Model(client=client)
    for _ in range(5):
        assert model.sort("anything_else", "what does it pay") == "OTHER"
        assert model.answer("what does it pay", "en", "[x]\nbenefit_text: Rs. 6,000.") is None
    assert model.failures == 0 and not model.keypad_only
    assert client.calls > 0
