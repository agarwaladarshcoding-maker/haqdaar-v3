"""Step 7.13 B3: the talk-only loop on a fake model and fake audio."""
import re
import time
from types import SimpleNamespace

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Hangup, Silence, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.data.scheme_text import SchemeText
from haqdaar.engine.call import Engine
from haqdaar.prompts import talk as prompt

from tests.test_qa_engine import QAAudio

ALL = ["pm-kisan", "kcc", "pmfby", "smam", "pmay-g", "ignwps", "jsy1", "mgnrega", "pmmy", "apy"]


class Audio(QAAudio):
    """English caller; the line drops when the script runs out."""

    def __init__(self, inputs):
        super().__init__([Digit("3")] + list(inputs) + [Hangup()], "en")
        self.hello = 0

    def say_text(self, text):
        if text in prompt.HELLO["en"]:           # the hello, sentence by sentence
            self.hello += 1
            self.played.append("HELLO")
            return True
        return super().say_text(text)


class Client:
    def __init__(self, replies, delay=0.0):
        self.replies, self.delay, self.calls = list(replies), delay, []
        self.models, self.busy = [], set()

    def call(self, messages, task="", timeout=None, model=None):
        self.models.append(model)
        if model in self.busy:
            return SimpleNamespace(success=False, data=None, is_429=True)
        self.calls.append(messages[1]["content"])
        time.sleep(self.delay)
        data = self.replies.pop(0) if self.replies else {"action": "not_for_me"}
        return SimpleNamespace(success=data is not None, data=data)


class Index:
    def __init__(self, ids=ALL):
        self.ids = list(ids)

    def search(self, text, k=4):
        ids = (["pmay-g"] + [i for i in self.ids if i != "pmay-g"]) if "house" in text else self.ids
        return [scheme_index.Hit(sid, 0.5, "vector") for sid in ids[:k]]


@pytest.fixture(scope="module")
def corpus():
    return Corpus.load("CURRENT")


@pytest.fixture
def call(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())

    calls = []

    def go(inputs, replies, delay=0.0):
        calls.append(1)
        audio, client = Audio(inputs), Client(replies, delay)
        log = Log.open(f"talk_test_{len(calls)}", corpus.snapshot_id, logs_dir=str(tmp_path))
        Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
        rows = log_text.read_rows(log.path)
        assert not [r for r in rows if r.get("invalid")]
        return audio, client, rows

    return go


def _say(text, **more):
    return {"action": "answer", "say": text, "facts": {}, "scheme": "", "ask_box": "", **more}


def _number(corpus, scheme_id):
    card = SchemeText.load(corpus.snapshot_id).card(scheme_id, "en")
    return re.search(r"\d[\d,]{2,}", card).group(0)


def test_clear_ask_is_answered_by_live_voice_and_logged(call, corpus):
    say = f"PM Kisan gives {_number(corpus, 'pm-kisan')} rupees to farmer families."
    audio, client, rows = call([Speech("what is PM Kisan")], [_say(say, scheme="pm-kisan")])
    assert audio.played[:3] == ["greeting_trilingual", "HELLO", "HELLO"]
    assert audio.answers == [say]
    assert [r["text"] for r in rows if r.get("ev") == "heard"] == ["what is PM Kisan"]
    assert [r["action"] for r in rows if r.get("ev") == "act"] == ["answer"]
    assert 'NEWEST CALLER WORDS: "what is PM Kisan"' in client.calls[0]
    assert "[pm-kisan]" in client.calls[0] and "mark: " in client.calls[0]
    assert audio.hung_up and rows[-1].get("stop")


def test_follow_up_keeps_the_scheme_and_reads_the_log(call):
    audio, client, _ = call(
        [Speech("tell me about the village house scheme"), Speech("how much money?")],
        [_say("It helps build a house in a village.", scheme="pmay-g"), _say("I do not have that information.")],
    )
    second = client.calls[1]
    assert "[pmay-g]" in second                               # the scheme in focus stays in the prompt
    assert 'CALLER: "tell me about the village house scheme"' in second
    assert 'AGENT: "It helps build a house in a village."' in second
    assert len(audio.answers) == 2


def test_facts_told_over_three_turns_fill_the_profile(call):
    audio, client, rows = call(
        [Speech("I need some scheme"), Speech("I do farming"), Speech("I am 30 years old"), Speech("ok")],
        [
            {"action": "ask", "say": "What kind of help do you need?", "ask_box": "category", "facts": {}},
            {"action": "show_scheme", "say": "There are schemes for farmers.",
             "facts": {"category": "farming", "occupation": "farmer"}},
            {"action": "show_scheme", "say": "There are schemes for farmers.", "facts": {"age": 30}},
            {"action": "not_for_me"},
        ],
    )
    assert "KNOWN ABOUT THE CALLER: nothing yet" in client.calls[0]
    assert "NEXT QUESTION: category" in client.calls[0]
    assert "category = farming; age = 18-35; occupation = farmer" in client.calls[3]
    answered = [(r["box"], r["value"]) for r in rows if r.get("class") == "ANSWER" and r.get("box")]
    assert answered == [("category", "farming"), ("occupation", "farmer"), ("age", "18-35")]


def test_a_fact_that_is_not_an_allowed_value_is_dropped_and_logged(call):
    _, client, rows = call(
        [Speech("I am old"), Speech("ok")],
        [_say("Tell me what you need.", facts={"age": "old", "gender": "alien", "shoe": "9"}),
         {"action": "not_for_me"}],
    )
    assert [r["text"] for r in rows if r.get("rule") == "fact"] == ["age = old", "gender = alien", "shoe = 9"]
    assert "KNOWN ABOUT THE CALLER: nothing yet" in client.calls[1]


def test_the_model_may_only_ask_the_pickers_box(call):
    wrong = {"action": "ask", "say": "Are you a man or a woman?", "ask_box": "gender"}
    right = {"action": "ask", "say": "What kind of help do you need?", "ask_box": "category"}
    audio, client, _ = call([Speech("I just called")], [wrong, right])
    assert audio.answers == ["What kind of help do you need?"]
    assert 'Ask about "category", not "gender".' in client.calls[1]

    audio, _, _ = call([Speech("I just called")], [wrong, wrong])     # twice wrong -> the fixed words
    assert audio.answers == [prompt.QUESTION["category"]["en"]]


def test_unclear_words_get_a_normal_clarifying_question(call):
    audio, _, _ = call([Speech("the the uh")],
                       [{"action": "ask", "say": "Sorry, what do you need help with?", "ask_box": ""}])
    assert audio.answers == ["Sorry, what do you need help with?"]


def test_side_talk_says_nothing_and_keeps_listening(call):
    audio, client, rows = call(
        [Speech("no not from there"), Speech("what is PM Kisan")],
        [{"action": "not_for_me", "say": ""}, _say("It is a scheme for farmer families.")],
    )
    assert audio.answers == ["It is a scheme for farmer families."]
    assert "sorry" not in " ".join(audio.played).lower()
    assert "AGENT said nothing (the words were not for the agent)" in client.calls[1]


def test_blocked_answer_is_logged_and_tried_once_more(call):
    bad = _say("It gives 98765 rupees.")
    audio, client, rows = call([Speech("how much is it")], [bad, _say("It gives money to farmers.")])
    assert audio.answers == ["It gives money to farmers."]
    assert [(r["rule"], r["text"]) for r in rows if r.get("ev") == "blocked"] == [("number", bad["say"])]
    assert 'refused by the "number" check' in client.calls[1]

    audio, _, rows = call([Speech("how much is it")], [bad, bad])       # twice blocked -> the safe line
    assert audio.answers == [s for s in re.split(r"(?<=\.)\s+", prompt.NOT_SURE["en"])]
    assert len([r for r in rows if r.get("ev") == "blocked"]) == 2


def test_verdict_is_blocked(call):
    audio, _, rows = call([Speech("will I get it")], [_say("You are eligible for this scheme."), _say("It is for farmers.")])
    assert audio.answers == ["It is for farmers."]
    assert [r["rule"] for r in rows if r.get("ev") == "blocked"][0] in ("verdict", "forbidden")


def test_reply_length_has_a_limit(call):
    four = "Take your Aadhaar card. Take your bank passbook. Go to the village office. Fill in the form."
    audio, _, _ = call([Speech("what papers and steps")], [_say(four)])
    assert len(audio.answers) == 4 and " ".join(audio.answers) == four
    audio, _, rows = call([Speech("what papers and steps")], [_say(four + " Then wait." * 4), _say("Take your Aadhaar card.")])
    assert [r["rule"] for r in rows if r.get("ev") == "blocked"] == ["too_long"]


def test_repeat_says_the_last_reply_again_with_no_new_text(call):
    audio, client, rows = call(
        [Speech("what is PM Kisan"), Speech("say that again")],
        [_say("It is a scheme for farmer families."), {"action": "repeat", "say": "something new"}],
    )
    assert audio.answers == ["It is a scheme for farmer families."] * 2


def test_quiet_reminder_then_goodbye(call):
    audio, client, rows = call([Silence(1), Silence(2)], [])
    assert audio.played[1:] == ["HELLO", "HELLO", "waiting_for_reply", "HELLO", "HELLO", "closing_farewell"]
    assert audio.hung_up and not client.calls


def test_goodbye_ends_the_call(call):
    audio, _, rows = call([Speech("thank you, bye"), Speech("never heard")],
                          [{"action": "goodbye", "say": "Take care."}])
    assert audio.answers == []                 # the farewell clip is the goodbye
    assert audio.played[-1] == "closing_farewell" and audio.hung_up
    assert len([r for r in rows if r.get("ev") == "heard"]) == 1


def test_one_moment_when_the_model_is_slow(call, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONE_MOMENT_S", 0.01)
    audio, _, _ = call([Speech("what is PM Kisan")], [_say("It is for farmers.")], delay=0.15)
    assert "one_moment" in audio.played
    monkeypatch.setattr(tunables, "TALK_ONE_MOMENT_S", 5.0)
    audio, _, _ = call([Speech("what is PM Kisan")], [_say("It is for farmers.")])
    assert "one_moment" not in audio.played


def test_a_failed_model_call_gives_the_not_sure_line_and_keys_are_ignored(call):
    audio, client, rows = call([Digit("5"), Speech("what is PM Kisan")], [None])
    assert " ".join(audio.answers) == prompt.NOT_SURE["en"]
    assert [r["means"] for r in rows if r.get("ev") == "key" and r["key"] == "5"] == ["keys are off"]


def test_keys_path_is_untouched_when_the_flag_is_off(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", False)
    audio = Audio([])
    log = Log.open("keys_test", corpus.snapshot_id, logs_dir=str(tmp_path))
    Engine.run_call(audio, None, corpus, log)
    assert not [r for r in log_text.read_rows(log.path) if r.get("ev") in ("heard", "act")]


def test_rate_limited_model_hands_over_to_the_next_one(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "TALK_MODELS", "big,small")
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())
    audio, client = Audio([Speech("what is PM Kisan")]), Client([_say("It is for farmers.")])
    client.busy = {"big"}
    Engine.run_call(audio, SimpleNamespace(client=client), corpus, Log.open("rl", corpus.snapshot_id, logs_dir=str(tmp_path)))
    assert client.models == ["big", "small"] and audio.answers == ["It is for farmers."]


def test_only_two_schemes_are_sent_in_full(call):
    _, client, _ = call([Speech("I need some scheme")], [{"action": "not_for_me"}])
    assert client.calls[0].count("how_to_apply:") == 2 and client.calls[0].count("mark: ") == 4


def test_clear_words_fill_the_box_by_fixed_code_not_by_the_model(call):
    """The real call of 5 Oct: "farmer schemes" said twice, the model asked "farming or business?" twice."""
    ask = {"action": "ask", "say": "Farming or business?", "ask_box": "category", "facts": {}}
    show = {"action": "show_scheme", "say": "Kisan Credit Card gives a loan for farming.", "scheme": "kcc"}
    audio, client, rows = call([Speech("मेरे को फार्मर स्कीम्स के बारे में जानना है।")], [ask, show])
    assert "category = farming" in client.calls[0] and "occupation = farmer" in client.calls[0]
    assert "NEXT QUESTION: category" not in client.calls[0]
    assert audio.answers == [show["say"]]            # the category question was refused, then the schemes
    assert client.calls[0].count("mark: ") == 4 and "[kcc]" in client.calls[0]


def test_a_box_asked_twice_with_no_answer_is_not_asked_again(call):
    # 1.3a: "I do not know" sets UNKNOWN at once (see test_talk_phrases); the
    # twice-asked path is for vague turns that answer nothing.
    ask = {"action": "ask", "say": "What kind of help do you need?", "ask_box": "category", "facts": {}}
    again = {"action": "ask", "say": "Which kind of help is it?", "ask_box": "category", "facts": {}}
    _, client, _ = call([Speech("hmm something"), Speech("err, something"), Speech("whatever is there"),
                         Speech("ok")], [ask, again, {"action": "not_for_me"}, {"action": "not_for_me"}])
    assert "NEXT QUESTION: category" in client.calls[1]
    assert "category = UNKNOWN" in client.calls[3] and "NEXT QUESTION: category" not in client.calls[3]


def test_a_code_name_is_never_said(call):
    audio, _, rows = call([Speech("hmm something")],
                          [_say("Options: farming, business_loans, jobs_skills."), _say("Tell me what you need.")])
    assert audio.answers == ["Tell me what you need."]
    assert [r["rule"] for r in rows if r.get("ev") == "blocked"] == ["code_name"]


def test_the_scheme_in_focus_is_sent_in_full_even_when_search_ranks_it_low(call):
    """Probe call of 5 Oct: PM Kisan was 4th in the list, so its papers were cut from the prompt."""
    _, client, _ = call(
        [Speech("how much does PM Kisan give"), Speech("which papers are needed")],
        [_say("It gives money to farmer families.", scheme="smam"), {"action": "not_for_me"}],
    )
    assert client.calls[1].index("[smam]") < client.calls[1].index("[pm-kisan]")
    first = client.calls[1].split("[smam]")[1].split("mark:")[0]
    assert "documents:" in first


def test_value_codes_and_other_scripts_are_not_said_in_hindi(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())
    for n, (bad, rule) in enumerate([("आपका लिंग क्या है? (male, female, other)", "code_name"),
                                     ("यह योजना पैसा देती है씩।", "script")]):
        audio = QAAudio([Digit("1"), Speech("कुछ"), Hangup()], "hi")
        client = Client([_say(bad), _say("यह योजना किसानों के लिए है।")])
        log = Log.open(f"hi_{n}", corpus.snapshot_id, logs_dir=str(tmp_path))
        Engine.run_call(audio, SimpleNamespace(client=client), corpus, log)
        assert audio.answers[-1] == "यह योजना किसानों के लिए है।"
        assert [r["rule"] for r in log_text.read_rows(log.path) if r.get("ev") == "blocked"] == [rule]


def test_a_very_long_sentence_is_refused(call):
    long = "To apply " + "go to the office and fill the form and " * 4 + "then wait."
    audio, _, rows = call([Speech("how do I apply")], [_say(long), _say("To apply, go to the village office.")])
    assert audio.answers == ["To apply, go to the village office."]
    assert [r["rule"] for r in rows if r.get("ev") == "blocked"] == ["too_long"]


def test_lakh_is_read_as_the_full_number_by_the_number_check(call, corpus):
    from haqdaar.engine import talk
    assert talk._plain_numbers("1.2 लाख रुपये") == "120000 रुपये"
    card = SchemeText.load(corpus.snapshot_id).card("pmay-g", "en")
    assert "1,20,000" in card
    audio, _, rows = call([Speech("money for a house")], [_say("It gives 1.2 lakh rupees.", scheme="pmay-g")])
    assert audio.answers == ["It gives 1.2 lakh rupees."] and not [r for r in rows if r.get("ev") == "blocked"]
    audio, _, rows = call([Speech("money for a house")], [_say("It gives 7.7 lakh rupees."), _say("It helps build a house.")])
    assert [r["rule"] for r in rows if r.get("ev") == "blocked"] == ["number"]


def test_other_topic_gets_the_fixed_line(call):
    audio, _, _ = call([Speech("what is the weather today")], [{"action": "other_topic", "say": "It is sunny."}])
    assert " ".join(audio.answers) == prompt.OTHER_TOPIC["en"]


def test_the_same_reply_is_not_said_twice_in_a_row(call):
    one = _say("There are schemes for farmers.")
    audio, client, rows = call([Speech("farming schemes"), Speech("farming schemes please")],
                               [one, one, _say("Kisan Credit Card is one more.")])
    assert audio.answers == ["There are schemes for farmers.", "Kisan Credit Card is one more."]
    assert [r["rule"] for r in rows if r.get("ev") == "blocked"] == ["same_again"]


def test_a_two_scheme_list_is_shown_with_no_man_or_woman_question(corpus):
    # 1.3a: talk stops asking at 2 or fewer left (was 4 or fewer). A short
    # list is shown with marks, not even man / woman.
    from haqdaar.contracts.types import SEVEN_BOXES, UNASKED
    from haqdaar.engine import talk_pick
    bv = {**{b: UNASKED for b in SEVEN_BOXES}, "category": "pension"}
    got = talk_pick.narrow(["apy", "ignwps"], bv, corpus)
    assert got.ask is None and "ignwps" in got.left


def test_one_moment_is_said_again_while_the_line_still_checks(call, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONE_MOMENT_S", 0.01)
    monkeypatch.setattr(tunables, "TALK_ONE_MOMENT_AGAIN_S", 0.05)
    audio, _, _ = call([Speech("what is PM Kisan")], [_say("It is for farmers.")], delay=0.2)
    assert audio.played.count("one_moment") >= 2
    assert audio.answers == ["It is for farmers."]


def test_stage_times_are_on_the_act_row_and_only_in_the_text_when_asked(call, corpus):
    say = f"PM Kisan gives {_number(corpus, 'pm-kisan')} rupees to farmer families."
    _audio, client, rows = call([Speech("what is PM Kisan", end_ms=600, stt_ms=500),
                                 Speech("tell me again")],
                                [_say(say, scheme="pm-kisan"), _say("", action="repeat")], delay=0.05)
    acts = [r for r in rows if r.get("ev") == "act"]
    assert [r["action"] for r in acts] == ["answer", "repeat"]
    first = acts[0]
    assert first["end_ms"] == 600 and first["stt_ms"] == 500
    assert first["model_ms"] >= 50 and first["search_ms"] >= 0 and first["voice_ms"] >= 0
    assert first["wait_ms"] >= 1100 + first["model_ms"] and first["ms"] >= first["model_ms"]
    assert "end_ms" not in acts[1] and "stt_ms" not in acts[1]      # no ear time known: left out
    assert rows.index(first) < max(i for i, r in enumerate(rows) if r.get("ev") == "said")
    assert "TIMES" not in log_text.log_text(rows)                   # the model's copy has no times
    assert "TIMES" not in client.calls[1]
    text = log_text.log_text(rows, times=True)
    assert "TIMES (ms): end wait 600, speech-to-text 500, search " in text
    assert text.count("TIMES (ms)") == 2 and "AGENT said its last reply again\n  TIMES" in text
    old = [{k: v for k, v in r.items() if not k.endswith("_ms")} for r in rows]
    assert "TIMES" not in log_text.log_text(old, times=True)        # an old log: no line, no error


class CutAudio(Audio):
    def __init__(self, inputs):
        super().__init__(inputs)
        self.again = 0

    def say_cut_again(self):
        self.again += 1
        return True


def test_words_that_cut_the_agent_but_were_not_for_it_make_it_go_on_from_the_cut_sentence(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())
    audio = CutAudio([Speech("what is PM Kisan"),
                      Speech("yes yes ok fine", cut_clip="answer", heard_ms=900),
                      Speech("wait, how do I apply", cut_clip="answer", heard_ms=400)])
    client = Client([_say("It is a scheme for farmer families."), {"action": "not_for_me", "say": ""},
                     _say("To apply, go to the CSC centre.")], 0.0)
    log = Log.open("talk_cut", corpus.snapshot_id, logs_dir=str(tmp_path))
    Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
    rows = log_text.read_rows(log.path)
    assert not [r for r in rows if r.get("invalid")]
    assert audio.again == 1                                     # only for the not_for_me cut
    assert audio.answers == ["It is a scheme for farmer families.", "To apply, go to the CSC centre."]
    assert "WHILE you were still talking" not in client.calls[0]
    assert "WHILE you were still talking" in client.calls[1] and "WHILE you were still talking" in client.calls[2]
    acts = [r for r in rows if r.get("ev") == "act"]
    assert [bool(r.get("again")) for r in acts] == [False, True, False]
    assert "went on from the sentence that was cut" in log_text.log_text(rows)


def test_the_prompt_names_the_scheme_in_talk_and_the_parts_already_told(call, corpus):
    first = f"PM Kisan gives {_number(corpus, 'pm-kisan')} rupees a year."
    _, client, _ = call(
        [Speech("what is PM Kisan"), Speech("tell me more"), Speech("ok")],
        [_say(first, scheme="pm-kisan", parts=["gives", "made_up"]),
         _say("You need an Aadhaar card.", scheme="pm-kisan", parts=["papers"]),
         _say("Anything else?")])
    assert "SCHEME IN TALK: none yet" in client.calls[0]     # the test's search finds no scheme by name
    assert "TOLD: gives. NOT TOLD YET: who, papers, apply." in client.calls[1]
    assert "TOLD: gives, papers. NOT TOLD YET: who, apply." in client.calls[2]


def test_an_answer_about_another_scheme_than_the_one_in_talk_is_sent_back_once(call, corpus):
    n = _number(corpus, "pm-kisan")
    audio, client, rows = call(
        [Speech("the first one"), Speech("how much money")],
        [_say("It is for farmer families.", scheme="pm-kisan"),
         _say("That one is a house scheme.", scheme="pmay-g"),
         _say(f"It gives {n} rupees a year.", scheme="pm-kisan")])
    assert [r["rule"] for r in rows if r.get("ev") == "blocked"] == ["other_scheme"]
    assert "Answer about [pm-kisan]" in client.calls[2]
    assert audio.answers[-1] == f"It gives {n} rupees a year."


def test_needed_papers_is_not_taken_for_a_promise_but_a_promise_still_is(corpus, tmp_path, monkeypatch):
    from tools import talk_questions

    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())
    ok = "क्या मैं आपको ज़रूरी कागज़ों के बारे में बताऊं?"
    client = Client([_say(ok), _say("यह पैसा आपको ज़रूर मिलेगा।"), _say("यह पैसा आपको ज़रूर मिलेगा, ज़रूरी कागज़ लाइए।")])
    t, audio, log = talk_questions._talk(corpus, client, "hi", str(tmp_path), "forbidden_test")
    t._turn("पीएम किसान")
    assert audio.answers == [ok]
    t._turn("पैसा मिलेगा क्या")
    assert " ".join(audio.answers[1:]) == prompt.NOT_SURE["hi"]      # said sentence by sentence
    assert [r["rule"] for r in log_text.read_rows(log.path) if r.get("ev") == "blocked"] == ["forbidden", "forbidden"]
