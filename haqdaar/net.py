"""haqdaar/net.py

One shared httpx client for the call path (Sarvam and Groq), and one quick second try.

Why: a new client per request pays a new TCP + TLS handshake every time, which a weak network
(a phone hotspot) turns into a long pause. One client kept for the life of the process keeps the
connections open between turns. httpx closes an idle connection after 5 s, shorter than the gap
between two turns, so the keep-alive is NET_KEEPALIVE_S.

The second try: a network error (connect error, reset, a kept-open connection the far end has
already closed) is tried once more at once, with no sleep. A time-out is NOT tried again (every
site has a time budget and its callers already handle "timeout"). An HTTP reply with any status is
NOT tried again either (the callers handle 429, 500 and the rest). So there is no retry loop.

Worst case: a network error that comes late can cost one more `timeout` on the second try. A
refused or reset connection comes back at once, so in practice the second try costs little.
"""
from __future__ import annotations

import threading
from contextlib import ExitStack, contextmanager
from typing import Any, Iterator, Optional

import httpx

from haqdaar.contracts import tunables

_lock = threading.Lock()
_client: Optional[httpx.Client] = None


def _shared() -> httpx.Client:
    """The one client, built on first use. httpx.Client is safe to use from several threads."""
    global _client
    with _lock:
        if _client is None:
            _client = httpx.Client(limits=httpx.Limits(keepalive_expiry=tunables.NET_KEEPALIVE_S))
        return _client


def _worth_a_second_try(exc: Exception) -> bool:
    """A network error, but not a time-out."""
    return isinstance(exc, httpx.TransportError) and not isinstance(exc, httpx.TimeoutException)


def post(url: str, *, timeout: Optional[float], **kw: Any) -> httpx.Response:
    """client.post on the shared client. One quick second try on a network error."""
    client = _shared()
    try:
        return client.post(url, timeout=timeout, **kw)
    except httpx.TransportError as exc:
        if not _worth_a_second_try(exc):
            raise
    return client.post(url, timeout=timeout, **kw)


@contextmanager
def stream(method: str, url: str, *, timeout: Optional[float], **kw: Any) -> Iterator[httpx.Response]:
    """Like httpx.stream, on the shared client. The second try is only for opening the stream
    (before any sound is handed on); an error while reading the body is raised as it comes."""
    client = _shared()
    with ExitStack() as stack:
        try:
            response = stack.enter_context(client.stream(method, url, timeout=timeout, **kw))
        except httpx.TransportError as exc:
            if not _worth_a_second_try(exc):
                raise
            response = stack.enter_context(client.stream(method, url, timeout=timeout, **kw))
        yield response
