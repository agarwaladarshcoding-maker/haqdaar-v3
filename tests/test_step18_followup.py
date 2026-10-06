"""Step 1.8 (A): follow-up talk by fixed code (pointing back, "any other", side by side, "will I get it",
say it another way, hold on, "can you hear me"). Fake model, fake audio, no network, no money."""
import re
from types import SimpleNamespace

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Hangup, Silence, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.engine import talk_follow, talk_pick
from haqdaar.engine.call import Engine
from haqdaar.prompts import talk as prompt

from tests.test_qa_engine import QAAudio
from tests.test_talk import ALL, Client, Index, _say

WIDOW = "The widow pension is one scheme."
ATAL = "The Atal pension is another scheme."
TWO = f"{WIDOW} {ATAL} Which one do you want to hear about?"
NAMES = {"widow pension": "ignwps", "atal pension": "apy", "pm kisan": "pm-kisan",
         "विधवा पेंशन": "ignwps", "अटल पेंशन": "apy"}
FIRST_IDS = ["ignwps", "apy"] + [i for i in ALL if i not in ("ignwps", "apy")]


class NamedIndex(Index):
    """The test index, plus the name finder of the real one."""

    def named_in(self, text, among=None):
        low = text.lower()
        found = sorted((low.index(n), sid) for n, sid in NAMES.items()
                       if n in low and (among is None or sid in among))
        return [sid for _at, sid in found]


class LangAudio(QAAudio):
    def __init__(self, inputs, lang):
        key = {v: k for k, v in tunables.turn0_keys().items()}[lang]
        super().__init__([Digit(key)] + list(inputs) + [Hangup()], lang)


@pytest.fixture(scope="module")
def corpus():
    return Corpus.load("CURRENT")


@pytest.fixture
def call(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": NamedIndex(FIRST_IDS))
    calls = []

    def go(inputs, replies, lang="en"):
        calls.append(1)
        audio, client = LangAudio(inputs, lang), Client(replies, 0.0)
        log = Log.open(f"step18_{len(calls)}", corpus.snapshot_id, logs_dir=str(tmp_path))
        Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
        return audio, client, log_text.read_rows(log.path)

    return go


def _blocked(rows):
    return [r["rule"] for r in rows if r.get("ev") == "blocked"]


def _scheme_in_talk(prompt_text):
    return prompt_text.split("SCHEME IN TALK: ")[1].split("\n")[0]


# --- 1. what was named: "the second one", "any other?" ---

@pytest.mark.parametrize("words", ["दूसरा वाला बताइए", "tell me the second one", "दुसरी सांगा"])
def test_the_second_one_is_the_second_of_the_last_reply(words):
    assert talk_follow.pick(words, ["ignwps", "apy"], ["ignwps", "apy"], "ignwps") == ("move", "apy")


@pytest.mark.parametrize("words", ["और कोई योजना है क्या", "any other scheme?", "आणखी काही आहे का"])
def test_any_other_asks_for_a_scheme_not_named_yet(words):
    assert talk_follow.pick(words, ["ignwps"], ["ignwps"], "ignwps") == ("other", "")


def test_more_about_the_same_scheme_is_not_any_other():
    for words in ("और बताइए", "tell me more", "अजून सांगा"):
        assert talk_follow.pick(words, ["ignwps"], ["ignwps"], "ignwps") == ("", "")


def test_the_talk_moves_to_the_second_scheme_by_code(call):
    audio, client, rows = call(
        [Speech("pension schemes"), Speech("the second one"), Speech("how much does it give")],
        [_say(TWO, action="show_scheme", scheme="ignwps"),
         _say("It is for people who save.", scheme="apy"),
         _say("It gives a monthly amount.", scheme="apy")])
    assert _scheme_in_talk(client.calls[1]).startswith("[apy]")
    assert "The caller means [apy]" in client.calls[1]
    assert _blocked(rows) == []


def test_the_second_one_in_hindi_moves_the_talk(call):
    _, client, _ = call(
        [Speech("pension schemes"), Speech("दूसरा वाला")],
        [_say("विधवा पेंशन एक योजना है। अटल पेंशन दूसरी योजना है। आप किसके बारे में सुनना चाहेंगे?",
              action="show_scheme", scheme="ignwps"), _say("यह बचत करने वालों के लिए है।", scheme="apy")],
        lang="hi")
    assert _scheme_in_talk(client.calls[1]).startswith("[apy]")


def test_a_second_scheme_named_in_a_two_scheme_reply_counts_as_shown(call):
    # the model's own `scheme` is the first; the answer about the second one must not be sent back
    _, _, rows = call(
        [Speech("pension schemes"), Speech("how much does it give")],
        [_say(TWO, action="show_scheme", scheme="ignwps"), _say("It is for people who save.", scheme="apy")])
    assert _blocked(rows) == []


def test_any_other_offers_only_schemes_not_named_and_says_when_none_are_left(call):
    _, client, _ = call(
        [Speech("just tell me some schemes"), Speech("any other?")],   # ask-first does not list a long list; "just tell me" does
        [_say(TWO, action="show_scheme", scheme="ignwps"), _say("There is also a loan scheme.")])
    note = client.calls[1].split("NOTE: ")[1]
    left = re.findall(r"\[([\w-]+)\]", note.split("Name only: ")[1].split(". Do not")[0])
    assert left and "ignwps" not in left and "apy" not in left
    _, client2, _ = call([Speech("any other?")], [_say("There is one more.")])
    assert "Name only" in client2.calls[0]       # nothing named yet: every scheme found is on offer


def test_nothing_left_tells_the_model_to_say_so(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": NamedIndex(["ignwps", "apy"]))
    audio, client = LangAudio([Speech("some schemes"), Speech("any other?")], "en"), Client(
        [_say(TWO, action="show_scheme", scheme="ignwps"), _say("There is no other one.")], 0.0)
    log = Log.open("step18_none", corpus.snapshot_id, logs_dir=str(tmp_path))
    Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
    assert "Every scheme found was already named" in client.calls[1]


# --- 2. going back ---

@pytest.mark.parametrize("words", ["वो पहले वाली", "the first one", "पहिली सांगा"])
def test_the_first_one_goes_back_to_an_earlier_scheme(words):
    assert talk_follow.pick(words, ["apy"], ["ignwps", "apy"], "apy") == ("move", "ignwps")
    assert talk_follow.pick(words, ["ignwps", "apy"], ["ignwps", "apy"], "apy") == ("move", "ignwps")


@pytest.mark.parametrize("words", ["the one before", "पिछली वाली", "मागची सांगा"])
def test_the_one_before_is_the_scheme_named_before_this_one(words):
    assert talk_follow.pick(words, ["apy"], ["ignwps", "apy"], "apy") == ("move", "ignwps")
    assert talk_follow.pick(words, ["ignwps"], ["ignwps"], "ignwps") == ("", "")


def test_going_back_keeps_the_parts_already_told_of_that_scheme(call):
    _, client, _ = call(
        [Speech("pension schemes"), Speech("tell me about the widow pension"), Speech("the second one"),
         Speech("the one before")],
        [_say(TWO, action="show_scheme", scheme="ignwps", parts=["gives"]),
         _say("It is for people who save.", scheme="apy", parts=["who"]),
         _say("The widow pension gives money every month.", scheme="ignwps")])
    assert "TOLD: gives." in client.calls[-1].split("SCHEME IN TALK: ")[1].split("\n")[0]
    assert _scheme_in_talk(client.calls[-1]).startswith("[ignwps]")


# --- 3. two schemes side by side ---

@pytest.mark.parametrize("words", ["किसमें ज़्यादा पैसा मिलता है", "which gives more", "कोणत्यात जास्त पैसे"])
def test_which_gives_more_is_side_by_side_only_with_two_named(words):
    assert talk_follow.side_by_side(words, ["ignwps", "apy"])
    assert not talk_follow.side_by_side(words, ["ignwps"])


def test_side_by_side_lets_the_two_last_named_through_and_sends_a_third_back(call):
    audio, client, rows = call(
        [Speech("pension schemes"), Speech("which gives more"), Speech("which gives more")],
        [_say(TWO, action="show_scheme", scheme="ignwps"),
         _say("The widow pension gives money. The Atal pension too.", scheme="apy"),
         _say("The PM Kisan gives money.", scheme="pm-kisan"),
         _say("Both give money.", scheme="ignwps")])
    assert "The caller compares [ignwps] and [apy]" in client.calls[1]
    assert "Never say which one is better" in client.calls[1]
    assert _blocked(rows) == ["other_scheme"]       # the third scheme, once
    assert "PM Kisan" not in " ".join(audio.answers) and audio.answers[-1] == "Both give money."


# --- 4. "will I get it?" ---

@pytest.mark.parametrize("words", ["मुझे मिलेगा क्या", "will I get it?", "मला मिळेल का"])
def test_will_i_get_it_is_found_in_hi_en_mr(words):
    assert talk_follow.will_get(words)


def test_the_picker_on_one_scheme_names_the_one_thing_it_depends_on(corpus):
    box = talk_pick.needs_ask("ignwps", _unasked(corpus), corpus)
    assert box
    known = _unasked(corpus)
    for b in list(known):
        known[b] = "UNKNOWN" if b != "category" else known[b]
    assert talk_pick.needs_ask("ignwps", known, corpus) is None
    assert talk_pick.needs_ask("ignwps", _unasked(corpus), corpus, skip=[box]) != box


def _unasked(corpus):
    from haqdaar.contracts.types import SEVEN_BOXES, UNASKED
    return {b: UNASKED for b in SEVEN_BOXES}


def test_will_i_get_it_asks_the_one_thing_the_scheme_depends_on(call, corpus):
    _, client, _ = call(
        [Speech("tell me about the widow pension"), Speech("will I get it?")],
        [_say(WIDOW, scheme="ignwps"), _say("It is for widows. Are you a woman?", action="ask")])
    asked = re.search(r"NEXT QUESTION: (\w+)", client.calls[1]).group(1)
    assert asked != "none" and asked != "category"      # "widow" told the gender: another box the scheme needs
    assert "Promise nothing" in client.calls[1]


def test_will_i_get_it_when_all_is_known_tells_who_it_is_for(call, corpus):
    # every box the scheme depends on is told in the same breath
    box_values = {b: v for b, v in _everything(corpus, "ignwps").items()}
    _, client, _ = call(
        [Speech("tell me about the widow pension"), Speech("मिलेगा क्या")],
        [_say(WIDOW, scheme="ignwps", facts=box_values),
         _say("It is for widows. You told me you are a woman.")])
    assert "Say \"it is for (who it is for); you told me" in client.calls[1]


def _everything(corpus, sid):
    """One allowed value per box that the scheme fits."""
    ix = talk_pick._ix(corpus, sid)
    out = {}
    for box in ("age", "gender", "occupation", "state", "social_category"):
        for v in corpus.values(box):
            if corpus.mask(box, v) & (1 << ix):
                out[box] = "70" if box == "age" and str(v).startswith("60") else v
                break
    return out


# --- 5. say it another way ---

@pytest.mark.parametrize("words", ["समझ नहीं आया", "I did not understand", "कळले नाही"])
def test_did_not_understand_is_found(words):
    assert talk_follow.simpler(words)


def test_simpler_is_an_action_with_a_note_and_its_reply_is_said(call):
    audio, client, rows = call(
        [Speech("tell me about the widow pension"), Speech("I did not understand")],
        [_say(WIDOW, scheme="ignwps"), {"action": "simpler", "say": "It helps widows with money.", "scheme": "ignwps"}])
    assert 'Use action "simpler"' in client.calls[1]
    assert audio.answers[-1] == "It helps widows with money."
    assert [r["action"] for r in rows if r.get("ev") == "act"] == ["answer", "simpler"]


@pytest.mark.parametrize("words", ["कितना बोला", "how much did you say", "किती म्हणालात"])
def test_how_much_did_you_say_is_found(words):
    assert talk_follow.how_much(words)


def test_how_much_did_you_say_is_only_the_number_sentence_with_no_model_call(call):
    audio, client, _ = call(
        [Speech("tell me about the widow pension"), Speech("how much did you say")],
        [_say("It is for widows. It gives 500 rupees a month. Shall I tell the papers?", scheme="ignwps")])
    assert audio.answers[-1] == "It gives 500 rupees a month."
    assert len(client.calls) == 1


# --- 6. hold on ---

@pytest.mark.parametrize("words", ["एक मिनट रुको", "hold on", "एक मिनिट थांबा"])
def test_hold_on_is_found(words):
    assert talk_follow.hold(words)


def test_a_long_sentence_with_wait_in_it_is_not_a_hold():
    assert not talk_follow.hold("wait tell me about the pension scheme for my mother")
    assert not talk_follow.hold("मुझे पेंशन चाहिए")


def test_hold_says_one_line_with_no_model_call_and_the_quiet_rule_waits(call):
    audio, client, rows = call(
        [Speech("hold on"), Silence(1), Silence(2), Silence(3)], [])
    assert " ".join(audio.answers).endswith(prompt.HOLD["en"])
    assert not client.calls
    assert "closing_farewell" not in audio.played and "waiting_for_reply" not in audio.played
    assert [r["action"] for r in rows if r.get("ev") == "act"] == ["hold"]


def test_with_no_hold_time_left_the_quiet_rule_runs_as_before(call, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_HOLD_S", 0.0)
    audio, _, _ = call([Speech("hold on"), Silence(1), Silence(2)], [])
    assert "waiting_for_reply" in audio.played and "closing_farewell" in audio.played


def test_the_hold_line_is_there_in_hi_mr_en():
    assert all(prompt.HOLD[k] and prompt.HEAR[k] for k in ("hi", "mr", "en"))


def test_the_model_may_ask_for_a_hold_too(call):
    audio, _, rows = call([Speech("give me some time please, I will find the card"), Silence(1), Silence(2)],
                          [{"action": "hold", "say": ""}])
    assert " ".join(audio.answers).endswith(prompt.HOLD["en"])
    assert "closing_farewell" not in audio.played


# --- 7. "hello? can you hear me?" mid-call ---

@pytest.mark.parametrize("words", ["हैलो? आवाज़ आ रही है?", "hello? can you hear me?", "हॅलो ऐकू येतंय का"])
def test_can_you_hear_me_is_found(words):
    assert talk_follow.hear(words)


def test_hello_alone_is_a_check_but_a_sentence_with_hello_is_not():
    assert talk_follow.hear("hello?")
    assert not talk_follow.hear("hello I need a scheme for my farm and my house")


ASKED = {"en": "Which one do you want to hear about?", "hi": "आप किसके बारे में सुनना चाहेंगे?",
         "mr": "तुम्हाला कशाबद्दल ऐकायचे आहे?"}
ONE = {"en": "The widow pension is one scheme.", "hi": "विधवा पेंशन एक योजना है।", "mr": "विधवा पेंशन ही एक योजना आहे."}


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_can_you_hear_me_answers_yes_then_asks_the_last_question_again(call, lang):
    audio, client, _ = call(
        [Speech("pension schemes"), Speech("hello? can you hear me?")],
        [_say(f"{ONE[lang]} {ASKED[lang]}", action="show_scheme", scheme="ignwps")], lang=lang)
    assert " ".join(audio.answers).endswith(prompt.HEAR[lang] + " " + ASKED[lang])
    assert len(client.calls) == 1


# --- the cost guard ---

def test_the_fixed_part_of_the_prompt_grew_by_less_than_150_words():
    system = prompt.build("en", "", {}, {}, None, [], [], "x")[0]["content"]
    assert len(system.split()) - 1638 <= 150
    assert "simpler" in prompt.ACTIONS and "hold" in prompt.ACTIONS


def test_two_needs_in_one_turn_do_not_break_the_follow_up_note(call):
    """The second need of a turn is kept in its own name; the follow-up note still reaches the model whole."""
    audio, client, rows = call(
        [Speech("समझ नहीं आया, खेती और घर दोनों के लिए कुछ है क्या")],
        [_say("Two schemes for you.", action="show_scheme", scheme="")], lang="hi")
    assert prompt.FOLLOW["simpler"] in client.calls[0]
