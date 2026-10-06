"""PLAN 9, step N2: keys and the voice for every question, the answer said back, one read-back.
Fake model, fake audio, no network. The hint tests use a small synthetic corpus (as test_ask_first does)."""
from types import SimpleNamespace

import pytest

from haqdaar.audio.turn import Turn
from haqdaar.contracts import tunables
from haqdaar.contracts.types import SEVEN_BOXES, UNASKED, Digit, Hangup, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.engine import talk_pick
from haqdaar.engine.talk import _Talk
from haqdaar.prompts import talk as prompt
from tests.test_ask_first import Synth, _talk
from tests.test_qa_engine import QAAudio
from tests.test_talk import Client


@pytest.fixture(scope="module")
def corpus():
    return Corpus.load("CURRENT")


@pytest.fixture(scope="module")
def idx():
    return scheme_index.SchemeIndex.load("CURRENT", embed=lambda texts: 1 / 0)


FARM = "I need help with farming"      # farming: 4 schemes fit, the picker asks work (7 values live)
ASK = {"action": "ask", "say": "What work do you do?", "ask_box": "occupation", "facts": {}, "scheme": ""}
OK = {"action": "answer", "say": "Okay.", "facts": {}, "scheme": ""}
HINT7 = ("Press 1 for Farmer, 2 for Street vendor, 3 for Apprentice, 4 for Own business, 5 for Artisan, "
         "7 for more, 0 if you do not know.")
RB_HINT = prompt.READ_BACK_HINT["en"]


def _run(corpus, idx, tmp_path, inputs, replies, first=FARM):
    """The talk's own loop on a script: the inputs after the first words, then the line drops."""
    audio, client = QAAudio(list(inputs) + [Hangup()], "en"), Client(replies)
    log = Log.open("askkeys", corpus.snapshot_id, logs_dir=str(tmp_path))
    t = _Talk(audio, SimpleNamespace(client=client), corpus, log, "en", idx)
    t.run(first)
    return t, audio, client


def _note(prompt_text):
    return prompt_text.split("NOTE:", 1)[1] if "NOTE:" in prompt_text else ""


def _schemes_block(text):
    return text.split("SCHEMES (", 1)[1].split("SCHEME IN TALK:", 1)[0]


def _keys_rows(t):
    return [r for r in log_text.read_rows(t.log.path) if r.get("ev") == "key"]


# --- the hint, from the values still alive in the list -------------------------------

def _synth(box, counts):
    """One scheme per count: scheme n holds the value of its group."""
    return Synth([{box: (v,)} for v, n in counts.items() for _ in range(n)])


def _hint_of(corpus, tmp_path, idx, synth, box, quiet=0):
    t = _talk(corpus, tmp_path, idx, "hint")
    t.corpus, t.left, t.last_asked = synth, tuple(synth._scheme_ids), box
    return t, t._add_keys("ask", "Q?", quiet)


def test_two_live_values_two_keys_and_zero(corpus, tmp_path, idx):
    t, say = _hint_of(corpus, tmp_path, idx, _synth("gender", {"female": 3, "male": 2}), "gender")
    assert say == "Q? Press 1 for Woman, 2 for Man, 0 if you do not know."
    assert t._kmap == {"1": "female", "2": "male", "0": "UNKNOWN"}


def test_keys_follow_how_many_left_schemes_hold_each_value(corpus, tmp_path, idx):
    synth = _synth("occupation", {"artisan": 1, "farmer": 4, "weaver": 2, "worker": 3})   # corpus order is not the order said
    _t, say = _hint_of(corpus, tmp_path, idx, synth, "occupation")
    assert say == "Q? Press 1 for Farmer, 2 for Worker, 3 for Weaver, 4 for Artisan, 0 if you do not know."


def test_a_value_no_left_scheme_holds_has_no_key(corpus, tmp_path, idx):
    synth = _synth("occupation", {"farmer": 2, "weaver": 1, "worker": 1})
    assert talk_pick.live_values("occupation", synth._scheme_ids[:2], synth) == ["farmer"]
    assert talk_pick.live_values("occupation", synth._scheme_ids, synth) == ["farmer", "weaver", "worker"]


def test_more_than_five_values_put_five_on_the_keys_and_seven_says_the_next(corpus, tmp_path, idx):
    vals = ["farmer", "street_vendor", "apprentice", "entrepreneur", "artisan", "weaver", "worker"]
    synth = _synth("occupation", {v: 7 - n for n, v in enumerate(vals)})
    t, say = _hint_of(corpus, tmp_path, idx, synth, "occupation")
    assert say == "Q? " + HINT7
    assert t._krest == ["weaver", "worker"] and "6" not in t._kmap and "9" not in t._kmap   # 6 and 9 keep their jobs
    assert t._key_words("7") is None                                # said by code, no model turn
    assert t._kmap == {"1": "weaver", "2": "worker", "0": "UNKNOWN"} and t._krest == []
    assert t._key_words("7") is None and t.no_reply == 1             # "7" has no page left: the hint again, a quiet turn


def test_age_has_no_keys(corpus, tmp_path, idx):
    synth = Synth([{"age": ("18-35",)}, {"age": ("36-39",)}, {"age": ("41-79",)}])
    t, say = _hint_of(corpus, tmp_path, idx, synth, "age")
    assert say == "Q?" and t._kmap == {}


def test_full_hint_on_the_first_two_questions_and_after_no_usable_reply_then_only_the_pairs(corpus, tmp_path, idx):
    synth = _synth("gender", {"female": 3, "male": 2})
    t, _ = _hint_of(corpus, tmp_path, idx, synth, "gender")
    assert "0 if you do not know" in t._add_keys("ask", "Q?", 0)              # the second question
    third = t._add_keys("ask", "Q?", 0)
    assert third == "Q? Press 1 for Woman, 2 for Man." and t._hinted == 3
    assert "0 if you do not know" in t._add_keys("ask", "Q?", -1)             # the last question got no usable reply


def test_the_hint_is_said_in_the_callers_language(corpus, tmp_path, idx):
    t = _talk(corpus, tmp_path, idx, "hint-hi")
    t.lang = "hi"
    t.corpus, t.left, t.last_asked = _synth("gender", {"female": 3, "male": 2}), tuple(f"s{n}" for n in range(5)), "gender"
    assert t._add_keys("ask", "Q?", 0) == "Q? महिला के लिए 1, पुरुष के लिए 2, पता न हो तो 0 दबाइए।"


# --- a key while a question stands ---------------------------------------------------

def test_the_question_is_followed_by_its_keys_and_key_1_sets_the_value_by_key(corpus, idx, tmp_path):
    t, audio, client = _run(corpus, idx, tmp_path, [Digit("1")], [ASK, OK])
    assert audio.answers[:2] == ["What work do you do?", HINT7]
    assert t.bv["occupation"] == "farmer"
    assert "JUST HEARD: their work = Farmer (by key)" in _note(client.calls[1])
    assert 'Start your reply by saying it back in a few words' in _note(client.calls[1])
    assert 'CALLER: "Farmer"' in client.calls[1]                      # the label is the caller's words in the log
    assert [r["means"] for r in _keys_rows(t)] == ["occupation = farmer"]


def test_a_spoken_answer_is_just_heard_by_voice(corpus, idx, tmp_path):
    t, _audio, client = _run(corpus, idx, tmp_path, [Speech("I am a farmer")], [ASK, OK])
    assert t.bv["occupation"] == "farmer"
    assert "their work = Farmer (by voice)" in _note(client.calls[1]) and "(by key)" not in client.calls[1]
    assert "the kind of help they want = Farming (by voice)" in _note(client.calls[0])


def test_key_0_is_i_do_not_know(corpus, idx, tmp_path):
    t, _audio, client = _run(corpus, idx, tmp_path, [Digit("0")], [ASK, OK])
    assert t.bv["occupation"] == "UNKNOWN"
    assert "their work = the caller does not know (by key)" in _note(client.calls[1])
    assert 'CALLER: "I do not know"' in client.calls[1]


def test_key_7_says_the_next_ones_and_the_next_key_picks_from_them(corpus, idx, tmp_path):
    t, audio, client = _run(corpus, idx, tmp_path, [Digit("7"), Digit("2")], [ASK, OK])
    assert audio.answers[2] == "Press 1 for Weaver, 2 for Worker, 0 if you do not know."
    assert len(client.calls) == 2 and t.bv["occupation"] == "worker"          # key 7 made no model turn


def test_a_key_with_no_meaning_says_the_hint_again_and_counts_as_no_usable_reply(corpus, idx, tmp_path):
    t, audio, client = _run(corpus, idx, tmp_path, [Digit("8")], [ASK])
    assert audio.answers == ["What work do you do?", HINT7, HINT7]
    assert len(client.calls) == 1 and t.no_reply == 1 and t.bv["occupation"] == UNASKED


def test_keys_6_and_9_keep_their_jobs_while_a_question_stands(corpus, idx, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "KEYS_IN_TALK", True)
    t = _Talk(QAAudio([Digit("6")], "en"), SimpleNamespace(client=Client([ASK])),
              corpus, Log.open("k6", corpus.snapshot_id, logs_dir=str(tmp_path)), "en", idx)
    got = t.run(FARM)
    assert isinstance(got, dict) and got["occupation"] == UNASKED          # to the keys part, nothing set
    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", True)
    monkeypatch.setattr("haqdaar.engine.talk.in_call.pending", lambda: None)
    monkeypatch.setattr("haqdaar.engine.talk.in_call.send_link", lambda *a, **k: {"sent": False, "token": "", "link": ""})
    t9, audio, client = _run(corpus, idx, tmp_path, [Digit("9")], [ASK])
    assert prompt.PHOTO["no_sms"]["en"] in audio.answers and len(client.calls) == 1 and t9.bv["occupation"] == UNASKED


def test_a_key_when_no_question_stands_does_what_it_did(corpus, idx, tmp_path):
    t, audio, client = _run(corpus, idx, tmp_path, [Digit("1")], [OK])      # the reply was an answer, not a question
    assert audio.answers == ["Okay."] and len(client.calls) == 1 and t.bv["occupation"] == UNASKED
    assert [r["means"] for r in _keys_rows(t)] == ["keys are off"]
    # age has no keys: a key after it is as before
    t3 = _talk(corpus, tmp_path, idx, "age-key")
    t3.last_asked, t3.left = "age", tuple(t3.corpus.scheme_id(n) for n in range(5))
    assert t3._add_keys("ask", "How old are you?", 0) == "How old are you?" and t3._kmap == {}


def test_the_audio_turn_lets_the_standing_keys_cut_the_voice(corpus, idx, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    turn = Turn.__new__(Turn)
    turn.keys_mode = False
    assert turn._talk_ignores("1", "x") is True                              # as before: a stray key
    t = _talk(corpus, tmp_path, idx, "turn")
    t.audio = SimpleNamespace(turn=turn)
    t._kmap, t._krest = {"1": "farmer", "0": "UNKNOWN"}, ["worker"]
    t._open_keys()
    assert turn._talk_ignores("1", "x") is False and turn._talk_ignores("0", "x") is False
    assert turn._talk_ignores("7", "x") is False and turn._talk_ignores("5", "x") is True
    t._kmap, t._krest = {}, []
    t._open_keys()
    assert turn._talk_ignores("1", "x") is True


# --- the one read-back ------------------------------------------------------------

def _readback_turn(corpus, idx, tmp_path, inputs, replies):
    return _run(corpus, idx, tmp_path, [Digit("1"), *inputs], [ASK, *replies])


def test_the_read_back_comes_before_the_first_schemes_and_holds_the_scheme_text_back(corpus, idx, tmp_path):
    say = {"action": "answer", "say": "You are a farmer who needs farming help. Is that right?", "facts": {}, "scheme": ""}
    t, audio, client = _readback_turn(corpus, idx, tmp_path, [], [say])
    ask = client.calls[1]
    assert "READ BACK NOW: farmer, needs help with farming" in _note(ask)
    assert "mark: " not in ask and "[pm-kisan]" not in _schemes_block(ask)       # no scheme text in the read-back
    assert "Do not ask \"is that right?\"" not in ask                              # the old recap rule does not fight it
    assert audio.answers[-2:] == ["Is that right?", RB_HINT] and t._rb == "open"


def test_yes_by_key_shows_the_schemes_and_there_is_no_second_read_back(corpus, idx, tmp_path):
    rb = {"action": "answer", "say": "Farmer, farming. Is that right?", "facts": {}, "scheme": ""}
    show = {"action": "show_scheme", "say": "PM Kisan helps farmers.", "scheme": "pm-kisan", "facts": {}, "parts": []}
    t, audio, client = _readback_turn(corpus, idx, tmp_path, [Digit("1"), Speech("tell me more")], [rb, show, OK])
    assert 'CALLER: "Yes"' in client.calls[2] and "mark: " in client.calls[2] and "NEXT QUESTION: none" in client.calls[2]
    assert "name the one or two best schemes" in _note(client.calls[2]) and "READ BACK NOW" not in client.calls[2]
    assert show["say"] in audio.answers
    assert t._rb == "done" and "READ BACK NOW" not in client.calls[3]
    assert audio.answers.count(RB_HINT) == 1                                  # said once


def test_yes_by_voice_shows_the_schemes(corpus, idx, tmp_path):
    rb = {"action": "answer", "say": "Farmer, farming. Is that right?", "facts": {}, "scheme": ""}
    show = {"action": "show_scheme", "say": "PM Kisan helps farmers.", "scheme": "pm-kisan", "facts": {}, "parts": []}
    t, _audio, client = _readback_turn(corpus, idx, tmp_path, [Speech("yes")], [rb, show])
    assert "mark: " in client.calls[2] and t._rb == "done"


def test_anything_else_after_the_read_back_is_a_normal_turn_and_it_counts_as_done(corpus, idx, tmp_path):
    rb = {"action": "answer", "say": "Farmer, farming. Is that right?", "facts": {}, "scheme": ""}
    t, _audio, client = _readback_turn(corpus, idx, tmp_path, [Speech("what is the website of pm kisan")], [rb, OK])
    assert t._rb == "done" and "READ BACK NOW" not in client.calls[2]


def test_no_asks_which_is_wrong_then_a_fixed_fact_earns_one_more_read_back_then_schemes(corpus, idx, tmp_path):
    rb = {"action": "answer", "say": "Farmer, farming. Is that right?", "facts": {}, "scheme": ""}
    which = {"action": "answer", "say": "Which one is wrong?", "facts": {}, "scheme": ""}
    fix = {"action": "answer", "say": "Okay.", "facts": {"occupation": "weaver"}, "scheme": ""}
    rb2 = {"action": "answer", "say": "Weaver, farming. Is that right?", "facts": {}, "scheme": ""}
    show = {"action": "show_scheme", "say": "PM Kisan helps farmers.", "scheme": "pm-kisan", "facts": {}, "parts": []}
    t, audio, client = _readback_turn(corpus, idx, tmp_path, [Digit("2"), Speech("my work is weaving"), Digit("2")],
                                      [rb, which, fix, rb2, show])
    assert "CALLER SAYS A FACT IS WRONG" in client.calls[2] and "mark: " not in client.calls[2]
    assert audio.answers.count(RB_HINT) >= 1
    # the fixed fact came in the model's words: the same turn asks again, with the new fact
    assert "READ BACK NOW: weaver, needs help with farming" in client.calls[4] and "mark: " not in client.calls[4]
    assert t.bv["occupation"] == "weaver"
    # the second read-back is answered "no" by key: no third read-back, schemes follow
    assert "READ BACK NOW" not in client.calls[5] and "mark: " in client.calls[5] and t._rb == "done"
    assert audio.answers.count(RB_HINT) == 2


def test_just_tell_me_and_a_named_scheme_skip_the_read_back(corpus, idx, tmp_path):
    show = {"action": "show_scheme", "say": "PM Kisan helps farmers.", "scheme": "pm-kisan", "facts": {}, "parts": []}
    t, _a, client = _run(corpus, idx, tmp_path, [Speech("just tell me, I am a farmer")], [ASK, show])
    assert t.bv["occupation"] == "farmer" and "READ BACK NOW" not in client.calls[1] and "mark: " in client.calls[1]
    assert t._rb == ""
    t2, _a, client = _run(corpus, idx, tmp_path, [Speech("I am a farmer, tell me about pm kisan")],
                          [ASK, {"action": "answer", "say": "It helps farmers.", "scheme": "pm-kisan", "facts": {}}])
    assert "READ BACK NOW" not in client.calls[1] and "[pm-kisan]" in _schemes_block(client.calls[1]) and t2._rb == ""


def test_a_show_scheme_in_place_of_the_read_back_is_sent_back_and_then_the_fixed_words_are_said(corpus, idx, tmp_path):
    show = {"action": "show_scheme", "say": "PM Kisan helps farmers.", "scheme": "pm-kisan", "facts": {}, "parts": []}
    t, audio, client = _readback_turn(corpus, idx, tmp_path, [], [show, show])
    assert len(client.calls) == 3 and "Do not use show_scheme" in client.calls[2]
    assert audio.answers[-3:] == ["So you told me: Farming, Farmer.", "Is that right?", RB_HINT] and t._rb == "open"


# --- the switch ----------------------------------------------------------------------

def test_switch_off_has_no_keys_no_say_back_and_no_read_back(corpus, idx, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ASK_FIRST", False)
    t, audio, client = _run(corpus, idx, tmp_path, [Digit("1"), Speech("I am a farmer")],
                            [ASK, {"action": "show_scheme", "say": "PM Kisan helps farmers.", "scheme": "pm-kisan",
                                   "facts": {}, "parts": []}])
    assert audio.answers[0] == "What work do you do?" and len(audio.answers) == 2     # no hint
    assert [r["means"] for r in _keys_rows(t)] == ["keys are off"]
    assert all("JUST HEARD" not in c and "READ BACK" not in c for c in client.calls) and t._rb == ""
