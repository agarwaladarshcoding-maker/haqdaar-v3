"""haqdaar/server.py

FastAPI entry point serving telephony webhooks and audio streams (T14, T19).
Exposes `app` for uvicorn (make run).
"""
from __future__ import annotations
import os
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
)
from tools.tone import generate_tone

load_dotenv()

app = FastAPI(title="haqdaar")


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
    try:
        while True:
            text = await websocket.receive_text()
            event = parse_event(text)
            if isinstance(event, StartEvent):
                tone_bytes = generate_tone()
                media_msg = build_media(event.stream_sid, tone_bytes)
                await websocket.send_json(media_msg)
                mark_msg = build_mark(event.stream_sid, "tone_end")
                await websocket.send_json(mark_msg)
            elif isinstance(event, DtmfEvent):
                print(f"dtmf {event.digit}", flush=True)
                if event.digit == "9":
                    await websocket.close()
                    break
            elif isinstance(event, MarkEvent):
                print(f"mark {event.name}", flush=True)
    except WebSocketDisconnect:
        pass
