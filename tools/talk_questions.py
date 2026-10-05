"""tools/talk_questions.py

Step 7.14 (B6.a + B6.c) — real questions through the REAL model, with no phone and no voice.

  --questions   40 caller sentences (Hindi and English), each as the first turn of a new call,
                once for every model in TALK_MODELS. Score per model: the right scheme, the truth
                checks (a refused first reply; the "not sure" line), and the model's time.
  --replay      the caller's words of the two real calls of 4 Oct (22:38 and 22:41), in order,
                through the talk loop. Those calls had only side talk and half words: the agent
                must say nothing to most of it, never "sorry", never start again.

It spends Groq requests only (free tier; PER MODEL: 8,000 tokens a minute, 1,000 requests a day
and, found 5 Oct, 200,000 TOKENS A DAY on qwen/qwen3.8-27b). One talk prompt is about 3,000
tokens: two calls a minute, and only about 65 turns a day on one model. The whole run is
40 x 3,000 = 120,000 tokens PER MODEL: more than half a day's tokens. Do not run it on a day
the phone demo is needed. The run waits between questions and tries twice more on "too many
requests"; when a model stays refused its day is used up: stop the run.

Run:  python -m tools.talk_questions --questions            (about 25 minutes)
      python -m tools.talk_questions --questions --limit 6  (a quick look)
      python -m tools.talk_questions --replay
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from haqdaar.contracts import tunables
from haqdaar.data import log_text, scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.engine import talk
from haqdaar.prompts import talk as prompt

GAP_S = 31.0            # between two calls to the same model
REPORT = Path("data_cache") / "reports" / "talk_questions.json"

# (what the caller says, language, the scheme the reply should be about)
QUESTIONS: list[tuple[str, str, str]] = [
    ("मुझे खेती के लिए कोई योजना चाहिए", "hi", "pm-kisan"),
    ("किसानों को हर साल पैसा मिलता है वो योजना", "hi", "pm-kisan"),
    ("PM Kisan ke bare mein batao", "hi", "pm-kisan"),
    ("मेरी फसल खराब हो गई, बीमा मिलेगा क्या", "hi", "pmfby"),
    ("I want insurance for my crops", "en", "pmfby"),
    ("किसान क्रेडिट कार्ड कैसे बनता है", "hi", "kcc"),
    ("I am a farmer and I need a loan for seeds", "en", "kcc"),
    ("ट्रैक्टर खरीदने पर सब्सिडी", "hi", "smam"),
    ("subsidy to buy farm machines", "en", "smam"),
    ("मेरे पति नहीं रहे, विधवा पेंशन चाहिए", "hi", "ignwps"),
    ("pension for a widow", "en", "ignwps"),
    ("मैं विकलांग हूँ, कोई पेंशन है क्या", "hi", "igndps"),
    ("pension for a disabled person", "en", "igndps"),
    ("घर के कमाने वाले की मौत हो गई, कोई मदद मिलेगी", "hi", "nfbs"),
    ("the earning member of our family died", "en", "nfbs"),
    ("गाँव में पक्का घर बनाने के लिए मदद चाहिए", "hi", "pmay-g"),
    ("I need help to build a house in my village", "en", "pmay-g"),
    ("गाँव में काम चाहिए, सौ दिन का रोजगार", "hi", "mgnrega"),
    ("मनरेगा जॉब कार्ड", "hi", "mgnrega"),
    ("बुढ़ापे के लिए पेंशन में पैसा जमा करना है", "hi", "apy"),
    ("Atal Pension Yojana", "en", "apy"),
    ("मैं ठेला लगाता हूँ, लोन चाहिए", "hi", "pm-svanidhi"),
    ("loan for a street vendor", "en", "pm-svanidhi"),
    ("मुद्रा लोन चाहिए दुकान के लिए", "hi", "pmmy"),
    ("I want to start a small business and need a loan", "en", "pmmy"),
    ("नया उद्योग लगाने के लिए सब्सिडी", "hi", "pmegp"),
    ("अस्पताल में डिलीवरी पर पैसा मिलता है क्या", "hi", "jsy1"),
    ("money for a pregnant woman for hospital delivery", "en", "jsy1"),
    ("अप्रेंटिस ट्रेनिंग में स्टाइपेंड", "hi", "naps"),
    ("महिला स्वयं सहायता समूह", "hi", "day-nrlm"),
    # one thing asked about a named scheme
    ("पीएम किसान में कितना पैसा मिलता है", "hi", "pm-kisan"),
    ("किसान क्रेडिट कार्ड के लिए कौन से कागज़ चाहिए", "hi", "kcc"),
    ("how do I apply for PM SVANidhi", "en", "pm-svanidhi"),
    ("मनरेगा में कितने दिन काम मिलता है", "hi", "mgnrega"),
    ("who can join the Atal Pension Yojana", "en", "apy"),
    ("विधवा पेंशन में कितने रुपये मिलते हैं", "hi", "ignwps"),
    ("what papers are needed for a Mudra loan", "en", "pmmy"),
    ("फसल बीमा के लिए आवेदन कैसे करें", "hi", "pmfby"),
    ("how much money does PMAY Gramin give", "en", "pmay-g"),
    ("जननी सुरक्षा योजना में कितना पैसा मिलता है", "hi", "jsy1"),
]

# The caller's words of the two real calls of 4 Oct, as speech-to-text gave them.
REPLAYS: dict[str, list[str]] = {
    "4 Oct 22:38 (CA247a...dcab49)": [
        "जागृत के बिना प्रॉब्लम होगी। अब फैमिली में कई सारा क्रेडिट्स अवेलेबल हैं।",
        "ठीक है, दस को भी दिक्कत थी, वो उठ गई। अरे, एक मिनट में तू भी खाते में बना के दे दो।",
        "एम 47 है।",
    ],
    "4 Oct 22:41 (CA3685...b38c3e)": ["हम्म, ठीक है।", "नहीं, कहीं से नहीं।", "हाँ बोलिए।"],
    # 5 Oct 11:12: the reply said a told sentence again, and offered parts it had just told.
    "5 Oct 11:12 (CA7863...c18fba) farmer": [
        "मेरे को फार्मर स्कीम्स के बारे में जानना है।", "पहले वाले के बारे में।", "नहीं।",
        "मैं इस स्कीम के बारे में और जानना चाहता हूँ।", "इस स्कीम के बेनिफिट्स क्या-क्या हैं?",
    ],
    "made up: vendor": ["मुझे ठेले के लिए लोन चाहिए।", "हाँ।", "कौन से कागज़ लगेंगे?", "और बताइए।"],
    "made up: jump": ["पेंशन की कोई योजना है क्या?", "दूसरी वाली।", "कितना पैसा मिलता है?",
                      "अच्छा, पीएम किसान में कितना मिलता है?", "ठीक है, धन्यवाद।"],
}


class Audio:
    """No phone: what the agent would say is only kept."""

    def __init__(self) -> None:
        self.answers: list[str] = []
        self.clips: list[tuple[str, ...]] = []

    def say(self, tokens: Any, *a: Any, **k: Any) -> None:
        self.clips.append(tuple(tokens))

    def say_text(self, text: str, *a: Any, **k: Any) -> bool:
        self.answers.append(text)
        return True


class Client:
    """The real client, but "too many requests" waits and tries the same model again."""

    def __init__(self, real: Any) -> None:
        self._real = real
        self.calls = 0
        self.waits = 0

    def call(self, messages: Any, task: str = "", timeout: Any = None, model: Any = None) -> Any:
        resp = None
        for _ in range(3):
            self.calls += 1
            resp = self._real.call(messages, task=task, timeout=timeout, model=model)
            if not getattr(resp, "is_429", False):
                return resp
            self.waits += 1
            print(f"      (too many requests for {model}: waiting 25 s)", flush=True)
            time.sleep(25)
        return resp


class _Model:
    def __init__(self, client: Any) -> None:
        self.client = client
        self.keypad_only = False


def _talk(corpus: Any, client: Any, lang: str, logs: str, name: str) -> tuple[Any, Audio, Any]:
    audio = Audio()
    log = Log.open(call_id=name, snapshot_id=corpus.snapshot_id, logs_dir=logs)
    return talk._Talk(audio, _Model(client), corpus, log, lang, None), audio, log


def _rows(log: Any) -> list[dict[str, Any]]:
    return log_text.read_rows(log.path)


def questions(corpus: Any, real_client: Any, models: list[str], limit: int) -> dict[str, Any]:
    logs = tempfile.mkdtemp(prefix="talk_questions_")
    out: dict[str, Any] = {m: [] for m in models}
    saved = tunables.TALK_MODELS
    last = {m: 0.0 for m in models}
    try:
        for n, (words, lang, want) in enumerate(QUESTIONS[:limit or None]):
            for m in models:
                wait = last[m] + GAP_S - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                tunables.TALK_MODELS = m
                client = Client(real_client)
                t, audio, log = _talk(corpus, client, lang, logs, f"q{n}_{models.index(m)}")
                t0 = time.monotonic()
                action = t._turn(words)
                took = time.monotonic() - t0
                last[m] = time.monotonic() + (GAP_S if client.calls > 1 else 0.0)
                rows = _rows(log)
                act = next((r for r in rows if r.get("ev") == "act"), {})
                said = " ".join(audio.answers)
                not_sure = said in (prompt.NOT_SURE.get(lang, ""), )
                row = dict(q=words, lang=lang, want=want, action=action, scheme=act.get("scheme", ""),
                           right=act.get("scheme") == want, blocked=[r["rule"] for r in rows if r.get("ev") == "blocked"],
                           not_sure=not_sure, model_ms=act.get("model_ms"), calls=client.calls, waits=client.waits,
                           took_s=round(took, 2), say=said)
                out[m].append(row)
                print(f"{n + 1:2}/{len(QUESTIONS[:limit or None])} {m:22} {'ok ' if row['right'] else 'NO '} "
                      f"{action:11} {act.get('scheme', ''):12} {row['model_ms']} ms  {','.join(row['blocked']) or '-'}"
                      f"{'  NOT SURE' if not_sure else ''}", flush=True)
    finally:
        tunables.TALK_MODELS = saved
    return out


def summary(out: dict[str, Any]) -> list[str]:
    lines = []
    for m, rows in out.items():
        if not rows:
            continue
        times = sorted(r["model_ms"] for r in rows if isinstance(r["model_ms"], int) and not r["waits"])
        clean = [r for r in rows if not r["blocked"]]
        mid = times[len(times) // 2] if times else 0
        p90 = times[int(len(times) * 0.9) - 1] if times else 0
        lines.append(f"{m:22} right scheme {sum(r['right'] for r in rows)}/{len(rows)}   "
                     f"first reply passed the truth checks {len(clean)}/{len(rows)}   "
                     f"'not sure' said {sum(r['not_sure'] for r in rows)}   "
                     f"model time: middle {mid} ms, 9 in 10 under {p90} ms")
    return lines


def replay(corpus: Any, real_client: Any, only: str = "") -> list[dict[str, Any]]:
    logs = tempfile.mkdtemp(prefix="talk_replay_")
    found = []
    for n, (name, turns) in enumerate(REPLAYS.items()):
        if only and only not in name:
            continue
        t, audio, log = _talk(corpus, Client(real_client), "hi", logs, f"replay{n}")
        print(f"\n== {name}")
        for words in turns:
            before = len(audio.answers)
            action = t._turn(words)
            said = " ".join(audio.answers[before:])
            print(f"CALLER: {words}\n   -> {action}" + (f': "{said}"' if said else " (nothing said)"), flush=True)
            print(f"      in talk: {t.focus or '-'}  told: {', '.join(sorted(t.told.get(t.focus, ()))) or '-'}", flush=True)
            found.append(dict(call=name, words=words, action=action, say=said))
            time.sleep(GAP_S / 2)
        hello = prompt.HELLO["hi"]
        bad = [a for a in audio.answers if a in hello or "माफ़" in a or "क्षमा" in a or "sorry" in a.lower()]
        print("   rules: " + ("BROKEN: " + "; ".join(bad) if bad else "no 'sorry', no restart"))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Real questions through the real model (no phone, no voice).")
    ap.add_argument("--questions", action="store_true")
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="only the first N questions")
    ap.add_argument("--models", default=tunables.TALK_MODELS)
    ap.add_argument("--only", default="", help="with --replay: only the calls with this in their name")
    args = ap.parse_args()
    from haqdaar.model.router import Model

    corpus = Corpus.load("CURRENT")
    scheme_index.get(corpus.snapshot_id)
    real = Model(corpus=corpus).client
    report: dict[str, Any] = {}
    if args.replay:
        report["replay"] = replay(corpus, real, args.only)
    if args.questions:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
        out = questions(corpus, real, models, args.limit)
        report["questions"] = out
        report["summary"] = summary(out)
        print("\n" + "\n".join(report["summary"]))
    if report:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
        old.update(report)
        REPORT.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nsaved: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
