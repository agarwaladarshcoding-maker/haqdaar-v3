"""tests/test_answer_store.py

Step 7.3 E4: saved answers. Fakes only. REPORTS_DIR is a tmp dir (tests/conftest.py).
"""
from __future__ import annotations

import json

from haqdaar.data import answer_store
from haqdaar.model.client import GroqModelClient, ModelClientResponse
from haqdaar.model.router import Model

CARDS = "[pm-kisan]\nbenefit_text: Rs. 6,000 per year in three instalments.\nexclusions: Income tax payers are excluded."
GOOD = {"answer": "The scheme pays Rs. 6,000 per year."}


class FakeCorpus:
    def __init__(self, snapshot_id):
        self.snapshot_id = snapshot_id


class CountingClient(GroqModelClient):
    def __init__(self, data):
        super().__init__(api_key="fake_key")
        self.data = data
        self.n = 0

    def call(self, messages, task="model_router", timeout=None, model=None):
        self.n += 1
        return ModelClientResponse(success=True, data=self.data)


def _ask(model, q="How much does it pay?", ids=("pm-kisan",)):
    return model.answer(q, "en", CARDS, scheme_ids=list(ids))


def test_key_ignores_case_punctuation_and_id_order():
    a = answer_store.make_key("snap1", "en", ["b", "a"], "How much does it pay?")
    assert a == answer_store.make_key("snap1", "en", ["a", "b"], "  how MUCH does it pay ")
    assert a != answer_store.make_key("snap2", "en", ["a", "b"], "how much does it pay")
    assert a != answer_store.make_key("snap1", "hi", ["a", "b"], "how much does it pay")


def test_put_get_survives_a_fresh_load(tmp_path):
    key = answer_store.make_key("s", "en", ["a"], "q")
    assert answer_store.get(key) is None
    answer_store.put(key, "text")
    assert answer_store.get(key) == "text"
    answer_store._cache.clear()  # a new process reads the file again
    assert answer_store.get(key) == "text"
    lines = (tmp_path / "reports" / "saved_answers.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["answer"] == "text"


def test_bad_line_is_a_miss_not_a_crash(tmp_path):
    path = tmp_path / "reports" / "saved_answers.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('not json\n{"key": "k", "answer": "ok"}\n', encoding="utf-8")
    assert answer_store.get("k") == "ok"


def test_second_identical_question_skips_the_model():
    client = CountingClient(GOOD)
    model = Model(corpus=FakeCorpus("snapA"), client=client)
    first = _ask(model)
    assert first and client.n == 1
    assert _ask(model, "how much does it PAY") == first
    assert client.n == 1


def test_new_snapshot_never_serves_an_old_answer():
    client = CountingClient(GOOD)
    _ask(Model(corpus=FakeCorpus("snapA"), client=client))
    _ask(Model(corpus=FakeCorpus("snapB"), client=client))
    assert client.n == 2


def test_blocked_answer_is_not_saved():
    client = CountingClient({"answer": "The scheme pays Rs. 7,500 per year."})  # number not in the card
    model = Model(corpus=FakeCorpus("snapA"), client=client)
    assert _ask(model) is None and _ask(model) is None
    assert client.n == 2


def test_no_corpus_or_no_scheme_ids_saves_nothing(tmp_path):
    client = CountingClient(GOOD)
    _ask(Model(client=client))
    _ask(Model(corpus=FakeCorpus("snapA"), client=client), ids=())
    assert client.n == 2 and not (tmp_path / "reports" / "saved_answers.jsonl").exists()
