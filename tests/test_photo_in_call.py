"""Steps 4.2 / 4.3: the photo link offered in a talk call, and the call-back that opens the next call.
Fake model, fake audio, fake SMS, PHOTO_DIR in a temp folder. No network, no money."""
import io
import json
import os
import urllib.parse
from types import SimpleNamespace

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Hangup, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.engine import talk as talk_mod
from haqdaar.engine import talk_follow
from haqdaar.engine.call import Engine
from haqdaar.photo import cases, in_call
from haqdaar.prompts import talk as prompt

from tests.test_step18_followup import FIRST_IDS, LangAudio, NamedIndex
from tests.test_talk import Client, _say

NUMBER = "+919999900001"
P = prompt.PHOTO


@pytest.fixture
def photo_dir(tmp_path, monkeypatch):
    folder = tmp_path / "photo"
    monkeypatch.setenv("PHOTO_DIR", str(folder))
    monkeypatch.delenv("CALL_ME_NUMBER", raising=False)
    return folder


@pytest.fixture
def sms(monkeypatch):
    sent = []
    monkeypatch.setattr(in_call, "_sms", lambda to, text: sent.append((to, text)) or "SM1")
    return sent


# --- twilio.send_sms ---

def test_send_sms_request(monkeypatch):
    from haqdaar.audio.telephony import twilio

    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_x")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_US_PHONE_NUMBER", "+14240000000")
    seen = {}

    def fake_open(req):
        seen["req"] = req
        return io.BytesIO(b'{"sid": "SM_new"}')

    assert twilio.send_sms("+910000000000", "hello", fake_open) == "SM_new"
    assert seen["req"].full_url.endswith("/Accounts/AC_x/Messages.json")
    form = urllib.parse.parse_qs(seen["req"].data.decode())
    assert form["To"] == ["+910000000000"] and form["From"] == ["+14240000000"] and form["Body"] == ["hello"]


# --- in_call.send_link ---

def test_send_link_texts_the_callers_number(photo_dir, sms):
    out = in_call.send_link("en", ["en"], NUMBER)
    assert out["sent"] and out["link"].endswith("/p/" + out["token"])
    assert sms[0][0] == NUMBER and sms[0][1] == f"Haqdaar: send your photo here: {out['link']}" and len(sms[0][1]) < 120
    assert cases.get(out["token"]).lang == "en"


def test_send_link_uses_the_owner_number_when_there_is_none(photo_dir, sms, monkeypatch):
    monkeypatch.setenv("CALL_ME_NUMBER", "+918888800002")
    assert in_call.send_link("en", ["en"], "")["sent"]
    assert sms[0][0] == "+918888800002"


def test_send_link_with_no_number_sends_nothing(photo_dir, sms):
    out = in_call.send_link("en", ["en"], "")
    assert not out["sent"] and out["why"] == "no number" and sms == [] and out["token"]


def test_send_link_never_raises_on_an_sms_fault(photo_dir):
    def boom(to, text):
        raise RuntimeError("down")

    out = in_call.send_link("en", ["en"], NUMBER, sms=boom)
    assert not out["sent"] and "RuntimeError" in out["why"]


# --- in_call.pending / done ---

def _ready(lang="en", **finding):
    case = cases.new_case(lang, NUMBER)
    cases.set_finding(case.token, {"shows": "a wall", "wrong": "", "sure": 0.9, "by": "muse", **finding}, "", "I see a wall.")
    (cases._base_dir() / "next_call.json").write_text(
        json.dumps({"token": case.token, "lang": lang, "say": "I see a wall.", "made": case.made}))
    return case


def test_pending_is_none_when_missing_or_broken(photo_dir):
    assert in_call.pending() is None
    photo_dir.mkdir(parents=True)
    (photo_dir / "next_call.json").write_text("{not json")
    assert in_call.pending() is None


def test_pending_good_photo(photo_dir):
    case = _ready()
    assert in_call.pending() == {"token": case.token, "lang": "en", "say": "I see a wall.", "bad": False}


def test_pending_is_none_when_old(photo_dir):
    _ready()
    path = photo_dir / "next_call.json"
    old = path.stat().st_mtime - tunables.PHOTO_PENDING_S - 5
    os.utime(path, (old, old))
    assert in_call.pending() is None


def test_damage_seen_in_the_photo_is_a_good_read(photo_dir):
    _ready(wrong="The leaves have brown spots.")
    assert in_call.pending()["bad"] is False


@pytest.mark.parametrize("finding", [{"wrong": "helper: not clear"}, {"shows": ""}, {"sure": 0.1}, {"by": "stand-in"}])
def test_pending_bad_by_each_rule(photo_dir, finding):
    _ready(**finding)
    assert in_call.pending()["bad"] is True


def test_done_good_marks_called_and_removes_the_file(photo_dir):
    case = _ready()
    in_call.done(case.token, False)
    assert not (photo_dir / "next_call.json").exists() and cases.get(case.token).state == "called"


def test_done_bad_opens_the_same_link_again(photo_dir):
    case = _ready(sure=0.1)
    in_call.done(case.token, True)
    got = cases.get(case.token)
    assert not (photo_dir / "next_call.json").exists() and got.state == "waiting" and got.finding == {}


# --- the words ---

@pytest.mark.parametrize("words", ["photo bhejna hai", "फोटो भेजूं", "can I send a photo", "मैं फोटो दिखा सकता हूँ",
                                   "dikha sakta hoon", "फोटो पाठवू का", "can i send you a picture"])
def test_photo_ask(words):
    assert talk_follow.photo_ask(words)


@pytest.mark.parametrize("words", ["i need a pension", "my house is old", "मुझे घर चाहिए"])
def test_not_photo_ask(words):
    assert not talk_follow.photo_ask(words) and not talk_follow.photo_seen(words)


@pytest.mark.parametrize("words", ["my crop is spoiled", "फसल खराब हो गई", "घर गिर गया", "गाय बीमार है", "पीक खराब झाले",
                                   "the field is flooded"])
def test_photo_seen(words):
    assert talk_follow.photo_seen(words)


def test_yes_and_no_are_short_answers():
    assert talk_follow.yes("yes") and talk_follow.yes("हाँ जी भेज दो") and talk_follow.yes("होय")
    assert talk_follow.no("no") and talk_follow.no("नहीं") and talk_follow.no("नको")
    assert not talk_follow.yes("no not now") and not talk_follow.yes("yes I want to know about the pension scheme")


# --- the talk ---

@pytest.fixture(scope="module")
def corpus():
    return Corpus.load("CURRENT")


@pytest.fixture
def call(corpus, tmp_path, monkeypatch, photo_dir, sms):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": NamedIndex(FIRST_IDS))
    made = []

    def go(inputs, replies, lang="en", number=NUMBER, setup=None):
        made.append(1)
        audio, client = LangAudio(inputs, lang), Client(replies, 0.0)
        audio.caller_number = number
        log = Log.open(f"photo_{len(made)}", corpus.snapshot_id, logs_dir=str(tmp_path))
        Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
        return audio, client, log_text.read_rows(log.path)

    return go


def _said(audio):
    """Every sentence said after the hello, as one text (the audio gets one sentence at a time)."""
    return " ".join(audio.answers).removeprefix(prompt.HELLO["en"]).removeprefix(prompt.HELLO["hi"]).strip()


def _photo_rows(rows):
    return [r for r in rows if r.get("ev") == "photo"]


def test_ask_offer_yes_sends_the_link(call, sms):
    audio, client, rows = call([Speech("can I send a photo"), Speech("yes")], [])
    assert _said(audio) == P["offer"]["en"] + " " + P["sent"]["en"]
    assert client.calls == []                                   # no model call for either
    assert [r["what"] for r in _photo_rows(rows)] == ["offer", "link"]
    assert _photo_rows(rows)[1]["sms"] is True and _photo_rows(rows)[1]["link"].startswith("http")
    assert len(sms) == 1 and sms[0][0] == NUMBER
    assert NUMBER not in json.dumps(rows) and NUMBER[3:] not in json.dumps(rows)
    assert [r["action"] for r in rows if r.get("ev") == "act"] == ["photo_offer", "photo_link"]


def test_yes_with_no_sms_says_so(call, sms):
    audio, _, rows = call([Speech("can I send a photo"), Speech("yes")], [], number="")
    assert _said(audio).endswith(P["no_sms"]["en"]) and sms == []
    assert [r["what"] for r in _photo_rows(rows)] == ["offer", "no_sms"]


def test_no_says_all_right_and_the_last_question_again(call):
    audio, _, _ = call(
        [Speech("pension schemes"), Speech("can I send a photo"), Speech("no")],
        [_say("There is a widow pension. Do you want to hear more?")])
    assert _said(audio).endswith("All right. Do you want to hear more?")


def test_no_with_no_earlier_question_is_only_all_right(call):
    audio, _, _ = call([Speech("can I send a photo"), Speech("no")], [])
    assert _said(audio).endswith("All right.") and not _said(audio).endswith("more? All right.")


def test_other_words_close_the_offer_and_the_turn_runs_as_usual(call, sms):
    audio, client, rows = call(
        [Speech("can I send a photo"), Speech("tell me about pension"), Speech("yes")],
        [_say("There is a pension scheme."), _say("It is for old people.")])
    assert len(client.calls) == 2 and "There is a pension scheme. It is for old people." in _said(audio)
    assert sms == [] and [r["what"] for r in _photo_rows(rows)] == ["offer"]   # the late "yes" is no longer an answer


def test_a_seen_need_adds_one_sentence_once(call):
    audio, _, rows = call(
        [Speech("my crop is spoiled"), Speech("my house fell"), Speech("yes")],
        [_say("There is a crop scheme."), _say("There is a housing scheme.")])
    assert _said(audio) == "There is a crop scheme. " + P["seen"]["en"] + " There is a housing scheme."   # added once a call
    assert [r["what"] for r in _photo_rows(rows)] == ["offer"]


def test_yes_after_the_added_sentence_sends_the_link(call, sms):
    audio, _, rows = call([Speech("my crop is spoiled"), Speech("yes")], [_say("There is a crop scheme.")])
    assert _said(audio).endswith(P["sent"]["en"]) and len(sms) == 1


def test_key_9_with_and_without_an_offer_then_a_second_key_9(call, sms):
    audio, client, rows = call([Digit("9"), Digit("9")], [])
    assert _said(audio) == P["sent"]["en"] + " " + P["already"]["en"] and len(sms) == 1
    assert client.calls == []
    audio, _, rows = call([Speech("can I send a photo"), Digit("9")], [])
    assert _said(audio) == P["offer"]["en"] + " " + P["sent"]["en"] and len(sms) == 2


def test_other_keys_stay_off(call):
    _, _, rows = call([Digit("5")], [])
    assert [r["means"] for r in rows if r.get("ev") == "key" and r["key"] == "5"] == ["keys are off"]


def test_fixed_lines_leave_last_say_alone(call):
    audio, _, _ = call(
        [Speech("pension schemes"), Speech("can I send a photo"), Speech("no"), Speech("say that again")],
        [_say("There is a widow pension. Do you want to hear more?"), {"action": "repeat", "say": "", "facts": {}, "scheme": "", "ask_box": ""}])
    assert _said(audio).endswith("There is a widow pension. Do you want to hear more?")


def test_hindi_lines(call):
    audio, _, _ = call([Speech("फोटो भेजना है"), Speech("हाँ")], [], lang="hi")
    assert _said(audio) == P["offer"]["hi"] + " " + P["sent"]["hi"]


def test_langs_spoken_in_order_with_no_repeats_and_a_cap(corpus, photo_dir, monkeypatch):
    class Audio:
        language = "en"

    talk = talk_mod._Talk(Audio(), None, corpus, None, "hi", NamedIndex(FIRST_IDS))
    for lang in ("en", "hi", "mr", "en", "gu", "ta", "mr"):
        talk.lang = lang
        talk._note_lang()
    assert talk.langs_spoken == ["hi", "en", "mr", "gu"]


def test_call_back_good_photo_opens_the_call(call, photo_dir):
    case = _ready()
    audio, _, rows = call([Speech("how are you")], [_say("Fine.")])
    assert _said(audio).startswith(P["back"]["en"] + " I see a wall.")
    assert not (photo_dir / "next_call.json").exists() and cases.get(case.token).state == "called"
    assert [r["what"] for r in _photo_rows(rows)] == ["back"]


def test_call_back_bad_photo_asks_again(call, photo_dir):
    case = _ready(sure=0.1)
    audio, _, rows = call([Hangup()], [])
    assert _said(audio) == P["bad"]["en"]
    assert cases.get(case.token).state == "waiting"
    assert [r["what"] for r in _photo_rows(rows)] == ["bad"]


def test_call_back_comes_before_the_first_words(corpus, tmp_path, monkeypatch, photo_dir, sms):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": NamedIndex(FIRST_IDS))
    _ready()
    audio, client = LangAudio([], "en"), Client([_say("Here is a pension.")], 0.0)
    audio.first_words = "pension schemes"
    log = Log.open("photo_fw", corpus.snapshot_id, logs_dir=str(tmp_path))
    Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
    assert _said(audio) == P["back"]["en"] + " I see a wall. Here is a pension."


def test_photo_in_call_off_is_the_old_behaviour(call, monkeypatch, sms):
    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", False)
    _ready()
    audio, client, rows = call([Digit("9"), Speech("can I send a photo")], [_say("There is a scheme.")])
    assert [r["means"] for r in rows if r.get("ev") == "key" and r["key"] == "9"] == ["keys are off"]
    assert "There is a scheme." in audio.answers and not any("link" in a for a in audio.answers) and sms == [] and _photo_rows(rows) == []
    assert (cases._base_dir() / "next_call.json").exists()
