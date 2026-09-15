"""haqdaar/voice_demo.py — fixed (rigged) voice demo call, Hindi or English (15 Sep).

The caller SPEAKS (or presses keys). Sarvam voice speaks every line; all lines are
rendered before the call. Sarvam speech-to-text hears the caller; if it is slow or
unsure, the call follows the script's default answer, so the demo never gets stuck.
Facts are from the 3 real farmer schemes in data_cache (myscheme.gov.in).

    make run-demo      (tunnel + this server + rings CALL_ME_NUMBER)
Step 1's server.py and the keypad demo_server.py are untouched. One caller at a time.
"""
from __future__ import annotations

import asyncio
import audioop
import base64
import hashlib
import io
import json
import os
import re
import threading
import time
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect

from haqdaar.audio.telephony import (
    DtmfEvent, MarkEvent, MediaEvent, StartEvent, StopEvent,
    build_clear, build_mark, build_media, build_stream_twiml, parse_event,
)
from haqdaar.demo_voice import render_ulaw as mac_render

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SPEAKER = "priya"
TTS_LANG = {"hi": "hi-IN", "en": "en-IN"}
CACHE = Path(__file__).resolve().parent / "voice_demo_clips"  # committed: works with no Sarvam credits
STT_WAIT = 4.5          # s; slower than this -> use the script's default answer
NO_SPEECH_WAIT = 7.0    # s of silence before "sorry, say again"
CHUNK = 8000            # 1 s of mu-law per media message

# ---- the script -------------------------------------------------------------
GREET = ("नमस्ते! हक़दार में आपका स्वागत है। हिंदी में बात करने के लिए हिंदी बोलिए, या एक दबाइए। "
         "For English, say English, or press two.")

LINES: dict[str, dict[str, str]] = {
    "hi": {
        "need": "मैं सरकारी योजनाओं में आपकी मदद करूँगी। बताइए, आपको किस चीज़ में मदद चाहिए? जैसे खेती, इलाज, पेंशन या रोज़गार।",
        "farm_ack": "ठीक है, खेती से जुड़ी योजनाएँ। सही योजना ढूँढने के लिए मैं आपसे दो छोटे सवाल पूछूँगी।",
        "q_land": "पहला सवाल। क्या खेती की ज़मीन आपके अपने नाम पर है? हाँ या ना बोलिए।",
        "q_loan": "दूसरा सवाल। क्या आपको खेती के लिए लोन की ज़रूरत है? हाँ या ना।",
        "res_yy": "आपके लिए तीन योजनाएँ मिली हैं। पहली, प्रधानमंत्री किसान सम्मान निधि, इसमें हर साल छह हज़ार रुपये मिलते हैं। दूसरी, किसान क्रेडिट कार्ड, खेती के लिए लोन। तीसरी, प्रधानमंत्री फसल बीमा योजना, कम प्रीमियम पर फसल का बीमा।",
        "res_yn": "आपके लिए दो योजनाएँ मिली हैं। पहली, प्रधानमंत्री किसान सम्मान निधि, इसमें हर साल छह हज़ार रुपये मिलते हैं। दूसरी, प्रधानमंत्री फसल बीमा योजना, कम प्रीमियम पर फसल का बीमा।",
        "res_ny": "ज़मीन आपके नाम पर नहीं है, इसलिए किसान सम्मान निधि नहीं मिलेगी। लेकिन दो योजनाएँ आपके लिए हैं, जो बटाईदार और किराए पर खेती करने वाले किसान भी ले सकते हैं। पहली, किसान क्रेडिट कार्ड, खेती के लिए लोन। दूसरी, प्रधानमंत्री फसल बीमा योजना।",
        "res_nn": "ज़मीन आपके नाम पर नहीं है, इसलिए किसान सम्मान निधि नहीं मिलेगी। लेकिन प्रधानमंत्री फसल बीमा योजना आपके लिए है। बटाईदार और किराए पर खेती करने वाले किसान भी इसे ले सकते हैं।",
        "q_which": "इनमें से किस योजना के बारे में और जानना चाहेंगे? योजना का नाम बोलिए।",
        "detail_pmkisan": "प्रधानमंत्री किसान सम्मान निधि। सरकारी वेबसाइट के अनुसार, हर पात्र किसान परिवार को साल में छह हज़ार रुपये मिलते हैं, दो-दो हज़ार की तीन किस्तों में, हर चार महीने पर। इसके लिए आधार कार्ड, ज़मीन के कागज़ और बैंक खाता चाहिए।",
        "detail_kcc": "किसान क्रेडिट कार्ड। सरकारी वेबसाइट के अनुसार, इससे फसल उगाने, कटाई के बाद के खर्च और खेती के सामान की मरम्मत के लिए लोन मिलता है। बटाईदार और किराए के किसान भी इसे ले सकते हैं। इसके लिए आवेदन फ़ॉर्म, दो फ़ोटो, आधार या वोटर कार्ड, और ज़मीन के कागज़ चाहिए।",
        "detail_pmfby": "प्रधानमंत्री फसल बीमा योजना। सरकारी वेबसाइट के अनुसार, खरीफ़ फसल पर किसान को सिर्फ़ दो प्रतिशत प्रीमियम देना होता है, और रबी फसल पर डेढ़ प्रतिशत। बाकी प्रीमियम सरकार देती है। सूखा, बाढ़, कीड़े और बीमारी से हुए नुकसान का बीमा होता है।",
        "q_apply": "क्या मैं आवेदन करने का तरीका बताऊँ? हाँ या ना।",
        "apply_pmkisan": "आवेदन का तरीका। पीएम किसान पोर्टल पर जाइए, या नज़दीकी जन सेवा केंद्र पर। न्यू फार्मर रजिस्ट्रेशन चुनिए, आधार नंबर और मोबाइल नंबर डालिए, ओटीपी डालिए, जानकारी भरिए, कागज़ अपलोड कीजिए और सबमिट कीजिए।",
        "apply_kcc": "आवेदन का तरीका। जिस बैंक से कार्ड लेना है, उसकी वेबसाइट पर या बैंक शाखा में जाइए। किसान क्रेडिट कार्ड चुनिए, फ़ॉर्म भरिए और सबमिट कीजिए। अगर आप पात्र हैं, तो बैंक तीन-चार कामकाजी दिनों में आपसे संपर्क करेगा।",
        "apply_pmfby": "आवेदन का तरीका। प्रधानमंत्री फसल बीमा योजना की वेबसाइट पर, या नज़दीकी जन सेवा केंद्र पर जाइए। फार्मर कॉर्नर में रजिस्ट्रेशन फ़ॉर्म भरिए। ज़मीन के कागज़, बैंक पासबुक और बोई गई फसल की जानकारी दीजिए। बुवाई शुरू होने के दो हफ़्ते के अंदर आवेदन करना होता है।",
        "q_more": "क्या आप किसी और योजना के बारे में जानना चाहेंगे? हाँ या ना।",
        "sorry": "माफ़ कीजिए, मैं सुन नहीं पाई। एक बार फिर बोलिए।",
        "bye": "हक़दार को कॉल करने के लिए धन्यवाद। आपका दिन शुभ हो। नमस्ते!",
    },
    "en": {
        "need": "I will help you find government schemes. Tell me, what do you need help with? For example farming, health, pension, or jobs.",
        "farm_ack": "Okay, schemes for farmers. To find the right ones, I will ask you two short questions.",
        "q_land": "First question. Is the farm land in your own name? Please say yes or no.",
        "q_loan": "Second question. Do you need a loan for farming? Yes or no.",
        "res_yy": "I found three schemes for you. One, PM Kisan Samman Nidhi, which gives six thousand rupees every year. Two, the Kisan Credit Card, a loan for farming. Three, Pradhan Mantri Fasal Bima Yojana, crop insurance at a low premium.",
        "res_yn": "I found two schemes for you. One, PM Kisan Samman Nidhi, which gives six thousand rupees every year. Two, Pradhan Mantri Fasal Bima Yojana, crop insurance at a low premium.",
        "res_ny": "Since the land is not in your name, PM Kisan does not apply. But two schemes are open to tenant farmers and sharecroppers too. One, the Kisan Credit Card, a loan for farming. Two, Pradhan Mantri Fasal Bima Yojana, crop insurance.",
        "res_nn": "Since the land is not in your name, PM Kisan does not apply. But Pradhan Mantri Fasal Bima Yojana, crop insurance, is open to tenant farmers and sharecroppers too.",
        "q_which": "Which scheme would you like to know more about? Please say its name.",
        "detail_pmkisan": "PM Kisan Samman Nidhi. According to the official website, every eligible farmer family gets six thousand rupees a year, in three equal installments of two thousand rupees, every four months. You need an Aadhaar card, land papers, and a savings bank account.",
        "detail_kcc": "Kisan Credit Card. According to the official website, it gives a loan for growing crops, post-harvest expenses, and repairs of farm assets. Tenant farmers and sharecroppers can also apply. You need the application form, two photos, an ID proof like Aadhaar or voter card, and land papers.",
        "detail_pmfby": "Pradhan Mantri Fasal Bima Yojana. According to the official website, the farmer pays only two percent premium for Kharif crops, and one and a half percent for Rabi crops. The government pays the rest. It covers losses from drought, floods, pests, and diseases.",
        "q_apply": "Shall I tell you how to apply? Yes or no.",
        "apply_pmkisan": "How to apply. Visit the PM Kisan portal, or your nearest Common Service Centre. Choose New Farmer Registration, enter your Aadhaar and mobile number, enter the OTP, fill in the details, upload the documents, and submit.",
        "apply_kcc": "How to apply. Visit the website or branch of the bank you want the card from. Choose Kisan Credit Card, fill in the form, and submit. If you are eligible, the bank will contact you within three to four working days.",
        "apply_pmfby": "How to apply. Visit the Pradhan Mantri Fasal Bima Yojana website, or your nearest Common Service Centre. Fill in the registration form under Farmer Corner, with your land papers, bank passbook, and the crop you sowed. Apply within two weeks of the start of sowing.",
        "q_more": "Would you like to hear about another scheme? Yes or no.",
        "sorry": "Sorry, I could not hear you. Please say that again.",
        "bye": "Thank you for calling Haqdaar. Have a good day. Goodbye!",
    },
}

RESULTS = {  # (land in own name, needs loan) -> line, schemes in the order spoken
    (True, True): ("res_yy", ["pmkisan", "kcc", "pmfby"]),
    (True, False): ("res_yn", ["pmkisan", "pmfby"]),
    (False, True): ("res_ny", ["kcc", "pmfby"]),
    (False, False): ("res_nn", ["pmfby"]),
}

YES = {"हाँ", "हां", "हा", "जी", "हाँजी", "हम्म", "बिल्कुल", "ज़रूर", "जरूर", "ठीक", "yes", "yeah", "yep", "haan", "han", "ha", "sure", "okay", "ok"}
NO = {"नहीं", "नही", "ना", "न", "मत", "no", "nahi", "nahin", "nope", "not"}
SCHEME_WORDS = [  # checked in this order ("kisan" is in two names)
    ("kcc", ("क्रेडिट", "कार्ड", "लोन", "credit", "card", "loan")),
    ("pmfby", ("बीमा", "फसल", "फ़सल", "bima", "insurance", "crop", "fasal")),
    ("pmkisan", ("सम्मान", "निधि", "पीएम", "samman", "nidhi", "pm kisan", "किसान", "kisan")),
]
ORDINALS = [("पहल", "first"), ("दूसर", "second"), ("तीसर", "third")]


def say(line: str) -> None:
    print(f"{datetime.now():%H:%M:%S.%f}"[:-3] + f"  {line}", flush=True)


# ---- voice out: Sarvam, prerendered -------------------------------------------
def _sarvam_key() -> str:
    return os.environ.get("SARVAM_API_KEY", "")


def sarvam_tts(text: str, lang: str) -> bytes:
    """Sarvam bulbul:v3 -> 8 kHz mu-law. Cached on disk."""
    key = hashlib.sha256(f"v3|{SPEAKER}|{lang}|{text}".encode()).hexdigest()[:24]
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{key}.ulaw"
    if out.exists():
        return out.read_bytes()
    body = json.dumps({"inputs": [text], "target_language_code": TTS_LANG[lang], "speaker": SPEAKER,
                       "model": "bulbul:v3", "speech_sample_rate": 8000}).encode()
    req = urllib.request.Request("https://api.sarvam.ai/text-to-speech", data=body, headers={
        "api-subscription-key": _sarvam_key(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        wav = base64.b64decode(json.loads(r.read())["audios"][0])
    with wave.open(io.BytesIO(wav)) as w:
        pcm, rate, width = w.readframes(w.getnframes()), w.getframerate(), w.getsampwidth()
    if width != 2:
        pcm = audioop.lin2lin(pcm, width, 2)
    if rate != 8000:
        pcm, _ = audioop.ratecv(pcm, 2, 1, rate, 8000, None)
    data = audioop.lin2ulaw(pcm, 2)
    tmp = CACHE / f"{key}.{threading.get_ident()}.part"
    tmp.write_bytes(data)
    tmp.replace(out)
    return data


AUDIO: dict[tuple[str, str], bytes] = {}
TEXT: dict[tuple[str, str], str] = {("hi", "greet"): GREET}
for _l, _lines in LINES.items():
    for _k, _t in _lines.items():
        TEXT[(_l, _k)] = _t
STATUS = {"ready": False, "lines": len(TEXT), "sarvam": 0, "mac_fallback": 0, "failed": 0}


def prerender() -> None:
    t0 = time.monotonic()

    def one(item: tuple[tuple[str, str], str]) -> None:
        (lang, name), text = item
        for attempt in range(2):
            try:
                AUDIO[(lang, name)] = sarvam_tts(text, lang)
                STATUS["sarvam"] += 1
                return
            except Exception as e:
                if attempt == 1:
                    say(f"!! sarvam failed for {lang}/{name}: {e!r}; using Mac voice")
        try:
            AUDIO[(lang, name)] = mac_render(text, lang)
            STATUS["mac_fallback"] += 1
        except Exception as e:
            STATUS["failed"] += 1
            say(f"!! no voice for {lang}/{name}: {e!r}")

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(one, TEXT.items()))
    try:  # find out now, not mid-call, whether Sarvam can still hear (0.3 s of quiet)
        speech_to_text(b"\x00\x00" * 2400, "hi")
    except Exception as e:
        say(f"!! no speech-to-text works: {e!r}. Keys still work.")
    say(f"hearing: {'Sarvam' if SARVAM_STT_OK[0] else 'Groq Whisper'}")
    STATUS["ready"] = True
    say(f"voice ready: {STATUS['lines']} lines, sarvam {STATUS['sarvam']}, "
        f"mac fallback {STATUS['mac_fallback']}, failed {STATUS['failed']}, {time.monotonic() - t0:.1f} s")


# ---- ears: energy end-pointing + Sarvam speech-to-text -------------------------
START_RMS, END_RMS = 700, 400
START_FRAMES, END_FRAMES = 3, 40        # 20 ms frames: 60 ms to start, 800 ms of quiet to end
MAX_UTTERANCE_FRAMES = 350              # 7 s


def _multipart(fields: dict[str, str], wav: bytes) -> tuple[bytes, str]:
    b = "----haqdaar" + hashlib.md5(wav[-64:]).hexdigest()
    head = "".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields.items())
    head += f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\nContent-Type: audio/wav\r\n\r\n'
    return head.encode() + wav + f"\r\n--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


SARVAM_STT_OK = [True]  # flips off after one failure (15 Sep: credits ran out) so Groq answers fast


def speech_to_text(pcm: bytes, lang: str) -> tuple[str, str]:
    """Sarvam saarika first; Groq Whisper if Sarvam fails. lang: "" (unknown), "hi" or "en"."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(pcm)
    wav = buf.getvalue()
    if SARVAM_STT_OK[0] and _sarvam_key():
        body, ctype = _multipart({"model": "saarika:v2.5", "language_code": TTS_LANG.get(lang, "unknown")}, wav)
        req = urllib.request.Request("https://api.sarvam.ai/speech-to-text", data=body, headers={
            "api-subscription-key": _sarvam_key(), "Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                j = json.loads(r.read())
            return j.get("transcript", ""), j.get("language_code", "")
        except Exception as e:
            SARVAM_STT_OK[0] = False
            say(f"!! sarvam speech-to-text failed ({e}); using Groq Whisper from now on")
    fields = {"model": "whisper-large-v3-turbo", "response_format": "verbose_json"}
    if lang:
        fields["language"] = lang
    body, ctype = _multipart(fields, wav)
    req = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", data=body, headers={
        "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}", "Content-Type": ctype,
        "User-Agent": "haqdaar/0.1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read())
    code = {"hindi": "hi-IN", "english": "en-IN"}.get(str(j.get("language", "")).lower(), j.get("language", ""))
    return j.get("text", "").strip(), code


class Hangup(Exception):
    pass


class Heard:
    def __init__(self, text: str = "", lang: str = "", digit: str = "", spoke: bool = False):
        self.text, self.lang, self.digit, self.spoke = text, lang, digit, spoke

    @property
    def low(self) -> str:
        return f" {self.text.lower()} "

    def nothing(self) -> bool:
        return not (self.digit or self.spoke)


def yes_no(h: Heard, default: bool = True) -> bool:
    if h.digit in ("1", "2"):
        return h.digit == "1"
    words = set(re.split(r"[\s।,.?!]+", h.text.lower()))
    if words & NO:
        return False
    if words & YES:
        return True
    return default


def pick_scheme(h: Heard, offered: list[str], default: str) -> str:
    if h.digit.isdigit() and 1 <= int(h.digit) <= len(offered):
        return offered[int(h.digit) - 1]
    t = h.low
    for scheme, words in SCHEME_WORDS:
        if scheme in offered and any(w in t for w in words):
            return scheme
    for i, words in enumerate(ORDINALS):
        if i < len(offered) and any(w in t for w in words):
            return offered[i]
    return default


# ---- one call ------------------------------------------------------------------
class Call:
    def __init__(self, ws: WebSocket, sid: str, q: asyncio.Queue):
        self.ws, self.sid, self.q = ws, sid, q
        self.lang = "hi"
        self.lang_known = False
        self.marks = 0

    async def _event(self, timeout: float):
        ev = await asyncio.wait_for(self.q.get(), timeout)
        if isinstance(ev, StopEvent) or ev is None:
            raise Hangup()
        return ev

    async def speak(self, name: str, lang: str | None = None) -> str:
        """Play one line; returns a digit if the caller pressed a key while it played."""
        lang = lang or self.lang
        data = AUDIO[(lang, name)]
        say(f"BOT     [{lang}/{name}] {TEXT[(lang, name)][:90]}")
        for i in range(0, len(data), CHUNK):
            await self.ws.send_json(build_media(self.sid, data[i:i + CHUNK]))
        self.marks += 1
        mark = f"m{self.marks}"
        await self.ws.send_json(build_mark(self.sid, mark))
        deadline = time.monotonic() + len(data) / 8000 + 8
        while True:
            try:
                ev = await self._event(max(0.1, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                say(f"!! no playback mark for {name}; moving on")
                return ""
            if isinstance(ev, MarkEvent) and ev.name == mark:
                return ""
            if isinstance(ev, DtmfEvent):
                say(f"CALLER  key {ev.digit} (interrupted)")
                await self.ws.send_json(build_clear(self.sid))
                return ev.digit

    async def listen(self) -> Heard:
        while not self.q.empty():  # drop audio queued while the line played (echo)
            ev = self.q.get_nowait()
            if isinstance(ev, StopEvent) or ev is None:
                raise Hangup()
        voiced, quiet, started, frames, peak = 0, 0, False, [], 0
        pre: list[bytes] = []
        deadline = time.monotonic() + NO_SPEECH_WAIT
        while True:
            try:
                ev = await self._event(max(0.05, deadline - time.monotonic()) if not started else 2.0)
            except asyncio.TimeoutError:
                if not started:
                    say(f"CALLER  (silence, peak level {peak})")
                    return Heard()
                break
            if isinstance(ev, DtmfEvent):
                say(f"CALLER  key {ev.digit}")
                return Heard(digit=ev.digit)
            if not isinstance(ev, MediaEvent):
                continue
            pcm = audioop.ulaw2lin(ev.payload_bytes, 2)
            level = audioop.rms(pcm, 2)
            peak = max(peak, level)
            if not started:
                pre = (pre + [pcm])[-15:]
                voiced = voiced + 1 if level > START_RMS else 0
                if voiced >= START_FRAMES:
                    started, frames = True, list(pre)
                elif time.monotonic() > deadline:
                    say(f"CALLER  (silence, peak level {peak})")
                    return Heard()
                continue
            frames.append(pcm)
            quiet = quiet + 1 if level < END_RMS else 0
            if quiet >= END_FRAMES or len(frames) >= MAX_UTTERANCE_FRAMES:
                break
        t0 = time.monotonic()
        try:
            text, lang = await asyncio.wait_for(asyncio.to_thread(speech_to_text, b"".join(frames), self.lang if self.lang_known else ""), STT_WAIT)
            say(f"CALLER  said: \"{text}\" ({lang}, {len(frames) * 20} ms audio, stt {time.monotonic() - t0:.1f} s)")
        except Exception as e:
            text, lang = "", ""
            say(f"CALLER  spoke {len(frames) * 20} ms; stt gave nothing in time ({type(e).__name__}) -> script default")
        return Heard(text, lang, spoke=True)

    async def ask(self, name: str) -> Heard:
        digit = await self.speak(name)
        if digit:
            return Heard(digit=digit)
        h = await self.listen()
        if h.nothing():
            digit = await self.speak("sorry")
            digit = digit or await self.speak(name)
            h = Heard(digit=digit) if digit else await self.listen()
        return h

    async def run(self) -> None:
        # language
        h = await self.ask_greet()
        t = h.low
        if h.digit == "2" or (not h.digit and ("english" in t or "इंग्लिश" in t or "अंग्रेज" in t
                                               or (h.lang == "en-IN" and "hindi" not in t and "हिंदी" not in t))):
            self.lang = "en"
        self.lang_known = True
        say(f"--      language: {self.lang}")
        # need (rigged: farming)
        h = await self.ask("need")
        say(f"--      need -> farming (script)")
        await self.speak("farm_ack")
        # follow-up questions
        land = yes_no(await self.ask("q_land"))
        say(f"--      land in own name: {land}")
        loan = yes_no(await self.ask("q_loan"))
        say(f"--      needs loan: {loan}")
        line, offered = RESULTS[(land, loan)]
        await self.speak(line)
        heard_about: list[str] = []
        while True:
            left = [s for s in offered if s not in heard_about]
            if len(offered) == 1:
                scheme = offered[0]
            else:
                scheme = pick_scheme(await self.ask("q_which"), offered, left[0] if left else offered[0])
            say(f"--      scheme: {scheme}")
            heard_about.append(scheme)
            await self.speak(f"detail_{scheme}")
            if yes_no(await self.ask("q_apply")):
                await self.speak(f"apply_{scheme}")
            if len(offered) == 1 or len(heard_about) >= len(offered):
                break
            if not yes_no(await self.ask("q_more"), default=False):
                break
        await self.speak("bye")

    async def ask_greet(self) -> Heard:
        digit = await self.speak("greet", "hi")
        if digit:
            return Heard(digit=digit)
        h = await self.listen()
        if h.nothing():
            digit = await self.speak("greet", "hi")
            h = Heard(digit=digit) if digit else await self.listen()
        return h


# ---- server --------------------------------------------------------------------
app = FastAPI(title="haqdaar-voice-demo")


@app.on_event("startup")
def _warm() -> None:
    threading.Thread(target=prerender, daemon=True).start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    return STATUS


@app.api_route("/answer", methods=["GET", "POST"])
def answer() -> Response:
    domain = os.environ.get("NGROK_DOMAIN", "")
    say("answer  line picked up, sent voice demo stream XML")
    return Response(content=build_stream_twiml(f"wss://{domain}/voice", keep_call_alive=False),
                    media_type="text/xml")


@app.websocket("/voice")
async def voice(ws: WebSocket) -> None:
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue()
    task: asyncio.Task | None = None

    async def run_call(sid: str) -> None:
        call = Call(ws, sid, q)
        try:
            if not STATUS["ready"]:
                say("!! call came before voice was ready; waiting")
                while not STATUS["ready"]:
                    await asyncio.sleep(0.2)
            await call.run()
            say("call    finished, hanging up")
        except Hangup:
            say("call    caller hung up")
        except Exception as e:
            say(f"!! call error: {e!r}")
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    try:
        while True:
            ev = parse_event(await ws.receive_text())
            if isinstance(ev, StartEvent):
                say(f"start   stream={ev.stream_sid}")
                task = asyncio.create_task(run_call(ev.stream_sid))
            elif isinstance(ev, (MediaEvent, DtmfEvent, MarkEvent, StopEvent)):
                q.put_nowait(ev)
                if isinstance(ev, StopEvent):
                    break
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as e:
        say(f"socket  {e!r}")
    finally:
        q.put_nowait(None)
        if task:
            await asyncio.gather(task, return_exceptions=True)
        say("socket  closed")
