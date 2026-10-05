"""tests/test_middle.py — step 1.4a reply half.

All faked at haqdaar.net: no test reaches a real host, no paid call.
"""
from __future__ import annotations

import types

import httpx
import pytest

from haqdaar import net
from haqdaar.model import middle
from haqdaar.model.middle import guard_ok, reply_in, scheme_names, split_sentences

NAMES = [
    {"en": ["pm kisan", "pm kisan samman nidhi"], "hi": ["पीएम किसान"], "mr": []},
    {"en": ["mgnrega", "mnrega"], "hi": ["मनरेगा"], "mr": []},
    {"en": ["kisan credit scheme", "kisan credit", "kcc"],
     "hi": ["किसान क्रेडिट योजना", "केसीसी"], "mr": ["किसान क्रेडिट योजना"]},
]

GUARD_CASES = [
    # (english, output, lang, passes)
    ("You get Rs 6,000 in a year.", "आपको साल में 6,000 रुपये मिलते हैं।", "hi", True),
    ("You get Rs 6,000.", "आपको 6000 मिलते हैं।", "hi", True),
    ("You get Rs 6,000.", "आपको ६,००० मिलते हैं।", "hi", True),
    ("You get Rs 6,000.", "તમને ૬૦૦૦ મળે છે.", "gu", True),
    ("You get Rs 6,000.", "உங்களுக்கு ௬௦௦௦ கிடைக்கும்.", "ta", True),
    ("You get Rs 6,000.", "आपको पैसे मिलते हैं।", "hi", False),
    ("You get Rs 6,000.", "आपको 3,200 रुपये मिलते हैं।", "hi", False),
    ("You get Rs 6,000.", "आपको 6,000 रुपये और 500 मिलते हैं।", "hi", False),
    ("You get Rs 6,000.", "आपको छह हज़ार रुपये मिलते हैं।", "hi", False),
    ("Pay Rs 500 at the office.", "दफ्तर में 500 रुपये दें।", "hi", True),
    ("Pay Rs. 500 at the office.", "दफ्तर में 500 रुपये दें।", "hi", True),
    ("Pay Rs 500 at the office.", "दफ्तर में 501 रुपये दें।", "hi", False),
    ("You must be 60 or older.", "आपकी उम्र 60 या ज़्यादा होनी चाहिए।", "hi", True),
    ("You must be 60 or older.", "आपकी उम्र ६० होनी चाहिए।", "hi", True),
    ("You must be 60 or older.", "आपकी उम्र 61 होनी चाहिए।", "hi", False),
    ("Age 60+ can apply.", "60+ उम्र वाले भर सकते हैं।", "hi", True),
    ("Age is 18 to 40 years.", "उम्र 18 से 40 साल है।", "hi", True),
    ("Age is 18 to 40 years.", "उम्र 18 से 41 साल है।", "hi", False),
    ("Age is 18 to 40 years.", "उम्र 18 साल है।", "hi", False),
    ("Interest is 5 percent.", "ब्याज 5 प्रतिशत है।", "hi", True),
    ("Interest is 5 percent.", "ब्याज 7 प्रतिशत है।", "hi", False),
    ("You pay 2.5 percent.", "आप 2.5 प्रतिशत देते हैं।", "hi", True),
    ("Apply before 15 August 2026.", "15 अगस्त 2026 से पहले भरें।", "hi", True),
    ("Apply before 15 August 2026.", "15 अगस्त 2025 से पहले भरें।", "hi", False),
    ("Come on 26 January.", "26 जनवरी को आएं।", "hi", True),
    ("Your number is 9876543210.", "आपका नंबर 9876543210 है।", "hi", True),
    ("Your number is 9876543210.", "आपका नंबर 9876543211 है।", "hi", False),
    ("Your number is 9876543210.", "आपका नंबर ९८७६५४३२१० है।", "hi", True),
    ("PM Kisan gives Rs 6,000.", "पीएम किसान में 6,000 मिलते हैं।", "hi", True),
    ("PM Kisan gives Rs 6,000.", "PM Kisan gives 6000 in a year.", "hi", True),
    ("PM Kisan gives Rs 6,000.", "प्रधानमंत्री किसान योजना में 6000 मिलते हैं।", "hi", False),
    ("PM Kisan gives Rs 6,000.", "इस योजना में 6,000 मिलते हैं।", "hi", False),
    ("KCC gives a loan.", "KCC से कर्ज मिलता है।", "hi", True),
    ("KCC gives a loan.", "केसीसी से कर्ज मिलता है।", "hi", True),
    ("KCC gives a loan.", "कार्ड से कर्ज मिलता है।", "hi", False),
    ("MGNREGA gives work.", "MGNREGA मधून काम मिळते.", "mr", True),
    ("MGNREGA gives work.", "काम मिळते.", "mr", False),
    ("MGNREGA gives work.", "मनरेगा से काम मिलता है।", "hi", True),
    ("Kisan Credit Scheme helps.", "किसान क्रेडिट योजना मदद करती है।", "mr", True),
    ("Kisan Credit Scheme helps.", "કિસાન ક્રેડિટ યોજના મદદ કરે છે.", "gu", False),
    ("Kisan Credit Scheme helps.", "Kisan Credit Scheme helps farmers here.", "gu", True),
    ("Come with your papers.", "कागज़ लेकर दफ्तर आएं।", "hi", True),
    ("Asha scheme helps.", "आशा योजना मदद करती है।", "hi", True),
    ("PM Kisan and MGNREGA help.", "पीएम किसान मदद करता है।", "hi", False),
    ("PM Kisan and MGNREGA help.", "पीएम किसान और मनरेगा मदद करते हैं।", "hi", True),
    ("You must be 60 or older.", "உங்களுக்கு ௬௦ வயது வேண்டும்.", "ta", True),
    ("You get Rs 100 and Rs 200.", "आपको 100 और 200 मिलते हैं।", "hi", True),
    ("You get Rs 100 and Rs 200.", "आपको 100 मिलते हैं।", "hi", False),
]


@pytest.mark.parametrize("en,out,lang,want", GUARD_CASES)
def test_guard_numbers_and_names(en, out, lang, want):
    assert guard_ok(en, out, lang, NAMES) is want


def test_guard_reads_names_when_not_given(monkeypatch):
    monkeypatch.setattr(middle, "scheme_names", lambda: NAMES)
    assert guard_ok("KCC gives a loan.", "कार्ड से कर्ज मिलता है।", "hi") is False
    assert guard_ok("KCC gives a loan.", "KCC से कर्ज मिलता है।", "hi") is True


def test_scheme_names_never_raises():
    assert isinstance(scheme_names(), list)


def test_split_keeps_rs_and_no():
    assert split_sentences("Pay Rs. 500 at No. 2 office. Come tomorrow.") == [
        "Pay Rs. 500 at No. 2 office.", "Come tomorrow."]


def test_split_marks_and_order():
    assert split_sentences("Which district? Tell me! Come soon.") == [
        "Which district?", "Tell me!", "Come soon."]


class _Resp:
    def __init__(self, text):
        self.status_code = 200
        self._text = text

    def json(self):
        return {"translated_text": self._text}


def _serve(monkeypatch, answers):
    """Fake net.post with scripted outputs or errors. Returns the inputs seen."""
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    calls = []

    def post(url, *, timeout, **kw):
        calls.append((kw.get("json") or {}).get("input"))
        item = answers[min(len(calls) - 1, len(answers) - 1)]
        if isinstance(item, Exception):
            raise item
        return _Resp(item)

    monkeypatch.setattr(net, "post", post)
    return calls


def test_reply_is_a_generator():
    assert isinstance(reply_in("Hi.", "hi"), types.GeneratorType)


def test_sentences_come_back_in_order(monkeypatch):
    calls = _serve(monkeypatch, ["पहला 100 है।", "दूसरा 200 है।"])
    outs = list(reply_in("First is Rs 100. Second is Rs 200.", "hi"))
    assert [o.text for o in outs] == ["पहला 100 है।", "दूसरा 200 है।"]
    assert [o.ok for o in outs] == [True, True]
    assert calls == ["First is Rs 100.", "Second is Rs 200."]
    assert all(isinstance(o.ms, int) and o.ms >= 0 for o in outs)


def test_en_comes_back_as_is_with_no_network_call(monkeypatch):
    def boom(url, *, timeout, **kw):
        raise AssertionError("en must not call the network")

    monkeypatch.setattr(net, "post", boom)
    outs = list(reply_in("Hello there. How are you?", "en"))
    assert [o.text for o in outs] == ["Hello there.", "How are you?"]
    assert all(o.ok for o in outs)
    assert all(o.ms == 0 for o in outs)


def test_unknown_code_is_not_supported(monkeypatch):
    def boom(url, *, timeout, **kw):
        raise AssertionError("unknown code must not call the network")

    monkeypatch.setattr(net, "post", boom)
    outs = list(reply_in("Hello there.", "xx"))
    assert len(outs) == 1
    assert outs[0].text == "not supported"
    assert outs[0].ok is False


def test_timeout_gives_failed_not_an_error(monkeypatch):
    calls = _serve(monkeypatch, [httpx.TimeoutException("slow")])
    outs = list(reply_in("You get Rs 100.", "hi"))
    assert len(outs) == 1
    assert outs[0].ok is False
    assert len(calls) == 2


def test_network_error_gives_failed_not_an_error(monkeypatch):
    calls = _serve(monkeypatch, [httpx.ConnectError("down")])
    outs = list(reply_in("You get Rs 100.", "hi"))
    assert len(outs) == 1
    assert outs[0].ok is False
    assert len(calls) == 2


def test_failed_text_never_passes(monkeypatch):
    calls = _serve(monkeypatch, ["no numbers here", "still no numbers"])
    outs = list(reply_in("You get Rs 100.", "hi"))
    assert outs[0].ok is False
    assert outs[0].text == "still no numbers"
    assert len(calls) == 2


def test_retry_first_bad_then_good(monkeypatch):
    calls = _serve(monkeypatch, ["आपको पैसे मिलते हैं।", "आपको 100 रुपये मिलते हैं।"])
    outs = list(reply_in("You get Rs 100.", "hi"))
    assert outs[0].ok is True
    assert outs[0].text == "आपको 100 रुपये मिलते हैं।"
    assert len(calls) == 2


def test_gu_and_ta_go_through_translate(monkeypatch):
    calls = _serve(monkeypatch, ["તમને 100 મળે છે."])
    outs = list(reply_in("You get Rs 100.", "gu"))
    assert outs[0].ok is True
    assert outs[0].text != "not supported"
    assert calls == ["You get Rs 100."]


def test_ta_goes_through_translate(monkeypatch):
    _serve(monkeypatch, ["உங்களுக்கு 100 கிடைக்கும்."])
    outs = list(reply_in("You get Rs 100.", "ta"))
    assert outs[0].ok is True


def test_empty_reply_sends_nothing(monkeypatch):
    calls = _serve(monkeypatch, ["कुछ भी।"])
    assert list(reply_in("   ", "hi")) == []
    assert calls == []
