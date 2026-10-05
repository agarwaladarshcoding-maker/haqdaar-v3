"""tools/talk_probe.py

A caller with no phone (step 7.13). It plays the phone company's part against the real server:
opens /stream, sends the caller's voice as 8 kHz mu-law frames in real time, presses keys, "plays"
what the agent sends and echoes the marks. The caller's voice is made by the Mac (`say`), free.
Everything after that is the real thing: ear, Sarvam speech-to-text, search, model, live voice.

  TALK_ONLY=true .venv/bin/python -m uvicorn haqdaar.server:app --port 8001      (one terminal)
  .venv/bin/python -m tools.talk_probe --script farmer                           (another)

A script is a list of steps: "key:1", "say:<words>", "over:<words>" (talk while the agent talks),
"during:<words>" (start 1.2 s into the agent's reply), "quiet:<seconds>". The probe waits for the agent to finish before each "say".
"""
from __future__ import annotations

import argparse
import asyncio
import audioop
import base64
import json
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import websockets

FRAME = 160                      # 20 ms at 8 kHz
QUIET = b"\xff" * FRAME          # mu-law silence
VOICES = {"hi": "Lekha", "en": "Rishi"}

SCRIPTS: dict[str, tuple[str, list[str]]] = {
    # the owner's call of 5 Oct, word for word
    "farmer": ("hi", ["key:1", "say:मेरे को फार्मर स्कीम्स के बारे में जानना है", "say:मेरे को खेती से जुड़ी योजनाएं चाहिए",
                      "say:पीएम किसान में कितना पैसा मिलता है", "say:इसके लिए कौन से कागज़ लगेंगे",
                      "say:फिर से बताइए", "say:ठीक है धन्यवाद, बस इतना ही"]),
    "vague": ("hi", ["key:1", "say:मुझे कोई सरकारी योजना चाहिए", "say:मुझे पेंशन चाहिए", "say:मेरी उम्र तीस साल है",
                     "say:अटल पेंशन योजना में कितना पैसा जमा करना होता है", "say:धन्यवाद, अलविदा"]),
    "sidetalk": ("hi", ["key:1", "say:मुझे घर बनाने के लिए मदद चाहिए", "say:अरे रमेश, चाय ला दो ज़रा",
                        "over:नहीं नहीं, वहाँ मत रखो", "say:इसमें कितना पैसा मिलता है", "say:धन्यवाद, अलविदा"]),
    "vendor": ("en", ["key:2", "say:I sell vegetables on a cart and I need a loan", "say:how do I apply for it",
                      "say:what is the weather today", "say:thank you, goodbye"]),
    # talk over the agent: with strict turns the agent must finish its sentence and not lose the thread
    "overtalk": ("hi", ["key:1", "say:मुझे खेती के लिए योजना चाहिए", "during:रुको रुको, एक मिनट",
                        "say:पीएम किसान में कितना पैसा मिलता है", "during:हाँ हाँ ठीक है",
                        "say:आज मौसम कैसा है", "say:धन्यवाद, अलविदा"]),
    # the owner's call of 5 Oct: asks for details, then says yes to the offer
    "details": ("hi", ["key:1", "say:मुझे खेती के लिए योजना चाहिए", "say:पीएम किसान के बारे में बताइए",
                       "say:इसके बारे में पूरी जानकारी विस्तार से बताइए", "say:हाँ बताइए", "say:धन्यवाद, अलविदा"]),
    "quiet": ("hi", ["key:1", "quiet:70"]),
}


def voice(text: str, lang: str, gain: float = 1.0) -> bytes:
    """Words -> 8 kHz mu-law, by the Mac's own voice."""
    with tempfile.TemporaryDirectory() as tmp:
        aiff, wav = Path(tmp) / "a.aiff", Path(tmp) / "a.wav"
        subprocess.run(["say", "-v", VOICES[lang], "-o", str(aiff), text], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@8000", "-c", "1", str(aiff), str(wav)], check=True)
        with wave.open(str(wav), "rb") as w:
            pcm = w.readframes(w.getnframes())
    if gain != 1.0:
        pcm = audioop.mul(pcm, 2, gain)
    return audioop.lin2ulaw(pcm, 2)


class Probe:
    def __init__(self, ws, call_id: str) -> None:
        self.ws, self.call_id = ws, call_id
        self.t0 = time.monotonic()
        self.out: list[bytes] = []          # caller frames waiting to go out
        self.play: list[object] = []        # agent audio being "played": bytes left, or a mark name
        self.last_agent = 0.0               # when the agent's sound last played
        self.agent_bytes = 0
        self.base = 0                       # agent bytes seen when the caller last stopped talking
        self.closed = False
        self.gaps: list[float] = []

    def now(self) -> float:
        return time.monotonic() - self.t0

    def note(self, text: str) -> None:
        print(f"{self.now():6.1f}  {text}", flush=True)

    async def send(self, msg: dict) -> None:
        await self.ws.send(json.dumps(msg))

    async def pump(self) -> None:
        """Every 20 ms: one caller frame out, 20 ms of the agent's audio played."""
        nxt = time.monotonic()
        while not self.closed:
            frame = self.out.pop(0) if self.out else QUIET
            try:
                await self.send({"event": "media", "streamSid": "MZprobe",
                                 "media": {"payload": base64.b64encode(frame).decode()}})
                budget = FRAME
                while self.play and budget > 0:
                    head = self.play[0]
                    if isinstance(head, str):
                        self.play.pop(0)
                        await self.send({"event": "mark", "streamSid": "MZprobe", "mark": {"name": head}})
                        continue
                    self.last_agent = self.now()
                    if head[0] <= budget:
                        budget -= head[0]
                        self.play.pop(0)
                    else:
                        head[0] -= budget
                        budget = 0
                while self.play and isinstance(self.play[0], str):      # marks at the very end
                    await self.send({"event": "mark", "streamSid": "MZprobe", "mark": {"name": self.play.pop(0)}})
            except Exception:
                self.closed = True
                return
            nxt += 0.02
            await asyncio.sleep(max(0.0, nxt - time.monotonic()))

    async def listen(self) -> None:
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if msg.get("event") == "media":
                    n = len(base64.b64decode(msg["media"]["payload"]))
                    self.agent_bytes += n
                    self.play.append([n])
                elif msg.get("event") == "mark":
                    self.play.append(msg["mark"]["name"])
                elif msg.get("event") == "clear":
                    self.play.clear()
        except Exception:
            pass
        self.closed = True
        self.note("line closed by the agent")

    def talking(self) -> bool:
        return any(not isinstance(p, str) for p in self.play)

    async def agent_done(self, settle: float = 1.5, limit: float = 60.0) -> None:
        """Wait until the agent has said its piece: nothing playing for `settle` seconds. If the agent
        says nothing at all (side talk), give up after 7 s."""
        start = self.now()
        while not self.closed and self.now() - start < limit:
            spoke = self.agent_bytes > self.base
            if not self.talking() and spoke and self.now() - self.last_agent > settle:
                return
            if not spoke and self.now() - start > 7.0:
                self.note("(the agent said nothing)")
                return
            await asyncio.sleep(0.05)

    async def say(self, text: str, lang: str, wait: bool = True) -> None:
        if wait:
            await self.agent_done()
        if self.closed:
            return
        sound = voice(text, lang)
        self.note(f"CALLER: {text}  ({len(sound) / 8000:.1f} s)")
        self.out += [sound[i:i + FRAME].ljust(FRAME, b"\xff") for i in range(0, len(sound), FRAME)]
        while self.out and not self.closed:
            await asyncio.sleep(0.02)
        end, heard = self.now(), self.agent_bytes
        self.base = heard
        while not self.closed and self.agent_bytes == heard and self.now() - end < 10:
            await asyncio.sleep(0.02)
        if self.agent_bytes > heard:
            self.gaps.append(self.now() - end)
            self.note(f"   agent starts {self.now() - end:.1f} s after the caller stops")


async def run(script: str, url: str) -> str:
    lang, steps = SCRIPTS[script]
    call_id = f"probe_{script}_{int(time.time())}"
    async with websockets.connect(url, max_size=None) as ws:
        p = Probe(ws, call_id)
        await p.send({"event": "connected", "protocol": "Call", "version": "1.0.0"})
        await p.send({"event": "start", "streamSid": "MZprobe", "sequenceNumber": "1",
                      "start": {"streamSid": "MZprobe", "callSid": call_id, "accountSid": "ACprobe",
                                "tracks": ["inbound"], "customParameters": {},
                                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}}})
        tasks = [asyncio.create_task(p.pump()), asyncio.create_task(p.listen())]
        for step in steps:
            if p.closed:
                break
            kind, _, arg = step.partition(":")
            if kind == "key":
                await asyncio.sleep(3.0)
                p.note(f"CALLER presses {arg}")
                await p.send({"event": "dtmf", "streamSid": "MZprobe", "dtmf": {"track": "inbound_track", "digit": arg}})
            elif kind == "say":
                await p.say(arg, lang)
            elif kind == "during":          # start talking 1.2 s into the agent's reply
                end = p.now() + 15
                while not p.closed and not p.talking() and p.now() < end:
                    await asyncio.sleep(0.02)
                await asyncio.sleep(1.2)
                left = sum(x[0] for x in p.play if not isinstance(x, str)) / 8000
                p.note(f"   (agent is talking: {p.talking()}, {left:.1f} s of its reply still to play)")
                await p.say(arg, lang, wait=False)
            elif kind == "over":
                await asyncio.sleep(1.5)
                await p.say(arg, lang, wait=False)
            elif kind == "quiet":
                p.note(f"CALLER is quiet for up to {arg} s")
                end = p.now() + float(arg)
                while not p.closed and p.now() < end:
                    await asyncio.sleep(0.2)
        await p.agent_done(limit=20)
        if not p.closed:
            await p.send({"event": "stop", "streamSid": "MZprobe"})
        p.closed = True
        for t in tasks:
            t.cancel()
        if p.gaps:
            print(f"reply gaps (s): {[round(g, 1) for g in p.gaps]}  worst {max(p.gaps):.1f}")
    return call_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default="farmer", choices=sorted(SCRIPTS))
    ap.add_argument("--url", default="ws://localhost:8001/stream")
    ap.add_argument("--logs", default="logs/calls")
    args = ap.parse_args()
    call_id = asyncio.run(run(args.script, args.url))
    time.sleep(1.0)
    from haqdaar.data import log_text

    path = Path(args.logs) / f"{call_id}.jsonl"
    print(f"\n=== the call as the log has it ({path})")
    print(log_text.log_text(log_text.read_rows(path), times=True) if path.exists() else "(no log file)")


if __name__ == "__main__":
    main()
