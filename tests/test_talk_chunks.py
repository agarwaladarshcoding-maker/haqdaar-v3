"""Step 1.5: the talk shows the model the top parts of schemes (search by part), not whole cards.
Fake audio, fake model, a stand-in parts index. No network."""
import time
from types import SimpleNamespace

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Speech
from haqdaar.data import chunk_index, log_text, scheme_index
from haqdaar.data.log import Log
from haqdaar.engine.call import Engine

from tests.test_talk import ALL, Audio, Client, Index, _say, corpus  # noqa: F401  (corpus is a fixture)

PAPERS = "PAPERS-OF-PM-KISAN: Aadhaar card, landholding papers and a bank passbook."
SUMMARY = "SUMMARY-OF-PMAY-G: help to build a house."


def hit(sid, part, text, score=1.0):
    return chunk_index.ChunkHit(sid, part, text, score)


class Parts:
    """Stands in for the loaded ChunkIndex. `answer(query)` gives the hits for a query."""

    def __init__(self, answer, delay=0.0):
        self.scheme_ids = tuple(ALL)
        self.chunks = [None] * 5
        self._answer, self.delay, self.asked = answer, delay, []

    def search(self, query, *, k=5, fits=None, max_chunks_per_scheme=2):
        self.asked.append((query, k, fits))
        time.sleep(self.delay)
        return self._answer(query)


def general(query):
    """What the caller's words alone find: two other schemes. The scheme's own name finds its papers."""
    if query.startswith("Pradhan Mantri Kisan") and "papers" in query:
        return [hit("pm-kisan", "papers needed", PAPERS)]
    if "Kisan" in query:
        return [hit("pmfby", "summary", "PMFBY-SUMMARY-PART")]
    return [hit("pmay-g", "summary", SUMMARY), hit("pmay-g", "benefits", "PMAYG-BENEFIT-PART")]


@pytest.fixture
def call(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "TALK_CHUNKS", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())
    calls = []

    def go(inputs, replies, parts=None):
        calls.append(1)
        if parts is not None:
            monkeypatch.setitem(chunk_index._loaded_chunks, corpus.snapshot_id, parts)
        audio, client = Audio(inputs), Client(replies)
        log = Log.open(f"chunks_test_{len(calls)}", corpus.snapshot_id, logs_dir=str(tmp_path))
        Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
        rows = log_text.read_rows(log.path)
        assert not [r for r in rows if r.get("invalid")]
        return audio, client, rows

    return go


def _schemes_block(prompt_text):
    return prompt_text.split("SCHEMES (", 1)[1].split("SCHEME IN TALK:", 1)[0]


def test_parts_not_whole_cards_reach_the_prompt(call):
    parts = Parts(general)
    _, client, _ = call([Speech("I want a house")], [_say("It helps build a house.")], parts)
    block = _schemes_block(client.calls[0])
    assert SUMMARY in block and "PMAYG-BENEFIT-PART" in block
    assert "[pmay-g]" in block and "name: " in block          # the id and the name stay
    assert "exclusions:" not in block and "how_to_apply:" not in block   # no whole card
    assert "summary: " + SUMMARY in block and "benefit_text: PMAYG-BENEFIT-PART" in block


def test_flag_off_is_the_old_whole_card_path(call, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_CHUNKS", False)

    def never(_q):
        raise AssertionError("the parts index must not be asked")

    parts = Parts(never)
    _, client, rows = call([Speech("I want a house")], [_say("It helps build a house.")], parts)
    assert parts.asked == []
    assert "exclusions:" in _schemes_block(client.calls[0])
    assert not [r for r in rows if r.get("ev") == "line"]


def test_scheme_in_talk_and_a_papers_question_bring_its_papers(call):
    parts = Parts(general)
    _, client, _ = call(
        [Speech("what is PM Kisan"), Speech("which papers")],
        [_say("PM Kisan helps farmers.", scheme="pm-kisan"), _say("Bring your Aadhaar card.", scheme="pm-kisan")],
        parts)
    assert "PAPERS-OF-PM-KISAN" not in client.calls[0]
    second = _schemes_block(client.calls[1])
    assert second.index("[pm-kisan]") < second.index("[pmfby]")       # the scheme in talk goes first
    assert "documents: " + PAPERS in second
    assert "SCHEME IN TALK: [pm-kisan]" in client.calls[1]


def test_a_search_that_raises_falls_back_to_whole_cards_and_logs_once(call):
    def boom(_q):
        raise RuntimeError("index broke")

    audio, client, rows = call(
        [Speech("I want a house"), Speech("tell me more")],
        [_say("It helps build a house."), _say("It is for village families.")], Parts(boom))
    assert all("exclusions:" in _schemes_block(c) for c in client.calls)
    assert len(audio.answers) == 2                                    # the call went on
    lines = [r for r in rows if r.get("ev") == "line"]
    assert len(lines) == 1 and "RuntimeError" in lines[0]["why"]


def test_an_index_that_did_not_load_falls_back_too(call, corpus, monkeypatch):
    monkeypatch.delitem(chunk_index._loaded_chunks, corpus.snapshot_id, raising=False)
    _, client, rows = call([Speech("I want a house")], [_say("It helps build a house.")])
    assert "exclusions:" in _schemes_block(client.calls[0])
    assert [r["why"] for r in rows if r.get("ev") == "line"] == ["parts: whole cards, parts index not loaded"]


def test_nothing_found_falls_back_to_whole_cards(call):
    _, client, _ = call([Speech("I want a house")], [_say("It helps build a house.")], Parts(lambda q: []))
    assert "exclusions:" in _schemes_block(client.calls[0])


def test_the_proof_is_the_whole_card_of_a_scheme_whose_part_was_sent(call):
    # The part sent is the summary. 10,000 is only in the card's other fields (who_can_apply, exclusions).
    # It must pass: the proof is the whole card. A number written nowhere is still refused.
    parts = Parts(lambda q: [hit("pm-kisan", "summary", "PM-Kisan gives 6,000 rupees a year.")])
    ok = _say("A pensioner who earns 10,000 rupees or more is left out.", scheme="pm-kisan")
    bad = _say("It gives 99917 rupees.", scheme="pm-kisan")
    audio, client, rows = call([Speech("who is PM Kisan for")], [bad, ok], parts)
    assert [r["rule"] for r in rows if r.get("ev") == "blocked"] == ["number"]
    assert audio.answers == [ok["say"]]
    assert "10,000" not in _schemes_block(client.calls[0])            # the model did not see it; the proof did


def test_the_proof_holds_the_scheme_in_talk_even_when_its_part_is_not_sent(call):
    # Turn 2 sends parts of other schemes only; 10,000 is in the card of the scheme in talk.
    parts = Parts(lambda q: [hit("pmay-g", "summary", SUMMARY)])
    ok = _say("A pensioner who earns 10,000 rupees or more is left out.", scheme="pm-kisan")
    audio, _, rows = call([Speech("what is PM Kisan"), Speech("anything else")],
                          [_say("PM Kisan helps farmers.", scheme="pm-kisan"), ok], parts)
    assert not [r for r in rows if r.get("ev") == "blocked"]
    assert audio.answers[-1] == ok["say"]


def test_fits_carries_what_the_caller_told_and_a_scheme_that_does_not_fit_is_dropped(call):
    # A 70 year old: apy (age 18-40) is marked "does not fit". Its part comes first from the search.
    parts = Parts(lambda q: [hit("apy", "summary", "APY-SUMMARY-PART"), hit("ignwps", "summary", SUMMARY)])
    _, client, _ = call([Speech("my age is seventy"), Speech("I want a pension")],
                        [_say("Noted.", facts={"age": 70}), _say("Here is a scheme.")], parts)
    assert parts.asked[-1][2]["apy"] == "does not fit"                # `fits` is the picker's mark per scheme
    assert set(parts.asked[-1][2]) == set(ALL)
    block = _schemes_block(client.calls[1])
    assert "APY-SUMMARY-PART" not in block and SUMMARY in block
    assert all(q[1] > 5 for q in parts.asked)                         # asked for more than 5, so 5 can remain


def test_search_ms_counts_the_part_search(call):
    _, _, rows = call([Speech("I want a house")], [_say("It helps build a house.")], Parts(general, delay=0.05))
    act = next(r for r in rows if r.get("ev") == "act")
    assert act["search_ms"] >= 45
