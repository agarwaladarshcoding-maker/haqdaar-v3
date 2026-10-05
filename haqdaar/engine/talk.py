"""haqdaar/engine/talk.py

The talk-only loop (step 7.13, B3). Picked by TALK_ONLY=true right after the language pick; the
keys path in call.py is left as it is. STRICT TURNS: the agent speaks, then listens (run it with
SPEECH_CUT_IN off). One turn:
  caller's words -> search over all schemes -> fixed filter + question picker -> ONE model call
  ({action, say, facts, scheme, ask_box}) -> facts checked -> truth checks -> live voice -> log.
Which profile question to ask is the picker's choice, not the model's (owner's change C1).
One caller at a time. No "model is down" handling: a failed call says the "not sure" line.
Step 1.6: a model that fails hands over to the next one; a reply the voice could not say is tried
once more; the call says goodbye by itself before the server's cap closes the line.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Optional

from haqdaar.contracts import tunables, vocab
from haqdaar.contracts.log_schema import (
    STOP_LE_4_SURVIVORS,
    STOP_MAX_TURNS,
    STOP_NO_SPLIT,
    STOP_ZERO_SURVIVORS,
    TurnLogRecord,
)
from haqdaar.contracts.types import SEVEN_BOXES, UNASKED, UNKNOWN, Digit, Hangup, Silence, Speech
from haqdaar.data import chunk_index, log_text, scheme_index
from haqdaar.data.scheme_text import SchemeText
from haqdaar.engine import talk_follow, talk_kind, talk_pick, talk_words, words_no_answer, words_tell_me
from haqdaar.engine.filter import Filter
from haqdaar.model import middle
from haqdaar.model.answer import check_answer, mask_digits
from haqdaar.prompts import talk as prompt

SEARCH_K = 10            # C1: the picker works on the search's top 10
SHOW_K = 4               # schemes the model is shown
FULL_K = 2               # of those, how many with the full text (the rest: name + summary). Groq
                         # allows 8000 tokens a minute per model; a turn must stay small.
PIECES_K = 5             # 1.5: parts of schemes the model is shown (TALK_CHUNKS)
PIECES_POOL = 12         # parts asked of the search, so a scheme that does not fit can be dropped and 5 still remain
FOCUS_PIECES = 2         # 1.5: at most this many parts of the scheme in talk are put first
ASK_TRIES = 2            # a box asked this often with no answer is left as not known; the picker moves on
_CODE_NAME = re.compile(r"[A-Za-z]+_[A-Za-z]+")   # "business_loans" must never be said aloud
# Letters the voice can say: Latin, Devanagari, usual marks, the rupee sign. (A model once wrote a Korean letter.)
_OTHER_SCRIPT = re.compile(r"[^\u0000-\u024F\u0900-\u097F\u2000-\u206F\u20B9]")
_HINDI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
SILENCE_HANGUP_RUNG = 2  # T1: no reply twice in a row -> goodbye
_SENTENCE_GAP = re.compile(r"(?<=[.!?।])\s+")
_SHORT_PIECE = 12        # "Rs." and such are not a sentence of their own
CAP_MARGIN_S = 60        # 1.6: goodbye this long before CALL_CEILING_S (the server's clock starts at the greeting)
VOICE_FAILS_HANGUP = 2   # 1.6: this many replies in a row with no voice -> goodbye


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


def _free_ask(last_asked: str, changed: set[str]) -> bool:
    """1.3 (A): every question the line asks counts. One is given back: the caller answered
    another box than the one asked last (asked age, told the state: the age ask was free)."""
    return bool(last_asked) and bool(changed) and last_asked not in changed


def _take_facts(facts: Any, bv: dict[str, Any], corpus: Any, log: Any, turn_n: int) -> set[str]:
    """C2: a fact counts only when it is an allowed value of its box. Others are dropped and logged."""
    changed: set[str] = set()
    if not isinstance(facts, dict):
        return changed
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
            changed.add(box)
    return changed


def _call(model: Any, messages: list[dict[str, str]]) -> Optional[dict]:
    client = getattr(model, "client", None)
    if client is None:
        return None
    resp = None
    try:
        # Each Groq model has its own tokens-a-minute limit: on "too many requests" try the next one.
        # 1.6: the same on a time-out or any other failure, while the time of two calls is not used up.
        t0 = time.monotonic()
        for name in [m.strip() for m in tunables.TALK_MODELS.split(",") if m.strip()] or [""]:
            try:
                resp = client.call(messages, task="talk", timeout=tunables.TALK_TIMEOUT_S, model=name or None)
            except TypeError:       # the sim's client takes no timeout / model
                resp = client.call(messages, "talk")
                break
            if getattr(resp, "success", False):
                break
            if not getattr(resp, "is_429", False) and time.monotonic() - t0 >= 2 * tunables.TALK_TIMEOUT_S:
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
        self.shown: set[str] = set()    # schemes an answer of this call was about (going back to one is allowed)
        self.last_named: list[str] = []  # 1.8: the schemes the last accepted reply named, in order
        self.all_named: list[str] = []   # 1.8: every scheme a reply named in this call, first named first
        self.hold_until = 0.0           # 1.8: "hold on": no quiet rule before this time
        self._held_n = 0                # 1.8: the quiet count when the hold began (the rule counts from there)
        self._pair: list[str] = []      # 1.8: this turn compares these two schemes
        self._others: Optional[list[str]] = None  # 1.8: this turn wants a scheme not named yet: the ones left
        self._will_get = False          # 1.8: "will I get it?" about the scheme in talk
        self.named = False              # the caller's newest words name a scheme
        self.last_action = ""
        self.left: tuple[str, ...] = ()
        self.asked: dict[str, int] = {}  # box -> how often we asked it
        self.just_tell = False  # 1.3a: the caller said "just tell me"; no more questions this call
        self.last_asked = ""    # 1.3b (C): the box the line's last act asked about
        self.turn_kind = ""     # 1.3b (P2.1): talk_kind of this turn
        self.more_needs: list[str] = []  # 1.3b (P2.3): other named needs, kept for later
        self.free_q = 0         # 1.3b (P3.2): the model's own questions this call (at most 1)
        self._new_need = False  # 1.3b (P2.4): the newest words name another need
        self._will_now = False  # 1.3b (P3.4): "will I get it" after just-tell: one question back
        self._will_used = False
        self._people: set[str] = set()  # the "for my mother" sentences already acted on
        self._refunded = False  # 1.3 (A): one ask given back a turn, not one a model try
        self.voice_fails = 0    # 1.6: replies in a row the voice could not say
        self.t0 = time.monotonic()      # 1.6: the talk's start, for the goodbye before the cap
        self.turn_n = 0
        self.stage: dict[str, float] = {}  # the turn's stage times (also set by _turn)
        self._found_text = ""           # 1.5: the words the last search used
        self._piece_memo: Optional[tuple[Any, Any]] = None   # 1.5: (what was asked, the parts), so one turn searches once
        self._proof_ids: Optional[list[str]] = None  # 1.5: schemes whose WHOLE cards are the answer check's proof
        self._sent_ids: list[str] = []  # 1.5: schemes whose parts the last prompt held
        self._chunks_said = False       # 1.5: the fall-back to whole cards is logged once a call

    # --- the fixed part: search -> filter -> picker ---
    def _help_kinds(self) -> list[str]:
        """The kinds of help the line holds (for the not-held reply): every
        need with at least one scheme left."""
        kinds = []
        for cat in self.corpus.values("category"):
            try:
                left = Filter.survivors({"category": cat}, self.corpus)
            except Exception:
                left = []
            if left:
                kinds.append(cat)
        return kinds

    def _state(self, ids: list[str]) -> tuple[talk_pick.Narrow, list[tuple[str, str, str]]]:
        nar = talk_pick.narrow(ids, self.bv, self.corpus)
        if self.just_tell and not self._will_now:  # 1.3a: asking stopped; the 2 best left are shown
            nar = talk_pick.Narrow(nar.left, None)
        if self.turn_kind == talk_kind.HELD_SCHEME and nar.ask:
            nar = talk_pick.Narrow(nar.left, None)  # 1.3b: a scheme we hold: answer first
        elif self.turn_kind == talk_kind.QUESTION and self.focus and nar.ask:
            nar = talk_pick.Narrow(nar.left, None)  # 1.3b: a question on the scheme in talk
        if sum(self.asked.values()) >= tunables.TALK_MAX_QUESTIONS:   # 1.3a: at most 3 questions
            nar = talk_pick.Narrow(nar.left, None)
        if self._will_get:                   # 1.8: "will I get it?": the picker on the scheme in talk alone
            box = talk_pick.needs_ask(self.focus, self.bv, self.corpus,
                                      [b for b, n in self.asked.items() if n >= ASK_TRIES])
            nar = talk_pick.Narrow(nar.left, box, tuple(self.corpus.values(box)) if box else (),
                                   (box,) if box else ())
        show = list(nar.left[:2] if self.just_tell else nar.left[:SHOW_K]) or ids[:SHOW_K]
        if self.focus:                       # the scheme the talk is about goes first, in full
            show = ([self.focus] + [s for s in show if s != self.focus])[:SHOW_K]
        pieces = self._pieces() if tunables.TALK_CHUNKS else None
        if pieces is not None:               # 1.5: parts, not cards; the proof is still the whole cards
            sent = [sid for sid, _m, _t in pieces]
            self._proof_ids = sent + [s for s in dict.fromkeys([self.focus, *self._pair]) if s and s not in sent]
            return nar, pieces
        self._proof_ids = None
        cards = []
        for n, sid in enumerate(show):
            text = self.texts.card(sid, "en")
            if n >= FULL_K:
                text = "\n".join(text.split("\n")[:3])      # [id], name, summary
            cards.append((sid, talk_pick.mark(sid, self.bv, self.corpus), text))
        return nar, cards

    def _no_pieces(self, why: str) -> None:
        """Whole cards for this turn. One line in the call log, the first time."""
        if not self._chunks_said:
            self._chunks_said = True
            self.log.write({"ev": "line", "why": "parts: whole cards, " + why})

    def _pieces(self) -> Optional[list[tuple[str, str, str]]]:
        """1.5: the top PIECES_K parts for the caller's words, one (id, mark, text) per scheme, best first,
        in the shape of a card. None: whole cards this turn (index not loaded, search failed or found
        nothing). Never raises: a call must not die from this.
        `fits`: the mark talk_pick gives each scheme from what the caller told us (the same one the card
        shows). A scheme that "does not fit" is pushed down by the search and dropped here, as the
        picker drops it from the cards; the scheme in talk is kept."""
        index = chunk_index._loaded_chunks.get(self.corpus.snapshot_id)   # loaded when the server starts
        if index is None:
            self._no_pieces("parts index not loaded")
            return None
        t0 = time.monotonic()
        try:
            fits = {sid: talk_pick.mark(sid, self.bv, self.corpus) for sid in index.scheme_ids}
            pins = [s for s in dict.fromkeys([self.focus, *self._pair]) if s]   # 1.8: the pair is pinned like the focus
            ask = (self._found_text, self.focus, self.heard[-1] if self.heard else "", tuple(sorted(fits.items())),
                   tuple(pins), tuple(self._others or ()))
            if self._piece_memo is None or self._piece_memo[0] != ask:
                hits = index.search(self._found_text, k=PIECES_POOL, fits=fits)
                if pins and self.heard:           # "which papers?": the parts of the scheme in talk, by its name
                    own = []
                    for pin in pins:
                        name = "".join(self.texts.card(pin, "en").split("\n")[1:2]).removeprefix("name: ")
                        own += [h for h in index.search(name + " " + self.heard[-1], k=PIECES_POOL, fits=fits)
                                if h.scheme_id == pin][:FOCUS_PIECES]
                    hits = own + hits
                fit = [h for h in hits if fits.get(h.scheme_id) != talk_pick.DOES_NOT_FIT or h.scheme_id in pins]
                if self._others is not None:      # 1.8: "any other?": only schemes not named yet
                    fit = [h for h in fit if h.scheme_id in self._others]
                got: list[Any] = []
                for h in fit if self._others is not None else fit or hits:
                    if (h.scheme_id, h.part) not in {(g.scheme_id, g.part) for g in got}:
                        got.append(h)
                self._piece_memo = (ask, got[:PIECES_K])
            hits = self._piece_memo[1]
            out: dict[str, list[str]] = {}
            for h in hits:
                out.setdefault(h.scheme_id, []).append(f"{chunk_index.PART_TO_FIELD.get(h.part, h.part)}: {h.text}")
            cards = []
            for sid, lines in out.items():
                head = "\n".join(self.texts.card(sid, "en").split("\n")[:2]) or f"[{sid}]"
                cards.append((sid, fits.get(sid, talk_pick.NOT_KNOWN), head + "\n" + "\n".join(lines)))
        except Exception as exc:
            self._no_pieces(f"search failed: {type(exc).__name__}")
            return None
        finally:
            self.stage["search"] = self.stage.get("search", 0.0) + time.monotonic() - t0
        if not cards:
            self._no_pieces("search found nothing")
            return None
        return cards

    def _names_in(self, say: str, scheme: str) -> list[str]:
        """1.8: the schemes a reply named, in the order said; the model's own `scheme` is one even when
        the reply only says "it"."""
        named = getattr(self.index, "named_in", None)
        try:
            names = list(named(say, set(self._sent_ids) | {scheme})) if callable(named) else []
        except Exception:
            names = []
        return [scheme] + names if scheme and scheme not in names else names

    def _hold(self) -> tuple[str, str]:
        self.hold_until = time.monotonic() + tunables.TALK_HOLD_S
        return "hold", prompt.HOLD.get(self.lang, prompt.HOLD["en"])

    def _early(self, words: str) -> Optional[tuple[str, str]]:
        """1.8: replies made by code alone, with no model call."""
        if talk_follow.hold(words):
            return self._hold()
        if self.last_say and talk_follow.hear(words):     # mid-call "hello? can you hear me?"
            sents = _sentences(self.last_say)
            again = ([s for s in sents if "?" in s] or sents)[-1]
            return "hear", prompt.HEAR.get(self.lang, prompt.HEAR["en"]) + " " + again
        if self.last_say and talk_follow.how_much(words):    # only the sentence that held the number
            nums = [s for s in _sentences(self.last_say) if re.search(r"\d", s)]
            if nums:
                return "answer", " ".join(nums)
        return None

    def _found(self) -> list[str]:
        """Search's top 10 on the last three caller turns, plus every scheme of the kind of help
        the caller named (search is weak on English words written in Hindi letters)."""
        named = self.index.search(self.heard[-1], 1) if self.heard else []
        self.named = bool(named and named[0].by == "name")
        if self.named:                       # the caller said a scheme's name: the talk is about it now
            self.focus = named[0].scheme_id
        if self._new_need:                   # 1.3b (P2.4): the new words only; the old talk is dropped
            if not self.named:
                self.focus = ""
            text = self.heard[-1]
        else:
            text = " ".join(self.heard[-3:])
        self._found_text = text
        ranked = [h.scheme_id for h in self.index.search(text, len(self.index.ids) or SEARCH_K)]
        ids = ranked[:SEARCH_K]
        category = self.bv.get("category")
        if category in self.corpus.values("category"):
            kind = {self.corpus.scheme_id(ix) for ix in Filter.survivors({"category": category}, self.corpus)}
            ids += [sid for sid in ranked[SEARCH_K:] if sid in kind]
        if self._others is not None:         # 1.8: "any other?": what is left of the found schemes
            self._others = [sid for sid in ids if sid not in self.all_named
                            and talk_pick.mark(sid, self.bv, self.corpus) != talk_pick.DOES_NOT_FIT]
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
        early = self._early(words)
        if early is not None:
            return early
        self._pair, self._others = [], None
        follow = [prompt.FOLLOW["simpler"]] if talk_follow.simpler(words) else []
        if talk_follow.how_much(words):
            follow.append(prompt.FOLLOW["how_much"])
        move, sid = talk_follow.pick(words, self.last_named, self.all_named, self.focus)
        if move == "move":                          # 1.8: "the second one": the talk moves to it, by code
            self.focus = sid
            follow.append(prompt.FOLLOW["move"].format(sid=sid))
        elif move == "other":
            self._others = []                       # filled by _found
        if talk_follow.side_by_side(words, self.all_named):
            self._pair = self.all_named[-2:]
        # The clear words first, by fixed code (a real call showed the model can miss "farmer schemes").
        known0 = {b: v for b, v in self.bv.items() if v != UNASKED}
        cat0 = self.bv.get("category")
        self._refunded = False
        who = talk_words.other_person(words)        # 1.3b (P2.6): help for another person now;
        if who and who not in self._people:         # once for each person, not on every "for my mother"
            self._people.add(who)
            for box in ("age", "gender", "occupation"):  # age, gender and work are theirs, not ours
                self.bv[box] = UNASKED
                self.asked.pop(box, None)
        spotted = talk_words.spot(words, self.corpus)
        if cat0 in self.corpus.values("category") and spotted.get("category") not in (None, cat0) \
                and talk_words.work_only(words, spotted["category"]):
            del spotted["category"]                 # "मैं किसान हूँ" in a pension talk is work, not a new need
        spot_filled = _take_facts(spotted, self.bv, self.corpus, self.log, self.turn_n)
        self._new_need = False
        cats = talk_words.spot_all(words, self.corpus).get("category", [])
        if cat0 in self.corpus.values("category"):
            cats = [c for c in cats if c == cat0 or not talk_words.work_only(words, c)]
        if cats and cats[0] != cat0:  # 1.3b (P2.3): take the first named need
            if cat0 in self.corpus.values("category"):
                self._new_need = True               # 1.3b (P2.4)
            if self.bv.get("category") != cats[0]:
                self.bv["category"] = cats[0]
                self.log.write(TurnLogRecord(turn_n=self.turn_n, turn_class="ANSWER",
                                             box="category", value=cats[0]))
        for extra in cats[1:]:                      # keep the other, come back to it once
            if extra != self.bv.get("category") and extra not in self.more_needs \
                    and len(self.more_needs) < 2:
                self.more_needs.append(extra)
        self._will_get = bool(self.focus and talk_follow.will_get(words))   # 1.8: "will I get it?": the scheme in talk
        self._will_now = bool(self.just_tell and not self._will_used and talk_follow.will_get(words))
        ids = self._timed("search", self._found)
        self.turn_kind = talk_kind.kind(words, self.index)  # 1.3b (P2.1): on every turn
        boxes = {b: self.corpus.values(b) for b in SEVEN_BOXES}
        text = log_text.log_text(_rows(self.log), tunables.TALK_LOG_CHARS)
        note = prompt.CUT_NOTE if cut else ""
        wrong_ask = False                           # the last try asked a box the picker did not name
        nar, cards = self._state(ids)
        if self._others is not None:
            follow.append(prompt.FOLLOW["other"].format(left=", ".join(f"[{s}]" for s in self._others))
                         if self._others else prompt.FOLLOW["other_none"])
        if len(self._pair) == 2:
            follow.append(prompt.FOLLOW["side"].format(a=self._pair[0], b=self._pair[1]))
        if self._will_get:
            follow.append(prompt.FOLLOW["will_ask" if nar.ask else "will_known"].format(sid=self.focus))
        note = " ".join([note, *follow]).strip()
        if self.turn_kind == talk_kind.NOT_HELD_SCHEME:  # 1.3b (P2.2): fixed words, no questions
            self.last_asked = ""
            return "answer", prompt.not_held_say(self.lang, self._help_kinds())
        if words_tell_me.is_just_tell_me(words):  # 1.3a: no more questions for the rest of the call
            self.just_tell = True
            nar, cards = self._state(ids)
        if (words_no_answer.no_answer(words) and nar.ask and nar.ask == self.last_asked
                and self.bv.get(nar.ask) == UNASKED):
            self.bv[nar.ask] = UNKNOWN            # 1.3b (C): only the box just asked about
            nar, cards = self._state(ids)
        for _try in (0, 1):
            known = {b: v for b, v in self.bv.items() if v != UNASKED}
            self._sent_ids = [sid for sid, _m, _t in cards]
            data = self._timed("model", _call, self.model, prompt.build(
                self.lang, text, known, boxes, nar.ask, nar.order, cards, words, note,
                self.focus, sorted(self.told.get(self.focus, ()))))
            wrong_ask = False
            if data is None:
                break
            action = str(data.get("action") or "").strip().lower()
            say = str(data.get("say") or "").strip().translate(_HINDI_DIGITS)   # the voice and the checks want 0-9
            if action not in prompt.ACTIONS:
                note = "action must be one of: " + ", ".join(prompt.ACTIONS)
                continue
            facts = data.get("facts")
            if (isinstance(facts, dict) and "gender" not in spot_filled and not who
                    and self.bv.get("gender") not in (UNASKED, UNKNOWN, None)
                    and facts.get("gender") not in (None, "", self.bv.get("gender"))
                    and any(t in talk_words.OTHER_PEOPLE for t in talk_words._toks(words.lower()))):
                # A relation word that is only mentioned ("मेरे पिताजी हैं") is not a switch of the person
                # in talk: the model's gender flip is dropped. Only "for my father" (who) switches.
                self.log.write({"ev": "blocked", "rule": "fact", "question": "", "text": f"gender = {facts.get('gender')}"})
                facts = {k: v for k, v in facts.items() if k != "gender"}
            filled = _take_facts(facts, self.bv, self.corpus, self.log, self.turn_n)
            nots = data.get("not")                  # 1.3b (P3.3): the model takes facts away
            for box in nots if isinstance(nots, list) else []:
                if isinstance(box, str) and box in SEVEN_BOXES and self.bv.get(box) != UNASKED:
                    self.bv[box] = UNASKED
            if data.get("just_tell") is True:       # 1.3b (P3.3): no more questions this call
                self.just_tell = True
            if not self._refunded and _free_ask(self.last_asked, set(spot_filled) | set(filled)):
                self._refunded = True               # 1.3 (A): they answered another box
                if self.asked.get(self.last_asked, 0) <= 1:
                    self.asked.pop(self.last_asked, None)
                else:
                    self.asked[self.last_asked] -= 1
            for box, n in self.asked.items():      # asked twice, still no answer: stop asking it
                if n >= ASK_TRIES and self.bv.get(box) == UNASKED:
                    self.bv[box] = UNKNOWN
            ids = self._timed("search", self._found)
            changed = set(spot_filled) | set(filled)
            if any(b in known0 and known0[b] != UNKNOWN for b in changed):
                category = self.bv.get("category")  # 1.3b (P2.5): a corrected fact builds
                if category in self.corpus.values("category"):  # the list again from the need
                    kind = {self.corpus.scheme_id(ix)
                            for ix in Filter.survivors({"category": category}, self.corpus)}
                    ranked = [h.scheme_id for h in self.index.search(
                        " ".join(self.heard[-3:]), len(self.index.ids) or SEARCH_K)]
                    ids = [s for s in self.index.ids if s in kind]
                    ids += [s for s in ranked if s not in kind]
            nar, cards = self._state(ids)          # the facts may have changed the picker's answer
            self.left = nar.left
            if action in ("not_for_me", "repeat", "goodbye"):
                if action != "repeat":
                    self.last_asked = ""
                return action, ""               # goodbye: the farewell clip is the only thing said
            if action == "other_topic":         # fixed words; the model does not write this one
                self.last_asked = ""
                return action, prompt.OTHER_TOPIC.get(self.lang, prompt.OTHER_TOPIC["en"])
            if action == "hold":                # 1.8: fixed words; the question being asked stays open
                return self._hold()
            ask_box = str(data.get("ask_box") or "").strip()
            if action == "ask" and ask_box and ask_box != nar.ask:
                wrong_ask = True
                note = (f'Ask about "{nar.ask}", not "{ask_box}".' if nar.ask else
                        "No question about the caller is left. Do not ask one: show the schemes or answer.")
                continue
            if action == "ask" and not ask_box and self.free_q >= 1:
                wrong_ask = True                # 1.3b (P3.2): one free question a call, no more
                note = ("You already asked your own question once this call. "
                        "Do not ask another: show the schemes or answer.")
                continue
            if self._proof_ids is None:
                whole = [c for _s, _m, c in cards]
            else:   # 1.5: the whole card of every scheme whose parts the model saw (this prompt or the last one)
                whole = [self.texts.card(s, "en") for s in dict.fromkeys(self._sent_ids + self._proof_ids)]
            proof = "\n\n".join(whole) + "\n" + " ".join(
                str(v) for vals in boxes.values() for v in vals)
            # What the caller said in this call may be said back (the age "सत्तर" -> 70). A made-up amount is still blocked.
            proof += " " + " ".join(str(int(n)) for n in middle._numbers(" ".join(self.heard)))
            checked = _plain_numbers(say)
            rule = "empty"
            for _ in range(6 if say else 0):
                rule = check_answer(checked, self.lang, _plain_numbers(proof),
                                    tunables.TALK_MAX_SENTENCES, tunables.TALK_MAX_WORDS)
                hit = vocab.find_forbidden(checked, self.lang) if rule == "forbidden" else ""
                # The word list is matched as plain letters: "आपको ज़रूर" (a promise) is found inside
                # "आपको ज़रूरी कागज़" (the papers needed). A hit that is only the start of a longer
                # Hindi word is not the forbidden words; the rest of the checks still run.
                inside = re.compile(re.escape(hit) + r"(?=[\u0900-\u097F])") if hit else None
                if not inside or not inside.search(checked) or re.search(re.escape(hit) + r"(?![\u0900-\u097F])", checked):
                    break
                checked = inside.sub("…", checked)
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
            # The talk was about one scheme and the caller named no other: an answer about another
            # scheme is off the point ("how much money?" got the first pension scheme, not the one in talk).
            if (_try == 0 and action == "answer" and self.last_action == "answer" and self.focus
                    and scheme in ids and scheme != self.focus and not self.named
                    and scheme not in self.shown and scheme not in self.told and scheme not in self._pair):
                self.log.write({"ev": "blocked", "rule": "other_scheme", "question": mask_digits(words), "text": say})
                note = (f"The caller is still asking about [{self.focus}] and named no other scheme. "
                        f"Answer about [{self.focus}].")
                continue
            if len(self._pair) == 2 and _try == 0 and action == "answer" and scheme in ids and scheme not in self._pair:
                self.log.write({"ev": "blocked", "rule": "other_scheme", "question": mask_digits(words), "text": say})
                note = f"The caller compares [{self._pair[0]}] and [{self._pair[1]}] only. Answer about those two."
                continue                        # 1.8: side by side: only the two last named
            if scheme in ids:
                self.focus = scheme
                if action in ("answer", "show_scheme") and say:
                    self.shown.add(scheme)
            if action in ("answer", "show_scheme") and say:
                names = self._names_in(say, scheme if scheme in ids else "")
                if names:                       # 1.8: what this reply named; a second scheme counts as shown
                    self.shown.update(names)
                    self.last_named = names
                    self.all_named += [n for n in names if n not in self.all_named]
            parts = data.get("parts")
            if self.focus and action in ("answer", "show_scheme") and isinstance(parts, list):
                self.told.setdefault(self.focus, set()).update(p for p in parts if p in prompt.PARTS)
            if action == "ask" and ask_box:
                self.asked[ask_box] = self.asked.get(ask_box, 0) + 1   # 1.3 (A): every ask counts
                self.last_asked = ask_box
                if self._will_now:
                    self._will_used = True
            elif action == "ask":                    # 1.3b (P3.2): the model's own question
                self.free_q += 1
                self.last_asked = ""
                if self._will_now:
                    self._will_used = True
            else:
                self.last_asked = ""
            if action in ("answer", "show_scheme") and self.more_needs and say:
                extra = self.more_needs.pop(0)      # 1.3b (P2.3): "you also asked about a house"
                say = say + " " + prompt.ALSO_ASKED.get(
                    self.lang, prompt.ALSO_ASKED["en"]).format(kind=prompt.kind_say(extra, self.lang))
            return action, say
        if wrong_ask and nar.ask:                   # C1: the picker's question, in fixed words
            self.asked[nar.ask] = self.asked.get(nar.ask, 0) + 1
            self.last_asked = nar.ask
            return "ask", prompt.QUESTION.get(nar.ask, {}).get(self.lang) or prompt.NOT_SURE[self.lang]
        self.last_asked = ""
        return "answer", prompt.NOT_SURE.get(self.lang, prompt.NOT_SURE["en"])

    # --- the mouth ---
    def _speak(self, say: str, before_first: Any = None) -> bool:
        """`before_first` is called when the first sentence's sound is ready, just before it is said.
        False: the voice gave no sound for any sentence, even on a second try (1.6)."""
        if not hasattr(self.audio, "say_text"):
            return True
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
        said = 0
        for n, sentence in enumerate(parts):
            if n and ahead:
                ahead[n - 1].join(timeout=tunables.QA_TTS_TIMEOUT_S)
            for _again in (0, 1):                   # 1.6: the voice failed: one more try
                if stream and n == 0:
                    ok = self.audio.say_text(sentence, on_first=before_first)
                else:
                    ok = self.audio.say_text(sentence)
                if ok is not False or self._gone() or self._newer():
                    break
            said += ok is not False
        return bool(said) or not parts or self._gone() or self._newer()

    def _gone(self) -> bool:
        turn = getattr(self.audio, "turn", None)
        return bool(turn is not None and turn.hung_up.is_set())

    def _newer(self) -> bool:
        """The caller spoke again while the reply was made: it is dropped on purpose, not a voice fault."""
        newer = getattr(self.audio, "newer_words", None)
        return bool(newer()) if callable(newer) else False

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
            if action in ("answer", "ask", "show_scheme"):
                self.last_action = action
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
                if self._speak(say, first_voice):
                    self.voice_fails = 0
                else:                               # 1.6: never silence: a recorded line asks again
                    self.voice_fails += 1
                    self.log.write({"ev": "blocked", "rule": "voice_failed", "question": "", "text": say})
                    stop_filler()
                    if self.voice_fails < VOICE_FAILS_HANGUP:
                        self.audio.say(("unclear_prompt",))
                if action not in ("hold", "hear"):  # 1.8: "repeat" and the next "hello?" go back to the question
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

    def run(self, first_words: str = "") -> None:
        if first_words:
            # The caller already asked at the greeting: answer that, with no second hello.
            if self._turn(first_words) == "goodbye":
                return self._end(farewell=True)
        else:
            self._speak(prompt.HELLO.get(self.lang, prompt.HELLO["en"]))
        while True:
            if self.turn_n >= tunables.TALK_MAX_TURNS:
                return self._end(farewell=True)
            if time.monotonic() - self.t0 >= tunables.CALL_CEILING_S - CAP_MARGIN_S:
                return self._end(farewell=True, reason=STOP_MAX_TURNS)   # 1.6: goodbye before the cap
            if self.voice_fails >= VOICE_FAILS_HANGUP:
                return self._end(farewell=True, reason=STOP_NO_SPLIT)    # 1.6: the voice is down
            inp = self.audio.next_input(profile="spoken")
            if isinstance(inp, Hangup):
                return self._end(farewell=False, reason=STOP_ZERO_SURVIVORS)
            if isinstance(inp, Silence):
                self.log.write(TurnLogRecord(turn_n=self.turn_n, turn_class="SILENCE", silence_n=inp.n))
                if time.monotonic() < self.hold_until:  # 1.8: "hold on": the quiet rule has not started
                    self._held_n = inp.n
                    continue
                if inp.n - self._held_n >= SILENCE_HANGUP_RUNG:
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
            self._held_n, self.hold_until = 0, 0.0   # words came: the hold is over
            if tunables.LANG_EACH_TURN:     # 1.2: the caller's last turn set the language
                self.lang = getattr(self.audio, "language", self.lang)
            if self._turn(inp.text.strip(), inp.end_ms, inp.stt_ms, bool(inp.cut_clip)) == "goodbye":
                return self._end(farewell=True)


def run(audio: Any, model: Any, corpus: Any, log: Any, lang: str, index: Any = None, first_words: str = "") -> None:
    """The rest of the call after the language pick. Ends the call itself. `first_words`: what the
    caller said at the greeting; it is turn 1 and the hello is skipped."""
    _Talk(audio, model, corpus, log, lang, index).run(first_words)
