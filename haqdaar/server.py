"""haqdaar/server.py

FastAPI entry point serving telephony webhooks and audio streams (T14, T19).
Exposes `app` for uvicorn (make run).

Plan 2.7: `/answer` sends the line to `/stream`, where the real keypad call runs: the engine
on its own thread, Mouth for what the caller hears, Turn for keys and silence.

Step 1.0 (plan v5): `/answer` must be signed by the phone provider and `/stream` takes only a call
`/answer` saw; a call ends after CALL_CEILING_S; a stream that drops is opened again
(`/answer-again`) and the call goes on; every call ends with a line report.

Privacy: the caller's number is never stored. `/answer` keeps only its sha256, and only until
the stream for that call starts.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import threading
import time
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Any, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect

from haqdaar.contracts import tunables
from haqdaar.contracts.tunables import NGROK_DOMAIN
from haqdaar.audio.telephony import (
    parse_event,
    build_end_twiml,
    build_stream_twiml,
    request_is_signed,
    SIGNATURE_HEADER,
    StartEvent,
    DtmfEvent,
    MarkEvent,
    MediaEvent,
    StopEvent,
)

load_dotenv()

# Step 1.0: no open /docs, /redoc or /openapi.json pages on a server the world can reach.
app = FastAPI(title="haqdaar", docs_url=None, redoc_url=None, openapi_url=None)


def say(line: str) -> None:
    """One call event per line, with the time. `make run` also copies it to logs/server.log."""
    print(f"{datetime.now():%H:%M:%S.%f}"[:-3] + f"  {line}", flush=True)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/live")
def live() -> dict[str, bool]:
    """Phase 4: is a call live? tools/photo_back waits on this before it rings the caller back."""
    return {"active": is_call_active()}


# One caller at a time guard (D14)
_ACTIVE_CALL: bool = False
_ACTIVE_CALL_LOCK = threading.Lock()


def is_call_active() -> bool:
    with _ACTIVE_CALL_LOCK:
        return _ACTIVE_CALL


def try_acquire_call() -> bool:
    global _ACTIVE_CALL
    with _ACTIVE_CALL_LOCK:
        if _ACTIVE_CALL:
            return False
        _ACTIVE_CALL = True
        return True


def release_call() -> None:
    global _ACTIVE_CALL
    with _ACTIVE_CALL_LOCK:
        _ACTIVE_CALL = False


# call id -> sha256 of the caller's number, from /answer until that call's stream starts.
_CALLER_HASH: dict[str, str] = {}
_CALLER_HASH_TS: dict[str, float] = {}
# call id -> the raw number of the PERSON, same life as the hash. In memory only: never in a log row,
# the trace or stdout. The talk needs it to send the photo link by SMS.
_CALLER_NUMBER: dict[str, str] = {}


def _prune_caller_hashes(max_age_s: float = 300.0) -> None:
    now = time.monotonic()
    stale = [k for k, ts in _CALLER_HASH_TS.items() if now - ts > max_age_s]
    for k in stale:
        _CALLER_HASH.pop(k, None)
        _CALLER_HASH_TS.pop(k, None)
        _CALLER_NUMBER.pop(k, None)


def caller_hash(number: str) -> str:
    return hashlib.sha256(number.encode("utf-8")).hexdigest() if number else ""


def _domain() -> str:
    return NGROK_DOMAIN or os.environ.get("NGROK_DOMAIN", "")


async def _phone_form(request: Request, path: str) -> Optional[dict[str, str]]:
    """The fields of a request from the phone line. None when it is not signed by the phone
    provider (step 1.0): anyone can find the tunnel's address, only the provider can sign."""
    body = (await request.body()).decode("utf-8", "replace")
    form = {k: v[0] for k, v in urllib.parse.parse_qs(body, keep_blank_values=True).items()}
    if tunables.PHONE_CHECK:
        url = f"https://{_domain()}{path}" + (f"?{request.url.query}" if request.url.query else "")
        if not request_is_signed(url, form, request.headers.get(SIGNATURE_HEADER, "")):
            say(f"!! {path} refused: not signed by the phone provider (PHONE_CHECK=false turns the check off)")
            return None
    return form


def _stream_twiml() -> str:
    again = f"https://{_domain()}/answer-again" if tunables.LINE_RECONNECT else ""
    return build_stream_twiml(f"wss://{_domain()}/stream", keep_call_alive=False, again_url=again)


@app.api_route("/answer", methods=["GET", "POST"])
async def answer(request: Request) -> Response:
    """TwiML voice webhook returning Stream instruction (T14, T19).

    Hard rules:
    - keepCallAlive="false"
    - Stream URL takes no query string.
    - Response Content-Type is text/xml.
    """
    form = await _phone_form(request, "/answer")
    if form is None:
        return Response(status_code=403)
    call_id = form.get("CallSid", "")
    _prune_caller_hashes()
    if call_id:
        _CALLER_HASH[call_id] = caller_hash(form.get("From", ""))
        _CALLER_HASH_TS[call_id] = time.monotonic()
        # "outbound-api": we placed the call, so the person is the one we rang (To), not From.
        _CALLER_NUMBER[call_id] = form.get("To", "") if form.get("Direction", "") == "outbound-api" else form.get("From", "")
    say("answer  line picked up, sent stream XML")
    return Response(content=_stream_twiml(), media_type="text/xml")


BACK_NOT_REACHED = ("no-answer", "busy", "failed", "canceled")      # how a call-back ends when nobody heard it


@app.post("/back-status")
async def back_status(request: Request) -> Response:
    """The phone line says how a call-back ended (tools/photo_back asks for it, with ?token=). Not reached:
    the answer goes by SMS. In a thread: it calls a model and a voice, and the line wants a quick reply."""
    form = await _phone_form(request, "/back-status")
    if form is None:
        return Response(status_code=403)
    token, status = request.query_params.get("token", ""), form.get("CallStatus", "")
    if token and status in BACK_NOT_REACHED:
        from haqdaar.photo import back_msg

        say(f"back    call-back of case ..{token[-3:]} ended: {status}; the answer goes by SMS")
        threading.Thread(target=back_msg.send, args=(token, status), daemon=True).start()
    return Response(status_code=204)


@app.post("/answer-again")
async def answer_again(request: Request) -> Response:
    """Step 1.0: the phone line asks this when a stream ends and the caller is still there.

    We ended the call (or do not know it): hang up, as before. The stream dropped: open it again,
    the call goes on. Too many drops, or too long: the line's own voice says so, then hangs up.
    """
    form = await _phone_form(request, "/answer-again")
    if form is None:
        return Response(status_code=403)
    line = _LINE
    if line is None or line.call_id != form.get("CallSid", "") or line.ended.is_set() or line.finished:
        return Response(content=build_end_twiml(), media_type="text/xml")
    now = time.monotonic()
    line.tries += 1
    since = now - (line.first_drop or now)
    if line.tries > tunables.LINE_RECONNECT_TRIES or since > tunables.LINE_RECONNECT_WAIT_S:
        line.why = f"the stream dropped {line.tries} time(s) and was not opened again"
        line.note(f"!! line    {line.why}; the caller is told the line dropped")
        line.ended.set()
        _finish(line)
        return Response(content=build_end_twiml(line_dropped=True), media_type="text/xml")
    line.note(f"line    the phone line asks for the stream again (try {line.tries})")
    return Response(content=_stream_twiml(), media_type="text/xml")


# --- plan 2.7: the real keypad call ---------------------------------------------------

_CALL: dict[str, Any] = {}  # the loaded snapshot and pool, shared by every call


def _corpus_and_pool() -> tuple[Any, Any]:
    """Load the CURRENT snapshot once. Corpus.load refuses it if any clip is missing."""
    if "corpus" not in _CALL:
        from haqdaar.audio.pool import AudioPool
        from haqdaar.data.corpus import Corpus

        corpus = Corpus.load("CURRENT")
        pool = AudioPool(tier2="none")
        # 3.8: pin only the fixed lines, chips and keys (~7 MB). Scheme clips are read from disk
        # when a scheme is read (~100 KB each, a few ms) and kept in the LRU.
        manifest = Path(tunables.SNAPSHOTS_DIR) / corpus.snapshot_id / "manifest.json"
        pool.warm(manifest=json.loads(manifest.read_text(encoding="utf-8")))
        _CALL["corpus"], _CALL["pool"] = corpus, pool
        say(f"corpus  {corpus.snapshot_id} loaded")
        if tunables.TALK_ONLY:
            from haqdaar.data import scheme_index

            index = scheme_index.get(corpus.snapshot_id)
            say(f"search  {len(index.ids)} schemes" + ("" if index._vectors is not None else " (names only: no model)"))
            if tunables.TALK_CHUNKS:    # 1.5: load the parts index now, never on a caller's first turn
                from haqdaar.data import chunk_index

                try:
                    parts = chunk_index.get(corpus.snapshot_id)
                    say(f"parts   {len(parts.chunks)} parts" + ("" if parts._vectors is not None else " (names only: no model)"))
                except Exception as exc:
                    say(f"!! parts index did not load ({exc}); the talk sends whole cards")
            if tunables.CUT_IN_GATE:
                from haqdaar.audio import silero

                say("cut-in  gate on, " + ("Silero voice check" if silero.make() else "LOUDNESS check (Silero did not load)"))
        from haqdaar.contracts.types import FIXED_LINE_IDS

        for line_id in FIXED_LINE_IDS:
            quiet = [l for l in tunables.LANGS_OFFERED
                     if not (corpus.audio(line_id, l) or corpus.audio(line_id, "all"))]
            if quiet:
                say(f"!! line {line_id} has no sound in {','.join(quiet)}")
    return _CALL["corpus"], _CALL["pool"]


class _Line:
    """Step 1.0: what of the one call must outlive a socket, so a dropped stream can be opened
    again and the same talk goes on. Also holds the numbers of the line report."""

    def __init__(self, call_id: str) -> None:
        self.call_id = call_id
        self.mouth: Any = None
        self.turn: Any = None
        self.outbox: Any = None
        self.note: Any = say
        self.gen = 0                      # which socket holds the call; an older socket's clean-up does nothing
        self.ended = threading.Event()    # we ended the call (goodbye, the cap, the engine is done)
        self.finished = False             # the engine was told the call is over
        self.dropped_at: Optional[float] = None   # when the stream dropped; None while a stream is up
        self.first_drop: Optional[float] = None
        self.drops = 0
        self.tries = 0                    # times the phone line asked for the stream again
        self.timers: list[threading.Timer] = []
        self.why = ""                     # why the line closed
        # What came in from the phone, so a quiet call can be told from a broken line afterwards.
        self.came = {"frames": 0, "bytes": 0, "keys": 0, "marks": 0, "last": 0.0, "t0": 0.0, "gap": 0.0}
        self.slow = {"stt_ms": 0, "model_ms": 0, "voice_ms": 0}   # slowest Sarvam ear, model, Sarvam voice

    def after(self, seconds: float, what: Any) -> None:
        timer = threading.Timer(seconds, what)
        timer.daemon = True
        self.timers.append(timer)
        timer.start()

    def tap(self, rec: Any) -> None:
        """Sees every row of the call log; keeps the slowest reply of each service."""
        if isinstance(rec, dict) and rec.get("ev") == "act":
            for key in self.slow:
                if isinstance(rec.get(key), (int, float)):
                    self.slow[key] = max(self.slow[key], int(rec[key]))

    def report(self) -> dict[str, Any]:
        """The line report (step 1.0): how the network was in this call."""
        why = self.why or ("we ended the call" if self.ended.is_set() else "not known")
        return {"ev": "line", "why": why, "gap_s": round(self.came["gap"], 2),
                "ahead_s": round(getattr(self.mouth, "ahead_max", 0.0), 1),
                "drops": self.drops, **self.slow}


_LINE: Optional[_Line] = None
_LINE_LOCK = threading.Lock()


def report_words(r: dict[str, Any]) -> str:
    return (f"line    report: closed because {r['why']}; longest gap in the caller's sound {r['gap_s']:.1f} s; "
            f"our sound was sent up to {r['ahead_s']:.1f} s ahead; slowest Sarvam ear {r['stt_ms']} ms, "
            f"model {r['model_ms']} ms, Sarvam voice {r['voice_ms']} ms; the stream dropped {r['drops']} time(s)")


def _hang_up(line: _Line) -> None:
    """We end the call: close the socket. With no socket up (the stream dropped) finish at once."""
    if not line.ended.is_set():
        line.ended.set()
        outbox = line.outbox
        if outbox is not None:
            outbox.emit({"event": "_close"})
            outbox.close()
    if line.dropped_at is not None:
        _finish(line)


def _finish(line: _Line) -> None:
    """The call is over for good: free the line and wake the engine. Safe to call twice."""
    global _LINE
    with _LINE_LOCK:
        if line.finished:
            return
        line.finished = True
        if _LINE is line:
            _LINE = None
    for timer in line.timers:
        timer.cancel()
    release_call()
    if line.turn is not None:
        line.turn.push_hangup()  # wakes the engine if it is waiting for a key


def _park(line: _Line) -> None:
    """The stream dropped and nobody hung up: keep the call, the phone line will ask for the stream again."""
    line.dropped_at = time.monotonic()
    line.first_drop = line.first_drop or line.dropped_at
    line.drops += 1
    gen = line.gen
    line.note(f"!! line    the stream dropped; the call is kept for {tunables.LINE_RECONNECT_WAIT_S:.0f} s")

    def gone() -> None:
        if line.dropped_at is not None and line.gen == gen and not line.finished:
            line.why = line.why or f"the stream dropped and did not come back in {tunables.LINE_RECONNECT_WAIT_S:.0f} s"
            line.note(f"!! line    {line.why}")
            _finish(line)
    line.after(tunables.LINE_RECONNECT_WAIT_S, gone)


def _run_engine(call_id: str, snapshot_id: str, number_hash: str, audio: Any, corpus: Any,
                done: Any, trace: Any = None, line: Optional[_Line] = None) -> None:
    from haqdaar.data.log import Log
    from haqdaar.engine.call import Engine
    from haqdaar.model.router import Model

    from haqdaar.photo import back_msg

    note = say if trace is None else (lambda line: (say(line), trace(line)))
    waiting = back_msg.back_token()     # a call-back waits: this call is it
    try:
        log = Log.open(call_id=call_id, snapshot_id=snapshot_id, caller_hash=number_hash,
                       logs_dir=tunables.CALL_LOGS_DIR)
        if trace is not None:
            log.tap = trace.record
        if line is not None:
            # The line report is the last row before the close row of the call's log.
            copy, close = log.tap, log.close

            def tap(rec: Any) -> None:
                line.tap(rec)
                if copy is not None:
                    copy(rec)

            def close_with_report(*args: Any, **kwargs: Any) -> None:
                log.write(line.report())
                close(*args, **kwargs)
            log.tap, log.close = tap, close_with_report  # type: ignore[method-assign]
        model = Model(corpus=corpus)
        Engine.run_call(audio=audio, model=model, corpus=corpus, log=log)
        note(f"call    {call_id} finished")
    except Exception as e:  # never leave the caller on a silent line
        note(f"!! engine error: {e!r}")
    finally:
        done()
        if back_msg.catch_drop(waiting):    # the call ended and its answer was not said in full
            note("back    the call-back did not finish: the answer goes by SMS")
        if line is not None:
            note(report_words(line.report()))
        if trace is not None:
            trace.close()


@app.websocket("/stream")
async def stream_endpoint(websocket: WebSocket) -> None:
    """One real call with spoken and keypad support. One caller at a time (D14)."""
    global _LINE
    from haqdaar.audio.ear import Ear
    from haqdaar.audio.mouth import Mouth, Outbox
    from haqdaar.audio.phone import PhoneAudio
    from haqdaar.audio.turn import Turn
    from haqdaar.data.trace import Trace

    # A busy line still lets a socket in when a call is kept: it may be that call's stream coming
    # back (step 1.0). Its start message says which call it is.
    holds = try_acquire_call()
    if not holds and not (tunables.LINE_RECONNECT and _LINE is not None and not _LINE.ended.is_set()):
        say("stream  refused busy: another call is active")
        await websocket.accept()
        await websocket.close(code=1008, reason="busy")
        return

    await websocket.accept()
    loop = asyncio.get_running_loop()

    async def send(msg: dict[str, Any]) -> None:
        if msg.get("event") == "_close":
            await websocket.close(code=msg.get("code", 1000))
        else:
            await websocket.send_json(msg)

    outbox = Outbox(loop, send)
    writer = asyncio.create_task(outbox.run())
    mouth: Optional[Mouth] = None
    turn: Optional[Turn] = None
    line: Optional[_Line] = None
    gen = 0
    note = say
    stopped = False     # the phone line said the caller hung up
    failed = ""

    def no_start() -> None:  # step 1.0: a socket that is not a call may not hold the line
        if line is None:
            say(f"!! stream  no start message in {tunables.STREAM_START_WAIT_S:.0f} s: closed")
            outbox.emit({"event": "_close", "code": 1008})
    waiting = loop.call_later(tunables.STREAM_START_WAIT_S, no_start)

    try:
        while True:
            event = parse_event(await websocket.receive_text())
            if isinstance(event, StartEvent) and line is None:
                call_id = event.call_sid or f"call_{int(time.time())}"
                kept = _LINE
                if kept is not None and kept.call_id == call_id and not kept.ended.is_set() and not kept.finished:
                    # The same call on a new stream: the talk goes on.
                    line, kept.gen = kept, kept.gen + 1
                    gen = line.gen
                    old, line.outbox = line.outbox, outbox
                    if old is not None and not old.closed:
                        old.emit({"event": "_close"})
                        old.close()
                    away = time.monotonic() - line.dropped_at if line.dropped_at is not None else 0.0
                    line.dropped_at = None
                    mouth, turn, note = line.mouth, line.turn, line.note
                    again = mouth.rebind(outbox.emit, event.stream_sid)
                    note(f"line    the stream is back after {away:.1f} s; {again} clip(s) said again")
                    continue
                if not holds:
                    if kept is not None and kept.dropped_at is not None and call_id in _CALLER_HASH:
                        # A new call while a dropped one is kept: that caller is gone. The line is one caller's.
                        kept.why = kept.why or "the stream dropped and a new call came"
                        _finish(kept)
                        holds = try_acquire_call()
                    if not holds:
                        say("stream  refused busy: another call is active")
                        outbox.emit({"event": "_close", "code": 1008})
                        continue
                if tunables.PHONE_CHECK and call_id not in _CALLER_HASH:
                    say("!! stream  refused: /answer never saw this call (PHONE_CHECK=false turns the check off)")
                    outbox.emit({"event": "_close", "code": 1008})
                    continue
                corpus, pool = _corpus_and_pool()
                # The timed copy of this call for the call page (`make calls-ui`).
                trace = Trace(call_id, tunables.CALL_LOGS_DIR, corpus.snapshot_id)

                def note(line: str, trace: Trace = trace) -> None:
                    say(line)
                    trace(line)

                line = _Line(call_id)
                line.outbox, line.note = outbox, note
                hang_up = (lambda held=line: _hang_up(held))
                mouth = line.mouth = Mouth(outbox.emit, event.stream_sid, log=note)
                vad = None
                if tunables.CUT_IN_GATE and tunables.TALK_ONLY:     # 7.14: a noise is not a voice
                    from haqdaar.audio import silero

                    vad = silero.make(log=note)
                ear = Ear(log=note, vad=vad)
                turn = line.turn = Turn(mouth, ear=ear, trace=trace, log=note)
                audio = PhoneAudio(corpus, pool, mouth, turn, close=hang_up, log=note, trace=trace)
                number_hash = _CALLER_HASH.pop(call_id, "")
                _CALLER_HASH_TS.pop(call_id, None)
                audio.caller_number = _CALLER_NUMBER.pop(call_id, "")
                _LINE = line
                say(f"start   call ..{call_id[-6:]}")

                def cap(held: _Line = line) -> None:  # step 1.0: no call holds the line for ever
                    if not held.finished and not held.ended.is_set():
                        held.why = f"the call passed {tunables.CALL_CEILING_S} s"
                        held.note(f"!! line    {held.why}: closed")
                        _hang_up(held)
                line.after(tunables.CALL_CEILING_S, cap)
                threading.Thread(
                    target=_run_engine,
                    args=(call_id, corpus.snapshot_id, number_hash, audio, corpus, hang_up, trace, line),
                    daemon=True,
                ).start()
            elif isinstance(event, MediaEvent) and turn is not None and line is not None:
                came = line.came
                now = time.monotonic()
                if not came["frames"]:
                    came["t0"] = now
                    note("phone   first sound from the caller's side arrived")
                elif now - came["last"] > 1.0 and line.gen == gen and came.get("gen", gen) == gen:
                    note(f"!! phone   no sound came from the caller's side for {now - came['last']:.1f} s")
                if came["frames"] and came.get("gen", gen) == gen:
                    came["gap"] = max(came["gap"], now - came["last"])
                came["gen"] = gen
                came["frames"] += 1
                came["bytes"] += len(event.payload_bytes)
                came["last"] = now
                turn.push_media(event.payload_bytes)
            elif isinstance(event, DtmfEvent) and turn is not None and line is not None:
                line.came["keys"] += 1
                say(f"<- dtmf {event.digit}")
                turn.push_key(event.digit)
            elif isinstance(event, MarkEvent) and mouth is not None and line is not None:
                line.came["marks"] += 1
                mouth.on_mark(event.name)
            elif isinstance(event, StopEvent):
                note("stop    caller hung up")
                stopped = True
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        failed = repr(e)
        say(f"!! stream error: {e!r}")
    finally:
        waiting.cancel()
        over = True
        if line is None:
            if holds:
                release_call()
        elif line.gen != gen:
            over = False                    # a newer stream holds this call
        elif not (stopped or failed or line.ended.is_set() or line.finished) and tunables.LINE_RECONNECT:
            over = False
            _park(line)                     # dropped: the call is kept
        else:
            line.why = line.why or ("the caller hung up" if stopped else f"stream error {failed}" if failed
                                    else "we ended the call" if line.ended.is_set() else "the stream dropped")
            _finish(line)
        outbox.close()
        try:
            await asyncio.wait_for(writer, timeout=2)
        except Exception:
            pass
        if line is not None and over:
            came = line.came
            if came["frames"]:
                say(f"phone   in all: {came['bytes'] / 8000:.1f} s of sound from the caller's side over "
                    f"{came['last'] - came['t0']:.1f} s, {came['keys']} key(s), {came['marks']} clip(s) played to the end")
            else:
                say("!! phone   NO sound at all came from the caller's side")
        say("socket  closed")
