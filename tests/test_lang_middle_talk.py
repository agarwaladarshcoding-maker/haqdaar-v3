"""1.4 wired + every Sarvam language: the talk works in English and the reply is translated into the
caller's language. Fake model, fake audio, fake translate: no network, no money."""
from types import SimpleNamespace

import pytest

from haqdaar.audio import ear, lang_words, live_tts, render
from haqdaar.contracts import tunables
from haqdaar.contracts.types import SARVAM_CODES, Hangup, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.log import Log
from haqdaar.engine import talk
from haqdaar.model import middle, translate
from haqdaar.prompts import talk as prompt

from tests.test_qa_engine import QAAudio
from tests.test_talk import Client, Index, _say, corpus  # noqa: F401  (fixture)

OTHER = [l for l in SARVAM_CODES if l not in ("hi", "mr", "en")]


class FakeTranslator:
    """Marks the text with the language; `bad` makes it fail, `twist` changes a number."""
    calls: list = []
    mode = "ok"

    def __init__(self, *a, **k):
        pass

    def translate(self, text, lang):
        FakeTranslator.calls.append((text, lang))
        if FakeTranslator.mode == "bad":
            return None
        if FakeTranslator.mode == "twist":
            return f"[{lang}] " + text.replace("6000", "3200")
        return f"[{lang}] {text}"


@pytest.fixture
def run(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", False)
    monkeypatch.setattr(tunables, "LANG_EACH_TURN", False)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())
    monkeypatch.setattr(middle, "AnswerTranslator", FakeTranslator)
    monkeypatch.setattr(middle, "scheme_names", lambda: [])
    FakeTranslator.calls, FakeTranslator.mode = [], "ok"
    n = []

    def go(lang, words, replies):
        n.append(1)
        said = [words] if isinstance(words, str) else words
        audio, client = QAAudio([Speech(w) for w in said] + [Hangup()], lang), Client(replies)
        log = Log.open(f"lang_{len(n)}", corpus.snapshot_id, logs_dir=str(tmp_path))
        talk.run(audio, SimpleNamespace(client=client), corpus, log, lang, Index())
        return audio, client, log_text.read_rows(log.path)

    return go


@pytest.mark.parametrize("lang", OTHER)
def test_another_sarvam_language_is_worked_in_english_and_said_in_its_own(run, lang, monkeypatch):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", False)     # not needed for these: they always go through English
    built, real = [], prompt.build
    monkeypatch.setattr(prompt, "build", lambda lang, *a: built.append(lang) or real(lang, *a))
    audio, _client, rows = run(lang, "what is there for farmers", [_say("It is a scheme for farmer families.")])
    assert built == ["en"]                                   # the model reads and writes English
    assert audio.answers[-1] == f"[{lang}] It is a scheme for farmer families."
    assert all(a.startswith(f"[{lang}] ") for a in audio.answers)   # the hello too
    assert not [r for r in rows if r.get("ev") == "blocked"]


def test_hindi_with_the_pipe_on_gets_the_english_reply_translated_and_its_own_hello(run, monkeypatch):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", True)
    audio, client, rows = run("hi", "farmers", [_say("It is a scheme for farmer families.")])
    assert audio.answers[-1] == "[hi] It is a scheme for farmer families."
    assert " ".join(audio.answers).startswith(prompt.HELLO["hi"].split("।")[0])   # the written Hindi hello
    acts = [r for r in rows if r.get("ev") == "act"]
    assert acts[-1].get("translate_ms") is not None


def test_hindi_with_the_pipe_off_is_direct_as_before(run, monkeypatch):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", False)
    audio, _client, _rows = run("hi", "किसान", [_say("यह योजना किसानों के लिए है।")])
    assert audio.answers[-1] == "यह योजना किसानों के लिए है।"
    assert FakeTranslator.calls == []


def test_english_is_never_translated(run, monkeypatch):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", True)
    audio, _client, _rows = run("en", "farmers", [_say("It is a scheme for farmer families.")])
    assert audio.answers[-1] == "It is a scheme for farmer families."
    assert FakeTranslator.calls == []


@pytest.mark.parametrize("mode", ["bad", "twist"])
def test_a_failed_or_wrong_translate_says_the_english_never_silence(run, monkeypatch, mode):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", True)
    monkeypatch.setattr(tunables, "TALK_ASK_FIRST", False)   # about the translate step; ask-first gives no scheme text (so no "6000") on a long list
    say = "It gives 6000 rupees a year."
    FakeTranslator.mode = mode
    audio, _client, rows = run("ta", "money", [_say(say)])
    assert audio.answers[-1] == say
    assert "translate" in [r["rule"] for r in rows if r.get("ev") == "blocked"]


# --- the one language list ---

def test_every_sarvam_language_is_known_everywhere():
    assert set(SARVAM_CODES) == {"hi", "mr", "en", "bn", "gu", "kn", "ml", "od", "pa", "ta", "te"}
    for lang, code in SARVAM_CODES.items():
        assert ear.SARVAM_LANG[lang] == code                  # the ear may be told it
        assert ear.normalize_lang(code) == code               # and its answer is kept
        assert render.TTS_LANG[lang] == code                  # the live voice speaks it
        assert lang in lang_words.NAMES                       # a talk call may follow the caller into it
        assert lang_words.language_from_code(code) == lang
        if lang != "en":
            assert translate.TARGET_CODES[lang] == code       # the reply can be translated into it
            assert lang in middle.LANGS
    assert live_tts.TTS_LANG is render.TTS_LANG


def test_an_unknown_code_is_still_hindi():
    assert lang_words.language_from_code("xx-IN") == "hi"
    assert lang_words.language_from_code("") == "hi"


def test_indic_digits_count_as_numbers_for_the_guard():
    for six in ("৬০০০", "૬૦૦૦", "੬੦੦੦", "୬୦୦୦", "௬௦௦௦", "౬౦౦౦", "೬೦೦೦", "൬൦൦൦", "६०००"):
        assert middle._numbers(f"Rs {six}") == [6000.0], six


def test_the_same_reply_is_not_said_twice_with_the_pipe_on(run, monkeypatch):
    """Hindi in the pipe: last_say holds Hindi, the model writes English; the repeat must still be caught."""
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", True)
    one = _say("There are schemes for farmers.")
    audio, _client, rows = run("hi", ["farming schemes", "farming schemes please"],
                               [one, one, _say("Kisan Credit Card is one more.")])
    assert [r["rule"] for r in rows if r.get("ev") == "blocked"] == ["same_again"]
    assert audio.answers[-1] == "[hi] Kisan Credit Card is one more."
