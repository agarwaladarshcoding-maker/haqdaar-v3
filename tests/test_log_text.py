"""tests/test_log_text.py

T2: the call log reads as text. Unit tests on fixed rows, and engine tests that a call writes
`said`, `key`, `cut` and `blocked` rows in call order without any row being stamped invalid.
Fakes only: no model, no Sarvam.
"""
from __future__ import annotations

import json

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Speech
from haqdaar.data.log import Log
from haqdaar.data.log_text import log_text, said_words
from haqdaar.engine.call import Engine, _LoggedAudio

from tests.test_call import MockAudio, corpus  # noqa: F401  (corpus is a fixture)
from tests.test_qa_engine import ANSWER_TEXT, QUESTION, QAAudio, QAModel, _question_inputs, _run

OLD_READER_KEYS = ("class", "turn_n", "stop", "mode", "lang")

ROWS = [
    {"call_id": "c1", "snapshot_id": "s", "lang": "hi", "lang_source": "default"},
    {"ev": "said", "tokens": ["greeting_trilingual"], "text": "namaste", "en": "Hello, press 1 for Hindi."},
    {"ev": "key", "key": "3", "means": "language = English"},
    {"lang": "en", "lang_source": "keypad", "turn_n": 0},
    {"turn_n": 0, "class": "ANSWER", "transcript": "en"},
    {"ev": "cut", "by": "speech", "clip": "q_age", "heard_ms": 900, "en": "How old are you?"},
    {"turn_n": 1, "class": "UNCLEAR", "discarded_transcript": "mumble"},
    {"ev": "blocked", "rule": "number", "question": "how much", "text": "It gives 99 rupees."},
    {"turn_n": 1, "class": "QUESTION", "transcript": "how much", "answer": "Fifty percent."},
    {"turn_n": 1, "class": "SILENCE", "silence_n": 1},
    {"slug": "pm-kisan", "ending": "direct_match", "sections": ["summary"], "lang": "en"},
    {"stop": "no_split", "mode": "voice", "ladder_rung": 0},
]


def test_log_text_has_a_line_for_every_kind_of_row_oldest_first():
    text = log_text(ROWS)
    lines = text.splitlines()
    assert lines[0].startswith("CALL STARTED")
    assert 'AGENT: "Hello, press 1 for Hindi."' in lines[1]
    assert lines[2] == "CALLER pressed 3 (language = English)"
    assert any(l.startswith("LANGUAGE: en") for l in lines)
    assert any("cut in by speech" in l and "How old are you?" in l and "900 ms" in l for l in lines)
    assert any(l.startswith("TURN 1: not understood") and "mumble" in l for l in lines)
    assert any(l.startswith("ANSWER REFUSED (number)") and "99 rupees" in l for l in lines)
    assert any(l.startswith('CALLER asked: "how much"') for l in lines)
    assert any("Fifty percent." in l for l in lines)  # no said row for the answer: the QUESTION row carries it
    assert any(l.startswith("CALLER silent") for l in lines)
    assert any(l.startswith("READ OUT: pm-kisan") for l in lines)
    assert lines[-1].startswith("CALL ENDED: no_split")


def test_log_text_does_not_say_the_live_answer_twice():
    rows = ROWS + [{"ev": "said", "tokens": ["answer"], "text": "Fifty percent.", "en": ""}]
    assert log_text(rows).count("Fifty percent.") == 1  # the said row has it; the QUESTION row does not repeat it
    assert "AGENT answered" not in log_text(rows)


def test_log_text_cap_keeps_the_newest_lines():
    full = log_text(ROWS).splitlines()
    cap = len("\n".join(full[-3:]))
    short = log_text(ROWS, max_chars=cap).splitlines()
    assert short == full[-3:]
    assert log_text(ROWS, max_chars=5) == full[-1][-5:]  # even one line is cut, from the old end


def test_log_text_cuts_long_scheme_text_and_ignores_bad_rows():
    rows = [{"ev": "said", "tokens": ["scheme:a:benefit_text"], "text": "x" * 5000, "en": "y " * 3000}, "junk", None]
    (line,) = log_text(rows).splitlines()
    assert len(line) < 300 and line.endswith('…"')


def test_said_words_with_unknown_tokens_is_empty_not_an_error():
    assert said_words(["no_such_token", "name:s1"], "en", lambda token, lang: "") == ""
    assert said_words(["x"], "en", lambda token, lang: 1 / 0) == ""


def test_said_words_adds_the_key_menu_to_a_menu_prompt():
    class C:
        def values(self, box):
            return ["male", "female"]

    table = {"keypad_gender": "Who is this for?", "chip_gender_male": "a man", "chip_gender_female": "a woman",
             "keypad_unknown_suffix": "Press 0 if you do not know."}
    text = said_words(["keypad_gender"], "en", lambda t, lang: table.get(t, ""), C())
    assert text == "Who is this for? press 1 for a man, press 2 for a woman. Press 0 if you do not know."


def _rows(tmp_path, name):
    return [json.loads(l) for l in open(tmp_path / f"{name}.jsonl")]


def test_keypad_call_writes_said_and_key_rows_in_call_order(corpus, tmp_path):  # noqa: F811
    audio = MockAudio(inputs=[Digit("3"), Digit("1"), Digit("2"), Digit("2"), Digit("2"), Digit("2"), Digit("2"),
                              Digit("2"), Digit("2"), Digit("2"), Digit("2")])
    log = Log.open("t2_keys", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)
    rows = _rows(tmp_path, "t2_keys")
    ev = [r for r in rows if "ev" in r]
    keys = [r for r in ev if r["ev"] == "key"]
    said = [r for r in ev if r["ev"] == "said"]

    assert keys[0] == {"ev": "key", "key": "3", "means": "language = English"}
    assert keys[1]["key"] == "1" and keys[1]["means"].startswith("category = ")
    assert said and all(r["tokens"] for r in said)
    # the prompt for the category was said before the key that answered it
    first_prompt = next(i for i, r in enumerate(rows) if r.get("ev") == "said" and "opener_prompt" in r["tokens"])
    assert first_prompt < rows.index(keys[1])
    # the row order is the call order: every said row sits where audio.say was called
    assert [t for r in said for t in r["tokens"]] == [t for t in audio.played if t not in ("greeting_trilingual",)
                                                      and not t.startswith(("name:", "end:")) and t != "REPEAT"]
    # no readable row can be mistaken for an old row, and nothing is invalid
    assert all(not any(k in r for k in OLD_READER_KEYS) for r in ev)
    assert not any(r.get("invalid") for r in rows)
    # and the call text reads
    assert log_text(rows).count("CALLER pressed") == len(keys)


def test_a_cut_speech_gives_a_cut_row_and_an_uncut_one_does_not(corpus, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tunables, "QA_ENABLED", True)
    inputs = _question_inputs()
    inputs[2] = Speech(QUESTION, cut_clip="q_gender", heard_ms=700)
    rows = _run(corpus, tmp_path, QAAudio(inputs), QAModel(), name="t2_cut")
    cuts = [r for r in rows if r.get("ev") == "cut"]
    assert len(cuts) == 1
    assert cuts[0]["by"] == "speech" and cuts[0]["clip"] == "q_gender" and cuts[0]["heard_ms"] == 700

    inputs[2] = Speech(QUESTION, cut_clip="q_gender", heard_ms=-1)
    rows = _run(corpus, tmp_path, QAAudio(inputs), QAModel(), name="t2_nocut")
    assert not [r for r in rows if r.get("ev") == "cut"]


def test_a_spoken_live_answer_is_a_said_row_and_a_refused_one_is_not(corpus, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tunables, "QA_ENABLED", True)
    rows = _run(corpus, tmp_path, QAAudio(_question_inputs()), QAModel(), name="t2_answer")
    live = [r for r in rows if r.get("ev") == "said" and r["tokens"] == ["answer"]]
    assert live == [{"ev": "said", "tokens": ["answer"], "text": ANSWER_TEXT, "en": ""}]
    assert not [r for r in rows if r.get("ev") == "blocked"]  # a model with no last_blocked writes none

    rows = _run(corpus, tmp_path, QAAudio(_question_inputs(), said=False), QAModel(), name="t2_unsaid")
    assert not [r for r in rows if r.get("ev") == "said" and r["tokens"] == ["answer"]]


def test_a_blocked_answer_gives_a_blocked_row_with_digits_masked(corpus, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tunables, "QA_ENABLED", True)

    class BlockedModel(QAModel):
        last_blocked = None

        def answer(self, question, lang, cards, profile=None, scheme_ids=None, english=False):
            self.last_blocked = {"rule": "number", "text": "It gives 123456789012 rupees."}
            return None

    inputs = _question_inputs()
    inputs[2] = Speech(QUESTION + " 987654321098")
    rows = _run(corpus, tmp_path, QAAudio(inputs), BlockedModel(), name="t2_blocked")
    blocked = [r for r in rows if r.get("ev") == "blocked"]
    assert len(blocked) == 2  # one per refused try
    assert blocked[0]["rule"] == "number"
    assert "123456789012" not in blocked[0]["text"] and "…" in blocked[0]["text"]
    assert "987654321098" not in blocked[0]["question"]
    assert all(not any(k in r for k in OLD_READER_KEYS) for r in blocked)
    assert not any(r.get("invalid") for r in rows)


def test_the_wrapper_passes_everything_through():
    class Plain:
        language = "hi"

        def say(self, sequence):
            return ("said", sequence)

    class Rich(Plain):
        def say_text(self, text):
            return False

        def select_language(self):
            return ("mr", "keypad")

    class Sink:
        snapshot_id = "x"

        def __init__(self):
            self.rows = []

        def write(self, row):
            self.rows.append(row)

    for real in (Plain(), Rich()):
        sink = Sink()
        wrapped = _LoggedAudio(real, sink, None)
        for name in ("say", "say_text", "select_language", "next_input", "language", "on_mark", "trace"):
            assert hasattr(wrapped, name) == hasattr(real, name), name
        assert wrapped.say(("a",)) == ("said", ("a",))
        wrapped.language = "en"
        wrapped.current_scheme = "s1"
        assert real.language == "en" and real.current_scheme == "s1" and wrapped.current_scheme == "s1"
    # say_text False: nothing was said, so no row; the value goes back untouched
    assert wrapped.say_text("hi") is False and sink.rows[-1]["ev"] == "said" and sink.rows[-1]["tokens"] == ["a"]
    assert wrapped.select_language() == ("mr", "keypad")
