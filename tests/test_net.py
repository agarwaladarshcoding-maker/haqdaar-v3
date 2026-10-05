"""Tests for haqdaar/net.py: the shared client and the one quick second try.

No network. The shared client's transport is a httpx.MockTransport that is scripted per test,
so the real send path runs but nothing leaves the process.
"""
from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

from haqdaar import net
from haqdaar.audio import live_tts
from haqdaar.audio.ear import GroqWhisperSTT, SarvamSTT
from haqdaar.contracts import tunables
from haqdaar.model.client import GroqModelClient
from haqdaar.model.translate import AnswerTranslator

URL = "http://testserver/x"
_REAL_SEND = httpx.Client.send     # taken at import, before conftest's guard replaces it


class _ScriptedClient(httpx.Client):
    """A client whose transport is scripted. Its send skips conftest's host guard, because the
    site tests use the real Sarvam / Groq addresses; no byte leaves the process (MockTransport)."""

    def send(self, request, *args, **kwargs):
        return _REAL_SEND(self, request, *args, **kwargs)


def _script(monkeypatch: pytest.MonkeyPatch, *steps: Any) -> list[httpx.Request]:
    """Answer requests in order: an Exception is raised, a callable gets the request, else a
    httpx.Response is returned. The last step repeats. Returns the list of requests seen."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        step = steps[min(len(seen), len(steps) - 1)]
        seen.append(request)
        if isinstance(step, Exception):
            raise step
        return step(request) if callable(step) else step

    monkeypatch.setattr(net, "_client", _ScriptedClient(transport=httpx.MockTransport(handler)))
    return seen


def _ok(payload: dict) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, json=payload)


def test_a_network_error_then_a_good_reply_gives_the_reply(monkeypatch):
    seen = _script(monkeypatch, httpx.ConnectError("down"), httpx.Response(200, text="ok"))
    assert net.post(URL, timeout=1.0).text == "ok"
    assert len(seen) == 2


def test_two_network_errors_raise_after_two_tries(monkeypatch):
    seen = _script(monkeypatch, httpx.RemoteProtocolError("closed"))
    with pytest.raises(httpx.RemoteProtocolError):
        net.post(URL, timeout=1.0)
    assert len(seen) == 2


def test_a_time_out_is_not_tried_again(monkeypatch):
    seen = _script(monkeypatch, httpx.ReadTimeout("slow"), httpx.Response(200))
    with pytest.raises(httpx.TimeoutException):
        net.post(URL, timeout=1.0)
    assert len(seen) == 1


def test_a_connect_time_out_is_not_tried_again(monkeypatch):
    seen = _script(monkeypatch, httpx.ConnectTimeout("slow"), httpx.Response(200))
    with pytest.raises(httpx.ConnectTimeout):
        net.post(URL, timeout=1.0)
    assert len(seen) == 1


def test_an_http_error_status_is_returned_not_tried_again(monkeypatch):
    seen = _script(monkeypatch, httpx.Response(500), httpx.Response(200))
    assert net.post(URL, timeout=1.0).status_code == 500
    assert len(seen) == 1


def test_one_client_is_used_for_every_request(monkeypatch):
    _script(monkeypatch, httpx.Response(200))
    first = net._shared()
    net.post(URL, timeout=1.0)
    net.post(URL, timeout=2.0)
    assert net._shared() is first


def test_the_client_is_built_once_with_the_keep_alive(monkeypatch):
    monkeypatch.setattr(net, "_client", None)
    monkeypatch.setattr(tunables, "NET_KEEPALIVE_S", 42.0)
    client = net._shared()
    try:
        assert net._shared() is client
        assert client._transport._pool._keepalive_expiry == 42.0
    finally:
        client.close()


def test_each_request_carries_its_own_timeout(monkeypatch):
    seen = _script(monkeypatch, httpx.Response(200))
    net.post(URL, timeout=1.5)
    net.post(URL, timeout=7.0)
    assert [r.extensions["timeout"]["read"] for r in seen] == [1.5, 7.0]


def test_the_stream_is_tried_again_when_it_fails_to_open(monkeypatch):
    seen = _script(
        monkeypatch, httpx.ConnectError("down"), httpx.Response(200, content=b"abc"),
    )
    with net.stream("POST", URL, timeout=1.0) as response:
        assert b"".join(response.iter_bytes()) == b"abc"
    assert len(seen) == 2


def test_the_stream_time_out_is_not_tried_again(monkeypatch):
    seen = _script(monkeypatch, httpx.ConnectTimeout("slow"), httpx.Response(200))
    with pytest.raises(httpx.ConnectTimeout):
        with net.stream("POST", URL, timeout=1.0):
            pass
    assert len(seen) == 1


def test_a_stream_error_after_a_chunk_is_raised_and_not_tried_again(monkeypatch):
    class Breaks(httpx.SyncByteStream):
        def __iter__(self):
            yield b"abc"
            raise httpx.ReadError("cut")

    seen = _script(monkeypatch, httpx.Response(200, stream=Breaks()), httpx.Response(200, content=b"zzz"))
    got: list[bytes] = []
    with pytest.raises(httpx.ReadError):
        with net.stream("POST", URL, timeout=1.0) as response:
            for chunk in response.iter_bytes():
                got.append(chunk)
    assert got == [b"abc"]
    assert len(seen) == 1


# --- one test per site: a network error, then a good reply, gives a good result ------------

def test_site_sarvam_stt(monkeypatch):
    seen = _script(
        monkeypatch, httpx.ConnectError("down"), _ok({"transcript": "hello", "language_code": "hi-IN"}),
    )
    res = SarvamSTT(api_key="k", model="saaras:v4").transcribe(b"wav", lang="hi")
    assert (res.success, res.transcript) == (True, "hello")
    assert len(seen) == 2


def test_site_groq_whisper_stt(monkeypatch):
    seen = _script(
        monkeypatch, httpx.RemoteProtocolError("closed"), _ok({"text": "kisan", "language": "hindi"}),
    )
    res = GroqWhisperSTT(api_key="k").transcribe(b"wav", lang="hi")
    assert (res.success, res.transcript) == (True, "kisan")
    assert len(seen) == 2


def test_site_model_call(monkeypatch, tmp_path):
    reply = {
        "choices": [{"message": {"content": json.dumps({"ok": True})}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    seen = _script(monkeypatch, httpx.ReadError("reset"), _ok(reply))
    client = GroqModelClient(api_key="k", ledger_path=tmp_path / "groq_usage.jsonl")
    res = client.call([{"role": "user", "content": "hi"}])
    assert (res.success, res.data) == (True, {"ok": True})
    assert len(seen) == 2


def test_site_translate(monkeypatch):
    seen = _script(monkeypatch, httpx.WriteError("reset"), _ok({"translated_text": " namaste "}))
    assert AnswerTranslator(api_key="k").translate("hello", "hi") == "namaste"
    assert len(seen) == 2


def test_site_voice_stream(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "k")
    monkeypatch.setattr(live_tts, "load_dotenv", lambda *a, **k: None)
    seen = _script(monkeypatch, httpx.ConnectError("down"), httpx.Response(200, content=b"\x01\x02\x03"))
    assert b"".join(live_tts.stream("hello", "en")) == b"\x01\x02\x03"
    assert len(seen) == 2
