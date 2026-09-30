"""Plan 2.1 — the renderer, with a fake voice (no network, no money)."""
from __future__ import annotations

import io
import math
import struct
import wave

import httpx
import pytest

from haqdaar.audio import render as R
from haqdaar.data.pipeline.texts import Text, _text


def _texts() -> list[Text]:
    return [
        _text("en", "Press 1 for Hindi.", "line", "a"),
        _text("hi", "हिंदी के लिए 1 दबाएँ।", "line", "a"),
        _text("mr", "मराठीसाठी 2 दाबा.", "line", "a"),
        _text("all", "नमस्ते।\nनमस्कार.\nNamaste.", "line", "greeting_trilingual"),
    ]


class FakeVoice:
    def __init__(self, fail_on: dict[int, R.RenderError] | None = None):
        self.calls: list[tuple[str, str]] = []
        self.fail_on = fail_on or {}

    def __call__(self, text: str, lang: str) -> bytes:
        self.calls.append((lang, text))
        err = self.fail_on.get(len(self.calls))
        if err is not None:
            raise err
        return b"\x10" * 800


def test_renders_everything_then_second_run_sends_nothing(tmp_path):
    voice = FakeVoice()
    result = R.render(_texts(), speak=voice, audio_dir=tmp_path, workers=3)
    assert result.missing == 0 and result.rendered == 4 and not result.failed
    for item in _texts():
        assert R.has_clip(tmp_path, item.key)
    assert len(voice.calls) == 6  # 3 single lines + the greeting's 3 parts

    again = FakeVoice()
    result = R.render(_texts(), speak=again, audio_dir=tmp_path)
    assert again.calls == [] and result.present == 4 and result.missing == 0


def test_greeting_speaks_each_part_in_its_language(tmp_path):
    voice = FakeVoice()
    R.render(_texts()[3:], speak=voice, audio_dir=tmp_path)
    assert [lang for lang, _ in voice.calls] == ["hi", "mr", "en"]


def test_clip_has_quiet_tail(tmp_path):
    item = _texts()[0]
    R.render([item], speak=FakeVoice(), audio_dir=tmp_path)
    data = R.clip_path(tmp_path, item.key).read_bytes()
    assert data.endswith(R._tail()) and len(data) == 800 + len(R._tail())


def test_a_silent_stub_counts_as_missing(tmp_path):
    item = _texts()[0]
    R.clip_path(tmp_path, item.key).write_bytes(b"\xff" * 960)
    assert not R.has_clip(tmp_path, item.key)
    voice = FakeVoice()
    R.render([item], speak=voice, audio_dir=tmp_path)
    assert len(voice.calls) == 1 and R.has_clip(tmp_path, item.key)


def test_count_only_sends_nothing(tmp_path):
    result = R.render(_texts(), audio_dir=tmp_path)
    assert result.missing == 4 and result.rendered == 0


def test_402_stops_the_run(tmp_path):
    voice = FakeVoice(fail_on={2: R.RenderError("402 no credits", fatal=True)})
    result = R.render(_texts(), speak=voice, audio_dir=tmp_path, workers=1)
    assert result.stopped and "402" in result.stopped
    assert len(voice.calls) == 2  # nothing more is asked for after the 402
    assert result.rendered == 1 and result.missing == 3


def test_one_bad_text_does_not_stop_the_rest(tmp_path):
    voice = FakeVoice(fail_on={1: R.RenderError("400 bad input")})
    result = R.render(_texts(), speak=voice, audio_dir=tmp_path, workers=1)
    assert result.stopped is None and len(result.failed) == 1
    assert result.rendered == 3 and result.missing == 1


def _wav(rate: int, seconds: float) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(rate * seconds)
        w.writeframes(b"".join(
            struct.pack("<h", int(8000 * math.sin(i / 10))) for i in range(n)
        ))
    return buf.getvalue()


def test_wav_to_ulaw_resamples_to_8k():
    ulaw = R.wav_to_ulaw(_wav(22050, 1.0))
    assert abs(len(ulaw) - 8000) < 20  # one byte per sample at 8 kHz


def test_stretch_makes_it_longer():
    ulaw = R.wav_to_ulaw(_wav(8000, 1.0))
    slow = R.stretch(ulaw, 0.8)
    assert 1.15 < len(slow) / len(ulaw) < 1.35


class _Resp:
    def __init__(self, status: int, body: dict | None = None):
        self.status_code = status
        self._body = body or {}
        self.text = str(self._body)

    def json(self):
        return self._body


def test_sarvam_402_is_fatal(monkeypatch, tmp_path):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(402, {"error": "no credits"}))
    client = R.SarvamTTS(api_key="test", ledger_path=tmp_path / "l.jsonl")
    with pytest.raises(R.RenderError) as e:
        client.speak("hello", "en")
    assert e.value.fatal


def test_sarvam_ok_writes_ledger(monkeypatch, tmp_path):
    import base64

    sent = {}

    def post(url, headers, json, timeout):
        sent.update(json)
        return _Resp(200, {"audios": [base64.b64encode(_wav(8000, 0.5)).decode()]})

    monkeypatch.setattr(httpx, "post", post)
    client = R.SarvamTTS(api_key="test", ledger_path=tmp_path / "l.jsonl")
    ulaw = client.speak("नमस्कार", "mr")
    assert len(ulaw) == 4000
    assert sent["target_language_code"] == "mr-IN" and sent["speaker"]
    assert client.requests == 1 and (tmp_path / "l.jsonl").read_text().count("\n") == 1


def test_429_is_retried_then_succeeds(monkeypatch, tmp_path):
    import base64

    replies = [_Resp(429, {"error": "rate"}),
               _Resp(200, {"audios": [base64.b64encode(_wav(8000, 0.25)).decode()]})]
    monkeypatch.setattr(httpx, "post", lambda *a, **k: replies.pop(0))
    slept: list[float] = []
    monkeypatch.setattr(R.time, "sleep", slept.append)
    client = R.SarvamTTS(api_key="test", ledger_path=tmp_path / "l.jsonl")
    assert len(client.speak("hi", "en")) == 2000
    assert R.tunables.TTS_429_WAIT_S in slept
