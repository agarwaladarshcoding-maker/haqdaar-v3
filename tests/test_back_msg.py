"""The call-back that never reached the caller: the answer goes by SMS, with a link to its sound.
Fake model, voice, SMS and clock; PHOTO_DIR in a temp folder. No network, no money, no real call."""
import io
import json
import queue
import sys
import threading
import urllib.parse
import wave
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from haqdaar.contracts import tunables
from haqdaar.photo import back_msg, cases, in_call
from haqdaar.prompts import talk as prompt
from tools import mac_call, photo_back, photo_desk

from tests.test_photo_in_call import NUMBER, _ready, photo_dir, sms  # noqa: F401  (fixtures)
from tests.test_talk import Client

ULAW = b"\xff" * 800            # 0.1 s of mu-law silence


class Voice:
    def __init__(self):
        self.said = []

    def speak(self, text, lang):
        self.said.append((text, lang))
        return ULAW


class DeadVoice:
    def speak(self, text, lang):
        raise RuntimeError("voice down")


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(tunables, "PHOTO_SHOW_LINK", False)
    monkeypatch.setattr(tunables, "PHOTO_FIRST_CALL", True)
    monkeypatch.setattr(tunables, "PHOTO_BACK_TRANSLATE", False)
    monkeypatch.setenv("PHOTO_BASE_URL", "https://photo.example")


def _model(reply):
    return SimpleNamespace(client=Client([reply]))


def _blocks(monkeypatch, first="CALLER: is this an Aadhaar card\nAGENT: send a photo", photo="a wall"):
    monkeypatch.setattr(in_call, "first_call_blocks", lambda token: (first, photo))


def _ready_no_number(lang="en"):
    case = cases.new_case(lang, "")
    cases.set_finding(case.token, {"shows": "a wall", "wrong": "", "sure": 0.9, "by": "muse"}, "", "I see a wall.")
    (cases._base_dir() / "next_call.json").write_text(
        json.dumps({"token": case.token, "lang": lang, "say": "I see a wall.", "made": case.made}))
    return case


# --- the text ---

def test_answer_is_the_models_when_it_is_usable(photo_dir, monkeypatch):
    case = _ready()
    _blocks(monkeypatch)
    text, lang = back_msg.answer_text(case.token, _model({"say": "It is a wall, not an Aadhaar card."}))
    assert (text, lang) == ("It is a wall, not an Aadhaar card.", "en")


@pytest.mark.parametrize("reply", [{"say": ""}, {"say": "x" * 321}, {"say": "यह दीवार है"}, None, {"other": 1}])
def test_answer_is_the_desk_text_when_the_model_is_not_usable(photo_dir, monkeypatch, reply):
    case = _ready()
    _blocks(monkeypatch)
    assert back_msg.answer_text(case.token, _model(reply)) == ("I see a wall.", "en")


def test_answer_is_the_desk_text_with_no_caller_words_and_the_model_is_not_asked(photo_dir, monkeypatch):
    case = _ready()
    _blocks(monkeypatch, first="AGENT: hello")
    model = _model({"say": "never"})
    assert back_msg.answer_text(case.token, model)[0] == "I see a wall." and model.client.calls == []


def test_answer_for_a_bad_photo_is_the_fixed_words(photo_dir):
    case = _ready(lang="hi", sure=0.1)
    assert back_msg.answer_text(case.token) == (prompt.PHOTO["bad"]["hi"], "hi")


def test_answer_is_translated_sentence_by_sentence_when_the_switch_is_on(photo_dir, monkeypatch):
    case = _ready(lang="hi")
    _blocks(monkeypatch, first="")
    seen = []
    monkeypatch.setattr(tunables, "PHOTO_BACK_TRANSLATE", True)
    text, lang = back_msg.answer_text(case.token, translate=lambda s, l: seen.append((s, l)) or f"[हि] {s}")
    assert (text, lang) == ("[हि] I see a wall.", "hi") and seen == [("I see a wall.", "hi")]
    monkeypatch.setattr(tunables, "PHOTO_BACK_TRANSLATE", False)
    assert back_msg.answer_text(case.token, translate=lambda s, l: "no")[0] == "I see a wall."


def test_no_case_gives_no_text(photo_dir):
    assert back_msg.answer_text("nosuchtoken") == ("", "")


# --- the sound ---

def test_sound_is_a_wav_file_that_opens(photo_dir):
    case = _ready()
    voice = Voice()
    link = back_msg.make_sound(case.token, "I see a wall.", "en", voice)
    assert link == f"https://photo.example/s/{case.token}.wav" and voice.said == [("I see a wall.", "en")]
    with wave.open(str(photo_dir / "sound" / f"{case.token}.wav")) as w:
        assert (w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()) == (tunables.SAMPLE_RATE, len(ULAW), 1, 2)


def test_a_voice_fault_gives_no_link_and_no_file(photo_dir):
    case = _ready()
    assert back_msg.make_sound(case.token, "I see a wall.", "en", DeadVoice()) == ""
    assert not (photo_dir / "sound").exists()


# --- send ---

def test_send_gives_one_sms_once_per_case(photo_dir, sms, monkeypatch):
    case = _ready()
    _blocks(monkeypatch)
    out = back_msg.send(case.token, "no-answer", model=_model({"say": "It is a wall."}), tts=Voice())
    assert out == {"token": case.token, "sent": True, "why": "no-answer"}
    link = f"https://photo.example/s/{case.token}.wav"
    assert sms == [(NUMBER, f"Haqdaar: It is a wall. Listen: {link}")]
    marker = json.loads((photo_dir / "sent" / f"{case.token}.json").read_text(encoding="utf-8"))
    assert set(marker) == {"token", "lang", "text", "link", "why", "made"}
    assert marker["text"] == "It is a wall." and marker["link"] == link and marker["why"] == "no-answer" and marker["lang"] == "en"
    again = back_msg.send(case.token, "dropped", tts=Voice())
    assert not again["sent"] and again["why"] == "already sent" and len(sms) == 1
    assert back_msg.message(case.token) == marker


def test_send_clears_the_waiting_call_back(photo_dir, sms):
    case = _ready()
    back_msg.send(case.token, "busy", tts=Voice())
    assert not (photo_dir / "next_call.json").exists() and cases.get(case.token).state == "called"


def test_send_for_a_bad_photo_opens_the_same_link_again(photo_dir, sms):
    case = _ready(sure=0.1)
    back_msg.send(case.token, "failed", tts=Voice())
    assert sms[0][1].startswith("Haqdaar: " + prompt.PHOTO["bad"]["en"])
    assert not (photo_dir / "next_call.json").exists() and cases.get(case.token).state == "waiting"


def test_send_in_hindi_has_the_hindi_prefix(photo_dir, sms):
    case = _ready(lang="hi", sure=0.1)
    back_msg.send(case.token, "busy", tts=Voice())
    assert sms[0][1].startswith("हकदार: " + prompt.PHOTO["bad"]["hi"] + " सुनें: ")


def test_an_sms_fault_never_raises_and_leaves_the_call_back_waiting(photo_dir):
    case = _ready()

    def boom(to, text):
        raise RuntimeError("down")

    out = back_msg.send(case.token, "busy", sms=boom, tts=Voice())
    assert not out["sent"] and "RuntimeError" in out["why"]
    assert (photo_dir / "next_call.json").exists() and not (photo_dir / "sent").exists()


def test_a_voice_fault_sends_the_text_with_no_link(photo_dir, sms):
    case = _ready()
    out = back_msg.send(case.token, "busy", tts=DeadVoice())
    assert out["sent"] and sms == [(NUMBER, "Haqdaar: I see a wall.")]
    assert back_msg.message(case.token)["link"] == ""


def test_any_other_fault_never_raises(photo_dir, sms, monkeypatch):
    case = _ready(lang="hi")
    monkeypatch.setattr(tunables, "PHOTO_BACK_TRANSLATE", True)
    _blocks(monkeypatch, first="")

    def boom(s, l):
        raise ValueError("x")

    out = back_msg.send(case.token, "busy", translate=boom, tts=Voice())
    assert not out["sent"] and out["why"] == "failed: ValueError" and sms == []
    assert back_msg.send("nosuchtoken", "busy")["why"] == "no case"


def test_no_number_uses_the_owner_number_else_sends_nothing(photo_dir, sms, monkeypatch):
    case = _ready_no_number()
    out = back_msg.send(case.token, "busy", tts=Voice())
    assert not out["sent"] and out["why"] == "no number" and sms == [] and (photo_dir / "next_call.json").exists()
    monkeypatch.setenv("CALL_ME_NUMBER", "+918888800002")
    assert back_msg.send(case.token, "busy", tts=Voice())["sent"] and sms[0][0] == "+918888800002"


def test_a_mac_call_prints_the_message_and_sends_no_sms(photo_dir, sms):
    case = _ready_no_number()
    shown = []
    out = back_msg.send(case.token, "dropped", tts=Voice(), show=True, out=shown.append)
    assert out["sent"] and sms == [] and len(shown) == 1
    assert shown[0].startswith("PHOTO MESSAGE: Haqdaar: I see a wall. Listen: https://photo.example/s/")
    assert not (photo_dir / "next_call.json").exists()


def test_the_number_is_never_printed_or_returned(photo_dir, sms, capsys):
    case = _ready()
    out = back_msg.send(case.token, "busy", tts=Voice())
    seen = capsys.readouterr().out + json.dumps(out) + json.dumps(back_msg.message(case.token))
    assert NUMBER not in seen and NUMBER[-6:] not in seen


# --- the photo page's two routes ---

def test_the_wav_route_serves_the_sound_and_the_json_route_the_message(photo_dir, sms):
    case = _ready()
    back_msg.send(case.token, "busy", tts=Voice())
    client = TestClient(photo_desk.photo_app)
    got = client.get(f"/s/{case.token}.wav")
    assert got.status_code == 200 and got.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(got.content)) as w:
        assert w.getnframes() == len(ULAW)
    msg = client.get(f"/m/{case.token}.json")
    assert msg.status_code == 200 and msg.headers["access-control-allow-origin"] == "*"
    assert msg.json() == {"ok": True, "text": "I see a wall.", "link": f"https://photo.example/s/{case.token}.wav", "lang": "en"}


@pytest.mark.parametrize("name", ["nosuchtoken", "..%2f..%2fnext_call", "a.b", "x" * 41])
def test_the_routes_say_404_for_what_is_not_there_or_not_a_token(photo_dir, name):
    (photo_dir / "sound").mkdir(parents=True)
    (photo_dir / "next_call.wav").write_bytes(b"x")
    client = TestClient(photo_desk.photo_app)
    assert client.get(f"/s/{name}.wav").status_code == 404
    assert client.get(f"/m/{name}.json").status_code == 404


# --- /back-status ---

@pytest.fixture
def status_client(monkeypatch):
    from haqdaar import server

    sent, got = [], threading.Event()
    monkeypatch.setattr(tunables, "PHONE_CHECK", False)
    monkeypatch.setattr(back_msg, "send", lambda token, why, **kw: (sent.append((token, why)), got.set()))
    return TestClient(server.app), sent, got


@pytest.mark.parametrize("status", ["no-answer", "busy", "failed", "canceled"])
def test_back_status_sends_the_message_when_nobody_heard_the_call(status_client, status):
    client, sent, got = status_client
    resp = client.post("/back-status?token=abc123", data={"CallStatus": status})
    assert resp.status_code == 204 and got.wait(2) and sent == [("abc123", status)]


@pytest.mark.parametrize("status", ["completed", "in-progress", "ringing", ""])
def test_back_status_does_nothing_for_the_other_statuses(status_client, status):
    client, sent, got = status_client
    assert client.post("/back-status?token=abc123", data={"CallStatus": status}).status_code == 204
    assert not got.wait(0.3) and sent == []


def test_back_status_needs_a_token_and_the_lines_signature(status_client, monkeypatch):
    client, sent, got = status_client
    client.post("/back-status", data={"CallStatus": "busy"})
    assert not got.wait(0.3)
    monkeypatch.setattr(tunables, "PHONE_CHECK", True)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    resp = client.post("/back-status?token=abc123", data={"CallStatus": "busy"}, headers={"X-Twilio-Signature": "bad"})
    assert resp.status_code == 403 and not got.wait(0.3) and sent == []


# --- the drop catch ---

def test_catch_drop_sends_when_the_file_is_still_there_and_not_when_it_is_gone(photo_dir, monkeypatch):
    sent = []
    monkeypatch.setattr(back_msg, "send", lambda token, why, **kw: sent.append((token, why)))
    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", True)
    case = _ready()
    waiting = back_msg.back_token()
    assert waiting == case.token
    back_msg.catch_drop(waiting).join(2)
    assert sent == [(case.token, "dropped")]
    in_call.done(case.token, False)                     # the answer was said in full: the file is gone
    assert back_msg.catch_drop(waiting) is None and len(sent) == 1
    assert back_msg.catch_drop("") is None and back_msg.back_token() == ""


def test_back_token_is_empty_when_photo_in_call_is_off(photo_dir, monkeypatch):
    _ready()
    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", False)
    assert back_msg.back_token() == ""


def _run_engine(monkeypatch, tmp_path, what):
    from haqdaar import server
    from haqdaar.engine.call import Engine
    from haqdaar.model import router

    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", True)
    monkeypatch.setattr(tunables, "CALL_LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(router, "Model", lambda **kw: object())
    monkeypatch.setattr(Engine, "run_call", staticmethod(what))
    ended = []
    server._run_engine("CAx", "snap", "", object(), object(), lambda: ended.append(1))
    assert ended == [1]


def test_the_server_sends_when_the_call_ends_with_the_call_back_still_waiting(photo_dir, tmp_path, monkeypatch):
    sent, got = [], threading.Event()
    monkeypatch.setattr(back_msg, "send", lambda token, why, **kw: (sent.append((token, why)), got.set()))
    case = _ready()
    _run_engine(monkeypatch, tmp_path, lambda audio, model, corpus, log: None)      # hung up before the answer was said
    assert got.wait(2) and sent == [(case.token, "dropped")]


def test_the_server_sends_nothing_when_the_answer_was_said_in_full(photo_dir, tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(back_msg, "send", lambda token, why, **kw: sent.append((token, why)))
    case = _ready()
    _run_engine(monkeypatch, tmp_path, lambda audio, model, corpus, log: in_call.done(case.token, False))
    _run_engine(monkeypatch, tmp_path, lambda audio, model, corpus, log: None)      # a call with no call-back waiting
    assert sent == []


# --- the drop flag ---

def test_set_drop_puts_a_flag_in_the_file_and_pending_gives_it_back(photo_dir):
    case = _ready()
    assert "drop" not in in_call.pending()
    assert not in_call.set_drop("othertoken") and "drop" not in in_call.pending()
    assert in_call.set_drop(case.token)
    assert in_call.pending() == {"token": case.token, "lang": "en", "say": "I see a wall.", "bad": False, "drop": True}


def test_set_drop_with_no_file_is_false(photo_dir):
    assert in_call.set_drop("abc") is False


# --- the 1 / 2 / 3 ask ---

def _reader(*lines):
    it = iter(lines)

    def read():
        got = next(it)
        if isinstance(got, BaseException):
            raise got
        return got
    return read


@pytest.mark.parametrize("typed,want", [("1", 1), (" 2 ", 2), ("3", 3)])
def test_ask_takes_1_2_or_3(typed, want):
    said = []
    assert back_msg.ask_case(_reader(typed), said.append) == want and len(said) == 1


def test_ask_says_what_to_type_and_asks_again_on_anything_else():
    said = []
    assert back_msg.ask_case(_reader("", "abc", "0", "4", "12", "2"), said.append) == 2
    assert said.count("type 1, 2 or 3") == 5


@pytest.mark.parametrize("end", [EOFError(), KeyboardInterrupt()])
def test_ask_treats_the_end_of_input_and_ctrl_c_as_case_1(end):
    assert back_msg.ask_case(_reader("x", end), lambda t: None) == 1


def test_demo_choices(photo_dir, monkeypatch):
    sent = []
    monkeypatch.setattr(back_msg, "send", lambda token, why, **kw: sent.append((token, why)))
    case = _ready()
    assert back_msg.demo_choice(case.token, 1) is True and sent == [] and "drop" not in in_call.pending()
    assert back_msg.demo_choice(case.token, 3) is True and in_call.pending()["drop"] is True and sent == []
    assert back_msg.demo_choice(case.token, 2) is False and sent == [(case.token, "not picked (demo)")]


def test_the_switch_is_off_by_default():
    assert tunables.PHOTO_BACK_ASK is False


# --- tools/photo_back.py ---

URL = "https://line.example/answer"


class Clock:
    t = 1000.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


@pytest.fixture
def watcher(photo_dir, monkeypatch):
    monkeypatch.setenv("PHOTO_BACK_URL", URL)
    monkeypatch.setenv("PHOTO_BACK_WAIT_S", "20")
    clock, lines = Clock(), []

    def make(**kw):
        return photo_back.PhotoBack(now=clock.now, sleep=clock.sleep, live=lambda u: False, out=lines.append, bell=lambda: None, **kw)

    return make, lines


def test_the_ring_asks_the_line_to_tell_back_status_how_it_ended(watcher):
    make, lines = watcher
    case = _ready()
    calls = []
    make(place=lambda n, u, s: calls.append((n, u, s)) or "CA1").look()
    assert calls == [(NUMBER, URL, f"https://line.example/back-status?token={case.token}")]


def test_a_place_that_takes_two_arguments_still_works(watcher):
    make, lines = watcher
    _ready()
    calls = []
    make(place=lambda n, u: calls.append((n, u)) or "CA1").look()
    assert calls == [(NUMBER, URL)]


def test_two_failed_rings_send_the_message_one_failed_ring_does_not(watcher):
    make, lines = watcher
    case = _ready()
    sent, tries = [], []

    def boom(n, u):
        tries.append(1)
        raise RuntimeError("no")

    make(place=boom, send=lambda token, why: sent.append((token, why))).look()
    assert len(tries) == 2 and sent == [(case.token, "ring failed")]
    sent.clear()
    case2 = _ready()
    flaky = iter([RuntimeError("no"), "CA2"])

    def once(n, u):
        got = next(flaky)
        if isinstance(got, Exception):
            raise got
        return got

    make(place=once, send=lambda token, why: sent.append((token, why))).look()
    assert sent == []


def test_the_ask_is_off_by_default_and_nothing_asks(watcher):
    make, lines = watcher
    _ready()
    calls = []

    def never():
        raise AssertionError("asked")

    make(place=lambda n, u: calls.append(1) or "CA1", ask=never, tty=lambda: True).look()
    assert calls == [1]


def test_the_ask_with_no_terminal_plays_case_1_and_says_so(watcher, monkeypatch):
    make, lines = watcher
    monkeypatch.setattr(tunables, "PHOTO_BACK_ASK", True)
    _ready()
    calls = []
    make(place=lambda n, u: calls.append(1) or "CA1", ask=lambda: 2, tty=lambda: False).look()
    assert calls == [1] and sum("no terminal" in l for l in lines) == 1


@pytest.mark.parametrize("choice,rings", [(1, True), (2, False), (3, True)])
def test_the_ask_with_a_terminal_plays_the_case_picked(watcher, monkeypatch, choice, rings):
    make, lines = watcher
    monkeypatch.setattr(tunables, "PHOTO_BACK_ASK", True)
    case = _ready()
    calls, sent = [], []
    monkeypatch.setattr(back_msg, "send", lambda token, why, **kw: sent.append((token, why)))
    make(place=lambda n, u: calls.append(1) or "CA1", ask=lambda: choice, tty=lambda: True).look()
    assert bool(calls) is rings
    assert sent == ([(case.token, "not picked (demo)")] if choice == 2 else [])
    assert bool((in_call.pending() or {}).get("drop")) is (choice == 3)


# --- tools/mac_call.py: the ask and the stdin thread ---

class _Tty:
    """A terminal that stays open: lines come when the test puts them."""

    def __init__(self):
        self.lines = queue.Queue()

    def isatty(self):
        return True

    def __iter__(self):
        while True:
            line = self.lines.get()
            if line is None:
                return
            yield line


@pytest.fixture
def mac(monkeypatch):
    shown = []
    monkeypatch.setattr(mac_call, "STDIN", queue.Queue())
    monkeypatch.setattr(mac_call, "_STDIN_THREAD", [])
    monkeypatch.setattr(mac_call, "say", lambda text, tag="": shown.append(text))
    return shown


def test_mac_ask_is_off_by_default_and_touches_no_terminal(mac, monkeypatch):
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: (_ for _ in ()).throw(AssertionError("read"))))
    assert mac_call.ask_demo("abc") == 1 and mac == []


def test_mac_ask_with_no_terminal_plays_case_1(mac, monkeypatch):
    monkeypatch.setattr(tunables, "PHOTO_BACK_ASK", True)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: False))
    assert mac_call.ask_demo("abc") == 1 and any("no terminal" in t for t in mac)


def test_mac_ask_reads_the_shared_stdin_lines_and_ignores_what_was_typed_before(mac, photo_dir, monkeypatch):
    sent = []
    monkeypatch.setattr(tunables, "PHOTO_BACK_ASK", True)
    monkeypatch.setattr(back_msg, "send", lambda token, why, **kw: sent.append((token, why, kw.get("show"))))
    tty = _Tty()
    monkeypatch.setattr(sys, "stdin", tty)
    mac_call.STDIN.put("1\n")                                    # typed while we waited for the photo
    threading.Timer(0.3, lambda: tty.lines.put("hello\n")).start()
    threading.Timer(0.5, lambda: tty.lines.put("2\n")).start()
    assert mac_call.ask_demo("abc") == 2
    assert sent == [("abc", "not picked (demo)", True)] and "type 1, 2 or 3" in mac
    tty.lines.put(None)                                          # the end of input: later reads are 1, never a hang
    assert mac_call.next_line(2) is None and mac_call.next_line(0) is None


def test_mac_ask_at_the_end_of_input_is_case_1(mac, monkeypatch):
    monkeypatch.setattr(tunables, "PHOTO_BACK_ASK", True)
    tty = _Tty()
    monkeypatch.setattr(sys, "stdin", tty)
    tty.lines.put(None)
    assert mac_call.ask_demo("abc") == 1


# --- twilio.place_call ---

def test_place_call_with_and_without_the_status_url(monkeypatch):
    from haqdaar.audio.telephony import place_call

    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_x")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_US_PHONE_NUMBER", "+14240000000")
    forms = []

    def fake_open(req):
        forms.append(urllib.parse.parse_qs(req.data.decode()))
        return io.BytesIO(b'{"sid": "CA_new"}')

    assert place_call("+910000000000", "https://d.example/answer", fake_open) == "CA_new"
    assert "StatusCallback" not in forms[0] and forms[0]["Url"] == ["https://d.example/answer"]
    assert place_call("+910000000000", "https://d.example/answer", fake_open, "https://d.example/back-status?token=t1") == "CA_new"
    assert forms[1]["StatusCallback"] == ["https://d.example/back-status?token=t1"] and forms[1]["StatusCallbackMethod"] == ["POST"]
    assert place_call("+910000000000", "https://d.example/answer", fake_open, status_url="https://d.example/s")
    assert forms[2]["StatusCallback"] == ["https://d.example/s"]


def test_the_demo_also_texts_the_owners_phone(tmp_path, monkeypatch):
    """PHOTO_BACK_ASK: a Mac call's message is shown AND goes to CALL_ME_NUMBER; a link to this Mac is left out."""
    from haqdaar.contracts import tunables

    monkeypatch.setenv("PHOTO_DIR", str(tmp_path))
    monkeypatch.setenv("CALL_ME_NUMBER", "+918888800002")
    monkeypatch.setattr(tunables, "PHOTO_BACK_ASK", True)
    for base, has_link in (("https://x.trycloudflare.com", True), ("http://127.0.0.1:8002", False)):
        monkeypatch.setenv("PHOTO_SOUND_URL", base)
        case = cases.new_case("en", "")
        cases.set_finding(case.token, {"shows": "a wall", "wrong": "", "sure": 0.9, "by": "muse"}, "", "I see a wall.")
        cases.approve(case.token, "I see a wall.")
        sms, shown = [], []

        class Voice:
            def speak(self, text, lang):
                return b"\xff" * 800

        out = back_msg.send(case.token, "not picked (demo)", sms=lambda to, text: sms.append((to, text)), tts=Voice(),
                            show=True, out=shown.append)
        assert out["sent"] and len(sms) == 1 and sms[0][0] == "+918888800002"
        assert (f"{base}/s/{case.token}.wav" in sms[0][1]) is has_link
        assert sms[0][1].startswith("Haqdaar: I see a wall.")
        assert "+91" not in " ".join(shown)


def test_a_failed_demo_sms_still_shows_the_message(tmp_path, monkeypatch):
    from haqdaar.contracts import tunables

    monkeypatch.setenv("PHOTO_DIR", str(tmp_path))
    monkeypatch.setenv("CALL_ME_NUMBER", "+918888800002")
    monkeypatch.setattr(tunables, "PHOTO_BACK_ASK", True)
    case = cases.new_case("en", "")
    cases.set_finding(case.token, {"shows": "a wall", "wrong": "", "sure": 0.9, "by": "muse"}, "", "I see a wall.")
    cases.approve(case.token, "I see a wall.")
    shown = []

    def boom(to, text):
        raise OSError("no line")

    out = back_msg.send(case.token, "not picked (demo)", sms=boom, tts=None, model=None, show=True, out=shown.append,
                        translate=lambda s, l: s)
    assert out["sent"] and any("did not go" in line for line in shown)


def test_a_sentence_left_in_english_is_translated_once_more(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTO_DIR", str(tmp_path))
    monkeypatch.setattr(tunables, "PHOTO_BACK_TRANSLATE", True)
    case = cases.new_case("hi", "")
    cases.set_finding(case.token, {"shows": "a wall", "wrong": "", "sure": 0.9, "by": "muse"}, "", "I see a wall.")
    cases.approve(case.token, "I see a wall.")
    tries = []

    def flaky(sent, lang):
        tries.append(sent)
        return sent if len(tries) == 1 else "मुझे एक दीवार दिख रही है।"

    assert back_msg.answer_text(case.token, translate=flaky) == ("मुझे एक दीवार दिख रही है।", "hi")
    assert len(tries) == 2
