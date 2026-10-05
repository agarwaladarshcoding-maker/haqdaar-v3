"""The faults of the 5 Oct real call (a son asks for his 70-year-old mother): L1-L4, P8, P9.
Fake model, fake audio, no network. Fresh sentences are here on purpose: the earlier fix pass
passed only the sentences it was given."""
import pytest

from haqdaar.data.corpus import Corpus
from haqdaar.engine import talk_words
from haqdaar.prompts import talk as prompt

from tests.test_talk import Speech, _say, call, corpus  # noqa: F401  (fixtures)


def _spot(text):
    return talk_words.spot(text, Corpus.load("CURRENT"))


def _blocked(rows):
    return [r["rule"] for r in rows if r.get("ev") == "blocked"]


# --- L1: a fact nobody said ---

def test_the_prompt_forbids_a_fact_the_caller_did_not_say():
    system = prompt.build("en", "", {}, {}, None, [], [], "x")[0]["content"]
    assert "Never say a fact about the caller that they did not say" in system
    assert '"if she is a widow, ..."' in system


# --- L2: a mention is not a switch of the person ---

@pytest.mark.parametrize("text", [
    "मेरी माँ विधवा नहीं है, मेरे पिताजी हैं, तो उसके हिसाब से बताइए",
    "मेरे पिताजी जिंदा हैं", "my mother is not a widow, my father is alive",
    "माझी आई विधवा नाही, माझे वडील आहेत", "her husband is alive so tell for her",
])
def test_a_relation_word_that_is_only_mentioned_names_no_one(text):
    assert talk_words.other_person(text) == ""
    assert "gender" not in _spot(text)


@pytest.mark.parametrize("text", [
    "मेरे पिताजी के लिए बताइए", "अब पिताजी के लिए बताइए", "for my father please", "now for my father",
    "माझ्या वडिलांसाठी सांगा",
])
def test_a_real_switch_names_the_person(text):
    assert talk_words.other_person(text)


def test_the_models_gender_flip_on_a_mention_is_dropped_but_a_real_switch_counts(call):
    flip = {"category": "pension", "gender": "male"}
    _, client, rows = call(
        [Speech("मेरे को स्कीम जानना है जो मेरी ओल्ड एज मदर को हेल्प करे"),
         Speech("मेरी माँ विधवा नहीं है, मेरे पिताजी हैं, तो उसके हिसाब से बताइए"),
         Speech("my mother is not a widow, my father is alive"),
         Speech("अब पिताजी के लिए बताइए")],
        [_say("How old is she?", facts={"category": "pension", "gender": "female"}),
         _say("Tell me about the pension scheme.", facts=flip),
         _say("Tell me about the pension scheme again.", facts=flip),
         _say("Here is the pension scheme for him.", facts=flip)])
    known = [c.split("KNOWN ABOUT THE CALLER:")[1].split("\n")[0] for c in client.calls]
    assert "gender = female" in known[1] and "gender = female" in known[2]
    assert "gender = male" not in known[1] + known[2]
    genders = [r["value"] for r in rows if r.get("box") == "gender"]
    assert genders == ["female", "male"]      # male only after the real switch "अब पिताजी के लिए"


# --- L3: the caller's own numbers may be said back ---

def test_a_number_the_caller_said_is_not_blocked_but_a_made_up_one_is(call):
    audio, _, rows = call(
        [Speech("सत्तर साल"), Speech("my mother is 66 years old")],
        [_say("Your mother is 70 years old, so I will look at pension schemes."),
         _say("This scheme gives 987654 rupees a month.")])
    assert audio.answers[0] == "Your mother is 70 years old, so I will look at pension schemes."
    assert _blocked(rows) == ["number"]
    assert "987654" not in " ".join(audio.answers)
    _, _, rows2 = call([Speech("she is 66 years old")], [_say("She is 66 years old, I understand.")])
    assert _blocked(rows2) == []


# --- L4: going back to a scheme shown earlier in this call ---

def test_going_back_to_a_shown_scheme_is_allowed_and_a_never_shown_one_is_blocked(call):
    audio, client, rows = call(
        [Speech("pension schemes"), Speech("and others"), Speech("tell me about the second"),
         Speech("tell me about the first one again")],
        [_say("The widow pension is one.", action="show_scheme", scheme="ignwps"),
         _say("The Atal pension is another.", action="show_scheme", scheme="apy"),
         _say("It is for people who save.", scheme="apy"),
         _say("It is for widows.", scheme="ignwps")])
    assert _blocked(rows) == []
    assert [r["scheme"] for r in rows if r.get("ev") == "act"][-1] == "ignwps"
    _, _, rows2 = call(
        [Speech("pension schemes"), Speech("tell me more"), Speech("and the other one")],
        [_say("The widow pension is one.", action="show_scheme", scheme="ignwps"),
         _say("It is for widows.", scheme="ignwps"),
         _say("The Atal pension is for savers.", scheme="apy"),
         _say("It is for widows.", scheme="ignwps")])
    assert _blocked(rows2) == ["other_scheme"]


# --- P8: the need follows "I want"; work said about oneself is not a need ---

@pytest.mark.parametrize("text,need", [
    ("मेरी मां बीमार है मुझे लोन चाहिए", "business_loans"),
    ("my mother is sick and I need a loan", "business_loans"),
    ("my wife is sick, I want a loan", "business_loans"),
    ("माझी आई बीमार आहे मला कर्ज हवे", "business_loans"),
    ("मेरे पिताजी का इलाज चल रहा है, मुझे कर्ज चाहिए", "business_loans"),
    ("मुझे खेती और घर चाहिए", "farming"),       # both wanted: the first named stays first
    ("मुझे इलाज चाहिए", "health"),
])
def test_the_need_follows_the_want_word(text, need):
    cats = talk_words.spot_all(text, Corpus.load("CURRENT"))["category"]
    assert cats[0] == need


@pytest.mark.parametrize("farmer,pension", [
    ("मैं किसान हूँ", "मुझे पेंशन चाहिए"),
    ("मी शेतकरी आहे", "मला पेन्शन हवी"),
    ("I am a farmer", "I want a pension"),
])
def test_a_work_word_in_a_pension_talk_sets_work_not_the_need(call, farmer, pension):
    _, client, rows = call(
        [Speech(pension), Speech(farmer)],
        [_say("Tell me more.", facts={"category": "pension"}), _say("Tell me more.")])
    assert "category = pension" in client.calls[1]
    assert "category = farming" not in client.calls[1]
    assert [r["value"] for r in rows if r.get("box") == "category"] == ["pension"]
    assert _spot(farmer).get("occupation") == "farmer"


def test_farmer_schemes_still_names_the_need():
    assert _spot("farmer schemes")["category"] == "farming"
    assert _spot("मेरे को फार्मर स्कीम्स बताइए")["category"] == "farming"


# --- P9: the not-held line in gu and ta ---

@pytest.mark.parametrize("lang,low,high", [("gu", "઀", "૿"), ("ta", "஀", "௿")])
def test_the_not_held_line_is_in_gujarati_and_tamil(lang, low, high):
    say = prompt.not_held_say(lang, ["pension"])
    assert say != prompt.not_held_say("en", ["pension"])
    assert any(low <= ch <= high for ch in prompt.NOT_HELD_SAY[lang])
    assert any(low <= ch <= high for ch in prompt.HELP_WITH[lang])
