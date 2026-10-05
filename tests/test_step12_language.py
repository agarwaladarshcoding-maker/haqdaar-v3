"""1.2 (first part) + 1.1 part B: the reply follows the language the caller speaks, and the
five-language greeting of a talk call. Fakes only: no sound is made, no network is used."""
from __future__ import annotations

from haqdaar.audio import live_tts
from haqdaar.audio.phone import PhoneAudio
from haqdaar.contracts import tunables
from haqdaar.contracts.types import Speech


def _phone(lang: str = "hi") -> PhoneAudio:
    phone = PhoneAudio.__new__(PhoneAudio)
    phone.language = lang  # type: ignore[assignment]
    phone._log = lambda line: None
    return phone


def test_reply_language_follows_a_full_spoken_turn(monkeypatch):
    monkeypatch.setattr(tunables, "LANG_EACH_TURN", True)
    phone = _phone("hi")
    phone._follow_language(Speech(text="I want a scheme for farmers", lang="en-IN"))
    assert phone.language == "en"
    assert phone._listen_lang() == ""          # the speech service is told no language


def test_short_turn_or_unknown_language_keeps_the_last_one(monkeypatch):
    monkeypatch.setattr(tunables, "LANG_EACH_TURN", True)
    phone = _phone("mr")
    phone._follow_language(Speech(text="yes ok", lang="en-IN"))                       # under 3 real words
    phone._follow_language(Speech(text="मला शेतकरी योजना हवी आहे", lang=""))          # no code came back
    phone._follow_language(Speech(text="मला शेतकरी योजना हवी आहे", lang="xx-IN"))     # not a Sarvam language
    assert phone.language == "mr"
    phone._follow_language(Speech(text="મને ખેડૂત યોજના જોઈએ છે", lang="gu-IN"))      # 1.4: every Sarvam language is followed
    assert phone.language == "gu"


def test_switch_off_keeps_the_picked_language(monkeypatch):
    monkeypatch.setattr(tunables, "LANG_EACH_TURN", False)
    phone = _phone("hi")
    phone._follow_language(Speech(text="I want a scheme for farmers", lang="en-IN"))
    assert phone.language == "hi"
    assert phone._listen_lang() == "hi"


class _Recorder:
    def __init__(self):
        self.played = []


def _greeting_phone(monkeypatch, speak):
    monkeypatch.setattr(tunables, "GREETING_FIVE", True)
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(live_tts, "speak", speak)
    phone = _phone()
    phone._speak = None
    phone._token_clips = {}
    phone._filler = True
    saved: dict[str, bytes] = {}
    phone._saved_answer = lambda key: saved.get(key)
    phone._save_answer = lambda key, audio: saved.__setitem__(key, audio)
    rec = _Recorder()
    phone._play = lambda clips, name: rec.played.append((name, clips))
    return phone, rec, saved


def test_greeting_is_said_in_five_languages_and_kept(monkeypatch):
    asked = []

    def speak(text, lang, code=""):
        asked.append(code)
        return b"\xff" * 80

    phone, rec, saved = _greeting_phone(monkeypatch, speak)
    assert phone._say_greeting_five() is True
    assert asked == ["hi-IN", "en-IN", "mr-IN", "gu-IN", "ta-IN"]
    name, clips = rec.played[0]
    assert name == "greeting_trilingual" and len(clips) == 5      # the call page reads this name
    assert phone._say_greeting_five() is True
    assert len(asked) == 5 and len(saved) == 5                     # second call: from disk, free


def test_greeting_line_that_fails_falls_back_to_the_recorded_one(monkeypatch):
    phone, rec, _ = _greeting_phone(monkeypatch, lambda text, lang, code="": None if code == "ta-IN" else b"\xff")
    assert phone._say_greeting_five() is False
    assert rec.played == []


def test_greeting_five_is_off_outside_a_talk_call(monkeypatch):
    phone, rec, _ = _greeting_phone(monkeypatch, lambda text, lang, code="": b"\xff")
    monkeypatch.setattr(tunables, "TALK_ONLY", False)
    assert phone._say_greeting_five() is False
