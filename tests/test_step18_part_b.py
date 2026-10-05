"""Step 1.8 (B): the details said back once, a slower voice, trust lines, a long number stopped, what the
line can not do, distress, off topic three times, "thanks" is not goodbye. Fake model, fake audio, no network.
The Hindi and Marathi lines are not checked by a speaker."""
import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Speech
from haqdaar.engine import talk_trust as tt
from haqdaar.prompts import talk as prompt

from tests.test_step18_followup import call, corpus  # noqa: F401  (fixtures)
from tests.test_talk import _say

SCHEMES = "It is a scheme for farmer families. It gives money each year."


def _said(audio, lang="en"):
    """Everything the line said after the hello, sentences joined."""
    text, hello = " ".join(audio.answers), prompt.HELLO[lang]
    assert text.startswith(hello)
    return text[len(hello):].strip()


def _acts(rows):
    return [r["action"] for r in rows if r.get("ev") == "act"]


def _act_rows(rows):
    return [r for r in rows if r.get("ev") == "act"]


# --- word lists: both sides, en / hi / mr ---

@pytest.mark.parametrize("words,kind", [
    ("is it free", "free"), ("क्या यह मुफ्त है", "free"), ("फुकट आहे का", "free"),
    ("are you the government", "government"), ("क्या आप सरकार से हैं", "government"), ("तुम्ही सरकारी आहात का", "government"),
    ("are you a person or a machine", "person"), ("are you a machine", "person"), ("आप इंसान हो", "person"), ("तुम्ही माणूस आहात का", "person"),
    ("let me talk to a person", "to_person"), ("मुझे किसी इंसान से बात करनी है", "to_person"), ("मला माणसाशी बोला", "to_person"),
])
def test_trust_words(words, kind):
    assert tt.trust(words) == kind


@pytest.mark.parametrize("words", [
    "is the insurance free", "is this scheme free", "क्या योजना मुफ्त है", "is the loan free",
    "i lost my crop and i want to know whether the help is free of charge", "what is the weather", "i am a farmer"])
def test_a_question_about_a_scheme_is_not_a_trust_line(words):
    assert tt.trust(words, blocked=True) == ""       # the code found a scheme name or a need in the words


@pytest.mark.parametrize("words,hit", [
    ("my aadhaar number is", True), ("1234 5678 9012", True), ("123456789012", True), ("OTP 4821", True),
    ("one two three four five six", True), ("एक दो तीन चार पांच छह सात", True), ("एक दोन तीन चार पाच सहा", True),
    ("मेरा आधार नंबर", True), ("माझा आधार नंबर", True), ("account number 12345678", True), ("482913", True),
    ("१२३४ ५६७८ ९०१२", True),
    ("i am 45", False), ("my income is 120000", False), ("मेरी आमदनी 120000 रुपये है", False), ("2024", False),
    ("70", False), ("i have 2 acres", False), ("pin code 411001", False), ("my age is forty five", False),
    ("मैं सत्तर साल का हूँ", False), ("i do not have an aadhaar card", False), ("my aadhaar was made in 2015", False),
    ("do i need aadhaar for pm kisan", False)])
def test_a_long_number_is_stopped_and_a_short_one_is_not(words, hit):
    assert tt.read_out(words) is hit


def test_the_mask_cuts_the_digits_out():
    assert "1234" not in tt.mask("my aadhaar is 1234 5678 9012") and "…" in tt.mask("my aadhaar is 1234 5678 9012")
    assert "one" not in tt.mask("it is one two three four five six")
    assert tt.mask("i am 45") == "i am 45"


@pytest.mark.parametrize("words,kind", [
    ("fill the form for me", "form"), ("मेरा फॉर्म भर दो", "form"), ("माझ्यासाठी अर्ज करून द्या", "form"),
    ("check my payment", "payment"), ("पैसा कब आएगा", "payment"), ("पैसे कधी येतील", "payment"),
    ("send me the details by sms", "sms"), ("मुझे एसएमएस भेजो", "sms"),
    ("how do i fill the form", ""), ("which papers do i need", ""), ("फॉर्म कैसे भरें", ""), ("how do i apply", "")])
def test_what_the_line_can_not_do(words, kind):
    assert tt.cannot(words) == kind


@pytest.mark.parametrize("words,hit", [
    ("my husband passed away", True), ("मेरे पति गुज़र गए", True), ("माझे वडील वारले", True), ("i want to die", True),
    ("मैं मरना चाहती हूँ", True), ("मला जगायचे नाही", True),
    ("my cow died", False), ("गाय मर गई", False), ("i want to get a pension", False), ("my mother needs a pension", False),
    ("आई गावाला गेली", False)])
def test_distress_words(words, hit):
    assert tt.distress(words) is hit


@pytest.mark.parametrize("words,hit", [
    ("thanks", True), ("thank you", True), ("धन्यवाद", True), ("शुक्रिया", True), ("ठीक है thank you", True), ("आभारी आहे", True),
    ("thanks bye", False), ("thank you goodbye", False), ("thanks for the pension scheme details please", False),
    ("pension scheme", False)])
def test_a_bare_thanks(words, hit):
    assert tt.thanks(words) is hit


@pytest.mark.parametrize("words,pace", [
    ("speak slowly", "slow"), ("धीरे बोलो", "slow"), ("हळू बोला", "slow"), ("normal speed", "normal"), ("तेज़ बोलो", "normal"),
    ("वेगाने बोला", "normal"), ("i work slowly in the field every day and need a loan", ""), ("a scheme", "")])
def test_pace_words(words, pace):
    assert tt.pace(words) == pace


# --- in a call ---

def test_is_it_free_is_a_fixed_true_line_and_leaves_the_last_reply_alone(call):
    audio, client, rows = call(
        [Speech("tell me about pm kisan"), Speech("is it free?"), Speech("say that again")],
        [_say(SCHEMES, scheme="pm-kisan"), {"action": "repeat", "say": ""}])
    assert _said(audio) == f"{SCHEMES} {prompt.TRUST['free']['en']} {SCHEMES}"
    assert len(client.calls) == 2                                  # the trust line made no model call
    assert True                             # "again" says the scheme answer, not the trust line
    assert "trust" in _acts(rows)


def test_is_the_insurance_free_goes_to_the_model(call):
    _, client, rows = call([Speech("is the insurance free")], [_say("It is a scheme for crops.")])
    assert len(client.calls) == 1 and "trust" not in _acts(rows)


def test_is_the_loan_free_has_a_need_word_and_goes_to_the_model(call):
    _, client, rows = call([Speech("is the loan free")], [_say("It is a loan scheme.")])
    assert len(client.calls) == 1 and "trust" not in _acts(rows)


@pytest.mark.parametrize("words,key,lang", [
    ("are you the government", "government", "en"), ("are you a machine", "person", "en"),
    ("let me talk to a person", "to_person", "en"), ("क्या आप सरकार से हैं", "government", "hi"),
    ("आप इंसान हो", "person", "hi"), ("तुम्ही माणूस आहात का", "person", "mr"), ("is it free", "free", "en"),
    ("फुकट आहे का", "free", "mr")])
def test_trust_lines_in_a_call(call, words, key, lang):
    audio, client, _ = call([Speech(words)], [], lang=lang)
    assert _said(audio, lang) == prompt.TRUST[key][lang] and client.calls == []


def test_a_long_number_gets_the_fixed_line_and_is_never_logged_or_sent(call, tmp_path):
    audio, client, rows = call(
        [Speech("my aadhaar number is 1234 5678 9012"), Speech("1234 5678 9012"), Speech("i am a farmer")],
        [_say(SCHEMES)])
    assert _said(audio) == f"{prompt.NUMBER['en']} {prompt.NUMBER['en']} {SCHEMES}"
    assert len(client.calls) == 1
    assert all(d not in client.calls[0] for d in ("1234", "5678", "9012"))
    raw = "".join(p.read_text() for p in tmp_path.glob("*.jsonl"))
    assert "1234" not in raw and "5678" not in raw and "9012" not in raw
    heard = [r["text"] for r in rows if r.get("ev") == "heard"]
    assert "…" in heard[0] and "…" in heard[1]


def test_a_spoken_number_in_hindi_is_not_logged(call, tmp_path):
    audio, _, rows = call([Speech("एक दो तीन चार पांच छह सात आठ")], [], lang="hi")
    assert _said(audio, "hi") == prompt.NUMBER["hi"]
    assert "तीन" not in [r["text"] for r in rows if r.get("ev") == "heard"][0]


def test_a_short_number_still_counts_as_proof_and_a_long_one_does_not(call):
    ok = _say("You said you are 45. It gives money each year.")
    _, _, rows = call([Speech("i am 45 years old, what does it give")], [ok])
    assert [r for r in rows if r.get("ev") == "blocked" and r["rule"] != "fact"] == []
    bad = _say("You told me 987654321012. It gives money.")
    _, _, rows = call([Speech("my number is 987654321012"), Speech("what does it give")], [bad, _say("It gives money.")])
    assert any(r.get("ev") == "blocked" for r in rows)


@pytest.mark.parametrize("words,lang,key", [
    ("fill the form for me", "en", "form"), ("check my payment", "en", "payment"),
    ("मेरा फॉर्म भर दो", "hi", "form"), ("पैसा कब आएगा", "hi", "payment"), ("माझ्यासाठी अर्ज करून द्या", "mr", "form"),
    ("send me the details by sms", "en", "sms"), ("मुझे एसएमएस भेजो", "hi", "sms")])
def test_what_the_line_can_not_do_in_a_call(call, words, lang, key):
    audio, client, rows = call([Speech(words)], [], lang=lang)
    assert _said(audio, lang) == prompt.CANNOT[key][lang] and client.calls == []
    assert "cannot" in _acts(rows)


def test_a_how_to_question_still_goes_to_the_model(call):
    _, client, _ = call([Speech("how do i fill the form")], [_say("To apply, go to the centre.")])
    assert len(client.calls) == 1


@pytest.mark.parametrize("words,lang", [("my husband passed away", "en"), ("मेरे पति गुज़र गए", "hi"), ("माझे वडील वारले", "mr")])
def test_distress_one_kind_sentence_then_the_model_with_a_note(call, words, lang):
    reply = "Do you want to tell me what help you need?" if lang == "en" else "आप किस बात में मदद चाहते हैं?"
    audio, client, rows = call([Speech(words)], [_say(reply, action="ask")], lang=lang)
    assert _said(audio, lang) == prompt.DISTRESS[lang] + " " + reply
    assert "Ask no list of questions" in client.calls[0]
    assert [r for r in _act_rows(rows)][0].get("distress") is True


def test_no_distress_note_on_an_ordinary_turn(call):
    audio, client, rows = call([Speech("my cow died, i need help")], [_say(SCHEMES)])
    assert _said(audio) == SCHEMES
    assert "Ask no list of questions" not in client.calls[0] and "distress" not in _act_rows(rows)[0]


def test_off_topic_three_times_in_a_row_ends_the_call_politely(call):
    off = {"action": "other_topic", "say": ""}
    audio, client, rows = call(
        [Speech("what is the weather"), Speech("who will win the match"), Speech("tell me a joke"), Speech("pension")],
        [off, off, off, _say(SCHEMES)])
    assert _said(audio) == f"{prompt.OTHER_TOPIC['en']} {prompt.OTHER_TOPIC['en']} {prompt.OFF_TOPIC_END['en']}"
    assert len(client.calls) == 3 and _acts(rows)[-1] == "goodbye"


def test_a_turn_on_topic_resets_the_off_topic_count(call):
    off = {"action": "other_topic", "say": ""}
    audio, client, _ = call(
        [Speech("what is the weather"), Speech("who will win"), Speech("pension scheme"), Speech("the weather"), Speech("a joke")],
        [off, off, _say(SCHEMES), off, off])
    assert prompt.OFF_TOPIC_END["en"] not in " ".join(audio.answers) and len(client.calls) == 5


def test_thanks_is_not_goodbye_the_first_time(call):
    audio, client, rows = call([Speech("thanks"), Speech("no"), Speech("never reached")], [])
    assert _said(audio) == prompt.THANKS["en"] and client.calls == []
    assert _acts(rows) == ["thanks", "goodbye"]


def test_thanks_then_a_new_question_goes_on(call):
    audio, client, rows = call([Speech("धन्यवाद"), Speech("pension scheme")], [_say("यह किसान परिवारों के लिए एक योजना है।")], lang="hi")
    assert _said(audio, "hi").startswith(prompt.THANKS["hi"]) and len(client.calls) == 1 and "goodbye" not in _acts(rows)


def test_a_real_bye_ends_as_before(call):
    _, client, rows = call([Speech("thank you goodbye")], [{"action": "goodbye", "say": ""}])
    assert len(client.calls) == 1 and "thanks" not in _acts(rows) and _acts(rows) == ["goodbye"]


def test_slower_voice_sets_the_pace_and_says_the_last_reply_again(call):
    def go(words, lang="en"):
        audio, _, rows = call([Speech("tell me about pm kisan"), Speech(words)], [_say(SCHEMES)], lang=lang)
        return audio, rows

    audio, rows = go("speak slowly")
    assert _said(audio) == f"{SCHEMES} {prompt.PACE['slow']['en']} {SCHEMES}"
    assert audio.pace == tunables.TALK_SLOW_PACE and "pace" in _acts(rows)
    audio, _ = go("धीरे बोलो", "hi")
    assert prompt.PACE["slow"]["hi"] in " ".join(audio.answers) and audio.pace == tunables.TALK_SLOW_PACE
    audio, _ = go("normal speed")
    assert _said(audio) == f"{SCHEMES} {prompt.PACE['normal']['en']}" and audio.pace == 0.0
    audio, _ = go("हळू बोला", "mr")
    assert audio.pace == tunables.TALK_SLOW_PACE


def test_the_live_voice_takes_the_pace():
    from haqdaar.audio import live_tts
    import inspect
    assert "pace" in inspect.signature(live_tts.stream).parameters
    assert "pace" in inspect.signature(live_tts.speak).parameters


# --- the details said back once, then the answer ---

def _age(known):
    return next((p for p in known.split("; ") if p.startswith("age = ")), "")


def test_the_details_are_said_back_once_then_the_answer(call):
    first = _say("You are a woman farmer who lost a crop. It gives money each year.", action="answer",
                 facts={"gender": "female", "occupation": "farmer", "age": 45})
    second = _say("It also covers the next season.", facts={})
    audio, client, rows = call(
        [Speech("just tell me, i am a woman, a farmer, my crop failed"), Speech("tell me more")], [first, second])
    note = client.calls[0].split("NOTE: ")[1]
    assert "First say back, in ONE short sentence" in note
    assert "woman" in note and "farmer" in note
    assert "Do not ask" in note and "new question" in note
    assert "First say back" not in client.calls[1]                 # once in a call
    recap_rows = [r for r in _act_rows(rows) if r.get("recap")]
    assert len(recap_rows) == 1 and recap_rows[0]["action"] == "answer"
    assert len([c for c in client.calls if "First say back" in c]) == 1


def test_no_recap_with_fewer_than_two_facts(call):
    _, client, rows = call([Speech("just tell me about pension")], [_say(SCHEMES)])
    assert "First say back" not in client.calls[0] and not [r for r in _act_rows(rows) if r.get("recap")]


def test_a_correction_after_the_recap_uses_the_new_value(call):
    first = _say("You are a woman farmer who lost a crop. It gives money.", facts={"age": 30})
    fix = _say("At 60, it gives a pension.", facts={"age": 60})
    nxt = _say("Here is more.", facts={})
    audio, client, rows = call(
        [Speech("just tell me, i am a woman farmer"), Speech("no, i am 60"), Speech("tell me more")], [first, fix, nxt])
    ages = [c.split("KNOWN ABOUT THE CALLER: ")[1].split("\n")[0] for c in client.calls]
    assert _age(ages[1]) and _age(ages[2]) and _age(ages[1]) != _age(ages[2])    # 30 -> 60: the new band is in the next prompt
    again = [c for c in client.calls if "First say back" in c]
    assert len(again) == 1


def test_a_correction_in_hindi_takes_the_new_value(call):
    first = _say("आप महिला किसान हैं।", facts={"age": 30})
    fix = _say("साठ की उम्र में पेंशन मिलती है।", facts={"age": 60})
    _, client, _ = call(
        [Speech("बस बताइए, मैं एक महिला किसान हूँ"), Speech("नहीं, मैं 60 की हूँ"), Speech("और बताइए")],
        [first, fix, _say("और जानकारी यह है।")], lang="hi")
    ages = [c.split("KNOWN ABOUT THE CALLER: ")[1].split("\n")[0] for c in client.calls]
    assert "age = " not in ages[0] and "age = " in ages[1] and ages[1] != ages[2]
