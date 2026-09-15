"""haqdaar/demo_server.py — keypad phone call on the real 12 schemes (demo, 15 Sep).

Same /health and /answer as server.py, but the stream goes to /demo, where the
real call engine runs in a thread and talks with the Mac's offline voice.
Step 1's server.py is untouched. One caller at a time.

    make demo-run      (tunnel + number pointed here)
    make demo          (terminal version, no phone)
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect

from haqdaar.audio.telephony import (
    DtmfEvent,
    StartEvent,
    StopEvent,
    build_clear,
    build_media,
    build_stream_twiml,
    parse_event,
)
from haqdaar.contracts import tunables
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.demo_voice import PhoneAudio, Words, all_texts, render_ulaw
from haqdaar.engine.call import Engine

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
REAL_SCHEMES = ROOT / "data_cache" / "derived" / "schemes.jsonl"
CHUNK_BYTES = 8000  # 1 s of mu-law per media message


def say(line: str) -> None:
    print(f"{datetime.now():%H:%M:%S.%f}"[:-3] + f"  {line}", flush=True)


def load_real(schemes_path: Path = REAL_SCHEMES) -> tuple[Corpus, list[dict[str, Any]]]:
    """Build a throwaway snapshot of the real schemes (as sim.py does) and load it."""
    schemes = [json.loads(l) for l in schemes_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    td = Path(tempfile.mkdtemp(prefix="haqdaar_demo_"))
    (td / "snapshots").mkdir()
    (td / "audio").mkdir()
    tunables.SNAPSHOTS_DIR = str(td / "snapshots")
    tunables.AUDIO_DIR = str(td / "audio")
    snap_id = build_snapshot(schemes_data=schemes, snapshot_id="demo_real_snap",
                             snapshots_dir=td / "snapshots", audio_dir=td / "audio", render_stubs=True)
    return Corpus.load(snap_id), schemes


CORPUS, SCHEMES = load_real()
WORDS = Words(CORPUS, SCHEMES)


def prerender() -> None:
    t0 = time.monotonic()
    from concurrent.futures import ThreadPoolExecutor
    texts = all_texts(WORDS)
    failed = 0

    def one(item: tuple[str, str]) -> bool:
        try:
            render_ulaw(*item)
            return True
        except Exception as e:
            say(f"!! prerender failed: {item[0][:60]!r} {e!r}")
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        failed = sum(not ok for ok in pool.map(one, texts))
    say(f"voice ready: {len(texts)} lines, {failed} failed, {time.monotonic() - t0:.1f} s")


app = FastAPI(title="haqdaar-demo")


@app.on_event("startup")
def _warm() -> None:
    threading.Thread(target=prerender, daemon=True).start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/answer", methods=["GET", "POST"])
def answer() -> Response:
    domain = tunables.NGROK_DOMAIN or os.environ.get("NGROK_DOMAIN", "")
    say("answer  line picked up, sent demo stream XML")
    return Response(content=build_stream_twiml(f"wss://{domain}/demo", keep_call_alive=False),
                    media_type="text/xml")


@app.websocket("/demo")
async def demo_stream(ws: WebSocket) -> None:
    await ws.accept()
    loop = asyncio.get_running_loop()
    sid = ""
    audio: PhoneAudio | None = None
    closed = threading.Event()

    def run(coro) -> None:
        if closed.is_set():
            return
        try:
            asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=10)
        except Exception as e:  # socket gone: the call is over
            say(f"send failed: {e!r}")
            closed.set()

    def send(data: bytes) -> None:
        for i in range(0, len(data), CHUNK_BYTES):
            run(ws.send_json(build_media(sid, data[i:i + CHUNK_BYTES])))

    def clear() -> None:
        # Called from the socket loop itself (a key arrived): schedule, never block the loop.
        if not closed.is_set():
            loop.create_task(ws.send_json(build_clear(sid)))

    def close() -> None:
        if not closed.is_set():
            run(ws.close())
        closed.set()

    def engine_thread(call_id: str) -> None:
        try:
            log = Log.open(call_id=call_id, snapshot_id="demo_real_snap", logs_dir="logs/demo_calls")
            Engine.run_call(audio=audio, model=None, corpus=CORPUS, log=log)
            say(f"call {call_id} finished")
        except Exception as e:
            say(f"!! engine error: {e!r}")
        finally:
            close()

    try:
        while True:
            ev = parse_event(await ws.receive_text())
            if isinstance(ev, StartEvent):
                sid = ev.stream_sid
                audio = PhoneAudio(WORDS, send, clear, close, log=say)
                call_id = f"demo_{int(time.time())}"
                say(f"start  stream={sid} call={call_id}")
                threading.Thread(target=engine_thread, args=(call_id,), daemon=True).start()
            elif isinstance(ev, DtmfEvent) and audio:
                say(f"dtmf   {ev.digit}")
                audio.push_digit(ev.digit)
            elif isinstance(ev, StopEvent):
                say("stop   caller hung up")
                break
    except WebSocketDisconnect:
        say("socket closed")
    finally:
        closed.set()
        if audio:
            audio.push_hangup()


def terminal_demo(argv: list[str] | None = None) -> int:
    """`make demo`: the same call in the terminal, with real words. --speak reads aloud."""
    import argparse
    from haqdaar.demo_voice import TextAudio
    ap = argparse.ArgumentParser()
    ap.add_argument("--speak", action="store_true")
    ap.add_argument("--keys", default="", help="canned keys, e.g. 3,1,1,1,0,2")
    a = ap.parse_args(argv)
    audio = TextAudio(WORDS, speak=a.speak, canned=[k for k in a.keys.split(",") if k])
    call_id = f"term_{int(time.time())}"
    log = Log.open(call_id=call_id, snapshot_id="demo_real_snap", logs_dir="logs/demo_calls")
    print("=" * 60 + "\n HAQDAAR — call on 12 real schemes from myscheme.gov.in\n" + "=" * 60)
    Engine.run_call(audio=audio, model=None, corpus=CORPUS, log=log)
    print(f"\nLog: logs/demo_calls/{call_id}.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(terminal_demo())
