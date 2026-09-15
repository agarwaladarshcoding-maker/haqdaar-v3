"""Demo voice: turns the engine's prompt ids into real words and plays them.

Demo glue for 15 Sep. The real audio pipeline (Sarvam render, Steps 9-11) is not
built, so this speaks with the Mac's offline voice. Nothing here needs network.

- Words: `Words.text(token, lang)` — fixed lines in en/hi, scheme text from the
  real snapshot chunks, keypad menus built from corpus.values(box).
- Terminal: `TextAudio` prints the words (and speaks them with --speak).
- Phone: `PhoneAudio` renders words to 8 kHz mu-law and hands them to a send
  callback; keys come in through `push_digit`. One caller at a time.
"""

from __future__ import annotations

import audioop
import hashlib
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from haqdaar.contracts.types import Digit, Hangup, Noise, Silence

VOICE = {"en": "Tara", "hi": "Lekha", "mr": "Lekha"}
CACHE_DIR = Path(tempfile.gettempdir()) / "haqdaar_demo_voice"
SECTION_MAX_CHARS = 320  # read-back sections are long legal text; say the first part
INPUT_WAIT_S = 12.0  # silence after playback ends before a Silence rung

LINES: dict[str, dict[str, str]] = {
    "greeting_trilingual": {
        "en": "Namaste. Welcome to Haqdaar, your helpline for government schemes. "
              "For Hindi, press 1. For Marathi, press 2. For English, press 3.",
        "hi": "नमस्ते। हक़दार में आपका स्वागत है। हिंदी के लिए 1 दबाएँ। मराठी के लिए 2 दबाएँ। "
              "For English, press 3.",
    },
    "consent_notice": {
        "en": "This call is recorded to improve the service. We never ask for your Aadhaar or bank details.",
        "hi": "यह कॉल सेवा सुधारने के लिए रिकॉर्ड की जाती है। हम कभी आपका आधार या बैंक विवरण नहीं माँगते।",
    },
    "keypad_only_mode": {
        "en": "Please answer using your phone keypad.",
        "hi": "कृपया अपने फ़ोन के बटन दबाकर जवाब दें।",
    },
    "opener_prompt": {"en": "What do you need help with?", "hi": "आपको किस चीज़ में मदद चाहिए?"},
    "keypad_occupation": {"en": "What work do you do?", "hi": "आप क्या काम करते हैं?"},
    "keypad_age": {"en": "What is your age?", "hi": "आपकी उम्र क्या है?"},
    "keypad_gender": {"en": "Are you a man or a woman?", "hi": "आप पुरुष हैं या महिला?"},
    "keypad_social_category": {"en": "What is your social category?", "hi": "आपकी सामाजिक श्रेणी क्या है?"},
    "keypad_income_band": {"en": "What is your family's yearly income?", "hi": "आपके परिवार की सालाना आमदनी कितनी है?"},
    "keypad_unknown_suffix": {"en": "If you don't know, press 0.", "hi": "अगर पता नहीं, तो 0 दबाएँ।"},
    "unclear_prompt": {"en": "Sorry, I did not get that.", "hi": "माफ़ कीजिए, मैं समझ नहीं पाई।"},
    "silence_presence": {"en": "Are you still there? Please press a key.", "hi": "क्या आप लाइन पर हैं? कृपया कोई बटन दबाएँ।"},
    "results_exact_preamble": {"en": "Good news. These schemes fit you.", "hi": "अच्छी ख़बर। ये योजनाएँ आपके लिए हैं।"},
    "results_overflow": {"en": "There are more schemes as well.", "hi": "और भी योजनाएँ हैं।"},
    "terminal_widened_preamble": {"en": "I could not find an exact match, but these are close.", "hi": "बिल्कुल सही योजना नहीं मिली, पर ये पास की हैं।"},
    "results_widened_lead": {"en": "These may help you.", "hi": "ये आपकी मदद कर सकती हैं।"},
    "section_menu": {
        "en": "For benefits press 1. How to apply, press 2. Documents, press 3. Who can apply, press 4. Next scheme, press 9. To finish, press 0.",
        "hi": "फ़ायदे के लिए 1 दबाएँ। आवेदन कैसे करें, 2। दस्तावेज़, 3। कौन आवेदन कर सकता है, 4। अगली योजना, 9। ख़त्म करने के लिए 0।",
    },
    "section_source_frame": {"en": "According to the official myScheme website:", "hi": "सरकारी माईस्कीम वेबसाइट के अनुसार:"},
    "next_scheme_intro": {"en": "Next scheme.", "hi": "अगली योजना।"},
    "no_more_schemes": {"en": "That was the last scheme.", "hi": "यह आख़िरी योजना थी।"},
    "anything_else": {
        "en": "Do you need help with anything else? Press 1 for yes, 2 for no.",
        "hi": "क्या आपको और किसी चीज़ में मदद चाहिए? हाँ के लिए 1, नहीं के लिए 2।",
    },
    "closing_farewell": {"en": "Thank you for calling Haqdaar. Goodbye.", "hi": "हक़दार को कॉल करने के लिए धन्यवाद। नमस्ते।"},
    "state_unknown_disclaimer": {"en": "These are national schemes.", "hi": "ये राष्ट्रीय योजनाएँ हैं।"},
}

VALUE_WORDS: dict[str, dict[str, str]] = {
    "agriculture": {"en": "farming", "hi": "खेती"},
    "business": {"en": "a business loan", "hi": "व्यापार का लोन"},
    "health": {"en": "health and hospital care", "hi": "इलाज और अस्पताल"},
    "housing": {"en": "a house", "hi": "घर"},
    "livelihood": {"en": "jobs and livelihood", "hi": "रोज़गार"},
    "pension": {"en": "pension", "hi": "पेंशन"},
    "skills": {"en": "training and apprenticeship", "hi": "ट्रेनिंग"},
    "farmer": {"en": "farmer", "hi": "किसान"},
    "street_vendor": {"en": "street vendor", "hi": "रेहड़ी पटरी वाले"},
    "<14": {"en": "under 14", "hi": "14 से कम"},
    "14-17": {"en": "14 to 17", "hi": "14 से 17"},
    "18-34": {"en": "18 to 34", "hi": "18 से 34"},
    "35-39": {"en": "35 to 39", "hi": "35 से 39"},
    ">=40": {"en": "40 or more", "hi": "40 या ज़्यादा"},
}

SECTION_KEY = {"benefit_text", "how_to_apply", "documents", "who_can_apply"}


class Words:
    def __init__(self, corpus: Any, schemes: list[dict[str, Any]]):
        self.corpus = corpus
        self.by_id = {s["scheme_id"]: s for s in schemes}

    def _line(self, line_id: str, lang: str) -> str:
        entry = LINES.get(line_id)
        if not entry:
            return ""
        return entry.get(lang) or entry.get("hi" if lang == "mr" else "en") or entry["en"]

    def menu(self, box: str, lang: str) -> str:
        vals = self.corpus.values(box) or []
        parts = []
        for i, v in enumerate(vals, start=1):
            w = VALUE_WORDS.get(str(v), {}).get("en" if lang == "en" else "hi", str(v).replace("_", " "))
            parts.append(f"{w}, press {i}." if lang == "en" else f"{w} के लिए {i} दबाएँ।")
        return " ".join(parts)

    def text(self, token: str, lang: str) -> str:
        if token.startswith(("name:", "end:")):
            return ""
        if token.startswith("scheme:"):
            _, sid, section = token.split(":", 2)
            row = self.by_id.get(sid)
            if not row:
                return ""
            chunk = (row.get("chunks") or {}).get(lang) or row["chunks"]["en"]
            words = str(chunk.get(section) or "").replace("\n", ". ")
            if section in SECTION_KEY and len(words) > SECTION_MAX_CHARS:
                words = words[:SECTION_MAX_CHARS].rsplit(" ", 1)[0] + "."
            return words
        if token.startswith("keypad_") and token != "keypad_unknown_suffix" and token != "keypad_only_mode":
            box = token[len("keypad_"):]
            return f"{self._line(token, lang)} {self.menu(box, lang)}"
        if token == "opener_prompt":
            return f"{self._line(token, lang)} {self.menu('category', lang)}"
        return self._line(token, lang)


def clean(text: str) -> str:
    """`say` froze for 60 s on raw myScheme text ("Rs.50,000/-..", slashes). Make it plain."""
    import re
    t = text.replace("/-", "").replace("/", " or ").replace("\u2011", "-")
    t = re.sub(r"[\'\"‘’“”]", "", t)
    t = re.sub(r"\.(\s*\.)+", ".", t)
    return re.sub(r"\s+", " ", t).strip()


def render_ulaw(text: str, lang: str) -> bytes:
    """Offline TTS: macOS `say` -> 8 kHz 16-bit PCM -> mu-law. Cached on disk."""
    text = clean(text)
    voice = VOICE.get(lang, "Tara")
    key = hashlib.sha256(f"{voice}|{text}".encode()).hexdigest()[:24]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"{key}.ulaw"
    if out.exists():
        return out.read_bytes()
    tag = f"{key}.{threading.get_ident()}"
    wav = CACHE_DIR / f"{tag}.wav"
    for attempt in range(2):
        try:
            subprocess.run(["say", "-v", voice, "-o", str(wav), "--data-format=LEI16@8000", text],
                           check=True, timeout=20)
            break
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            if attempt == 1:
                raise
    import wave
    with wave.open(str(wav), "rb") as w:
        pcm = w.readframes(w.getnframes())
    data = audioop.lin2ulaw(pcm, 2)
    tmp = CACHE_DIR / f"{tag}.part"
    tmp.write_bytes(data)
    tmp.replace(out)  # atomic: a reader never sees half a clip
    wav.unlink(missing_ok=True)
    return data


def all_texts(words: Words, langs: tuple[str, ...] = ("en", "hi")) -> list[tuple[str, str]]:
    """Every sentence a demo call can say, for pre-rendering before the call."""
    tokens = list(LINES) + ["keypad_occupation", "keypad_age"]
    for sid in words.by_id:
        tokens += [f"scheme:{sid}:{s}" for s in ("name", "summary", "benefit_text", "how_to_apply", "documents", "who_can_apply")]
    out = []
    for lang in langs:
        for t in tokens:
            txt = words.text(t, lang)
            if txt:
                out.append((txt, lang))
    return out


class _BaseAudio:
    def __init__(self, words: Words):
        self.words = words
        self.language = "hi"
        self._last: tuple[str, ...] = ()
        self._silence = 0

    def _emit(self, text: str, token: str) -> None:
        raise NotImplementedError

    def say(self, sequence: tuple[str, ...]) -> None:
        self._last = sequence
        # The engine puts section_menu after every listed scheme; say it once, at the end.
        if sequence.count("section_menu") > 1:
            sequence = tuple(t for t in sequence if t != "section_menu") + ("section_menu",)
        for token in sequence:
            txt = self.words.text(token, self.language)
            if txt:
                self._emit(txt, token)

    def repeat(self) -> None:
        self.say(self._last)

    def on_mark(self, mark: str) -> float:
        return 0.0


class TextAudio(_BaseAudio):
    """Terminal demo: readable words, keys typed at the prompt."""

    def __init__(self, words: Words, speak: bool = False, canned: Optional[list[str]] = None):
        super().__init__(words)
        self.speak = speak
        self.canned = list(canned or [])

    def _emit(self, text: str, token: str) -> None:
        print(f"  HAQDAAR: {text}")
        if self.speak:
            subprocess.run(["say", "-v", VOICE.get(self.language, "Tara"), clean(text)])

    def _read(self) -> str:
        if self.canned:
            v = self.canned.pop(0)
            print(f"  CALLER presses: {v}")
            return v
        try:
            return input("  CALLER presses (digit, s=silence, h=hang up): ").strip().lower()
        except EOFError:
            return "h"

    def select_language(self):
        self.language = "en"
        self._emit(self.words.text("greeting_trilingual", "en"), "greeting_trilingual")
        v = self._read()
        self.language = {"1": "hi", "2": "mr", "3": "en"}.get(v, "hi")
        return self.language, "keypad" if v in ("1", "2", "3") else "default"

    def next_input(self, profile: str = "normal"):
        v = self._read()
        if v in ("s", ""):
            self._silence += 1
            return Silence(n=self._silence)
        self._silence = 0
        if v == "h":
            return Hangup()
        if v == "n":
            return Noise()
        return Digit(digit=v[:1] if v[:1] in "0123456789*#" else "1")

    def hangup(self) -> None:
        print("  [call ends]")


class PhoneAudio(_BaseAudio):
    """Phone demo. Engine thread calls say/next_input; the socket thread pushes keys."""

    def __init__(self, words: Words, send: Callable[[bytes], None], clear: Callable[[], None],
                 close: Callable[[], None], log: Callable[[str], None] = print):
        super().__init__(words)
        self.send, self.clear, self.close, self.log = send, clear, close, log
        self.keys: "queue.Queue[str]" = queue.Queue()
        self.play_until = 0.0
        self.hung_up = threading.Event()

    def _emit(self, text: str, token: str) -> None:
        if self.hung_up.is_set():
            return
        # A key pressed during speech barges in: stop queuing more words.
        if not self.keys.empty():
            return
        try:
            data = render_ulaw(text, self.language)
        except Exception as e:  # never let one bad line kill the call
            self.log(f"!! voice failed on {token}: {e!r}")
            return
        self.log(f"SAY [{self.language}] {token}: {text[:90]}")
        self.send(data)
        now = time.monotonic()
        self.play_until = max(now, self.play_until) + len(data) / 8000.0

    def push_digit(self, d: str) -> None:
        if time.monotonic() < self.play_until:
            self.clear()
            self.play_until = time.monotonic()
        self.keys.put(d)

    def push_hangup(self) -> None:
        self.hung_up.set()
        self.keys.put("h")

    def _wait_key(self) -> Optional[str]:
        while True:
            remaining = self.play_until - time.monotonic()
            try:
                return self.keys.get(timeout=max(remaining, 0) + INPUT_WAIT_S)
            except queue.Empty:
                if self.play_until - time.monotonic() > 0:
                    continue
                return None

    def select_language(self):
        self.language = "en"
        self.say(("greeting_trilingual",))
        k = self._wait_key()
        self.language = {"1": "hi", "2": "mr", "3": "en"}.get(k or "", "hi")
        self.log(f"KEY {k} -> language {self.language}")
        return self.language, "keypad" if k in ("1", "2", "3") else "default"

    def next_input(self, profile: str = "normal"):
        k = self._wait_key()
        if k is None:
            self._silence += 1
            self.log(f"SILENCE rung {self._silence}")
            return Silence(n=self._silence)
        self._silence = 0
        self.log(f"KEY {k} ({profile})")
        if k == "h":
            return Hangup()
        return Digit(digit=k)

    def hangup(self) -> None:
        # Let the farewell finish playing, then end the call.
        wait = self.play_until - time.monotonic()
        if wait > 0 and not self.hung_up.is_set():
            time.sleep(min(wait + 0.5, 15))
        self.close()
