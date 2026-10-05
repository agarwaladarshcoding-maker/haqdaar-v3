"""haqdaar/engine/talk.py

The talk-only loop (step 7.13, B3). Picked by TALK_ONLY=true right after the language pick; the
keys path in call.py is left as it is. STRICT TURNS: the agent speaks, then listens (run it with
SPEECH_CUT_IN off). One turn:
  caller's words -> search over all schemes -> fixed filter + question picker -> ONE model call
  ({action, say, facts, scheme, ask_box}) -> facts checked -> truth checks -> live voice -> log.
Which profile question to ask is the picker's choice, not the model's (owner's change C1).
One caller at a time. No "model is down" handling: a failed call says the "not sure" line.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Optional

from haqdaar.contracts import tunables, vocab
from haqdaar.contracts.log_schema import (
    STOP_LE_4_SURVIVORS,
    STOP_NO_SPLIT,
    STOP_ZERO_SURVIVORS,
    TurnLogRecord,
)
from haqdaar.contracts.types import SEVEN_BOXES, UNASKED, UNKNOWN, Digit, Hangup, Silence, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.scheme_text import SchemeText
from haqdaar.engine import talk_pick, talk_words
from haqdaar.engine.filter import Filter
from haqdaar.model.answer import check_answer, mask_digits
from haqdaar.prompts import talk as prompt

SEARCH_K = 10            # C1: the picker works on the search's top 10
SHOW_K = 4               # schemes the model is shown
FULL_K = 2               # of those, how many with the full text (the rest: name + summary). Groq
                         # allows 8000 tokens a minute per model; a turn must stay small.
ASK_TRIES = 2            # a box asked this often with no answer is left as not known; the picker moves on
_CODE_NAME = re.compile(r"[A-Za-z]+_[A-Za-z]+")   # "business_loans" must never be said aloud
# Letters the voice can say: Latin, Devanagari, usual marks, the rupee sign. (A model once wrote a Korean letter.)
_OTHER_SCRIPT = re.compile(r"[^\u0000-\u024F\u0900-\u097F\u2000-\u206F\u20B9]")
SILENCE_HANGUP_RUNG = 2  # T1: no reply twice in a row -> goodbye
_SENTENCE_GAP = re.compile(r"(?<=[.!?।])\s+")
_SHORT_PIECE = 12        # "Rs." and such are not a sentence of their own


_BIG = {"हज़ार": 1_000, "हजार": 1_000, "thousand": 1_000, "लाख": 100_000, "lakh": 100_000, "lakhs": 100_000,
        "करोड़": 10_000_000, "crore": 10_000_000}
_BIG_NUMBER = re.compile(r"(\d+(?:\.\d+)?)\s*(" + "|".join(_BIG) + r")", re.I)


def _plain_numbers(text: str) -> str:
    """ "1.2 लाख" -> "120000", so the number check can find it in the scheme text (1,20,000)."""
    return _BIG_NUMBER.sub(lambda m: str(int(round(float(m.group(1)) * _BIG[m.group(2).lower()]))), text)


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    for piece in _SENTENCE_GAP.split(text.strip()):
        if out and len(out[-1]) < _SHORT_PIECE:
            out[-1] += " " + piece
        elif piece:
            out.append(piece)
    return out


def _age_band(value: str, corpus: Any) -> Optional[str]:
    """Age in years -> the snapshot's band code ("18-35", "80+")."""
    try:
        years = int(float(value))
    except ValueError:
        return None
    for code in corpus.values("age"):
        lo, _, hi = str(code).rstrip("+").partition("-")
        try:
            if int(lo) <= years <= (int(hi) if hi else 200):
                return str(code)
        except ValueError:
            continue
    return None


def _take_facts(facts: Any, bv: dict[str, Any], corpus: Any, log: Any, turn_n: int) -> bool:
    """C2: a fact counts only when it is an allowed value of its box. Others are dropped and logged."""
    changed = False
    if not isinstance(facts, dict):
        return False
    for box, value in facts.items():
        if value is None or str(value).strip() == "":
            continue
        said = str(value).strip()
        allowed = corpus.values(box) if box in SEVEN_BOXES else ()
        match = next((a for a in allowed if str(a).lower() == said.lower()), None)
        if match is None and box == "age":
            match = _age_band(said, corpus)
        if match is None:
            log.write({"ev": "blocked", "rule": "fact", "question": "", "text": f"{box} = {said}"})
            continue
        if bv.get(box) != match:
            bv[box] = match
            log.write(TurnLogRecord(turn_n=turn_n, turn_class="ANSWER", box=box, value=match))
            changed = True
    return changed


def _call(model: Any, messages: list[dict[str, str]]) -> Optional[dict]:
    client = getattr(model, "client", None)
    if client is None:
        return None
    resp = None
    try:
        # Each Groq model has its own tokens-a-minute limit: on "too many requests" try the next one.
        for name in [m.strip() for m in tunables.TALK_MODELS.split(",") if m.strip()] or [""]:
            try:
                resp = client.call(messages, task="talk", timeout=tunables.TALK_TIMEOUT_S, model=name or None)
            except TypeError:       # the sim's client takes no timeout / model
                resp = client.call(messages, "talk")
            if not getattr(resp, "is_429", False):
                break
    except Exception:
        return None
    data = getattr(resp, "data", None) if getattr(resp, "success", False) else None
    return data if isinstance(data, dict) else None


def _rows(log: Any) -> list[dict[str, Any]]:
    try:
        return log_text.read_rows(log.path)
    except Exception:
        return []


class _Talk:
    def __init__(self, audio: Any, model: Any, corpus: Any, log: Any, lang: str, index: Any) -> None:
        self.audio, self.model, self.corpus, self.log, self.lang = audio, model, corpus, log, lang
        self.index = index if index is not None else scheme_index.get(corpus.snapshot_id)
        self.texts = SchemeText.load(corpus.snapshot_id)
        self.bv: dict[str, Any] = {b: UNASKED for b in SEVEN_BOXES}
        self.heard: list[str] = []      # the caller's turns, oldest first
        self.last_say = ""
        self.focus = ""                 # the scheme the talk is about now
        self.told: dict[str, set[str]] = {}  # scheme -> the parts of it already said (prompt.PARTS)
        self.left: tuple[str, ...] = ()
        self.asked: dict[str, int] = {}  # box -> how often we asked it
        self.turn_n = 0

    # --- the fixed part: search -> filter -> picker ---
    def _state(self, ids: list[str]) -> tuple[talk_pick.Narrow, list[tuple[str, str, str]]]:
        nar = talk_pick.narrow(ids, self.bv, self.corpus)
        show = list(nar.left[:SHOW_K]) or ids[:SHOW_K]
        if self.focus:                       # the scheme the talk is about goes first, in full
            show = ([self.focus] + [s for s in show if s != self.focus])[:SHOW_K]
        cards = []
        for n, sid in enumerate(show):
            text = self.texts.card(sid, "en")
            if n >= FULL_K:
                text = "\n".join(text.split("\n")[:3])      # [id], name, summary
            cards.append((sid, talk_pick.mark(sid, self.bv, self.corpus), text))
        return nar, cards

    def _found(self) -> list[str]:
        """Search's top 10 on the last three caller turns, plus every scheme of the kind of help
        the caller named (search is weak on English words written in Hindi letters)."""
        named = self.index.search(self.heard[-1], 1) if self.heard else []
        if named and named[0].by == "name":  # the caller said a scheme's name: the talk is about it now
            self.focus = named[0].scheme_id
        ranked = [h.scheme_id for h in self.index.search(" ".join(self.heard[-3:]), len(self.index.ids) or SEARCH_K)]
        ids = ranked[:SEARCH_K]
        category = self.bv.get("category")
        if category in self.corpus.values("category"):
            kind = {self.corpus.scheme_id(ix) for ix in Filter.survivors({"category": category}, self.corpus)}
            ids += [sid for sid in ranked[SEARCH_K:] if sid in kind]
        return ids

    def _timed(self, stage: str, fn: Any, *args: Any) -> Any:
        """Run one stage of the turn and add its time to the turn's stage times."""
        t0 = time.monotonic()
        try:
            return fn(*args)
        finally:
            self.stage[stage] = self.stage.get(stage, 0.0) + time.monotonic() - t0

    def _decide(self, words: str, cut: bool = False) -> tuple[str, str]:
        """(action, say). At most two model calls: the second only after a refused first reply."""
        # The clear words first, by fixed code (a real call showed the model can miss "farmer schemes").
        _take_facts(talk_words.spot(words, self.corpus), self.bv, self.corpus, self.log, self.turn_n)
        ids = self._timed("search", self._found)
        boxes = {b: self.corpus.values(b) for b in SEVEN_BOXES}
        text = log_text.log_text(_rows(self.log), tunables.TALK_LOG_CHARS)
        note = prompt.CUT_NOTE if cut else ""
        wrong_ask = False                           # the last try asked a box the picker did not name
        nar, cards = self._state(ids)
        for _try in (0, 1):
            known = {b: v for b, v in self.bv.items() if v != UNASKED}
            data = self._timed("model", _call, self.model, prompt.build(
                self.lang, text, known, boxes, nar.ask, nar.order, cards, words, note,
                self.focus, sorted(self.told.get(self.focus, ()))))
            wrong_ask = False
            if data is None:
                break
            action = str(data.get("action") or "").strip().lower()
            say = str(data.get("say") or "").strip()
            if action not in prompt.ACTIONS:
                note = "action must be one of: " + ", ".join(prompt.ACTIONS)
                continue
            _take_facts(data.get("facts"), self.bv, self.corpus, self.log, self.turn_n)
            for box, n in self.asked.items():      # asked twice, still no answer: stop asking it
                if n >= ASK_TRIES and self.bv.get(box) == UNASKED:
                    self.bv[box] = UNKNOWN
            ids = self._timed("search", self._found)
            nar, cards = self._state(ids)          # the facts may have changed the picker's answer
            self.left = nar.left
            if action in ("not_for_me", "repeat", "goodbye"):
                return action, ""               # goodbye: the farewell clip is the only thing said
            if action == "other_topic":         # fixed words; the model does not write this one
                return action, prompt.OTHER_TOPIC.get(self.lang, prompt.OTHER_TOPIC["en"])
            ask_box = str(data.get("ask_box") or "").strip()
            if action == "ask" and ask_box and ask_box != nar.ask:
                wrong_ask = True
                note = (f'Ask about "{nar.ask}", not "{ask_box}".' if nar.ask else
                        "No question about the caller is left. Do not ask one: show the schemes or answer.")
                continue
            proof = "\n\n".join(c for _s, _m, c in cards) + "\n" + " ".join(
                str(v) for vals in boxes.values() for v in vals)
            rule = check_answer(_plain_numbers(say), self.lang, _plain_numbers(proof),
                                tunables.TALK_MAX_SENTENCES, tunables.TALK_MAX_WORDS) if say else "empty"
            # A long sentence is sent back once to be cut. The second time it is said as it is:
            # a long true reply is better on the phone than "I am not sure".
            if not rule and _try == 0 and any(
                    len(s.split()) > tunables.TALK_SENTENCE_WORDS for s in _sentences(say)):
                rule = "too_long"
            if not rule and _try == 0 and say == self.last_say:
                rule = "same_again"
            if not rule and _OTHER_SCRIPT.search(say):
                rule = "script"
            codes = {str(v).lower() for vals in boxes.values() for v in vals if str(v).isalpha()}
            if not rule and (_CODE_NAME.search(say) or (
                    self.lang != "en" and codes & set(re.findall(r"[a-z]+", say.lower())))):
                rule = "code_name"
            if rule:
                self.log.write({"ev": "blocked", "rule": rule, "question": mask_digits(words), "text": say})
                note = (f'Your reply "{say}" was refused by the "{rule}" check. Say it another way, '
                        "shorter and only with what is written in SCHEMES.")
                if rule == "forbidden":             # name the words, or the second try uses them again
                    note += f' Do not use the words "{vocab.find_forbidden(say, self.lang)}" or words that start with them.'
                continue
            scheme = str(data.get("scheme") or "").strip()
            if scheme in ids:
                self.focus = scheme
            parts = data.get("parts")
            if self.focus and action in ("answer", "show_scheme") and isinstance(parts, list):
                self.told.setdefault(self.focus, set()).update(p for p in parts if p in prompt.PARTS)
            if action == "ask" and ask_box:
                self.asked[ask_box] = self.asked.get(ask_box, 0) + 1
            return action, say
        if wrong_ask and nar.ask:                   # C1: the picker's question, in fixed words
            self.asked[nar.ask] = self.asked.get(nar.ask, 0) + 1
            return "ask", prompt.QUESTION.get(nar.ask, {}).get(self.lang) or prompt.NOT_SURE[self.lang]
        return "answer", prompt.NOT_SURE.get(self.lang, prompt.NOT_SURE["en"])

    # --- the mouth ---
    def _speak(self, say: str, before_first: Any = None) -> None:
        """`before_first` is called when the first sentence's sound is ready, just before it is said."""
        if not hasattr(self.audio, "say_text"):
            return
        parts = _sentences(say)
        warm = getattr(self.audio, "warm_text", None)
        stream = bool(warm) and tunables.LIVE_TTS_STREAM    # the first sentence plays as its sound arrives
        ahead = []                              # the later sentences are made while the first is said
        for sentence in parts[1:] if warm else []:
            ahead.append(threading.Thread(target=warm, args=(sentence,), daemon=True))
            ahead[-1].start()
        if warm and parts and not stream:
            warm(parts[0])
        if before_first and not stream:
            before_first()
        for n, sentence in enumerate(parts):
            if n and ahead:
                ahead[n - 1].join(timeout=tunables.QA_TTS_TIMEOUT_S)
            if stream and n == 0:
                self.audio.say_text(sentence, on_first=before_first)
            else:
                self.audio.say_text(sentence)

    def _turn(self, words: str, end_ms: int = -1, stt_ms: int = -1, cut: bool = False) -> str:
        """`cut`: the caller said these words while the agent was talking, and it stopped (B5)."""
        self.turn_n += 1
        self.stage = {}
        self.heard.append(words)
        self.log.write({"ev": "heard", "text": mask_digits(words)})
        t0 = time.monotonic()
        lock = threading.Lock()
        done = threading.Event()                # the reply has started to sound, or there is none
        back = [0.0]                            # when the model came back

        def stop_filler() -> None:
            with lock:
                done.set()

        def filler() -> None:
            """Never dead air while the line is checking: "one moment" after TALK_ONE_MOMENT_S with
            nothing said, and again every TALK_ONE_MOMENT_AGAIN_S while it is still checking."""
            wait = tunables.TALK_ONE_MOMENT_S
            for _ in range(4):
                if done.wait(wait):
                    return
                if back[0] and time.monotonic() - back[0] < 1.5:
                    wait = 1.5                  # the reply is being voiced; it sounds in a moment
                    continue
                with lock:
                    if done.is_set():
                        return
                    self.audio.say(("one_moment",))
                wait = tunables.TALK_ONE_MOMENT_AGAIN_S

        threading.Thread(target=filler, daemon=True).start()
        try:
            action, say = self._decide(words, cut)
            back[0] = time.monotonic()
            row: dict[str, Any] = {
                "ev": "act", "action": action, "scheme": self.focus, "ms": int((back[0] - t0) * 1000),
                "end_ms": end_ms if end_ms >= 0 else None, "stt_ms": stt_ms if stt_ms >= 0 else None,
                "search_ms": int(self.stage.get("search", 0.0) * 1000),
                "model_ms": int(self.stage.get("model", 0.0) * 1000)}

            def first_voice() -> None:
                """The first sentence's sound is ready: the stage times are whole, the row is written."""
                stop_filler()
                if "ev" not in row:
                    return
                now = time.monotonic()
                row["voice_ms"] = int((now - back[0]) * 1000)
                row["wait_ms"] = max(end_ms, 0) + max(stt_ms, 0) + int((now - t0) * 1000)
                self.log.write(dict(row))
                row.clear()

            if cut and action == "not_for_me" and hasattr(self.audio, "say_cut_again"):
                stop_filler()                       # not for the agent: it goes on from the cut sentence
                row["again"] = bool(self.audio.say_cut_again()) or None
            if action == "repeat":
                say = self.last_say
            if say:
                self._speak(say, first_voice)
                self.last_say = say
            if "ev" in row:                         # nothing was said (or no voice on this audio)
                self.log.write(dict(row))
                row.clear()
        finally:
            stop_filler()
        return action

    def _end(self, farewell: bool, reason: str = "") -> None:
        if farewell:
            self.audio.say(("closing_farewell",))
            if hasattr(self.audio, "on_mark"):
                self.audio.on_mark("closing_farewell")
        self.audio.hangup()
        if not reason:
            reason = STOP_LE_4_SURVIVORS if 0 < len(self.left) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT
        self.log.close(reason=reason, ladder_rung=0, mode="voice")

    def run(self) -> None:
        self._speak(prompt.HELLO.get(self.lang, prompt.HELLO["en"]))
        while True:
            if self.turn_n >= tunables.TALK_MAX_TURNS:
                return self._end(farewell=True)
            inp = self.audio.next_input(profile="spoken")
            if isinstance(inp, Hangup):
                return self._end(farewell=False, reason=STOP_ZERO_SURVIVORS)
            if isinstance(inp, Silence):
                self.log.write(TurnLogRecord(turn_n=self.turn_n, turn_class="SILENCE", silence_n=inp.n))
                if inp.n >= SILENCE_HANGUP_RUNG:
                    return self._end(farewell=True, reason=STOP_ZERO_SURVIVORS)
                self.audio.say(("waiting_for_reply",))
                if not self.last_say:
                    self._speak(prompt.HELLO.get(self.lang, prompt.HELLO["en"]))
                continue
            if isinstance(inp, Digit):          # keys are off in talk mode
                self.log.write({"ev": "key", "key": inp.digit, "means": "keys are off"})
                continue
            if not isinstance(inp, Speech) or not inp.text.strip():
                continue                        # noise: say nothing, keep listening
            if self._turn(inp.text.strip(), inp.end_ms, inp.stt_ms, bool(inp.cut_clip)) == "goodbye":
                return self._end(farewell=True)


def run(audio: Any, model: Any, corpus: Any, log: Any, lang: str, index: Any = None) -> None:
    """The rest of the call after the language pick. Ends the call itself."""
    _Talk(audio, model, corpus, log, lang, index).run()
