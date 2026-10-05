"""Step 1.3a (d): "just tell me" and "I do not know / I will not say", in Hindi, Marathi, English."""
import pytest
from types import SimpleNamespace

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Hangup, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.engine.call import Engine
from haqdaar.engine import words_no_answer, words_tell_me
from tests.test_talk import Audio, Client, Index


@pytest.fixture(scope="module")
def corpus():
    return Corpus.load("CURRENT")


@pytest.fixture
def call(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())
    n = [0]

    def go(inputs, replies):
        n[0] += 1
        audio, client = Audio(inputs), Client(list(replies))
        log = Log.open(f"phrase_test_{n[0]}", corpus.snapshot_id, logs_dir=str(tmp_path))
        Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
        return audio, client

    return go


def _ask(box):
    return {"action": "ask", "say": "What kind of help?", "ask_box": box, "facts": {}}


def test_just_tell_me_stops_the_questions_and_shows_two(call):
    show = {"action": "show_scheme", "say": "Two schemes for you.", "scheme": ""}
    audio, client = call(
        [Speech("I need some scheme"), Speech("just tell me"), Speech("ok")],
        [_ask("category"), show, {"action": "not_for_me"}],
    )
    assert "NEXT QUESTION: category" in client.calls[0]
    assert "NEXT QUESTION: none" in client.calls[1]      # asking stopped
    assert client.calls[1].count("mark: ") == 2          # the 2 best left are shown
    assert "NEXT QUESTION: none" in client.calls[2]      # still stopped on the next turn
    assert audio.answers[1] == "Two schemes for you."


def test_dont_know_sets_unknown_at_once_not_after_twice(call):
    audio, client = call(
        [Speech("I need some scheme"), Speech("I do not know"), Speech("ok")],
        [_ask("category"), {"action": "not_for_me"}, {"action": "not_for_me"}],
    )
    assert "category = UNKNOWN" in client.calls[1]       # not known at once
    assert "NEXT QUESTION: category" not in client.calls[1]
    assert "NEXT QUESTION: category" not in client.calls[2]  # never asked again


def test_just_tell_me_hindi():
    yes = ["नहीं नहीं, बस योजना बता दो", "कोई भी योजना बता दो", "सीधे बताओ", "सवाल मत पूछो",
           "अरे सीधा बताओ ना"]
    for said in yes:
        assert words_tell_me.is_just_tell_me(said), said
    for said in ["मुझे लोन चाहिए", "मैं किसान हूँ", "कौन सी योजना है"]:
        assert not words_tell_me.is_just_tell_me(said), said


def test_just_tell_me_marathi():
    for said in ["फक्त योजना सांगा", "थेट सांगा", "प्रश्न विचारू नका", "प्रश्न नको, योजना सांगा"]:
        assert words_tell_me.is_just_tell_me(said), said
    assert not words_tell_me.is_just_tell_me("मला कर्ज हवे आहे")


def test_just_tell_me_english():
    for said in ["no no, just tell me the scheme", "tell me directly", "no more questions please",
                 "skip the questions", "don't ask, just tell me"]:
        assert words_tell_me.is_just_tell_me(said), said
    assert not words_tell_me.is_just_tell_me("i need a loan for my shop")


def test_dont_know_hindi():
    for said in ["पता नहीं", "मुझे नहीं पता", "याद नहीं आ रहा", "मालूम नही"]:
        assert words_no_answer.no_answer(said) == "dont_know", said
    assert words_no_answer.no_answer("मैं किसान हूँ") == ""


def test_dont_know_marathi():
    for said in ["माहित नाही", "मला आठवत नाही"]:
        assert words_no_answer.no_answer(said) == "dont_know", said
    assert words_no_answer.no_answer("मला कर्ज हवे आहे") == ""


def test_dont_know_english():
    for said in ["I do not know", "don't know really", "not sure", "no idea", "I forgot"]:
        assert words_no_answer.no_answer(said) == "dont_know", said
    assert words_no_answer.no_answer("I am thirty") == ""


def test_plain_tell_me_about_x_is_not_just_tell_me():
    """1.3b (B): "tell me about X" names a topic; it must not stop the questions."""
    assert not words_tell_me.is_just_tell_me("मुझे किसान योजना बता दो")
    assert not words_tell_me.is_just_tell_me("शेतकरी योजना सांगा")
    assert not words_tell_me.is_just_tell_me("I have no questions")
    # Bare "tell me (any scheme)" still stops them.
    assert words_tell_me.is_just_tell_me("कोई भी योजना बता दो")
    assert words_tell_me.is_just_tell_me("नहीं नहीं, बस योजना बता दो")


def test_wont_say_hindi_marathi_english():
    assert words_no_answer.no_answer("मैं नहीं बताऊंगा") == "wont_say"
    assert words_no_answer.no_answer("मत पूछो") == "wont_say"
    assert words_no_answer.no_answer("मी सांगणार नाही") == "wont_say"
    assert words_no_answer.no_answer("I will not say") == "wont_say"
    assert words_no_answer.no_answer("I would rather not say") == "wont_say"
