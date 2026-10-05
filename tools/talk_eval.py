"""tools/talk_eval.py

Step 7.14 (B6.b) — many scripted TALK calls on the barge-eval rig, and four rules each must keep.

The rig is `tools/barge_eval.py`'s: the real engine, talk loop, PhoneAudio, Turn, Mouth and Ear on
a made-up clock, with only the edges faked (the phone line, speech-to-text, the model, the voice).
No network, no money. A plain call is run first; then the same call again and again with ONE more
thing put in at every place the agent spoke (side talk, a real cut-in, "hmm", "ok ok", a noise, a
key, a hang-up), with the cut-in gate off (strict turns) and on.

Rules, for every call:
  R1  it always ends (no crash, not stuck, the line is closed, the log has its last row)
  R2  never dead air over 2.5 s between the caller's last word and the agent's first sound
  R3  never the same line twice in a row (unless the caller asked to hear it again)
  R4  never a restart (the hello is not said again once the caller has been answered)
  R5  words that were not for the agent never get a spoken reply

Run:  python -m tools.talk_eval            (all calls, a short report)
      python -m tools.talk_eval --show 12  (one call as a timeline, by its number)
"""
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional

from haqdaar.audio import ear as ear_mod
from haqdaar.audio import phone as phone_mod
from haqdaar.audio import turn as turn_mod
from haqdaar.audio.ear import Ear, EnergyVAD
from haqdaar.audio.mouth import Mouth
from haqdaar.audio.phone import PhoneAudio
from haqdaar.audio.turn import Turn
from haqdaar.contracts import tunables
from haqdaar.data import scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.engine.call import Engine
from haqdaar.prompts import talk as prompt
from tools import barge_eval as be

MODEL_S = 0.7           # what one model call costs (measured: 0.4 to 1.0 s)
TTS_S = 0.4             # what the first sound of a new sentence costs (measured: 0.2 to 0.45 s)
END_FRAMES = 30         # 600 ms of quiet ends the caller's turn, as in a real talk call
DEAD_AIR_S = 2.5
REMIND_S, HANGUP_S = 6.0, 12.0

BYE = ("say", "thank you goodbye", 1.0)
SCRIPTS: dict[str, list[Any]] = {
    "ask": [("say", "i need a scheme for farming", 1.8), ("say", "how much money does it give", 1.6),
            ("say", "which papers are needed", 1.4), ("say", "say that again please", 1.2), BYE],
    "vague": [("say", "i need some help", 1.2), ("say", "a pension", 0.9), ("say", "i am sixty years old", 1.5),
              ("say", "what is the weather today", 1.4), BYE],
    "sidetalk": [("say", "i need help to build a house", 1.8), ("say", "arre ramesh bring the tea", 1.5),
                 ("say", "how do i apply for it", 1.4), BYE],
    "quiet": [("say", "i need a scheme for farming", 1.8), "s", ("say", "how much money does it give", 1.6), "s", "s"],
    # 1.3b: clarify-first flows (each must keep the rules with the wired kinds).
    "q_situation": [("say", "my crops died", 1.5), ("say", "i grow wheat", 1.2), BYE],
    "q_named": [("say", "pm kisan", 1.0), ("say", "how much money does it give", 1.6), BYE],
    "q_notheld": [("say", "ayushman card मिलेगा क्या", 1.8), BYE],
    "q_justtell": [("say", "i need some scheme", 1.2), ("say", "just tell me", 1.0),
                   ("say", "ok", 0.8), BYE],
    "q_dontknow": [("say", "i need some scheme", 1.2), ("say", "i do not know", 1.0),
                   ("say", "ok", 0.8), BYE],
    "q_two": [("say", "खेती और घर दोनों के लिए कुछ है क्या", 2.0), ("say", "ok", 0.8), BYE],
    "q_newneed": [("say", "मुझे पेंशन चाहिए", 1.2), ("say", "मुझे लोन चाहिए", 1.2), BYE],
    "q_three": [("say", "hmm", 0.6), ("say", "hmm", 0.6), ("say", "hmm", 0.6),
                ("say", "ok", 0.8), BYE],
}
# One more thing the caller's side does: (text, seconds), or a key, or a hang-up.
KINDS: dict[str, Any] = {
    "side_talk": ("arre ramesh put it over there", 1.6),
    "cut_in": ("wait tell me about the pension scheme", 1.8),
    "hmm": ("hmm", 0.5),
    "ok_ok": ("ok ok", 1.0),
    "noise": ("", 1.2),
    "long_noise": ("", 4.0),
    "key": "5",
    "hangup": "h",
}
SIDE_WORDS = ("ramesh",)

_CORPUS: Any = None
_TMP: Optional[tempfile.TemporaryDirectory] = None


def corpus() -> Any:
    global _CORPUS
    if _CORPUS is None:
        _CORPUS = Corpus.load("CURRENT")
    return _CORPUS


class Index:
    """Search with no model: every scheme, in the snapshot's order."""

    def __init__(self, corp: Any) -> None:
        self.ids = [corp.scheme_id(ix) for ix in range(len(corp._scheme_ids))]

    def search(self, text: str, k: int = 4) -> list[Any]:
        return [scheme_index.Hit(sid, 0.5, "vector") for sid in self.ids[:k]]


class TalkClient:
    """The model: reads the newest caller words out of the prompt and answers by fixed rules."""

    def __init__(self, world: be.World) -> None:
        self._w = world
        self.n = 0
        self.seen: list[str] = []

    def call(self, messages: list[dict[str, str]], task: str = "", timeout: Any = None, model: Any = None) -> Any:
        self._w.advance_to(self._w.now + MODEL_S)
        found = re.search(r'NEWEST CALLER WORDS: "(.*)"', messages[-1]["content"])
        words = (found.group(1) if found else "").lower()
        self.seen.append(words)
        self.n += 1
        if any(w in words for w in SIDE_WORDS):
            data = {"action": "not_for_me", "say": ""}
        elif "goodbye" in words:
            data = {"action": "goodbye", "say": ""}
        elif "again" in words:
            data = {"action": "repeat", "say": ""}
        elif "weather" in words:
            data = {"action": "other_topic", "say": ""}
        else:
            name = "".join("abcdefghij"[int(d)] for d in str(self.n))     # no digits: the number check reads them
            data = {"action": "answer", "say": f"This is reply {name} about the scheme. "
                                               f"It has a second short part. Do you want to hear more?"}
        return SimpleNamespace(success=True, data={"facts": {}, "scheme": "", "ask_box": "", **data},
                               error=None, is_429=False, is_timeout=False, latency_s=MODEL_S)


def run_call(script: str, gate: bool, inject: Optional[Callable[[be.World, be.Caller], None]] = None,
             n: int = 0) -> be.Result:
    """One whole talk call on the real engine."""
    global _TMP
    if _TMP is None:
        _TMP = tempfile.TemporaryDirectory(prefix="talk_eval_")
    corp = corpus()
    flags = dict(TALK_ONLY=True, QA_SPEAK=True, CUT_IN_GATE=gate, SPEECH_CUT_IN=False, LIVE_TTS_STREAM=False,
                 QA_ENABLED=False, SILENCE_REMIND_S=REMIND_S, SILENCE_HANGUP_S=HANGUP_S)
    saved = {k: getattr(tunables, k) for k in flags}
    saved_time = (turn_mod.time, ear_mod.time, phone_mod.time)
    saved_index = scheme_index.get
    for k, v in flags.items():
        setattr(tunables, k, v)
    world = be.World()
    turn_mod.time = ear_mod.time = phone_mod.time = be.FakeTime(world)
    scheme_index.get = lambda snapshot_id="CURRENT": Index(corp)
    res = be.Result()
    try:
        line, rec = be.Line(world), be.Rec(world)
        caller = be.Caller(world, [be.lang_key("en")] + SCRIPTS[script])
        stt = be.FakeSTT(world, caller)
        clock = lambda: world.now  # noqa: E731
        mouth = Mouth(line.emit, "MZ-talk", clock=clock, log=rec)
        ear = Ear(stt=stt, vad=EnergyVAD(end_frames=END_FRAMES), log=rec)
        ear._events = be.VQueue(world)
        turn = Turn(mouth, ear=ear, trace=rec, log=rec, clock=clock)
        turn._keys = be.VQueue(world)

        def close() -> None:
            line.closed_at = world.now
            world.frames_on = False

        def speak(text: str, lang: str) -> bytes:
            world.advance_to(world.now + TTS_S)
            return b"\x55" * int(tunables.SAMPLE_RATE * (0.8 + len(text) / 30.0))

        phone = PhoneAudio(corp, be.Pool(str(Path(_TMP.name) / "audio")), mouth, turn, close=close,
                           log=rec, trace=rec, speak=speak)
        phone._saved_answer = lambda key: None      # always made new: the slow path
        phone._save_answer = lambda key, audio: None
        phone.warm_text = None                      # no threads on the made-up clock: one sentence at a time
        line.on_mark = phone.on_mark
        world.line, world.turn = line, turn
        real_next, real_lang = phone.next_input, phone.select_language

        def next_input(profile: str = "normal") -> Any:
            caller.on_wait(profile)
            inp = real_next(profile)
            caller.wait_log[-1].update(got=type(inp).__name__, got_t=world.now,
                                       text=getattr(inp, "text", getattr(inp, "digit", "")))
            return inp

        def select_language() -> Any:
            caller.on_wait("greeting")
            return real_lang()

        phone.next_input, phone.select_language = next_input, select_language
        if inject is not None:
            inject(world, caller)
        log = Log.open(call_id=f"talk_{n}", snapshot_id=corp.snapshot_id, logs_dir=str(Path(_TMP.name) / "logs"))
        log.tap = rec.record
        client = TalkClient(world)
        try:
            Engine.run_call(audio=phone, model=SimpleNamespace(client=client, keypad_only=False), corpus=corp, log=log)
        except be.Stuck as e:
            res.error = f"stuck: {e}"
        except Exception as e:  # a crash is a finding, not a reason to stop the run
            res.error = f"crash: {type(e).__name__}: {e}"
        res.clips, res.clears, res.rows, res.lines = line.clips, line.clears, rec.rows, rec.lines
        res.log_rows, res.waits, res.said, res.keys = rec.log_rows, caller.wait_log, caller.said, caller.keys
        res.closed_at, res.hung_up_at, res.end_t = line.closed_at, caller.hung_up_at, world.now
        res.model_seen = client.seen
        try:
            (Path(_TMP.name) / "logs" / f"talk_{n}.jsonl").unlink()
        except OSError:
            pass
    finally:
        turn_mod.time, ear_mod.time, phone_mod.time = saved_time
        scheme_index.get = saved_index
        for k, v in saved.items():
            setattr(tunables, k, v)
    return res


# --- the rules -------------------------------------------------------------------------

SPOKEN = ("answer", "ask", "show_scheme", "other_topic", "repeat")


def check(res: be.Result) -> list[str]:
    """The rules this call broke, as short lines. Empty: all kept."""
    bad: list[str] = []
    rows = res.log_rows
    error = getattr(res, "error", None)
    if error:
        bad.append(f"R1 {error}")
    if res.closed_at is None and res.hung_up_at is None:
        bad.append("R1 the line was never closed")
    if not any("stop" in r for r in rows):
        bad.append("R1 the log has no last row")

    said_texts = {s["t1"]: s for s in res.said}
    for row in rows:
        if row.get("ev") != "act":
            continue
        before = [t1 for t1 in said_texts if t1 <= row["t"]]
        if not before:
            continue
        t1 = max(before)
        action = row.get("action")
        speaks = action in SPOKEN or action == "goodbye" or (action == "not_for_me" and row.get("again"))
        if not speaks or (res.hung_up_at is not None and res.hung_up_at <= t1 + DEAD_AIR_S):
            continue
        starts = [c["start"] for c in res.clips if c["start"] >= t1 - 0.01]
        gap = (min(starts) - t1) if starts else 99.0
        if gap > DEAD_AIR_S:
            bad.append(f"R2 {gap:.1f} s of dead air after \"{said_texts[t1]['text']}\" ({action})")

    last, may_repeat = None, False
    heard = False
    hello = prompt.HELLO["en"]
    for row in rows:
        ev = row.get("ev")
        if ev == "act" and row.get("action") in SPOKEN:      # side talk alone is not "the caller was heard"
            heard = True
        if ev == "act" and row.get("action") == "repeat" or row.get("class") == "SILENCE":
            may_repeat = True
        if ev == "said" and row.get("tokens") == ["answer"]:
            text = row.get("text", "")
            if text == last and not may_repeat:
                bad.append(f"R3 said twice in a row: \"{text[:60]}\"")
            if heard and text and text in hello:
                bad.append("R4 the hello was said again after the caller was heard")
            last, may_repeat = text, False
    # A wrong key at the language pick plays the greeting again: that is the pick, not a restart.
    talk_from = min([c["start"] for c in res.clips if c["name"] == "answer"], default=None)
    if talk_from is not None and [c for c in res.clips if c["name"] == "greeting_trilingual" and c["start"] > talk_from]:
        bad.append("R4 the greeting was played again after the talk began")

    quiet_for = None
    for row in rows:
        ev = row.get("ev")
        if ev == "act":
            quiet_for = row if row.get("action") == "not_for_me" else None
        elif ev == "said" and quiet_for is not None and row.get("tokens") == ["answer"]:
            bad.append("R5 a spoken reply to words that were not for the agent")
            quiet_for = None
        elif ev == "heard" or row.get("class") == "SILENCE":
            quiet_for = None
    return bad


def _inject(kind: str, at: float) -> Callable[[be.World, be.Caller], None]:
    what = KINDS[kind]

    def plan(world: be.World, caller: be.Caller) -> None:
        if what == "h":
            world.at(at, caller.hang_up)
        elif isinstance(what, str):
            world.at(at, lambda: caller.press(what))
        else:
            world.at(at, lambda: caller.speak(world.now, what[1], what[0]))

    return plan


def plan(scripts: Optional[list[str]] = None, kinds: Optional[list[str]] = None,
         places: Optional[int] = None) -> list[dict[str, Any]]:
    """Every call to run: the plain ones, then one extra thing at each place the agent spoke
    (near its start, well inside it, and in the quiet just after it)."""
    cases: list[dict[str, Any]] = []
    for script in scripts or list(SCRIPTS):
        for gate in (False, True):
            plain = run_call(script, gate)
            cases.append(dict(script=script, gate=gate, kind="plain", at=None, res=plain))
            times: list[float] = []
            for clip in plain.clips:
                times += [clip["start"] + 0.3, clip["start"] + 1.2, clip["end"] + 0.2]
            times = sorted(set(round(t, 2) for t in times))
            if places:
                step = max(1, len(times) // places)
                times = times[::step][:places]
            for kind in kinds or list(KINDS):
                for at in times:
                    cases.append(dict(script=script, gate=gate, kind=kind, at=at, res=None))
    return cases


def run_all(scripts: Optional[list[str]] = None, kinds: Optional[list[str]] = None,
            places: Optional[int] = None) -> list[dict[str, Any]]:
    cases = plan(scripts, kinds, places)
    for n, case in enumerate(cases):
        if case["res"] is None:
            case["res"] = run_call(case["script"], case["gate"], _inject(case["kind"], case["at"]), n)
        case["n"], case["bad"] = n, check(case["res"])
    return cases


def show(case: dict[str, Any]) -> None:
    res = case["res"]
    ev: list[tuple[float, str]] = []
    for c in res.clips:
        cut = f", CUT at {c['cut_at'] - be.T0:.2f}" if c["cut_at"] is not None else ""
        ev.append((c["start"], f"agent   {c['name']} ({c['end'] - c['start']:.1f} s{cut})"))
    for s in res.said:
        ev.append((s["t0"], f"CALLER  \"{s['text'] or '(noise)'}\" ({s['t1'] - s['t0']:.1f} s)"))
    for t, key in res.keys:
        ev.append((t, f"CALLER  key {key}"))
    for r in res.log_rows:
        if r.get("ev") in ("heard", "act", "cut") or "stop" in r:
            ev.append((r["t"], "log     " + ", ".join(f"{k}={v}" for k, v in r.items() if k not in ("t", "ts"))[:120]))
    if res.hung_up_at is not None:
        ev.append((res.hung_up_at, "CALLER  hangs up"))
    for t, line in sorted(ev):
        print(f"{t - be.T0:7.2f}  {line}")
    print("rules broken:", case["bad"] or "none")


def main() -> int:
    ap = argparse.ArgumentParser(description="Many scripted talk calls; four rules each must keep.")
    ap.add_argument("--show", type=int, default=None, help="print one call as a timeline, by its number")
    ap.add_argument("--script", action="append", choices=list(SCRIPTS))
    ap.add_argument("--kind", action="append", choices=list(KINDS))
    ap.add_argument("--places", type=int, default=None, help="at most this many places per plain call")
    args = ap.parse_args()
    cases = run_all(args.script, args.kind, args.places)
    if args.show is not None:
        case = cases[args.show]
        print(f"call {case['n']}: script {case['script']}, gate {'on' if case['gate'] else 'off'}, "
              f"{case['kind']} at {(case['at'] or be.T0) - be.T0:.2f}")
        show(case)
        return 0
    failed = [c for c in cases if c["bad"]]
    print(f"talk calls: {len(cases)}   rules broken in: {len(failed)}")
    for gate in (False, True):
        some = [c for c in cases if c["gate"] == gate]
        cuts = sum(len(c["res"].clears) for c in some)
        print(f"  cut-in gate {'on ' if gate else 'off'}: {len(some)} calls, {len([c for c in some if c['bad']])} with a broken rule, "
              f"the agent was stopped {cuts} times")
    by_rule: dict[str, int] = {}
    for c in failed:
        for line in c["bad"]:
            by_rule[line.split()[0]] = by_rule.get(line.split()[0], 0) + 1
    for rule, count in sorted(by_rule.items()):
        print(f"  {rule}: {count}")
    for c in failed[:12]:
        print(f"  call {c['n']} ({c['script']}, gate {'on' if c['gate'] else 'off'}, {c['kind']} at "
              f"{(c['at'] or be.T0) - be.T0:.2f}): {c['bad'][0]}")
    if failed:
        print("  see one with: python -m tools.talk_eval --show <call number>")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
