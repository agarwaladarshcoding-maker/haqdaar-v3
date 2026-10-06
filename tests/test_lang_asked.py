"""The caller asks for a language in words ("explain this in Hindi"): the model sets "lang", the reply
is said in it, and the call stays in it. Fake model, fake audio, fake translate: no network."""
from haqdaar.audio import lang_words
from haqdaar.audio.phone import PhoneAudio
from haqdaar.contracts import tunables
from haqdaar.contracts.types import Speech
from haqdaar.prompts import talk as prompt

from tests.test_lang_middle_talk import FakeTranslator, run  # noqa: F401  (fixture)
from tests.test_talk import _say, corpus  # noqa: F401  (fixture)

ANSWER = "It is a scheme for farmer families."


def test_names_are_found_offered_or_not():
    assert lang_words.languages_named("please explain this in Hindi") == {"hi"}
    assert lang_words.languages_named("मराठीत सांगा") == {"mr"}
    assert lang_words.languages_named("tamil mein bolo") == {"ta"}
    assert lang_words.languages_named("what is there for farmers") == set()


def test_english_caller_asks_for_hindi_and_the_reply_is_hindi(run):
    audio, client, _rows = run("en", "explain this to me in Hindi", [_say(ANSWER, lang="hi")])
    assert 'The caller named a language: Hindi = "hi"' in client.calls[0]
    assert audio.answers[-1] == f"[hi] {ANSWER}"
    assert audio.language == "hi" and audio.lang_asked == "hi"


def test_hindi_caller_asks_for_english_with_the_pipe_on(run, monkeypatch):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", True)
    audio, _client, _rows = run("hi", "मुझे English में बताओ", [_say(ANSWER, lang="en")])
    assert audio.answers[-1] == ANSWER and audio.language == "en"


def test_a_language_with_no_words_of_its_own(run):
    audio, _client, _rows = run("en", "tell me in Tamil please", [_say(ANSWER, lang="ta-IN")])
    assert audio.answers[-1] == f"[ta] {ANSWER}" and audio.language == "ta"


def test_only_a_language_named_this_turn_is_taken(run):
    audio, client, _rows = run("en", "what is there for farmers", [_say(ANSWER, lang="hi")])
    assert "The caller named a language" not in client.calls[0]
    assert audio.answers[-1] == ANSWER and audio.language == "en"
    audio, _client, _rows = run("en", "tell me in Hindi", [_say(ANSWER, lang="mr")])   # not the one named
    assert audio.answers[-1] == ANSWER and audio.language == "en"


def test_a_mention_alone_does_not_switch(run):
    audio, client, _rows = run("en", "I studied in a Hindi school", [_say(ANSWER)])
    assert "The caller named a language" in client.calls[0]     # offered, and the model left it
    assert audio.answers[-1] == ANSWER and audio.language == "en" and not getattr(audio, "lang_asked", "")


def test_with_the_pipe_off_the_turn_that_names_a_language_is_worked_in_english(run, monkeypatch):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", False)        # the model writes Hindi itself on other turns
    built, real = [], prompt.build
    monkeypatch.setattr(prompt, "build", lambda lang, *a: built.append(lang) or real(lang, *a))
    audio, _client, _rows = run("hi", "English में बताओ", [_say(ANSWER, lang="en")])
    assert built == ["en"] and audio.answers[-1] == ANSWER and audio.language == "en"
    built.clear()
    audio, _client, _rows = run("hi", "मराठी में बोलो", [_say(ANSWER, lang="mr")])
    assert built == ["en"] and audio.answers[-1] == f"[mr] {ANSWER}" and audio.language == "mr"
    built.clear()                                               # a mention: still Hindi, by the translate step
    audio, _client, _rows = run("hi", "मैं English स्कूल में पढ़ा हूँ", [_say(ANSWER)])
    assert built == ["en"] and audio.answers[-1] == f"[hi] {ANSWER}" and audio.language == "hi"


def test_say_it_again_in_english_when_the_last_reply_was_written_in_hindi(run, monkeypatch):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", False)
    audio, client, _rows = run("hi", ["किसानों के लिए क्या है", "English में फिर से बोलो"],
                               [_say("यह किसान परिवारों की योजना है।"), {"action": "repeat", "say": "", "lang": "en"},
                                _say(ANSWER, lang="en")])
    assert "Write your last reply again" in client.calls[-1]
    assert audio.answers[-1] == ANSWER and audio.language == "en"


def test_say_that_again_in_hindi_says_the_last_reply_in_hindi(run):
    audio, _client, _rows = run("en", ["what is there for farmers", "say that again in Hindi"],
                                [_say(ANSWER), {"action": "repeat", "say": "", "lang": "hi"}])
    assert audio.answers[-1] == f"[hi] {ANSWER}"


def test_the_asked_language_stays_on_the_next_turns(run, monkeypatch):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", True)         # the talk's own way: the model stays in English
    audio, _client, _rows = run("en", ["explain this in Hindi", "what papers do I need for it"],
                                [_say(ANSWER, lang="hi"), _say("You need an Aadhaar card.")])
    assert audio.answers[-1] == "[hi] You need an Aadhaar card."


def test_the_ear_does_not_move_an_asked_language_back(monkeypatch):
    monkeypatch.setattr(tunables, "LANG_EACH_TURN", True)
    phone = PhoneAudio.__new__(PhoneAudio)
    phone.language, phone._log = "hi", lambda line: None  # type: ignore[assignment]
    phone.lang_asked = "hi"
    phone._follow_language(Speech("what papers do I need", lang="en-IN"))
    assert phone.language == "hi"
    phone.lang_asked = ""
    phone._follow_language(Speech("what papers do I need", lang="en-IN"))
    assert phone.language == "en"
