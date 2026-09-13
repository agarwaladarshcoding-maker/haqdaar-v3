"""haqdaar/server.py

FastAPI entry point serving telephony webhooks and audio streams (T14, T19).
Exposes `app` for uvicorn (make run).
"""
from __future__ import annotations
import os
import time
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect

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


@app.api_route("/answer", methods=["GET", "POST"])
def answer() -> Response:
    """TwiML voice webhook returning Stream instruction (T14, T19).

    Hard rules:
    - keepCallAlive="false"
    - Stream URL takes no query string.
    - Response Content-Type is text/xml.
    """
    domain = NGROK_DOMAIN or os.environ.get("NGROK_DOMAIN", "")
    stream_url = f"wss://{domain}/stream"
    say("answer  line picked up, sent stream XML")
    twiml = build_stream_twiml(stream_url, keep_call_alive=False)
    return Response(content=twiml, media_type="text/xml")


@app.websocket("/stream")
async def stream_endpoint(websocket: WebSocket) -> None:
    """Bidirectional telephony media stream WebSocket.

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
