"""Plan 2.5 — Mouth on a fake socket: a key stops the line in < 200 ms, and nothing freezes."""
from __future__ import annotations

import asyncio
import threading
import time

from haqdaar.audio.mouth import Mouth, Outbox
from haqdaar.contracts import tunables


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[tuple[float, dict]] = []

    async def send_json(self, msg: dict) -> None:
        await asyncio.sleep(0.001)  # a real socket takes a moment per message
        self.sent.append((time.monotonic(), msg))


def _events(sock: FakeSocket) -> list[str]:
    return [m["event"] for _, m in sock.sent]


def test_frames_then_a_mark_per_clip():
    out: list[dict] = []
    mouth = Mouth(out.append, "S")
    mouth.play([("a", b"\x10" * 20000), ("b", b"\x10" * 100)])
    assert [m["event"] for m in out] == ["media", "media", "media", "mark", "media", "mark"]
    assert out[3]["mark"]["name"].endswith(":a")


def test_marks_coming_back_mean_done():
    out: list[dict] = []
    mouth = Mouth(out.append, "S")
    mouth.play([("a", b"\x10" * 80000)])  # 10 s
    assert mouth.playing and mouth.remaining() > 9
    mouth.on_mark(out[-1]["mark"]["name"])
    assert not mouth.playing and mouth.remaining() == 0


def test_second_hash_repeats_slower():
    out: list[dict] = []
    mouth = Mouth(out.append, "S")
    audio = bytes((i * 37) % 200 + 20 for i in range(16000))  # 2 s of not-silence
    mouth.play([("line", audio)])

    def media_bytes() -> int:
        import base64
        n = sum(len(base64.b64decode(m["media"]["payload"])) for m in out if m["event"] == "media")
        out.clear()
        return n

    first = media_bytes()
    mouth.repeat()
    same = media_bytes()
    mouth.repeat()
    slow = media_bytes()
    assert same == first
    assert slow > first * 1.1  # stretched to SLOW_PACE
    mouth.play([("new", audio)])  # a new line resets the count
    media_bytes()
    mouth.repeat()
    assert media_bytes() == first


def test_a_key_stops_the_line_fast_and_nothing_freezes():
    sock = FakeSocket()
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    result: dict = {}

    async def main() -> None:
        outbox = Outbox(asyncio.get_running_loop(), sock.send_json)
        writer = asyncio.create_task(outbox.run())
        mouth = Mouth(outbox.emit, "S")
        result["mouth"], result["outbox"] = mouth, outbox
        ready.set()
        # The engine thread speaks a 30 s line...
        engine = threading.Thread(target=mouth.play, args=([("long", b"\x10" * 240000)],))
        engine.start()
        await asyncio.sleep(0.05)
        # ...and the caller presses a key: the socket loop calls clear() directly.
        pressed = time.monotonic()
        mouth.clear()
        # The loop must stay free: a tick scheduled now runs at once, not after a 10 s wait.
        t0 = time.monotonic()
        await asyncio.sleep(0)
        result["loop_gap"] = time.monotonic() - t0
        while not any(m["event"] == "clear" for _, m in sock.sent):
            await asyncio.sleep(0.005)
            if time.monotonic() - pressed > 5:
                break
        result["clear_after"] = next(
            (t for t, m in sock.sent if m["event"] == "clear"), float("inf")
        ) - pressed
        engine.join(timeout=5)
        outbox.close()
        await asyncio.wait_for(writer, timeout=5)

    loop.run_until_complete(asyncio.wait_for(main(), timeout=10))
    loop.close()
    assert result["clear_after"] < 0.2, result["clear_after"]
    assert result["loop_gap"] < 0.05
    assert not result["mouth"].playing
    assert "clear" in _events(sock)


def test_emit_after_close_is_dropped():
    loop = asyncio.new_event_loop()
    sent: list = []

    async def send(msg):
        sent.append(msg)

    outbox = Outbox(loop, send)
    outbox.close()
    outbox.emit({"event": "media"})  # the engine may still be talking after hang-up
    loop.run_until_complete(asyncio.wait_for(outbox.run(), timeout=2))
    loop.close()
    assert sent == []
    assert tunables.FRAME_BYTES == 8000


def test_a_clear_in_the_middle_of_a_send_stops_the_rest():
    out: list[dict] = []
    holder: dict = {}

    def emit(msg: dict) -> None:
        out.append(msg)
        media = sum(1 for m in out if m["event"] == "media")
        if media == 2 and not holder.get("done"):
            holder["done"] = True
            holder["mouth"].clear()  # the key lands while frame 3 of 10 is being cut

    mouth = Mouth(emit, "S")
    holder["mouth"] = mouth
    mouth.play([("a", b"\x10" * 80000), ("b", b"\x10" * 8000)])
    events = [m["event"] for m in out]
    assert events == ["media", "media", "clear"]
