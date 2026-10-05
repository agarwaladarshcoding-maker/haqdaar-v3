"""Step 1.1 part A: the greeting door of a talk call.

Keys stay open after a noise with no words. Any real words at the greeting start the talk, in the
language the speech service heard; the words are turn 1 and the talk says no second hello. A bare
"hello?" starts the talk with no first words. Sound with no words never resets the 30 s quiet rule.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from haqdaar.audio.ear import SttResult
from haqdaar.audio.lang_words import is_bare_greeting, language_from_code
from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Noise, Silence, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.log import Log
from haqdaar.engine.call import Engine
from haqdaar.prompts import talk as prompt

from tests.test_live_speech import FakeSTT, Line, _later
from tests.test_silence_rules import _phone
from tests.test_talk import Audio, Client, Index, _say, corpus  # noqa: F401  (corpus is a fixture)

HINDI_QUESTION = "पीएम किसान में कितना पैसा मिलता है"


@pytest.fixture(autouse=True)
def _talk_call(monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", False)
    monkeypatch.setattr(tunables, "KEY_GUARD_MS", 0)
    monkeypatch.setattr(tunables, "SILENCE_GAP_S", 0.3)
    monkeypatch.setattr(tunables, "SILENCE_REMIND_S", 3.0)
    monkeypatch.setattr(tunables, "SILENCE_HANGUP_S", 6.0)
    monkeypatch.setattr(tunables, "LANGS_OFFERED", ("hi", "mr", "en"))


def _greeting(said: str, code: str):
    """A real Mouth, Turn, Ear and PhoneAudio; the caller says `said` once the greeting has ended.
    Returns (line, what select_language gave)."""
    line = Line(stt=FakeSTT(SttResult(transcript=said, lang=code, success=True)))
    _later(0.05, line.marks_back)       # the greeting clip ends
    _later(0.25, line.voice, 30, 45)    # then the caller speaks
    return line, line.phone.select_language()


# --- 1. keys stay open after a noise with no words -----------------------------------------


def test_noise_then_key_1_is_taken():
    line = Line(stt=FakeSTT(SttResult(transcript="", lang="", success=True)))
    keys = []

    def log(text):
        # The key comes right after the noise was dropped: the prompt must still be open for it.
        if "noise, no words" in text and not keys:
            keys.append(1)
            line.turn.push_key("1")

    line.phone._log = log
    line.turn._log = log
    _later(0.05, line.marks_back)
    _later(0.25, line.voice, 30, 45)
    assert line.phone.select_language() == ("hi", "keypad")
    assert keys == [1]


# --- 2. any real words start the talk -----------------------------------------------------


def test_the_bare_word_hindi_picks_hindi_with_no_first_words():
    line, got = _greeting("Hindi", "en-IN")
    assert got == ("hi", "voice") and line.phone.first_words == ""


def test_a_full_hindi_question_starts_the_talk_in_hindi():
    line, got = _greeting(HINDI_QUESTION, "hi-IN")
    assert got == ("hi", "voice")
    assert line.phone.first_words == HINDI_QUESTION and line.phone.language == "hi"


def test_a_full_english_question_starts_the_talk_in_english():
    line, got = _greeting("how much money does PM Kisan give", "en-IN")
    assert got == ("en", "voice") and line.phone.first_words == "how much money does PM Kisan give"


def test_a_marathi_question_is_marathi_and_an_unknown_code_is_hindi():
    assert _greeting("मला पेन्शन हवी आहे", "mr-IN")[1] == ("mr", "voice")
    line, got = _greeting("mane yojana joiye", "gu-IN")     # every Sarvam language is now kept (1.4)
    assert got == ("gu", "voice") and line.phone.first_words == "mane yojana joiye"
    line, got = _greeting("mane yojana joiye", "xx-IN")
    assert got == ("hi", "voice")
    line, got = _greeting("mane yojana joiye", "")
    assert got == ("hi", "voice")


def test_the_language_code_maps_to_the_three_languages_the_code_knows():
    assert [language_from_code(c) for c in ("hi-IN", "mr-IN", "en-IN", "EN", "ta-IN", "unknown", "")] == [
        "hi", "mr", "en", "en", "ta", "hi", "hi"]     # every Sarvam language is kept (1.4); others are Hindi


def test_without_a_talk_call_words_that_name_no_language_still_ask_again(monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", False)
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", True)
    line, got = _greeting(HINDI_QUESTION, "hi-IN")
    assert isinstance(got, Speech) and line.phone.first_words == ""


# --- 4. "hello?" alone is not a need -------------------------------------------------------


@pytest.mark.parametrize("said", ["hello?", "Hello hello", "haan?", "हैलो", "हां जी", "जी"])
def test_a_bare_greeting_word_starts_the_talk_with_no_first_words(said):
    line, got = _greeting(said, "hi-IN")
    assert got == ("hi", "voice") and line.phone.first_words == ""
    assert is_bare_greeting(said)


def test_a_need_is_not_a_bare_greeting():
    assert not is_bare_greeting("hello what is PM Kisan") and not is_bare_greeting(HINDI_QUESTION)


# --- 3. the words are turn 1, and there is no second hello ---------------------------------


@pytest.fixture
def talk(corpus, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())

    def go(lang, first_words, inputs, replies):
        class Picked(Audio):
            def select_language(self):
                self.played.append("greeting_trilingual")
                self.inputs.pop(0)                 # the language key Audio puts first
                self.language = lang
                return lang, "voice"

        audio, client = Picked(inputs), Client(replies)
        audio.first_words = first_words
        log = Log.open("step11", corpus.snapshot_id, logs_dir=str(tmp_path))
        Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
        return audio, client, log_text.read_rows(log.path)

    return go


def test_a_full_hindi_question_is_turn_1_with_no_second_hello(talk):
    audio, client, rows = talk("hi", HINDI_QUESTION, [], [_say("यह किसान परिवारों के लिए योजना है।")])
    assert [r["text"] for r in rows if r.get("ev") == "heard"] == [HINDI_QUESTION]
    assert f'NEWEST CALLER WORDS: "{HINDI_QUESTION}"' in client.calls[0]
    assert audio.answers == ["यह किसान परिवारों के लिए योजना है।"]
    assert not any(s in prompt.HELLO["hi"] for s in audio.answers)


def test_a_full_english_question_is_turn_1_with_no_second_hello(talk):
    audio, client, rows = talk("en", "what is PM Kisan", [], [_say("It is for farmer families.")])
    assert [r["text"] for r in rows if r.get("ev") == "heard"] == ["what is PM Kisan"]
    assert "HELLO" not in audio.played
    assert audio.answers == ["It is for farmer families."]


def test_hello_alone_gets_the_talks_short_hello(talk):
    audio, client, rows = talk("en", "", [], [])
    assert audio.played.count("HELLO") == 2          # the two sentences of the talk's own hello
    assert not client.calls and not [r for r in rows if r.get("ev") == "heard"]


def test_the_bare_word_hindi_gets_the_talks_hello_too(talk):
    audio, client, _ = talk("hi", "", [], [])
    assert audio.answers and all(s in prompt.HELLO["hi"] for s in audio.answers)
    assert not client.calls


# --- 5. room sound does not reset the 30 s quiet rule at the greeting ---------------------


def test_wordless_sound_at_the_greeting_does_not_reset_the_quiet_rule(monkeypatch):
    monkeypatch.setattr(tunables, "SILENCE_REMIND_S", 30.0)
    monkeypatch.setattr(tunables, "SILENCE_HANGUP_S", 60.0)
    # a TV 10 s in, then quiet; more room sound 4 s into the second wait, then quiet
    phone, turn = _phone(monkeypatch, [(10.0, Noise()), Silence(n=1), (4.0, Noise()), Silence(n=1)])
    phone.say = lambda sequence: None
    got = [phone.select_language() for _ in range(2)]
    assert got == [Silence(n=1), Silence(n=2)]       # greeting once more, then goodbye
    assert turn.gaps == [30.0, 20.0, 30.0, 26.0]     # 30 s in all, then 30 s in all
