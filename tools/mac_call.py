"""tools/mac_call.py

A call from the Mac itself, no phone and no Twilio. It plays the phone company's part against the real
server: opens /stream, sends the Mac's microphone as 8 kHz mu-law frames in real time, plays what the
agent sends through the speakers, and echoes each mark when that sound has really been played.
Type a key (0-9, * or #) and press Enter to press it on the phone. Type q and Enter (or Ctrl+C) to hang up.
The screen shows the talk as it goes: what the ear heard (YOU), what the agent says (AGENT), keys, what
the agent chose and how long the reply took. It reads these from the call's own log, so it is what the
server really heard and said. --plain gives the same lines with no colour.
Everything after the socket is the real thing: ear, Sarvam speech-to-text, search, model, live voice.

  make mac-call                                         (starts the server, then the call)
  .venv/bin/python -m tools.mac_call --serve            (same)
  .venv/bin/python -m tools.mac_call --list-devices     (see the sound devices)
"""
from __future__ import annotations

import argparse
import asyncio
import audioop
import base64
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import websockets

RATE = 8000                      # what the phone line carries
FRAME = 160                      # 20 ms at 8 kHz, in bytes of mu-law
SILENCE = b"\xff"                # mu-law silence
KEYS = set("0123456789*#")


def split_frames(buf: bytes) -> tuple[list[bytes], bytes]:
    """Cut bytes into 160-byte frames. The part that is too short for a frame is given back."""
    whole = len(buf) // FRAME * FRAME
    return [buf[i:i + FRAME] for i in range(0, whole, FRAME)], buf[whole:]


class Resampler:
    """16-bit mono sound from one rate to another, with the state kept between blocks (no clicks)."""

    def __init__(self, src: int, dst: int) -> None:
        self.src, self.dst, self.state = src, dst, None

    def feed(self, pcm: bytes) -> bytes:
        if self.src == self.dst:
            return pcm
        out, self.state = audioop.ratecv(pcm, 2, 1, self.src, self.dst, self.state)
        return out


class PlayQueue:
    """The agent's sound waiting for the speakers, with marks in between. Safe to use from the sound
    thread and the socket thread. A mark comes back from pull() only after all sound before it was pulled."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.items: list[object] = []        # bytes of sound, or a mark name (str)

    def push_sound(self, data: bytes) -> None:
        with self.lock:
            self.items.append(bytes(data))

    def push_mark(self, name: str) -> None:
        with self.lock:
            self.items.append(name)

    def pull(self, n: int) -> tuple[bytes, list[str]]:
        """n bytes of sound (padded with silence) and the marks that are now done."""
        out, done = b"", []
        with self.lock:
            while len(out) < n and self.items:
                head = self.items[0]
                if isinstance(head, str):
                    done.append(self.items.pop(0))
                    continue
                take = head[:n - len(out)]
                out += take
                if len(take) == len(head):
                    self.items.pop(0)
                else:
                    self.items[0] = head[len(take):]
            while self.items and isinstance(self.items[0], str):      # marks right behind the last sound
                done.append(self.items.pop(0))
        return out.ljust(n, SILENCE), done

    def clear(self) -> list[str]:
        """Drop all the sound at once. The pending marks come back: Twilio answers them right away."""
        with self.lock:
            marks = [x for x in self.items if isinstance(x, str)]
            self.items.clear()
        return marks

    def speaking(self) -> bool:
        with self.lock:
            return any(not isinstance(x, str) for x in self.items)


def pick_rate(sd, device, kind: str) -> int:
    """8000 if the device takes it, else its own default rate (such as 48000)."""
    try:
        check = sd.check_input_settings if kind == "input" else sd.check_output_settings
        check(device=device, channels=1, dtype="int16", samplerate=RATE)
        return RATE
    except Exception:
        return int(sd.query_devices(device, kind)["default_samplerate"])


LANG_NAMES = {"hi": "Hindi", "mr": "Marathi", "en": "English", "gu": "Gujarati", "ta": "Tamil"}
COLOURS = {"YOU": "1;32", "AGENT": "1;36", "KEY": "1;33", "!": "1;31", "": "2"}
SCREEN = {"t0": 0.0, "colour": False, "last": None}


def paint(text: str, tag: str) -> str:
    return f"\033[{COLOURS.get(tag, '2')}m{text}\033[0m" if SCREEN["colour"] else text


def clock() -> str:
    if not SCREEN["t0"]:
        return "     "
    s = int(time.time() - SCREEN["t0"])
    return f"{s // 60:02d}:{s % 60:02d}"


def say(text: str, tag: str = "") -> None:
    """One line on the screen: time into the call, who (YOU / AGENT / KEY / ! / nothing), the words.
    The time and the name are left out when the same speaker goes on, so a reply reads as one block."""
    again = tag in ("YOU", "AGENT") and SCREEN["last"] == tag
    if tag in ("YOU", "AGENT") and not again:
        print(flush=True)
    SCREEN["last"] = tag
    head = " " * 12 if again else f"{clock()}  {paint(f'{tag or chr(183):<5}', tag)}"
    print(f"{head}  {paint(text, '') if tag == '' else text}", flush=True)


def secs(ms) -> str:
    ms = int(ms or 0)
    return f"{ms} ms" if ms < 1000 else f"{ms / 1000:.1f} s"


def show(row: dict) -> tuple[str, str] | None:
    """A row of the call's log as (who, words) for the screen, or None for a row the screen leaves out."""
    ev = row.get("ev")
    if ev == "heard":
        return "YOU", row.get("text") or "(no words)"
    if ev == "said":
        en = row.get("en") or ""
        return "AGENT", (row.get("text") or "") + (f"   [{en}]" if en and en != row.get("text") else "")
    if ev == "key":
        return "KEY", f"{row.get('key')}  ({row.get('means')})" if row.get("means") else str(row.get("key"))
    if ev == "act":
        parts = [f"{name} {secs(row[k])}" for name, k in (("ear", "stt_ms"), ("search", "search_ms"),
                 ("model", "model_ms"), ("voice", "voice_ms")) if row.get(k)]
        what = " ".join(str(x) for x in (row.get("action"), row.get("scheme")) if x)
        wait = f", reply after {secs(row['wait_ms'])}" if row.get("wait_ms") else ""
        return "", f"chose: {what}{wait}" + (f" ({', '.join(parts)})" if parts else "")
    if ev == "blocked":
        return "!", f"a reply was held back by the rule '{row.get('rule')}': {row.get('text', '')[:120]}"
    if ev == "line":
        return "", (f"line: {row.get('why')}, longest gap {row.get('gap_s')} s, "
                    f"sound sent {row.get('ahead_s')} s ahead, {row.get('drops')} drops")
    if ev:
        rest = {k: v for k, v in row.items() if k != "ev"}
        return "", f"{ev}: {json.dumps(rest, ensure_ascii=False)[:160]}"
    if row.get("class") == "SILENCE":
        return "", f"silence ({row.get('silence_n')})"
    if "box" in row and "value" in row:
        return "", f"noted: {row['box']} = {row['value']}"
    if "lang_source" in row and "turn_n" in row:
        return "", f"language: {LANG_NAMES.get(row.get('lang'), row.get('lang'))} (by {row['lang_source']})"
    if "slug" in row and "ending" in row:
        return "", f"scheme: {row['slug']} ({row['ending']})"
    return None


class LogTail:
    """Reads the call's log as it grows. Gives each whole new row once; a half-written line waits."""

    def __init__(self, path: Path) -> None:
        self.path, self.pos, self.rest = Path(path), 0, b""

    def rows(self) -> list[dict]:
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read()
        except OSError:
            return []
        self.pos += len(data)
        *lines, self.rest = (self.rest + data).split(b"\n")
        out = []
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                out.append(row)
        return out


async def call(url: str, in_device, out_device, logs: str = "logs/calls") -> str:
    import sounddevice as sd             # here and not at the top: the pure parts load with no sound device

    loop = asyncio.get_running_loop()
    call_id = f"mac_{int(time.time())}"
    in_rate, out_rate = pick_rate(sd, in_device, "input"), pick_rate(sd, out_device, "output")
    say(f"sound: microphone at {in_rate} Hz, speakers at {out_rate} Hz")

    mic_q: asyncio.Queue[bytes] = asyncio.Queue()
    mark_q: asyncio.Queue[str] = asyncio.Queue()
    key_q: asyncio.Queue[str] = asyncio.Queue()
    play = PlayQueue()
    end = asyncio.Event()
    up, down = Resampler(in_rate, RATE), Resampler(RATE, out_rate)
    leftover = bytearray()               # speaker bytes made but not yet used by the callback

    def on_mic(indata, frames, t, status) -> None:          # PortAudio thread: no waiting here
        loop.call_soon_threadsafe(mic_q.put_nowait, bytes(indata))

    def on_speaker(outdata, frames, t, status) -> None:     # PortAudio thread: no waiting here
        need = frames * 2
        while len(leftover) < need:
            ulaw, marks = play.pull(FRAME)
            leftover.extend(down.feed(audioop.ulaw2lin(ulaw, 2)))
            for m in marks:
                loop.call_soon_threadsafe(mark_q.put_nowait, m)
        outdata[:] = bytes(leftover[:need])
        del leftover[:need]

    def read_keys() -> None:             # a plain thread: stdin cannot be waited on politely
        for line in sys.stdin:
            loop.call_soon_threadsafe(key_q.put_nowait, line.strip())
        loop.call_soon_threadsafe(key_q.put_nowait, "q")

    threading.Thread(target=read_keys, daemon=True).start()
    loop.add_signal_handler(signal.SIGINT, end.set)

    async with websockets.connect(url, max_size=None) as ws:
        async def send(msg: dict) -> None:
            await ws.send(json.dumps(msg))

        sid = "MZmac"
        await send({"event": "connected", "protocol": "Call", "version": "1.0.0"})
        await send({"event": "start", "streamSid": sid, "sequenceNumber": "1",
                    "start": {"streamSid": sid, "callSid": call_id, "accountSid": "ACmac",
                              "tracks": ["inbound"], "customParameters": {},
                              "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}}})
        SCREEN["t0"] = time.time()
        say(f"connected, call {call_id}")
        say("use headphones, or the mic will hear the speakers")
        say("type a key (0-9 * #) and Enter to press it; q and Enter to hang up")

        async def mic_out() -> None:
            """The mic sets the pace: one 20 ms frame out for each 20 ms heard, the whole call."""
            rest, n, t0 = b"", 0, time.time()
            while True:
                pcm = await mic_q.get()
                frames, rest = split_frames(rest + audioop.lin2ulaw(up.feed(pcm), 2))
                for f in frames:
                    n += 1
                    await send({"event": "media", "streamSid": sid, "sequenceNumber": str(n + 1),
                                "media": {"track": "inbound", "chunk": str(n),
                                          "timestamp": str(int((time.time() - t0) * 1000)),
                                          "payload": base64.b64encode(f).decode()}})

        async def from_agent() -> None:
            try:
                async for raw in ws:
                    msg = json.loads(raw)
                    kind = msg.get("event")
                    if kind == "media":
                        play.push_sound(base64.b64decode(msg["media"]["payload"]))
                    elif kind == "mark":
                        play.push_mark(msg["mark"]["name"])
                    elif kind == "clear":
                        for name in play.clear():
                            await send({"event": "mark", "streamSid": sid, "mark": {"name": name}})
            except Exception:
                pass
            say("line closed by the agent")
            end.set()

        async def marks_back() -> None:
            while True:
                name = await mark_q.get()
                await send({"event": "mark", "streamSid": sid, "mark": {"name": name}})

        async def keys() -> None:
            while True:
                text = await key_q.get()
                if text == "q":
                    end.set()
                elif len(text) == 1 and text in KEYS:
                    say(text, "KEY")
                    await send({"event": "dtmf", "streamSid": sid, "dtmf": {"track": "inbound_track", "digit": text}})
                elif text:
                    say("keys are 0-9, * and #; q to hang up")

        async def turns() -> None:
            was = False
            while True:
                now = play.speaking()
                if now != was:
                    say("the agent is speaking" if now else "your turn, speak now")
                    was = now
                await asyncio.sleep(0.1)

        async def talk() -> None:
            """The words of the call, from the call's own log, as the server writes them."""
            tail = LogTail(Path(logs) / f"{call_id}.jsonl")
            while True:
                for row in tail.rows():
                    line = show(row)
                    if row.get("ev") == "key":               # the key itself is shown when it is typed
                        line = ("", f"key {row.get('key')} means: {row['means']}") if row.get("means") else None
                    if line:
                        say(line[1], line[0])
                await asyncio.sleep(0.2)

        tasks = [asyncio.create_task(c()) for c in (mic_out, from_agent, marks_back, keys, turns, talk)]
        with sd.RawInputStream(samplerate=in_rate, channels=1, dtype="int16", device=in_device,
                               blocksize=in_rate // 50, callback=on_mic), \
             sd.RawOutputStream(samplerate=out_rate, channels=1, dtype="int16", device=out_device,
                                blocksize=out_rate // 50, callback=on_speaker):
            await end.wait()
        for t in tasks:
            t.cancel()
        try:
            await send({"event": "stop", "streamSid": sid})
        except Exception:
            pass
    return call_id


def wait_for_port(port: int, server: subprocess.Popen, limit: float = 90.0) -> bool:
    end = time.time() + limit
    while time.time() < end and server.poll() is None:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None, help="default ws://127.0.0.1:<port>/stream")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--serve", action="store_true", help="start the server for a no-phone call, stop it at the end")
    ap.add_argument("--in-device", default=None, help="microphone: sounddevice id or name")
    ap.add_argument("--out-device", default=None, help="speakers: sounddevice id or name")
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--logs", default="logs/calls")
    ap.add_argument("--plain", action="store_true", help="no colour on the screen")
    args = ap.parse_args()

    if args.list_devices:
        import sounddevice as sd

        print(sd.query_devices())
        return

    def device(x):
        return int(x) if x is not None and x.isdigit() else x

    SCREEN["colour"] = sys.stdout.isatty() and not args.plain and not os.environ.get("NO_COLOR")

    server = None
    if args.serve:
        Path("logs").mkdir(exist_ok=True)
        env = {**os.environ, "PHONE_CHECK": "false", "TALK_ONLY": "true", "PYTHONUNBUFFERED": "1"}
        out = open("logs/mac-call-server.log", "ab")
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "haqdaar.server:app", "--port", str(args.port)],
                                  env=env, stdout=out, stderr=subprocess.STDOUT)
        say(f"starting the server on port {args.port} (its log: logs/mac-call-server.log)")
        if not wait_for_port(args.port, server):
            server.terminate()
            sys.exit("the server did not come up; look at logs/mac-call-server.log")
    url = args.url or f"ws://127.0.0.1:{args.port}/stream"
    call_id = None
    try:
        call_id = asyncio.run(call(url, device(args.in_device), device(args.out_device), args.logs))
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
    if call_id:
        time.sleep(1.0)
        path = Path(args.logs) / f"{call_id}.jsonl"
        say(f"\nthe call log: {path}" + ("" if path.exists() else "  (not written yet or no file)"))


if __name__ == "__main__":
    main()
