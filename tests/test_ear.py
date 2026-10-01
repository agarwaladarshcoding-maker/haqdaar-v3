"""tests/test_ear.py

Unit and shape tests for haqdaar/audio/ear.py.
All tests are strictly offline and fake the HTTP layer (never touch the network).
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import struct
import wave

import httpx
import pytest

from haqdaar.audio.ear import (
    BASE_DIR,
    END_FRAMES,
    END_RMS,
    FRAME_PCM_BYTES,
    MAX_UTTERANCE_FRAMES,
    PRE_ROLL_FRAMES,
    SAMPLE_RATE,
    START_FRAMES,
    START_RMS,
    Ear,
    EnergyVAD,
    GroqWhisperSTT,
    SarvamSTT,
    SpeechToText,
    SttResult,
    frame_rms,
    load_audio,
    pcm_to_ulaw,
    pcm_to_wav,
    speech_to_text,
    ulaw_to_pcm,
)
from haqdaar.contracts.types import Digit, Hangup, Noise, Silence, Speech


def _make_pcm_frame(level: int) -> bytes:
    """Generate one 20 ms linear PCM frame (160 samples, 320 bytes) with a square/sine wave."""
    samples = [level if (i % 2 == 0) else -level for i in range(160)]
    return struct.pack(f"<{len(samples)}h", *samples)


def test_pcm_to_wav_padding():
    """Verify pcm_to_wav produces valid WAV with exactly 1.0s silence on each side."""
    raw_pcm = _make_pcm_frame(500) * 10  # 200 ms of audio (3200 bytes)
    wav_bytes = pcm_to_wav(raw_pcm, sample_rate=8000, pad_seconds=1.0)

    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 8000
        total_frames = w.getnframes()
        # 1.0s (8000) + 0.2s (1600) + 1.0s (8000) = 17600 frames
        assert total_frames == 8000 + 1600 + 8000
        frames = w.readframes(total_frames)

    # First 8000 samples (16000 bytes) must be all zeros
    assert frames[:16000] == b"\x00" * 16000
    # Last 8000 samples must be all zeros
    assert frames[-16000:] == b"\x00" * 16000


def test_ulaw_pcm_conversion_and_rms():
    """Verify roundtrip ulaw <-> pcm and RMS calculation."""
    pcm = _make_pcm_frame(1000)
    assert len(pcm) == FRAME_PCM_BYTES
    rms = frame_rms(pcm)
    assert rms == pytest.approx(1000, abs=10)

    ulaw = pcm_to_ulaw(pcm)
    assert len(ulaw) == 160
    pcm_recovered = ulaw_to_pcm(ulaw)
    assert len(pcm_recovered) == FRAME_PCM_BYTES
    # mu-law is slightly lossy logarithmic, RMS should remain close
    rms_rec = frame_rms(pcm_recovered)
    assert rms_rec == pytest.approx(1000, abs=50)


def test_energy_vad_silence():
    """Quiet audio should never start speech."""
    vad = EnergyVAD(start_rms=700, end_rms=400)
    quiet_frame = _make_pcm_frame(200)

    for _ in range(50):
        endpoint = vad.feed_frame(quiet_frame)
        assert not endpoint
        assert not vad.started
        assert vad.voiced == 0

    assert vad.peak_rms == pytest.approx(200, abs=5)
    assert len(vad.frames) == 0


def test_energy_vad_speech_and_endpoint():
    """Voiced audio should start speech and end after 40 quiet frames."""
    vad = EnergyVAD(start_rms=700, end_rms=400, start_frames=3, end_frames=40)
    quiet_frame = _make_pcm_frame(100)
    loud_frame = _make_pcm_frame(1200)

    # 1. Five quiet frames
    for _ in range(5):
        assert not vad.feed_frame(quiet_frame)
        assert not vad.started

    # 2. Loud frames start speech after 3 frames
    assert not vad.feed_frame(loud_frame)  # voiced=1
    assert not vad.started
    assert not vad.feed_frame(loud_frame)  # voiced=2
    assert not vad.started
    assert not vad.feed_frame(loud_frame)  # voiced=3 -> started!
    assert vad.started
    # Pre-roll should be captured
    assert len(vad.frames) >= 3

    # 3. Feed more loud frames
    for _ in range(10):
        assert not vad.feed_frame(loud_frame)

    # 4. Feed quiet frames until endpoint
    for i in range(39):
        assert not vad.feed_frame(quiet_frame), f"endpoint triggered too early at quiet frame {i+1}"

    # 40th quiet frame reaches endpoint
    endpoint = vad.feed_frame(quiet_frame)
    assert endpoint
    speech_pcm = vad.get_speech_pcm()
    assert len(speech_pcm) > 0


def test_sarvam_stt_transcribe_success(monkeypatch):
    """Sarvam STT success with 200 response parses transcript and lang."""
    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        assert url == SarvamSTT.endpoint
        assert headers.get("api-subscription-key") == "fake_sarvam_key"
        assert data.get("model") == "saaras:v4"
        assert data.get("language_code") == "hi-IN"
        return httpx.Response(
            200,
            json={"transcript": "किसान क्रेडिट योजना", "language_code": "hi-IN"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", lambda self, *args, **kwargs: fake_post(*args, **kwargs))

    stt = SarvamSTT(api_key="fake_sarvam_key")
    res = stt.transcribe(b"fake_wav", lang="hi")
    assert res.success
    assert res.transcript == "किसान क्रेडिट योजना"
    assert res.lang == "hi-IN"
    assert res.provider == "sarvam"


def test_sarvam_stt_timeout_handled(monkeypatch):
    """Sarvam STT timeout must return failure SttResult, never raise."""
    def fake_post_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(httpx.Client, "post", fake_post_timeout)

    stt = SarvamSTT(api_key="fake_sarvam_key")
    res = stt.transcribe(b"fake_wav", lang="hi")
    assert not res.success
    assert res.error == "timeout"
    assert res.transcript == ""


def test_groq_whisper_transcribe_success(monkeypatch):
    """Groq Whisper STT parses text and language correctly."""
    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        assert url == GroqWhisperSTT.endpoint
        assert "Bearer fake_groq_key" in headers.get("Authorization", "")
        assert data.get("model") == "whisper-large-v3-turbo"
        assert data.get("language") == "mr"
        assert data.get("prompt") == "kisan scheme"
        return httpx.Response(
            200,
            json={"text": "शेतकरी कर्ज योजना", "language": "marathi"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", lambda self, *args, **kwargs: fake_post(*args, **kwargs))

    stt = GroqWhisperSTT(api_key="fake_groq_key")
    res = stt.transcribe(b"fake_wav", lang="mr", hint="kisan scheme")
    assert res.success
    assert res.transcript == "शेतकरी कर्ज योजना"
    assert res.lang == "mr-IN"
    assert res.provider == "groq"


def test_speech_to_text_fallback_to_groq(monkeypatch, tmp_path):
    """When Sarvam fails, SpeechToText falls back to Groq Whisper."""
    sarvam_calls = []
    groq_calls = []

    def fake_sarvam_post(url, headers=None, data=None, files=None, timeout=None):
        sarvam_calls.append(url)
        return httpx.Response(500, text="Internal Server Error", request=httpx.Request("POST", url))

    def fake_groq_post(url, headers=None, data=None, files=None, timeout=None):
        groq_calls.append(url)
        return httpx.Response(
            200,
            json={"text": "I am a farmer", "language": "english"},
            request=httpx.Request("POST", url),
        )

    def dispatch_post(self, url, *args, **kwargs):
        if "sarvam.ai" in url:
            return fake_sarvam_post(url, *args, **kwargs)
        elif "groq.com" in url:
            return fake_groq_post(url, *args, **kwargs)
        raise ValueError(f"Unexpected url {url}")

    monkeypatch.setattr(httpx.Client, "post", dispatch_post)

    sarvam = SarvamSTT(api_key="key_sarvam")
    groq = GroqWhisperSTT(api_key="key_groq")
    ledger = tmp_path / "stt_usage.jsonl"
    engine = SpeechToText(sarvam=sarvam, groq=groq, ledger_path=ledger)

    # 1. First call: Sarvam fails -> falls back to Groq
    res = engine.transcribe(_make_pcm_frame(500) * 10, lang="en")
    assert res.success
    assert res.transcript == "I am a farmer"
    assert res.provider == "groq"
    assert len(sarvam_calls) == 1
    assert len(groq_calls) == 1
    assert not engine.sarvam_ok  # Circuit flipped off

    # 2. Second call: skips Sarvam directly to Groq
    res2 = engine.transcribe(_make_pcm_frame(500) * 10, lang="en")
    assert res2.success
    assert res2.transcript == "I am a farmer"
    assert len(sarvam_calls) == 1  # Not called again
    assert len(groq_calls) == 2

    # Check ledger written
    assert ledger.exists()
    lines = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 2
    assert lines[0]["provider"] == "groq"


def test_speech_to_text_both_fail_no_exception(monkeypatch, tmp_path):
    """When both providers time out or fail, returns failure signal without raising or looping."""
    def fake_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Timeout")

    monkeypatch.setattr(httpx.Client, "post", fake_timeout)

    sarvam = SarvamSTT(api_key="key_sarvam")
    groq = GroqWhisperSTT(api_key="key_groq")
    ledger = tmp_path / "stt_usage.jsonl"
    engine = SpeechToText(sarvam=sarvam, groq=groq, ledger_path=ledger)

    res = engine.transcribe(_make_pcm_frame(500) * 5, lang="en")
    assert not res.success
    assert res.error == "timeout"
    assert res.transcript == ""


def test_ear_silence_detection():
    """Ear returns Silence(n) when no sound exceeds START_RMS before timeout."""
    ear = Ear()
    # Feed quiet frames
    for _ in range(5):
        ear.push_media(pcm_to_ulaw(_make_pcm_frame(100)))

    # Short timeout for test
    inp = ear.listen(timeout=0.1)
    assert isinstance(inp, Silence)
    assert inp.n == 1

    # Second silence increments counter
    inp2 = ear.listen(timeout=0.1)
    assert isinstance(inp2, Silence)
    assert inp2.n == 2


def test_ear_noise_detection():
    """Ear returns Noise() when sound was voiced but STT returned empty transcript."""
    class FakeSTT(SpeechToText):
        def transcribe(self, audio_bytes, lang="", hint="", is_wav=False):
            return SttResult(transcript="", lang="", provider="sarvam", success=True)

    ear = Ear(stt=FakeSTT())

    # Feed voiced frames (> START_RMS) followed by quiet frames to trigger endpoint
    for _ in range(5):
        ear.push_media(pcm_to_ulaw(_make_pcm_frame(1200)))
    for _ in range(41):
        ear.push_media(pcm_to_ulaw(_make_pcm_frame(100)))

    inp = ear.listen(timeout=2.0)
    assert isinstance(inp, Noise)


def test_ear_speech_success():
    """Ear returns Speech(text) when voiced frames are transcribed."""
    class FakeSTT(SpeechToText):
        def transcribe(self, audio_bytes, lang="", hint="", is_wav=False):
            return SttResult(transcript="Hello world", lang="en-IN", provider="sarvam", success=True)

    ear = Ear(stt=FakeSTT())

    for _ in range(5):
        ear.push_media(pcm_to_ulaw(_make_pcm_frame(1200)))
    for _ in range(41):
        ear.push_media(pcm_to_ulaw(_make_pcm_frame(100)))

    inp = ear.listen(timeout=2.0)
    assert isinstance(inp, Speech)
    assert inp.text == "Hello world"
    assert ear.silence_count == 0


def test_ear_keypress_precedence_over_speech():
    """A DTMF keypress always wins over speech, whether pre-queued or in-flight."""
    ear = Ear()
    # Pre-queued key
    ear.push_dtmf("3")
    # Even if speech audio arrives, key wins immediately
    ear.push_media(pcm_to_ulaw(_make_pcm_frame(1200)))
    inp = ear.listen(timeout=2.0)
    assert isinstance(inp, Digit)
    assert inp.digit == "3"

    # In-flight speech interrupted by key
    ear2 = Ear()
    for _ in range(4):
        ear2.push_media(pcm_to_ulaw(_make_pcm_frame(1200)))
    ear2.push_dtmf("9")
    inp2 = ear2.listen(timeout=2.0)
    assert isinstance(inp2, Digit)
    assert inp2.digit == "9"


def test_ear_hangup_event():
    """Ear returns Hangup when push_hangup() is called."""
    ear = Ear()
    ear.push_hangup()
    inp = ear.listen(timeout=1.0)
    assert isinstance(inp, Hangup)


@pytest.mark.asyncio
async def test_ear_async_alisten():
    """Ear.alisten() works cleanly in asyncio event loops."""
    class FakeSTT(SpeechToText):
        def transcribe(self, audio_bytes, lang="", hint="", is_wav=False):
            return SttResult(transcript="Async speech", lang="en-IN", provider="groq", success=True)

    ear = Ear(stt=FakeSTT())
    for _ in range(5):
        ear.push_media(pcm_to_ulaw(_make_pcm_frame(1200)))
    for _ in range(41):
        ear.push_media(pcm_to_ulaw(_make_pcm_frame(100)))

    inp = await ear.alisten(timeout=2.0)
    assert isinstance(inp, Speech)
    assert inp.text == "Async speech"


def test_fixtures_exist_and_loadable():
    """All 9 speech fixtures in fixtures/audio/speech/ plus silence and noise exist and load."""
    fixtures_dir = BASE_DIR / "fixtures" / "audio" / "speech"
    manifest_path = fixtures_dir / "manifest.json"
    assert manifest_path.exists(), "fixtures/audio/speech/manifest.json must exist"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest) == 11  # 9 utterances + silence + noise

    for key, info in manifest.items():
        wav_file = fixtures_dir / info["file"]
        assert wav_file.exists(), f"Missing fixture file {wav_file}"
        pcm = load_audio(wav_file)
        assert len(pcm) > 0
        rms = frame_rms(pcm)
        if key == "silence":
            assert rms == 0
        else:
            assert rms > 0


def test_offline_accuracy_on_all_fixtures(monkeypatch):
    """Verify Ear end-to-end processing across all 9 static speech fixtures offline."""
    fixtures_dir = BASE_DIR / "fixtures" / "audio" / "speech"
    manifest = json.loads((fixtures_dir / "manifest.json").read_text(encoding="utf-8"))

    # Mock STT to return the fixture's expected text
    class FixtureMockSTT(SpeechToText):
        def __init__(self):
            super().__init__()
            self.current_text = ""
            self.current_lang = ""

        def transcribe(self, audio_bytes, lang="", hint="", is_wav=False):
            return SttResult(
                transcript=self.current_text,
                lang=self.current_lang,
                provider="sarvam",
                success=True,
            )

    mock_stt = FixtureMockSTT()
    ear = Ear(stt=mock_stt)

    for uid in ["p1_en", "p1_hi", "p1_mr", "p2_en", "p2_hi", "p2_mr", "p3_en", "p3_hi", "p3_mr"]:
        entry = manifest[uid]
        mock_stt.current_text = entry["text"]
        mock_stt.current_lang = entry["lang"]

        wav_path = fixtures_dir / entry["file"]
        pcm = load_audio(wav_path)

        # Slice PCM into 20 ms frames (320 bytes each) and feed into Ear
        chunk_size = FRAME_PCM_BYTES
        for i in range(0, len(pcm), chunk_size):
            chunk = pcm[i : i + chunk_size]
            if len(chunk) == chunk_size:
                ear.push_media(chunk, is_ulaw=False)

        # Feed quiet frames to close the utterance
        quiet_frame = _make_pcm_frame(50)
        for _ in range(45):
            ear.push_media(quiet_frame, is_ulaw=False)

        inp = ear.listen(timeout=2.0, lang=entry["lang"])
        assert isinstance(inp, Speech)
        assert inp.text == entry["text"]
