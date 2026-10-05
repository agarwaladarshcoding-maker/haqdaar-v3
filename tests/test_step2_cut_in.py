"""Phase 2 (steps 2.3, 2.4, 2.5): a talk call works with the cut-in gate off (as before) and on.

2.4 a key the talk does not act on does not stop the voice (gate off and on); key 9 does.
2.3 real words over the greeting stop it and become turn 1 (gate on only).
2.5 "say it again" over the agent starts at the cut sentence; the cut row names what was not heard.
2.2 is not built (see PLAN.md Phase 2 / the step report): nothing here tests it.
"""
from types import SimpleNamespace

import pytest

from haqdaar.audio.mouth import Mouth
from haqdaar.audio.turn import Turn
from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.log import Log
from haqdaar.engine.call import Engine
from haqdaar.prompts import talk as prompt
from tools import barge_eval as be
from tools import talk_eval as te

from tests.test_talk import Client, CutAudio, Index, _say, corpus  # noqa: F401  (corpus is a fixture)


# --- 2.4: keys, on the Turn ------------------------------------------------------------

def _reply(talk=True, photo=True, monkeypatch=None):
    monkeypatch.setattr(tunables, "TALK_ONLY", talk)
    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", photo)
    out: list[dict] = []
    mouth = Mouth(out.append, "S")
    turn = Turn(mouth)
    n = turn.start_prompt("answer")
    mouth.play([("answer", b"\x10" * 80000)], tag=(n, "answer"))   # a 10 s reply
    return mouth, turn, out


def _cleared(out):
    return any(m.get("event") == "clear" for m in out)


@pytest.mark.parametrize("gate", [False, True])
def test_a_stray_key_does_not_stop_the_voice_in_a_talk_call(monkeypatch, gate):
    monkeypatch.setattr(tunables, "CUT_IN_GATE", gate)
    mouth, turn, out = _reply(monkeypatch=monkeypatch)
    turn.push_key("5")
    assert not _cleared(out) and mouth.playing
    key = turn.get_valid_key()                       # still comes through, so the talk logs "keys are off"
    assert isinstance(key, Digit) and key.digit == "5" and key.cut_clip == ""
    assert turn.prompt_open                          # it answered nothing


@pytest.mark.parametrize("gate", [False, True])
def test_key_9_stops_the_voice_even_after_a_stray_key_in_the_same_reply(monkeypatch, gate):
    monkeypatch.setattr(tunables, "CUT_IN_GATE", gate)
    mouth, turn, out = _reply(monkeypatch=monkeypatch)
    turn.push_key("5")
    assert turn.get_valid_key().digit == "5"
    turn.push_key("9")
    assert _cleared(out) and not mouth.playing
    key = turn.get_valid_key()
    assert key is not None and key.digit == "9" and key.cut_clip == "answer"


def test_key_9_is_not_acted_on_when_the_photo_link_is_off(monkeypatch):
    mouth, turn, out = _reply(photo=False, monkeypatch=monkeypatch)
    turn.push_key("9")
    assert not _cleared(out) and mouth.playing


def test_the_greeting_still_stops_for_a_language_key_in_a_talk_call(monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    out: list[dict] = []
    mouth = Mouth(out.append, "S")
    turn = Turn(mouth)
    n = turn.start_prompt("greeting_trilingual")
    mouth.play([("greeting_trilingual", b"\x10" * 80000)], tag=(n, "greeting_trilingual"))
    turn.push_key("2")
    assert _cleared(out)
    assert turn.get_valid_key().digit == "2"


def test_the_keys_path_is_untouched(monkeypatch):
    mouth, turn, out = _reply(talk=False, monkeypatch=monkeypatch)
    turn.push_key("5")
    assert _cleared(out) and not mouth.playing
    key = turn.get_valid_key()
    assert key.digit == "5" and key.cut_clip == "answer" and not turn.prompt_open


# --- 2.4: keys, in a whole talk call ---------------------------------------------------

def _at(res, name, nth, plus):
    """When the nth sentence of the FIRST REPLY starts (the hello is two sentences before it), plus a little."""
    return [c for c in res.clips if c["name"] == name][2 + nth]["start"] + plus


@pytest.mark.parametrize("gate", [False, True])
def test_a_stray_key_mid_reply_does_not_chop_the_reply(gate):
    plain = te.run_call("ask", gate)
    for nth in (0, 2):          # while the reply is still being made (the key is for an older sentence) and while the talk waits
        res = te.run_call("ask", gate, te._inject("key", _at(plain, "answer", nth, 0.3)))
        assert te.check(res) == []
        assert [c for c in res.clips if c["name"] == "answer" and c["cut_at"] is not None] == []
        assert res.clears == []
        assert [r for r in res.rows if r.get("event") == "key" and r.get("value") == "5"]    # it was seen
        assert [c["name"] for c in res.clips][:5] == [c["name"] for c in plain.clips][:5]   # every sentence said


@pytest.mark.parametrize("gate", [False, True])
def test_a_stray_key_while_the_talk_waits_is_logged_keys_are_off(gate):
    plain = te.run_call("ask", gate)
    res = te.run_call("ask", gate, te._inject("key", _at(plain, "answer", 2, 0.3)))   # all three sentences are queued: the talk waits
    assert [(r["key"], r["means"]) for r in res.log_rows if r.get("ev") == "key" and r["key"] == "5"] == [("5", "keys are off")]


@pytest.mark.parametrize("gate", [False, True])
def test_key_9_mid_reply_stops_it_and_the_link_line_is_said(gate):
    plain = te.run_call("ask", gate)
    res = te.run_call("ask", gate, te._inject("key9", _at(plain, "answer", 2, 0.3)))   # the talk waits: the key reaches it
    assert te.check(res) == []
    assert [c for c in res.clips if c["cut_at"] is not None]
    assert [r["means"] for r in res.log_rows if r.get("ev") == "key" and r["key"] == "9"] == ["send the photo link"]
    said = [r["text"] for r in res.log_rows if r.get("ev") == "said" and r.get("tokens") == ["answer"]]
    assert "I have sent the link to your phone." in said     # the first sentence of prompt.PHOTO["sent"]


# --- 2.3: words over the greeting ------------------------------------------------------

def _heard(res):
    return [r["text"] for r in res.log_rows if r.get("ev") == "heard"]


def test_real_words_over_the_greeting_stop_it_and_are_turn_one_with_the_gate_on():
    res = te.run_call("g_words", True)
    assert te.check(res) == []
    greeting = [c for c in res.clips if c["name"] == "greeting_trilingual"]
    assert greeting[0]["cut_at"] is not None                      # the greeting was stopped
    assert _heard(res)[0] == "i need a scheme for farming"        # and the words are turn 1, whole
    assert any("the talk starts" in line for _t, line in res.lines)


def test_the_greeting_plays_whole_with_the_gate_off():
    res = te.run_call("g_words", False)
    assert te.check(res) == []
    assert [c for c in res.clips if c["name"] == "greeting_trilingual"][0]["cut_at"] is None
    assert res.clears == []


def test_one_word_over_the_greeting_does_not_end_it():
    res = te.run_call("g_one_word", True)
    assert te.check(res) == []
    assert not any("the talk starts" in line for _t, line in res.lines)   # "ok" is not turn 1
    assert len([c for c in res.clips if c["name"] == "greeting_trilingual"]) >= 2   # it was said again, whole
    assert _heard(res)[0] == "i need a scheme for farming"


def test_noise_over_the_greeting_does_nothing():
    res = te.run_call("ask", True, te._inject("noise", 0.3))
    assert te.check(res) == []
    assert _heard(res)[0] == "i need a scheme for farming"
    assert not any("the talk starts" in line for _t, line in res.lines)


def test_a_language_said_over_the_greeting_is_the_pick_not_a_false_cut(monkeypatch):
    monkeypatch.setitem(te.SCRIPTS, "g_lang", [("over", 0.3, "english please", 1.2, False), te.BYE])
    res = te.run_call("g_lang", True)
    assert te.check(res) == []
    assert any(line == "<- voice: language en" for _t, line in res.lines)
    assert _heard(res) == ["thank you goodbye"]                   # no first words: the talk says its own hello


# --- 2.5: say it again after a cut -----------------------------------------------------

def _cut_again_call(gate):
    plain = te.run_call("ask", gate)
    # over the second sentence of the first reply
    return te.run_call("ask", gate, te._inject("cut_again", _at(plain, "answer", 1, 0.3)))


def test_say_it_again_over_the_agent_starts_at_the_cut_sentence_and_the_log_says_what_was_not_heard():
    res = _cut_again_call(True)
    assert te.check(res) == []
    cut = [r for r in res.log_rows if r.get("ev") == "cut"]
    assert len(cut) == 1 and cut[0]["by"] == "speech" and cut[0]["clip"] == "answer"
    assert cut[0]["unsaid"] == ["It has a second short part.", "Do you want to hear more?"]   # not the top sentence
    again = [r for r in res.log_rows if r.get("ev") == "act" and r.get("action") == "repeat"]
    assert again and again[0]["again"] is True
    # nothing was said as new text for the repeat: the cut sentence and the rest were sent again, 2 clips
    said_after = [r for r in res.log_rows if r.get("ev") == "said" and r["t"] > again[0]["t"]]
    assert said_after == [] or said_after[0]["text"] != "This is reply b about the scheme."


def test_with_the_gate_off_nothing_cuts_the_reply_and_no_row_has_unsaid():
    res = _cut_again_call(False)          # strict turns: the words over the reply are not heard at all
    assert te.check(res) == []
    assert not [r for r in res.log_rows if "unsaid" in r or r.get("ev") == "cut"]
    assert res.clears == []
    texts = [r["text"] for r in res.log_rows if r.get("ev") == "said" and r.get("tokens") == ["answer"]]
    assert texts.count("This is reply b about the scheme.") == 1       # said whole, once


def test_a_cough_that_cut_the_agent_writes_no_unsaid_and_loses_nothing():
    plain = te.run_call("ask", True)
    res = te.run_call("ask", True, te._inject("hmm", _at(plain, "answer", 1, 0.3)))
    assert te.check(res) == []
    assert not [r for r in res.log_rows if "unsaid" in r]


# --- 2.5 on the talk loop alone --------------------------------------------------------

def _talk(corpus, tmp_path, monkeypatch, gate, again_result):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "CUT_IN_GATE", gate)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())

    class Audio(CutAudio):
        def say_cut_again(self):
            self.again += 1
            return again_result

    audio = Audio([Speech("what is PM Kisan"), Speech("wait, say it again", cut_clip="answer", heard_ms=300)])
    client = Client([_say("It is a scheme for farmer families."), {"action": "repeat", "say": ""}], 0.0)
    log = Log.open("talk_cut_again", corpus.snapshot_id, logs_dir=str(tmp_path))
    Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
    return audio, log_text.read_rows(log.path)


def test_a_repeat_that_cut_the_agent_goes_on_from_the_cut_sentence_not_the_top(corpus, tmp_path, monkeypatch):
    audio, rows = _talk(corpus, tmp_path, monkeypatch, True, True)
    assert audio.again == 1 and audio.answers == ["It is a scheme for farmer families."]
    assert [r.get("again") for r in rows if r.get("ev") == "act"] == [None, True]


def test_a_repeat_with_nothing_cut_to_say_again_is_the_whole_reply(corpus, tmp_path, monkeypatch):
    audio, _ = _talk(corpus, tmp_path, monkeypatch, True, False)
    assert audio.answers == ["It is a scheme for farmer families."] * 2


def test_a_repeat_with_the_gate_off_never_asks_for_the_cut_sentence(corpus, tmp_path, monkeypatch):
    audio, rows = _talk(corpus, tmp_path, monkeypatch, False, True)
    assert audio.again == 0 and audio.answers == ["It is a scheme for farmer families."] * 2
    assert "again" not in [k for r in rows if r.get("action") == "repeat" for k in r]


def test_the_cut_row_has_unsaid_only_when_there_is_something_unsaid(corpus, tmp_path):
    from haqdaar.engine.call import _LoggedAudio

    class Real:
        unsaid = ["One.", "Two."]

    log = Log.open("cut_row", corpus.snapshot_id, logs_dir=str(tmp_path))
    audio = _LoggedAudio(Real(), log, corpus)
    audio._cut(Speech("go on please", cut_clip="answer", heard_ms=200))
    Real.unsaid = []
    audio._cut(Speech("go on please", cut_clip="answer", heard_ms=200))
    cuts = [r for r in log_text.read_rows(log.path) if r.get("ev") == "cut"]
    assert cuts[0]["unsaid"] == ["One.", "Two."] and "unsaid" not in cuts[1]
