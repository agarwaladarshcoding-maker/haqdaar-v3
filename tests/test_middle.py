"""tests/test_middle.py — step 1.4a reply half.

All faked at haqdaar.net: no test reaches a real host, no paid call.
"""
from __future__ import annotations

import time
import types

import httpx
import pytest

from haqdaar import net
from haqdaar.engine.talk import _sentences
from haqdaar.model import middle
from haqdaar.model.middle import guard_ok, reply_in, scheme_names, split_sentences

# Point 2: Use real scheme names from data, not a hand-made list
NAMES = scheme_names()

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
    # Point 5: 6,000 -> 6 हज़ार or छह हज़ार passes
    ("You get Rs 6,000.", "आपको छह हज़ार रुपये मिलते हैं।", "hi", True),
    ("You get Rs 6,000.", "आपको 6 हज़ार रुपये मिलते हैं।", "hi", True),
    # Point 4 & 5: 2 lakh -> 2,00,000 passes, 5 lakh -> 5 हज़ार fails
    ("You get 2 lakh.", "आपको 2,00,000 रुपये मिलते हैं।", "hi", True),
    ("You get 5 lakh.", "आपको 5 हज़ार मिलते हैं।", "hi", False),
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
    # Point 4: 1.5 vs 5.1 fails
    ("You pay 1.5 percent.", "आप 5.1 प्रतिशत देते हैं।", "hi", False),
    ("Apply before 15 August 2026.", "15 अगस्त 2026 से पहले भरें।", "hi", True),
    ("Apply before 15 August 2026.", "15 अगस्त 2025 से पहले भरें।", "hi", False),
    ("Come on 26 January.", "26 जनवरी को आएं।", "hi", True),
    ("Your number is 9876543210.", "आपका नंबर 9876543210 है।", "hi", True),
    ("Your number is 9876543210.", "आपका नंबर 9876543211 है।", "hi", False),
    ("Your number is 9876543210.", "आपका नंबर ९८७६५४३२१० है।", "hi", True),
    # Point 5: phone number without dashes passes
    ("Your number is 9876-543-210.", "आपका नंबर 9876543210 है।", "hi", True),
    # Point 5: 2nd -> दूसरा passes
    ("This is the 2nd installment.", "यह दूसरा हफ्ता है।", "hi", True),
    # Point 2: PM Kisan -> PM Awas fails
    ("PM Kisan gives Rs 6,000.", "पीएम किसान में 6,000 मिलते हैं।", "hi", True),
    ("PM Kisan gives Rs 6,000.", "PM Kisan gives 6000 in a year.", "hi", True),
    ("PM Kisan gives Rs 6,000.", "प्रधानमंत्री आवास योजना में 6000 मिलते हैं।", "hi", False),
    ("PM Kisan gives Rs 6,000.", "इस योजना में 6,000 मिलते हैं।", "hi", False),
    # Point 3: KCC helps -> किसी से मदद लें fails (whole words)
    ("KCC gives a loan.", "KCC से कर्ज मिलता है।", "hi", True),
    ("KCC gives a loan.", "केसीसी से कर्ज मिलता है।", "hi", True),
    ("KCC helps.", "किसी से मदद लें।", "hi", False),
    ("KCC gives a loan.", "कार्ड से कर्ज मिलता है।", "hi", False),
    ("MGNREGA gives work.", "MGNREGA मधून काम मिळते.", "mr", True),
    ("MGNREGA gives work.", "काम मिळते.", "mr", False),
    ("MGNREGA gives work.", "मनरेगा से काम मिलता है।", "hi", True),
    ("Kisan Credit Scheme helps.", "किसान क्रेडिट योजना मदद करती है।", "mr", True),
    # Point 6: Gujarati and Tamil scheme name in caller's script passes
    ("Kisan Credit Scheme helps.", "કિસાન ક્રેડિટ યોજના મદદ કરે છે.", "gu", True),
    ("Kisan Credit Scheme helps.", "Kisan Credit Scheme helps farmers here.", "gu", True),
    ("Come with your papers.", "कागज़ लेकर दफ्तर आएं।", "hi", True),
    ("Asha scheme helps.", "आशा योजना मदद करती है।", "hi", True),
    ("PM Kisan and MGNREGA help.", "पीएम किसान मदद करता है।", "hi", False),
    ("PM Kisan and MGNREGA help.", "पीएम किसान और मनरेगा मदद करते हैं।", "hi", True),
    ("You must be 60 or older.", "உங்களுக்கு ௬௦ வயது வேண்டும்.", "ta", True),
    ("You get Rs 100 and Rs 200.", "आपको 100 और 200 मिलते हैं।", "hi", True),
    # Order of the numbers is free (the verb comes last in Hindi, Tamil ...); the numbers must be the same
    ("You get Rs 100 and Rs 200.", "आपको 200 और 100 मिलते हैं।", "hi", True),
    ("Rs 5,000 a month after age 60.", "60 साल के बाद हर महीने 5,000 रुपये।", "hi", True),
    ("You get Rs 100 and Rs 200.", "आपको 100 और 300 मिलते हैं।", "hi", False),
    # Other Sarvam languages: units, a letter stuck to the digits, a name by its sound
    ("You can borrow 2 lakh.", "நீங்கள் 2 லட்சம் ரூபாய் வரை பெறலாம்.", "ta", True),
    ("You can borrow 2 lakh.", "మీరు 2 లక్షల రూపాయల వరకు తీసుకోవచ్చు.", "te", True),
    ("You get Rs 6,000.", "உங்களுக்கு ரூ6,000 கிடைக்கும்.", "ta", True),
    ("You get Rs 6,000.", "ನಿಮಗೆ 6 ಸಾವಿರ ರೂಪಾಯಿ ಸಿಗುತ್ತದೆ.", "kn", True),
    ("PM Kisan gives help.", "പി.എം. കിസാൻ സഹായം നൽകുന്നു.", "ml", True),
    ("PM Kisan gives help.", "పీఎం కిసాన్ సహాయం ఇస్తుంది.", "te", True),
    ("PM Kisan gives help.", "প্রধানমন্ত্রী আবাস যোজনা সাহায্য দেয়।", "bn", False),
    ("KCC gives a loan.", "ঋণ দেওয়া হয়।", "bn", False),
    # Point 4: number repetition fails
    ("You get Rs 100 and Rs 100.", "आपको 100 मिलते हैं।", "hi", False),
    ("You get Rs 100 and Rs 200.", "आपको 100 मिलते हैं।", "hi", False),
    # Mac call, 6 Oct: "One is ..." / "Another is ..." stayed English, "एक" / "दूसरी" were read as amounts.
    # A bare one / two word with no partner is grammar. A digit or an amount is still strict.
    ("One is Pradhan Mantri Mudra Yojana for small business loans.", "एक है प्रधानमंत्री मुद्रा योजना, छोटे व्यवसाय ऋण के लिए।", "hi", True),
    ("Another is PM Kisan for farmers.", "दूसरी है पीएम किसान, किसानों के लिए।", "hi", True),
    ("Another is PM Kisan for farmers.", "एक और है पीएम किसान, किसानों के लिए।", "hi", True),
    ("Do you have a ration card?", "क्या आपके पास एक राशन कार्ड है?", "hi", True),
    ("PM Kisan gives Rs 6,000 a year.", "पीएम किसान एक साल में 6,000 रुपये देता है।", "hi", True),
    ("You may get two schemes.", "आपको दो योजनाएं मिल सकती हैं।", "hi", True),
    ("PM Kisan gives Rs 6,000 a year in three parts.", "पीएम किसान तीन भागों में 6,000 रुपये प्रति वर्ष देता है।", "hi", True),
    ("You get 2 hectares.", "आपको एक हेक्टेयर मिलता है।", "hi", False),
    ("You get 2 hectares.", "आपको हेक्टेयर मिलता है।", "hi", False),
    ("PM Kisan helps farmers.", "पीएम किसान किसानों की तीन बार मदद करता है।", "hi", False),
    ("PM Kisan helps farmers.", "पीएम किसान किसानों को 2 बार मदद करता है।", "hi", False),
    ("PM Kisan gives Rs 6,000 a year.", "पीएम किसान साल में तीन हज़ार दो सौ रुपये देता है।", "hi", False),
    # a counted "two" / "दो" is an amount: a swap with "one" / "एक" is refused
    ("Land of up to two hectares is covered.", "एक हेक्टेयर तक की ज़मीन आती है।", "hi", False),
    ("Only one child is covered.", "केवल दो बच्चे आते हैं।", "hi", False),
    ("Two daughters are covered.", "एक मुलगी येते.", "mr", False),
    ("Two daughters are covered.", "दोन मुली येतात.", "mr", True),
    # Marathi "साठी" (for) is not "साठ" (60): a vowel sign after the word means a longer word
    ("Yes, there are schemes for business.", "होय, व्यवसायासाठी योजना आहेत.", "mr", True),
    ("You must be 60.", "तुमचे वय साठ हवे.", "mr", True),
    # "three" as a word in a language whose number words are not known: not held against the sentence
    ("PM Kisan gives Rs 6,000 a year in three parts.", "పీఎం కిసాన్ సంవత్సరానికి 6,000 రూపాయలు మూడు విడతలుగా ఇస్తుంది.", "te", True),
]


@pytest.mark.parametrize("en,out,lang,want", GUARD_CASES)
def test_guard_numbers_and_names(en, out, lang, want):
    assert guard_ok(en, out, lang, NAMES) is want


def test_guard_reads_names_when_not_given():
    assert guard_ok("KCC gives a loan.", "कार्ड से कर्ज मिलता है।", "hi") is False
    assert guard_ok("KCC gives a loan.", "KCC से कर्ज मिलता है।", "hi") is True


def test_scheme_names_never_raises():
    assert isinstance(scheme_names(), list)
    assert len(scheme_names()) > 0


def test_split_sentences_matches_talk():
    """Point 8: Split the way haqdaar.engine.talk._sentences does.
    Does not cut 'e.g.', '5 p.m.', 'U.P.' into isolated pieces.
    """
    samples = [
        "Which district? Tell me! Come soon.",
        "Visit U.P. at 5 p.m. Bring papers e.g. Aadhaar.",
        "First is Rs 100. Second is Rs 200.",
        "You get Rs 6,000 in a year, in three parts.",
    ]
    for text in samples:
        assert split_sentences(text) == _sentences(text)


def test_split_abbreviations():
    """Point 8: 'e.g.', '5 p.m.', 'U.P.' are not cut into their own pieces."""
    s = split_sentences("Visit U.P. at 5 p.m. Bring papers e.g. Aadhaar.")
    assert len(s) >= 1
    assert not any(sent.strip() in ("U.P.", "e.g.", "p.m.", "5 p.m.") for sent in s)


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
    assert outs[0].text == "You get Rs 100."  # Point 1: returns English sentence
    assert len(calls) == 2


def test_network_error_gives_failed_not_an_error(monkeypatch):
    calls = _serve(monkeypatch, [httpx.ConnectError("down")])
    outs = list(reply_in("You get Rs 100.", "hi"))
    assert len(outs) == 1
    assert outs[0].ok is False
    assert outs[0].text == "You get Rs 100."  # Point 1: returns English sentence
    assert len(calls) == 2


def test_failed_text_never_passes(monkeypatch):
    """Point 1: A refused sentence hands back the English sentence, never wrong text."""
    calls = _serve(monkeypatch, ["no numbers here", "still no numbers"])
    outs = list(reply_in("You get Rs 100.", "hi"))
    assert outs[0].ok is False
    assert outs[0].text == "You get Rs 100."
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


def test_none_reply_gives_back_nothing():
    """Point 9: reply_in(None, 'en') raises nothing and returns empty."""
    assert list(reply_in(None, "en")) == []
    assert list(reply_in(None, "hi")) == []


def test_whole_reply_timeout(monkeypatch):
    """Point 7: Whole reply time limit (default 4.0s). Sentences after timeout are refused."""
    monkeypatch.setenv("MIDDLE_REPLY_TIMEOUT_S", "0.05")

    def slow_post(url, *, timeout, **kw):
        time.sleep(0.04)
        return _Resp("आपको 100 मिलते हैं।")

    monkeypatch.setattr(net, "post", slow_post)
    outs = list(reply_in("First is 100. Second is 200. Third is 300.", "hi"))
    assert len(outs) == 3
    # Beyond the 0.05s total limit, sentences are refused with original English text
    assert outs[-1].ok is False
    assert outs[-1].text == "Third is 300."


def test_sentences_go_at_once_and_come_back_in_order(monkeypatch):
    """Four sentences of 0.3 s each take about 0.3 s, not 1.2 s, and the order is the reply's order."""
    delays = {"Yes": 0.3, "One": 0.05, "Ano": 0.2, "Whi": 0.1}
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    says = {"Yes": "हाँ, योजनाएँ हैं।", "One": "एक है पीएम किसान।", "Ano": "दूसरी है मनरेगा।", "Whi": "आप कौन सी सुनना चाहते हैं?"}

    def post(url, *, timeout, **kw):
        key = kw["json"]["input"][:3]
        time.sleep(delays[key])
        return _Resp(says[key])

    monkeypatch.setattr(net, "post", post)
    t0 = time.monotonic()
    outs = list(reply_in("Yes, there are schemes. One is PM Kisan. Another is MGNREGA. Which one do you want to hear?", "hi"))
    assert time.monotonic() - t0 < 0.8
    assert [o.ok for o in outs] == [True] * 4
    assert [o.text for o in outs] == [says[k] for k in ("Yes", "One", "Ano", "Whi")]


def test_a_time_out_is_not_tried_again(monkeypatch):
    """One stuck sentence holds the reply for one time-out, not two; the others still come in Hindi."""
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    monkeypatch.setenv("MIDDLE_TIMEOUT_S", "0.3")
    calls = []

    def post(url, *, timeout, **kw):
        text = kw["json"]["input"]
        calls.append(text)
        if text.startswith("One"):
            time.sleep(timeout)
            raise httpx.TimeoutException("slow")
        return _Resp("हाँ, योजनाएँ हैं।")

    monkeypatch.setattr(net, "post", post)
    t0 = time.monotonic()
    outs = list(reply_in("Yes, there are schemes. One is PM Kisan.", "hi"))
    assert time.monotonic() - t0 < 0.55
    assert [o.ok for o in outs] == [True, False]
    assert outs[1].text == "One is PM Kisan."
    assert calls.count("One is PM Kisan.") == 1


# 6 Oct: Sarvam spelled "PMEGP" in Hindi letters, the guard found no name, the sentence was said in English.
@pytest.mark.parametrize("en,out,lang,want", [
    ("To apply, visit the official PMEGP website and fill the online form.",
     "आवेदन करने के लिए, आधिकारिक पी.एम.ई.जी.पी. वेबसाइट पर जाएं और ऑनलाइन फॉर्म भरें।", "hi",
     "आवेदन करने के लिए, आधिकारिक PMEGP वेबसाइट पर जाएं और ऑनलाइन फॉर्म भरें।"),
    ("To apply, visit the official PMEGP website.", "अर्ज करण्यासाठी, अधिकृत पीएमईजीपी संकेतस्थळाला भेट द्या.", "mr",
     "अर्ज करण्यासाठी, अधिकृत PMEGP संकेतस्थळाला भेट द्या."),
    ("Go to the nearest CSC centre.", "जवळच्या सी.एस.सी. केंद्रावर जा.", "mr", "जवळच्या CSC केंद्रावर जा."),
    ("It is PMEGP.", "यह पी.एम.ई.जी.पी. है।", "hi", "यह PMEGP है।"),
])
def test_short_name_goes_back_to_english_letters(en, out, lang, want):
    assert middle.keep_short_names(en, out, lang) == want


def test_short_name_fix_leaves_the_rest_alone():
    hi = "आवेदन करने के लिए नज़दीकी केंद्र पर जाएँ।"
    assert middle.keep_short_names("To apply, go to the nearest centre.", hi, "hi") == hi       # no short name in the English
    assert middle.keep_short_names("Visit the PMEGP website.", "PMEGP वेबसाइट पर जाएं।", "hi") == "PMEGP वेबसाइट पर जाएं।"
    assert middle.keep_short_names("Visit the PMEGP website.", "பி.எம்.இ.ஜி.பி.", "ta") == "பி.எம்.இ.ஜி.பி."   # Hindi and Marathi only


def test_reply_with_a_spelled_short_name_is_said_in_hindi(monkeypatch):
    class T:
        def __init__(self, timeout=None):
            pass

        def translate(self, sent, lang):
            return "आवेदन करने के लिए, आधिकारिक पी.एम.ई.जी.पी. वेबसाइट पर जाएं और ऑनलाइन फॉर्म भरें।"

    monkeypatch.setattr(middle, "AnswerTranslator", T)
    monkeypatch.setattr(middle, "scheme_names", lambda: [{"id": "pmegp", "en": ["pmegp"], "hi": ["pmegp योजना"]}])
    outs = list(reply_in("To apply, visit the official PMEGP website and fill the online form.", "hi"))
    assert [o.ok for o in outs] == [True]
    assert "PMEGP" in outs[0].text and "To apply" not in outs[0].text


# 6 Oct sweep: right Hindi / Marathi was refused (and English said) for a name worded the translator's way, and for a range.
@pytest.mark.parametrize("en,out,lang", [
    ("Indira Gandhi National Widow Pension Scheme", "इंदिरा गांधी राष्ट्रीय विधवा निवृत्तीवेतन योजना", "mr"),
    ("Indira Gandhi National Disability Pension Scheme", "इंदिरा गांधी राष्ट्रीय विकलांगता पेंशन योजना", "hi"),
    ("Visit the Apprenticeship Portal at apprenticeshipindia.gov.in.", "apprenticeshipindia.gov.in पर शिक्षुता पोर्टल पर जाएँ।", "hi"),
    ("Atal Pension Yojana guarantees a monthly pension of Rs 1,000‑5,000 from age 60.",
     "अटल पेंशन योजना 60 वर्ष की आयु से 1,000-5,000 रुपये की मासिक पेंशन की गारंटी देती है।", "hi"),
])
def test_guard_takes_the_translators_own_wording(en, out, lang):
    assert guard_ok(en, out, lang, scheme_names())


def test_guard_still_refuses_the_wrong_scheme_and_the_wrong_amount():
    names = scheme_names()
    assert not guard_ok("Indira Gandhi National Widow Pension Scheme", "इंदिरा गांधी राष्ट्रीय विकलांगता पेंशन योजना", "hi", names)
    assert not guard_ok("It gives Rs 1,000‑5,000 a month.", "यह हर महीने 1,000-6,000 रुपये देती है।", "hi", names)
