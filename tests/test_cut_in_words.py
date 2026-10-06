"""6 Oct: short words must cut in. On the owner's Mac calls "Hindi" over the greeting was thrown away four
times as "too short" (600 ms of voice was asked for, and a 300 ms stop between words started the count again).

The rig is talk_eval's (real engine, made-up clock). The last tests use the real Silero voice check on the
Mac's own voice; they are skipped where `say` or its Indian voices are missing.
"""
import shutil
import subprocess
import sys

import pytest

from haqdaar.audio.ear import Ear, EnergyVAD, FRAME_PCM_BYTES
from haqdaar.contracts import tunables
from tools import talk_eval as te

LOUD = (3000).to_bytes(2, "little", signed=True) * (FRAME_PCM_BYTES // 2)
QUIET = b"\x00" * FRAME_PCM_BYTES


def _heard(res):
    return [r["text"] for r in res.log_rows if r.get("ev") == "heard"]


def _greeting_cut(res):
    return [c for c in res.clips if c["name"].startswith("greeting") and c["cut_at"] is not None]


def _watch(pattern, min_ms, gap_ms):
    """pattern: (voiced?, ms) pieces fed to the ear's watch; every answer it gave."""
    ear = Ear(vad=EnergyVAD(), log=lambda *_: None)
    ear.start_watch()
    out = []
    for voiced, ms in pattern:
        for _ in range(ms // 20):
            ear.push_media(LOUD if voiced else QUIET, is_ulaw=False)
            got = ear.watch_voice(False, min_ms, gap_ms)
            if got:
                out.append(got)
            if got == "cut":
                return out
    return out


# --- the bar itself ------------------------------------------------------------------------

def test_the_bars_are_low_enough_for_one_word():
    assert tunables.CUT_IN_GREETING_MS <= 200 and tunables.CUT_IN_GATE_MS <= 300
    assert tunables.CUT_IN_GATE_GAP_MS >= 400


def test_a_short_word_cuts_at_the_new_bar_and_did_not_at_the_old():
    word = [(False, 200), (True, 400), (False, 800)]
    assert _watch(word, tunables.CUT_IN_GATE_MS, tunables.CUT_IN_GATE_GAP_MS) == ["cut"]
    assert _watch(word, 600, 300) == ["short"]


def test_two_words_with_a_stop_between_them_count_as_one():
    words = [(False, 200), (True, 160), (False, 400), (True, 160), (False, 800)]
    assert _watch(words, tunables.CUT_IN_GATE_MS, tunables.CUT_IN_GATE_GAP_MS) == ["cut"]
    assert "cut" not in _watch(words, 600, 300)


def test_a_click_is_still_too_short():
    assert "cut" not in _watch([(False, 200), (True, 100), (False, 800)],
                               tunables.CUT_IN_GREETING_MS, tunables.CUT_IN_GATE_GAP_MS)


def test_two_clicks_far_apart_do_not_add_up():
    clicks = [(False, 200), (True, 100), (False, 900), (True, 100), (False, 900)]
    assert "cut" not in _watch(clicks, tunables.CUT_IN_GREETING_MS, tunables.CUT_IN_GATE_GAP_MS)


# --- the greeting --------------------------------------------------------------------------

@pytest.mark.parametrize("script, lang", [("g_lang_short", "hi"), ("g_lang_late", "en")])
def test_one_short_language_word_over_the_greeting_is_the_pick(script, lang):
    res = te.run_call(script, True)
    assert te.check(res) == []
    assert _greeting_cut(res), "the greeting was not stopped"
    assert any(line == f"<- voice: language {lang}" for _t, line in res.lines)


def test_the_greeting_stops_within_a_second_of_the_word():
    res = te.run_call("g_lang_short", True)
    said = res.said[0]
    cut_at = min(c["cut_at"] for c in _greeting_cut(res))
    assert cut_at - said["t0"] < 1.0


def test_hello_over_the_greeting_is_no_pick_and_the_key_still_works():
    res = te.run_call("g_hello", True)
    assert te.check(res) == []
    assert not any("the talk starts" in line for _t, line in res.lines)
    assert _heard(res)[0] == "i need a scheme for farming"


def test_hello_then_the_language_word_both_over_the_greeting():
    res = te.run_call("g_hello_lang", True)
    assert te.check(res) == []
    assert any(line == "<- voice: language hi" for _t, line in res.lines)


def test_gate_off_a_word_over_the_greeting_stops_nothing():
    res = te.run_call("g_hello", False)
    assert te.check(res) == [] and not _greeting_cut(res)


# --- a talk reply --------------------------------------------------------------------------

def _first_reply(res):
    return [c for c in res.clips if c["name"] == "answer"][2]["start"]


@pytest.mark.parametrize("kind", ["two_words", "short_ask"])
def test_two_short_words_over_a_reply_stop_it_and_are_the_turn(kind):
    plain = te.run_call("ask", True)
    res = te.run_call("ask", True, te._inject(kind, _first_reply(plain) + 0.5))
    assert te.check(res) == []
    assert res.clears, "the reply was not stopped"
    assert any(text.startswith(te.KINDS[kind][0]) for text in _heard(res))


def test_one_word_over_a_reply_is_no_turn():
    plain = te.run_call("ask", True)
    res = te.run_call("ask", True, te._inject("one_word", _first_reply(plain) + 0.5))
    assert te.check(res) == []
    assert "no" not in _heard(res)
    assert res.model_answers == plain.model_answers


@pytest.mark.parametrize("script", ["k_mixed", "k_readout", "f_photo_yes"])
@pytest.mark.parametrize("kind", ["one_word", "two_words", "short_ask"])
def test_short_words_at_a_few_places_of_the_keys_and_photo_calls_break_no_rule(script, kind):
    if script not in te.SCRIPTS:
        pytest.skip("no such script")
    plain = te.run_call(script, True)
    starts = [c["start"] for c in plain.clips][::4]
    for at in starts:
        res = te.run_call(script, True, te._inject(kind, at + 0.4))
        assert te.check(res) == [], f"{script} {kind} at {at - te.be.T0:.2f}"


# --- the real voice check (Silero) on the Mac's own voice ----------------------------------

def _mac_voice():
    if sys.platform != "darwin" or not shutil.which("say"):
        return False
    voices = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    return "Lekha" in voices and "Rishi" in voices


def _silero(text, lang, min_ms, gap_ms, gain=0.3):
    from haqdaar.audio import silero
    from tools.talk_probe import FRAME, voice

    vad = silero.make()
    if vad is None:
        pytest.skip("Silero not loaded")
    ear = Ear(vad=vad, log=lambda *_: None)
    ear.start_watch()
    sound = voice(text, lang, gain)
    quiet = b"\xff" * FRAME
    out = []
    for frame in [quiet] * 10 + [sound[i:i + FRAME] for i in range(0, len(sound) - FRAME + 1, FRAME)] + [quiet] * 40:
        ear.push_media(frame)
        got = ear.watch_voice(False, min_ms, gap_ms)
        if got:
            out.append(got)
        if got == "cut":
            break
    return out


@pytest.mark.skipif(not _mac_voice(), reason="needs the Mac's say voices")
@pytest.mark.parametrize("text, lang", [("Hindi", "en"), ("English", "en"), ("hello", "en"), ("हिंदी", "hi"),
                                        ("मराठी", "hi"), ("हेलो", "hi")])
def test_real_voice_one_word_cuts_the_greeting(text, lang):
    assert "cut" in _silero(text, lang, tunables.CUT_IN_GREETING_MS, tunables.CUT_IN_GATE_GAP_MS)
    assert "cut" not in _silero(text, lang, 600, 300)      # the old bar threw it away


@pytest.mark.skipif(not _mac_voice(), reason="needs the Mac's say voices")
@pytest.mark.parametrize("text, lang", [("रुको रुको", "hi"), ("एक मिनट", "hi"), ("हेलो हेलो", "hi"),
                                        ("Hindi please", "en"), ("मुझे खेती की योजना चाहिए", "hi")])
def test_real_voice_two_words_cut_a_reply(text, lang):
    assert "cut" in _silero(text, lang, tunables.CUT_IN_GATE_MS, tunables.CUT_IN_GATE_GAP_MS)
