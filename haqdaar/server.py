"""haqdaar/server.py

FastAPI entry point serving telephony webhooks and audio streams (T14, T19).
Exposes `app` for uvicorn (make run).

Plan 2.7: `/answer` sends the line to `/stream`, where the real keypad call runs: the engine
on its own thread, Mouth for what the caller hears, Turn for keys and silence. `/tone` is the
Step 1 line check (1 s tone, keys echoed) kept for testing the line on its own.

Privacy: the caller's number is never stored. `/answer` keeps only its sha256, and only until
the stream for that call starts.
"""
from __future__ import annotations
import asyncio
import hashlib
import os
import threading
import time
import urllib.parse
from datetime import datetime
from typing import Any, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect

from haqdaar.contracts import tunables
from haqdaar.contracts.tunables import NGROK_DOMAIN
from haqdaar.audio.telephony import (
    parse_event,
    build_media,
    build_mark,
    build_stream_twiml,
    StartEvent,
    DtmfEvent,
    MarkEvent,
    MediaEvent,
    StopEvent,
)
from tools.tone import generate_tone

load_dotenv()

app = FastAPI(title="haqdaar")


def say(line: str) -> None:
    """One call event per line, with the time. `make run` also copies it to logs/server.log."""
    print(f"{datetime.now():%H:%M:%S.%f}"[:-3] + f"  {line}", flush=True)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


# call id -> sha256 of the caller's number, from /answer until that call's stream starts.
_CALLER_HASH: dict[str, str] = {}


def caller_hash(number: str) -> str:
    return hashlib.sha256(number.encode("utf-8")).hexdigest() if number else ""


@app.api_route("/answer", methods=["GET", "POST"])
async def answer(request: Request) -> Response:
    """TwiML voice webhook returning Stream instruction (T14, T19).

    Hard rules:
    - keepCallAlive="false"
    - Stream URL takes no query string.
    - Response Content-Type is text/xml.
    """
    form = urllib.parse.parse_qs((await request.body()).decode("utf-8", "replace"))
    call_id = (form.get("CallSid") or [""])[0]
    if call_id:
        _CALLER_HASH[call_id] = caller_hash((form.get("From") or [""])[0])
    domain = NGROK_DOMAIN or os.environ.get("NGROK_DOMAIN", "")
    stream_url = f"wss://{domain}/stream"
    say("answer  line picked up, sent stream XML")
    twiml = build_stream_twiml(stream_url, keep_call_alive=False)
    return Response(content=twiml, media_type="text/xml")


@app.websocket("/tone")
async def tone_endpoint(websocket: WebSocket) -> None:
    """Step 1 line check: bidirectional media stream WebSocket with a test tone.

    Behaviour:
    - On start: send 1s 440 Hz μ-law tone as one media message, then mark 'tone_end'.
    - On inbound mark: print 'mark <name>'.
    - On inbound dtmf: print 'dtmf <digit>'.
    - If digit == '9': close the socket.
    """
    await websocket.accept()
    say("socket  open")
    heard = 0
    started = time.monotonic()
    last_arrival = started
    last_chunk, last_ts = "", "0"
    clean_stop = False
    stream_start = started
    behind_warned = 1.0
    try:
        while True:
            text = await websocket.receive_text()
            event = parse_event(text)
            now = time.monotonic()
            if now - last_arrival > 1.0:
                say(f"!! nothing arrived for {now - last_arrival:.1f} s (line stalled)")
            last_arrival = now
            if isinstance(event, MediaEvent):
                heard += 1
                last_chunk, last_ts = event.chunk, event.timestamp
                behind = (now - stream_start) - int(last_ts or 0) / 1000
                if behind > behind_warned:
                    say(f"!! falling behind: audio arrives {behind:.1f} s late (link too slow)")
                    behind_warned = behind + 1.0
            elif isinstance(event, StartEvent):
                stream_start = now
                say(f"start   call ..{event.call_sid[-6:]}")
                tone_bytes = generate_tone()
                media_msg = build_media(event.stream_sid, tone_bytes)
                await websocket.send_json(media_msg)
                mark_msg = build_mark(event.stream_sid, "tone_end")
                await websocket.send_json(mark_msg)
                say(f"-> tone {len(tone_bytes) / 8000:.1f} s, then mark tone_end")
            elif isinstance(event, DtmfEvent):
                say(f"<- dtmf {event.digit}  (audio clock {int(last_ts or 0) / 1000:.1f} s)")
                if event.digit == "9":
                    say("-> closing socket (digit 9)")
                    await websocket.close()
                    break
            elif isinstance(event, MarkEvent):
                say(f"<- mark {event.name}  (finished playing)")
            elif isinstance(event, StopEvent):
                clean_stop = True
                say("stop    caller side ended the stream")
    except WebSocketDisconnect:
        pass
    open_s = time.monotonic() - started
    how = "clean stop" if clean_stop else "dropped, no stop event"
    say(
        f"socket  closed ({how}) after {open_s:.1f} s; heard {heard} audio packets"
        f" = {heard * 0.02:.1f} s, last chunk {last_chunk or '-'}"
        f" at audio clock {int(last_ts or 0) / 1000:.1f} s"
    )


# --- plan 2.7: the real keypad call ---------------------------------------------------

_CALL: dict[str, Any] = {}  # the loaded snapshot and pool, shared by every call


def _corpus_and_pool() -> tuple[Any, Any]:
    """Load the CURRENT snapshot once. Corpus.load refuses it if any clip is missing."""
    if "corpus" not in _CALL:
        from haqdaar.audio.pool import AudioPool
        from haqdaar.data.corpus import Corpus

        corpus = Corpus.load("CURRENT")
        pool = AudioPool(tier2="none")
        pool.warm()  # every clip in audio/ into RAM up to AUDIO_CACHE_MB (37 MB today)
        _CALL["corpus"], _CALL["pool"] = corpus, pool
        say(f"corpus  {corpus.snapshot_id} loaded")
    return _CALL["corpus"], _CALL["pool"]


def _run_engine(call_id: str, snapshot_id: str, number_hash: str, audio: Any, corpus: Any,
                done: Any) -> None:
    from haqdaar.data.log import Log
    from haqdaar.engine.call import Engine

    try:
        log = Log.open(call_id=call_id, snapshot_id=snapshot_id, caller_hash=number_hash,
                       logs_dir=tunables.CALL_LOGS_DIR)
        Engine.run_call(audio=audio, model=None, corpus=corpus, log=log)
        say(f"call    {call_id} finished")
    except Exception as e:  # never leave the caller on a silent line
        say(f"!! engine error: {e!r}")
    finally:
        done()


@app.websocket("/stream")
async def stream_endpoint(websocket: WebSocket) -> None:
    """One real keypad call. One caller at a time (D14)."""
    from haqdaar.audio.mouth import Mouth, Outbox
    from haqdaar.audio.phone import PhoneAudio
    from haqdaar.audio.turn import Turn

    await websocket.accept()
    loop = asyncio.get_running_loop()

    async def send(msg: dict[str, Any]) -> None:
        if msg.get("event") == "_close":
            await websocket.close()
        else:
            await websocket.send_json(msg)

    outbox = Outbox(loop, send)
    writer = asyncio.create_task(outbox.run())
    mouth: Optional[Mouth] = None
    turn: Optional[Turn] = None
    ended = threading.Event()

    def hang_up() -> None:
        if not ended.is_set():
            ended.set()
            outbox.emit({"event": "_close"})
            outbox.close()

    try:
        while True:
            event = parse_event(await websocket.receive_text())
            if isinstance(event, StartEvent) and mouth is None:
                corpus, pool = _corpus_and_pool()
                mouth = Mouth(outbox.emit, event.stream_sid, log=say)
                turn = Turn(mouth)
                audio = PhoneAudio(corpus, pool, mouth, turn, close=hang_up, log=say)
                call_id = event.call_sid or f"call_{int(time.time())}"
                number_hash = _CALLER_HASH.pop(call_id, "")
                say(f"start   call ..{call_id[-6:]}")
                threading.Thread(
                    target=_run_engine,
                    args=(call_id, corpus.snapshot_id, number_hash, audio, corpus, hang_up),
                    daemon=True,
                ).start()
            elif isinstance(event, DtmfEvent) and turn is not None:
                say(f"<- dtmf {event.digit}")
                turn.push_key(event.digit)
            elif isinstance(event, MarkEvent) and mouth is not None:
                mouth.on_mark(event.name)
            elif isinstance(event, StopEvent):
                say("stop    caller hung up")
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        say(f"!! stream error: {e!r}")
    finally:
        if turn is not None:
            turn.push_hangup()  # wakes the engine if it is waiting for a key
        ended.set()
        outbox.close()
        try:
            await asyncio.wait_for(writer, timeout=2)
        except Exception:
            pass
        say("socket  closed")
