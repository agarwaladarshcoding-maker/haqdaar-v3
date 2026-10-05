"""haqdaar/audio/ear.py

Phase 4 (Voice), Step 4.1 — speech to text and hearing.

Components:
- SarvamSTT: primary speech-to-text provider (saaras:v4 / speech-to-text endpoint).
  Note: Sarvam REST STT ignores 'hint'; hint is used by Groq Whisper fallback.
- GroqWhisperSTT: fallback speech-to-text provider (whisper-large-v3-turbo).
- SpeechToText: combined engine (Sarvam primary, Groq fallback, raw httpx, 1s padding, hint words).
- EnergyVAD: 20 ms frame energy detection (START_RMS=700, END_RMS=400, START_FRAMES=3, END_FRAMES=40).
- Ear: listener handling telephony audio, DTMF, and hangup events.
  - Distinguishes NOISE from SILENCE.
  - Keypress always wins over speech (barge-in).
  - An STT timeout is a failure signal, never an exception, never a retry loop (one quick
    second try on a network error only, see net.py).
  - One caller at a time; never blocks the socket loop.

Environment overrides:
- STT_TIMEOUT_S: timeout per STT call in seconds (default: 5.0)
- SARVAM_STT_MODEL: Sarvam model override (default: saaras:v4)
- GROQ_STT_MODEL: Groq Whisper model override (default: whisper-large-v3-turbo)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import queue
import time
from typing import Any, Callable, Optional
import wave

# audioop is deprecated in Python 3.11/3.12 and removed in 3.13+. Runtime is pinned to 3.11.
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*audioop.*")
import audioop

from dotenv import load_dotenv
import httpx

from haqdaar import net
from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Hangup, Input, Noise, Silence, Speech

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# VAD Tunables (20 ms frames at 8000 Hz: 160 samples, 320 bytes linear PCM)
FRAME_MS: int = 20
SAMPLE_RATE: int = 8000
BYTES_PER_SAMPLE: int = 2
FRAME_SAMPLES: int = int(SAMPLE_RATE * (FRAME_MS / 1000.0))  # 160
FRAME_PCM_BYTES: int = FRAME_SAMPLES * BYTES_PER_SAMPLE       # 320

START_RMS: int = 700
END_RMS: int = 400
START_FRAMES: int = 3          # 3 frames (60 ms) > START_RMS to start speech
END_FRAMES: int = (tunables.TALK_END_WAIT_MS // 20) if tunables.TALK_ONLY else 40   # 40 frames (800 ms) < END_RMS of quiet to end speech; a talk call: 600 ms
MAX_UTTERANCE_FRAMES: int = 350 # 7.0 s maximum utterance
PRE_ROLL_FRAMES: int = 15      # 300 ms pre-speech buffer

SARVAM_LANG: dict[str, str] = {
    "hi": "hi-IN",
    "mr": "mr-IN",
    "en": "en-IN",
}

GROQ_LANG_MAP: dict[str, str] = {
    "hindi": "hi-IN",
    "english": "en-IN",
    "marathi": "mr-IN",
    "hi": "hi-IN",
    "en": "en-IN",
    "mr": "mr-IN",
    "hi-in": "hi-IN",
    "en-in": "en-IN",
    "mr-in": "mr-IN",
}


def normalize_lang(code: str) -> str:
    """Normalize language code across providers to standard format (hi-IN, mr-IN, en-IN)."""
    if not code:
        return ""
    c = code.strip().lower()
    return GROQ_LANG_MAP.get(c, code)



def ulaw_to_pcm(ulaw: bytes) -> bytes:
    """Convert 8-bit mu-law to 16-bit linear PCM at 8 kHz."""
    if not ulaw:
        return b""
    return audioop.ulaw2lin(ulaw, BYTES_PER_SAMPLE)


def pcm_to_ulaw(pcm: bytes) -> bytes:
    """Convert 16-bit linear PCM to 8-bit mu-law at 8 kHz."""
    if not pcm:
        return b""
    return audioop.lin2ulaw(pcm, BYTES_PER_SAMPLE)


def frame_rms(pcm: bytes) -> int:
    """RMS energy of 16-bit linear PCM."""
    if not pcm or len(pcm) < BYTES_PER_SAMPLE:
        return 0
    return audioop.rms(pcm, BYTES_PER_SAMPLE)


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE, pad_seconds: float = 1.0) -> bytes:
    """Wrap 16-bit mono linear PCM into WAV bytes with silence padding on both ends.

    Whisper / Sarvam garble a lone short word without ~1 s padding (demo 15 Sep).
    """
    quiet_samples = int(sample_rate * pad_seconds)
    quiet = b"\x00\x00" * quiet_samples
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(BYTES_PER_SAMPLE)
        w.setframerate(sample_rate)
        w.writeframes(quiet + pcm + quiet)
    return buf.getvalue()


def load_audio(path: Path | str) -> bytes:
    """Load audio file (.wav or .ulaw) and return 16-bit mono linear PCM at 8 kHz."""
    p = Path(path)
    data = p.read_bytes()
    if p.suffix.lower() == ".wav":
        buf = io.BytesIO(data)
        with wave.open(buf, "rb") as w:
            pcm = w.readframes(w.getnframes())
            if w.getsampwidth() != 2 or w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1:
                # Basic rate/channel normalization if needed
                if w.getnchannels() == 2:
                    pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
                if w.getframerate() != SAMPLE_RATE:
                    pcm, _ = audioop.ratecv(pcm, 2, 1, w.getframerate(), SAMPLE_RATE, None)
            return pcm
    elif p.suffix.lower() == ".ulaw":
        return ulaw_to_pcm(data)
    return data


@dataclass
class SttResult:
    transcript: str
    lang: str
    provider: str = ""
    success: bool = True
    error: str | None = None
    latency_s: float = 0.0
    english: bool = False   # True when `transcript` is an English translation (ENGLISH_PIPE)


class SarvamSTT:
    """Sarvam AI Speech-To-Text client using raw httpx."""

    endpoint = "https://api.sarvam.ai/speech-to-text"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "saaras:v4",
        timeout: float = 5.0,
    ) -> None:
        if api_key is None:
            load_dotenv()
            api_key = os.environ.get("SARVAM_API_KEY", "")
        self.api_key = api_key
        self.model = os.environ.get("SARVAM_STT_MODEL", model)
        self.timeout = float(os.environ.get("STT_TIMEOUT_S", str(timeout)))

    def transcribe(
        self,
        wav_bytes: bytes,
        lang: str = "",
        hint: str = "",
        timeout: Optional[float] = None,
    ) -> SttResult:
        if not self.api_key:
            return SttResult(
                transcript="",
                lang="",
                provider="sarvam",
                success=False,
                error="no_key",
            )

        headers = {
            "api-subscription-key": self.api_key,
        }
        data: dict[str, str] = {
            "model": self.model,
            "mode": "translate" if tunables.ENGLISH_PIPE else "transcribe",
        }
        lang_code = SARVAM_LANG.get(lang.lower(), "")
        if lang_code:
            data["language_code"] = lang_code
        elif lang:
            data["language_code"] = lang

        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav"),
        }

        t0 = time.monotonic()
        eff_timeout = timeout if timeout is not None else self.timeout
        try:
            resp = net.post(self.endpoint, headers=headers, data=data, files=files, timeout=eff_timeout)
            latency = time.monotonic() - t0
            if resp.status_code == 200:
                body = resp.json()
                transcript = body.get("transcript", "").strip()
                detected_lang = normalize_lang(body.get("language_code", lang_code))
                return SttResult(
                    transcript=transcript,
                    lang=detected_lang,
                    provider="sarvam",
                    success=True,
                    latency_s=latency,
                    english=tunables.ENGLISH_PIPE,
                )
            return SttResult(
                transcript="",
                lang="",
                provider="sarvam",
                success=False,
                error=f"http_{resp.status_code}",
                latency_s=latency,
            )
        except httpx.TimeoutException:
            return SttResult(
                transcript="",
                lang="",
                provider="sarvam",
                success=False,
                error="timeout",
                latency_s=time.monotonic() - t0,
            )
        except Exception as e:
            return SttResult(
                transcript="",
                lang="",
                provider="sarvam",
                success=False,
                error=f"{type(e).__name__}: {e}",
                latency_s=time.monotonic() - t0,
            )


class GroqWhisperSTT:
    """Groq Whisper STT client using raw httpx."""

    endpoint = "https://api.groq.com/openai/v1/audio/transcriptions"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "whisper-large-v3-turbo",
        timeout: float = 5.0,
    ) -> None:
        if api_key is None:
            load_dotenv()
            api_key = os.environ.get("GROQ_API_KEY", "")
        self.api_key = api_key
        self.model = os.environ.get("GROQ_STT_MODEL", model)
        self.timeout = float(os.environ.get("STT_TIMEOUT_S", str(timeout)))

    def transcribe(
        self,
        wav_bytes: bytes,
        lang: str = "",
        hint: str = "",
        timeout: Optional[float] = None,
    ) -> SttResult:
        if not self.api_key:
            return SttResult(
                transcript="",
                lang="",
                provider="groq",
                success=False,
                error="no_key",
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "haqdaar/0.1",
        }
        data: dict[str, str] = {
            "model": self.model,
            "response_format": "verbose_json",
            "temperature": "0",
        }
        if lang:
            data["language"] = lang
        if hint:
            data["prompt"] = hint

        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav"),
        }

        t0 = time.monotonic()
        eff_timeout = timeout if timeout is not None else self.timeout
        try:
            resp = net.post(self.endpoint, headers=headers, data=data, files=files, timeout=eff_timeout)
            latency = time.monotonic() - t0
            if resp.status_code == 200:
                body = resp.json()
                transcript = body.get("text", "").strip()
                raw_lang = str(body.get("language", "")).lower()
                detected_lang = normalize_lang(raw_lang)
                return SttResult(
                    transcript=transcript,
                    lang=detected_lang,
                    provider="groq",
                    success=True,
                    latency_s=latency,
                )
            return SttResult(
                transcript="",
                lang="",
                provider="groq",
                success=False,
                error=f"http_{resp.status_code}",
                latency_s=latency,
            )
        except httpx.TimeoutException:
            return SttResult(
                transcript="",
                lang="",
                provider="groq",
                success=False,
                error="timeout",
                latency_s=time.monotonic() - t0,
            )
        except Exception as e:
            return SttResult(
                transcript="",
                lang="",
                provider="groq",
                success=False,
                error=f"{type(e).__name__}: {e}",
                latency_s=time.monotonic() - t0,
            )


class SpeechToText:
    """Primary Sarvam STT with Groq Whisper fallback.

    - 1 s silence padding.
    - Hint words forwarded to Groq prompt.
    - Timeout is a failure signal, never an exception, never a retry loop (one quick second try
      on a network error only, see net.py).
    - Usage recorded to reports ledger.
    """

    def __init__(
        self,
        sarvam: Optional[SarvamSTT] = None,
        groq: Optional[GroqWhisperSTT] = None,
        ledger_path: Optional[Path] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.sarvam = sarvam if sarvam is not None else SarvamSTT()
        self.groq = groq if groq is not None else GroqWhisperSTT()
        self.sarvam_ok: bool = True
        self.sarvam_failures: int = 0
        self.ledger_path: Path = (
            Path(ledger_path)
            if ledger_path is not None
            else BASE_DIR / tunables.REPORTS_DIR / "stt_usage.jsonl"
        )
        self._log: Callable[[str], None] = log or (lambda s: None)

    def reset_circuit(self) -> None:
        """Reset Sarvam circuit breaker for a new listen / utterance."""
        self.sarvam_ok = True
        self.sarvam_failures = 0

    def _write_ledger(self, result: SttResult, audio_duration_s: float, lang: str) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "provider": result.provider,
            "success": result.success,
            "lang": lang,
            "transcript_len": len(result.transcript),
            "audio_duration_s": round(audio_duration_s, 2),
            "latency_s": round(result.latency_s, 2),
            "error": result.error,
        }
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def transcribe(
        self,
        audio_bytes: bytes,
        lang: str = "",
        hint: str = "",
        is_wav: bool = False,
    ) -> SttResult:
        """Transcribe audio (16-bit linear PCM by default, or WAV if is_wav=True).

        Applies 1s padding on both ends when converting PCM to WAV.
        Tries Sarvam first; on any failure, falls back to Groq Whisper.
        Never raises: timeout or error returns failure SttResult.
        """
        wav_bytes = audio_bytes if is_wav else pcm_to_wav(audio_bytes, pad_seconds=1.0)
        duration_s = max(0.0, (len(audio_bytes) / 16000.0) if not is_wav else ((len(wav_bytes) - 44) / 16000.0))

        total_timeout = float(os.environ.get("STT_TIMEOUT_S", str(tunables.STT_TIMEOUT_S)))
        t0 = time.monotonic()

        # 1. Primary: Sarvam STT (gets full budget)
        if self.sarvam_ok and self.sarvam.api_key:
            res = self.sarvam.transcribe(wav_bytes, lang=lang, hint=hint, timeout=total_timeout)
            self._write_ledger(res, duration_s, lang)
            if res.success:
                self.sarvam_failures = 0
                return res
            # Circuit flips off after failure so Groq responds promptly for this utterance
            self.sarvam_failures += 1
            self.sarvam_ok = False
            self._log(f"!! Sarvam STT failed ({res.error}); falling back to Groq Whisper")

        # 2. Fallback: Groq Whisper (gets remainder of shared deadline)
        elapsed = time.monotonic() - t0
        remaining_timeout = total_timeout - elapsed
        if remaining_timeout <= 0.2:
            timeout_res = SttResult(
                transcript="",
                lang="",
                provider="groq",
                success=False,
                error="deadline_exceeded",
                latency_s=elapsed,
            )
            self._write_ledger(timeout_res, duration_s, lang)
            return timeout_res

        res = self.groq.transcribe(wav_bytes, lang=lang, hint=hint, timeout=remaining_timeout)
        self._write_ledger(res, duration_s, lang)
        return res


_DEFAULT_STT: Optional[SpeechToText] = None


def speech_to_text(pcm: bytes, lang: str = "", hint: str = "") -> tuple[str, str]:
    """Port-compatible convenience function: returns (transcript, language_code)."""
    global _DEFAULT_STT
    if _DEFAULT_STT is None:
        _DEFAULT_STT = SpeechToText()
    res = _DEFAULT_STT.transcribe(pcm, lang=lang, hint=hint)
    return res.transcript, res.lang


class EnergyVAD:
    """Voice Activity Detection based on RMS energy of 20 ms linear PCM frames.

    - Speech start: 3 frames (60 ms) above START_RMS (700).
    - Speech end (endpoint): 40 frames (800 ms) below END_RMS (400) after speech started.
    - Max utterance: 350 frames (7.0 s).
    - Pre-roll buffer: 15 frames (300 ms) prepended to preserve utterance start.
    """

    def __init__(
        self,
        start_rms: int = START_RMS,
        end_rms: int = END_RMS,
        start_frames: int = START_FRAMES,
        end_frames: int = END_FRAMES,
        max_frames: int = MAX_UTTERANCE_FRAMES,
        pre_roll_frames: int = PRE_ROLL_FRAMES,
    ) -> None:
        self.start_rms = start_rms
        self.end_rms = end_rms
        self.start_frames = start_frames
        self.end_frames = end_frames
        self.max_frames = max_frames
        self.pre_roll_frames = pre_roll_frames
        self.reset()

    def reset(self) -> None:
        self.voiced: int = 0
        self.quiet: int = 0
        self.started: bool = False
        self.peak_rms: int = 0
        self.frames: list[bytes] = []
        self._pre: list[bytes] = []
        self.last_level: int = 0

    def level(self, pcm_frame: bytes) -> int:
        """How loud this frame is. A voice detector (silero.py) gives 0 for a frame that is no voice."""
        return frame_rms(pcm_frame)

    def feed_frame(self, pcm_frame: bytes) -> bool:
        """Feed one 20 ms linear PCM frame (320 bytes).

        Returns True when utterance boundary (endpoint) is reached, False otherwise.
        """
        level = self.last_level = self.level(pcm_frame)
        self.peak_rms = max(self.peak_rms, level)

        if not self.started:
            self._pre.append(pcm_frame)
            if len(self._pre) > self.pre_roll_frames:
                self._pre.pop(0)

            if level > self.start_rms:
                self.voiced += 1
            else:
                self.voiced = 0

            if self.voiced >= self.start_frames:
                self.started = True
                self.frames = list(self._pre)
            return False

        # Speech is in progress
        self.frames.append(pcm_frame)
        if level < self.end_rms:
            self.quiet += 1
        else:
            self.quiet = 0

        if self.quiet >= self.end_frames or len(self.frames) >= self.max_frames:
            return True

        return False

    def get_speech_pcm(self) -> bytes:
        return b"".join(self.frames)


class Ear:
    """The ear: turns telephony audio stream and DTMF into Input tokens.

    Interface contracts:
    - Returns Digit | Speech | Noise | Silence(n) | Hangup.
    - Distinguishes NOISE vs SILENCE:
      - Silence: no speech started within timeout -> Silence(n).
      - Noise: speech started (energy detected), but STT returned empty or failed -> Noise().
    - Keypress always wins over speech:
      - Any DTMF key queued or arriving during speech/STT aborts speech and returns Digit(digit).
    - STT timeout is a failure signal, never an exception, never a retry loop (one quick second
      try on a network error only, see net.py).
    - One caller at a time; socket loop methods never block.
    """

    def __init__(
        self,
        stt: Optional[SpeechToText] = None,
        vad: Optional[EnergyVAD] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.stt: SpeechToText = stt if stt is not None else SpeechToText(log=log)
        self.vad: EnergyVAD = vad if vad is not None else EnergyVAD()
        self._log: Callable[[str], None] = log or (lambda s: None)
        self._events: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        self._keys: "queue.Queue[str]" = queue.Queue()
        self.silence_count: int = 0
        self.hung_up: bool = False
        self.last_discarded_transcript: Optional[str] = None
        self.stt_failed: bool = False
        self.failures: int = 0
        self._needs_stale_drain: bool = False
        self._turn_gate: Optional[Any] = None   # set by Turn: the one place keys are judged
        self._voiced_ms: int = 0                # voice heard so far while a clip plays (cut-in)
        self._quiet_ms: int = 0                 # quiet since the last voiced frame of that burst

    @property
    def keypad_only(self) -> bool:
        """Trigger keypad-only fallback if STT failed or voice broke."""
        return self.stt_failed or (self.failures >= 1)

    def force_stt_failure(self) -> None:
        """For testing or manual degradation: force ear STT failure."""
        self.stt_failed = True
        self.failures += 1

    def drain_media(self) -> int:
        """Drain queued media packets (e.g. from during STT or line playback) (TOP-10 #7)."""
        stale_non_media = []
        drained = 0
        while not self._events.empty():
            try:
                ev = self._events.get_nowait()
                if ev[0] == "media":
                    drained += 1
                else:
                    stale_non_media.append(ev)
            except queue.Empty:
                break
        for ev in stale_non_media:
            self._events.put_nowait(ev)
        return drained

    def start_watch(self) -> None:
        """Begin listening for the caller's voice over a playing clip."""
        self.vad.reset()
        self._voiced_ms = 0
        self._quiet_ms = 0

    def watch_voice(self, in_guard: bool = False, min_ms: int = 0, gap_ms: int = 0) -> str:
        """Feed the audio that arrived so far to the voice detector while a clip plays.

        Returns "cut" once the caller has voiced CUT_IN_MIN_MS (same detector, same thresholds as
        listen), "short" when a shorter burst ended (a cough, "hm"), else "". Frames that arrive
        inside the guard window of a new prompt are thrown away. After "cut" the frames not yet
        read stay queued for listen(resume=True).
        """
        kept: list[tuple[str, Any]] = []
        result = ""
        while result != "cut":
            try:
                ev = self._events.get_nowait()
            except queue.Empty:
                break
            if ev[0] != "media":
                kept.append(ev)
                continue
            pcm = ev[1]
            if in_guard:
                self.start_watch()
                continue
            ended = self.vad.feed_frame(pcm)
            if self.vad.started and getattr(self.vad, "last_level", frame_rms(pcm)) >= self.vad.end_rms:
                self._voiced_ms += FRAME_MS
                self._quiet_ms = 0
            elif self.vad.started:
                self._quiet_ms += FRAME_MS
                # The burst is over: a second cough must not add to the first one.
                ended = ended or self._quiet_ms >= (gap_ms or tunables.CUT_IN_GAP_MS)
            if self._voiced_ms >= (min_ms or tunables.CUT_IN_MIN_MS):
                result = "cut"
            elif ended:
                if self._voiced_ms > 0:
                    result = "short"
                self.start_watch()
        for ev in kept:
            self._events.put_nowait(ev)
        return result

    # --- socket loop methods (thread-safe, O(1), non-blocking) --------------------
    def push_media(self, payload: bytes, is_ulaw: bool = True) -> None:
        """Called by socket loop on MediaEvent (e.g. 20 ms 160-byte mu-law)."""
        pcm = ulaw_to_pcm(payload) if is_ulaw else payload
        self._events.put_nowait(("media", pcm))

    def push_dtmf(self, digit: str) -> None:
        """Called by socket loop on DtmfEvent."""
        if self._turn_gate is None:
            self._keys.put_nowait(digit)
        self._events.put_nowait(("dtmf", digit))

    def push_hangup(self) -> None:
        """Called by socket loop when caller ends the stream."""
        self.hung_up = True
        self._events.put_nowait(("hangup", None))

    # --- engine thread methods ----------------------------------------------------
    def has_key(self) -> bool:
        return not self._keys.empty()

    def _take_key(self) -> Optional[Digit]:
        """The next key that counts. With a gate (Turn), the gate decides; else our own queue."""
        if self._turn_gate is not None:
            return self._turn_gate.get_valid_key(block=False)
        try:
            return Digit(digit=self._keys.get_nowait())
        except queue.Empty:
            return None

    def listen(
        self,
        timeout: float = 6.0,
        lang: str = "",
        hint: str = "",
        drain_stale: bool = False,
        resume: bool = False,
    ) -> Input:
        """Wait for input on the line: key, speech, noise, silence, or hangup.

        A keypress always wins over speech. `resume` carries on with the voice watch_voice() has
        already started to hear (cut-in), instead of starting a fresh utterance.
        """
        # 1. Immediate key check (barge-in or pre-queued key)
        if self.hung_up:
            return Hangup()

        taken = self._take_key()
        if taken is not None:
            self.silence_count = 0
            self._log(f"<- key {taken.digit} (pre-queued)")
            return taken

        # Drain stale media packets queued before listen() started / during previous STT (TOP-10 #7)
        if (drain_stale or self._needs_stale_drain) and not resume:
            self.drain_media()
            self._needs_stale_drain = False

        if not resume:
            self.vad.reset()
        self.stt.reset_circuit()
        deadline = time.monotonic() + timeout

        while True:
            if self.hung_up:
                return Hangup()

            # If key arrived, it wins immediately
            taken = self._take_key()
            if taken is not None:
                self.silence_count = 0
                self._log(f"<- key {taken.digit} (interrupted silence/listening)")
                return taken

            now = time.monotonic()
            if not self.vad.started and now >= deadline:
                # Silence: deadline passed and caller never spoke
                self.silence_count += 1
                self._log(f"<- silence {self.silence_count} (peak {self.vad.peak_rms})")
                return Silence(n=self.silence_count)

            # Wait for next event
            wait_time = max(0.02, deadline - now) if not self.vad.started else 2.0
            try:
                kind, val = self._events.get(timeout=wait_time)
            except queue.Empty:
                if not self.vad.started:
                    self.silence_count += 1
                    self._log(f"<- silence {self.silence_count} (peak {self.vad.peak_rms})")
                    return Silence(n=self.silence_count)
                # Speech had started but stream stalled/quiet for 2s: treat as endpoint
                break

            if kind == "dtmf":
                # Key must be present in _keys; if empty, it was already consumed
                taken = self._take_key()
                if taken is None:
                    continue  # already taken, or dropped by the gate: keep listening
                self.silence_count = 0
                self._log(f"<- key {taken.digit} (won over speech)")
                return taken

            if kind == "hangup":
                self.hung_up = True
                return Hangup()

            if kind == "media":
                pcm = val
                endpoint = self.vad.feed_frame(pcm)
                if endpoint:
                    break

        # Utterance complete: speech frames gathered
        self.silence_count = 0
        end_ms = int(getattr(self.vad, "quiet", 0)) * 20
        speech_pcm = self.vad.get_speech_pcm()

        # Keycheck again before calling STT
        if self.hung_up:
            return Hangup()
        taken = self._take_key()
        if taken is not None:
            self.silence_count = 0
            self._log(f"<- key {taken.digit} (won over post-utterance)")
            return taken

        # Call STT (timeout handled internally, never raises)
        t0 = time.monotonic()
        stt_res = self.stt.transcribe(speech_pcm, lang=lang, hint=hint)
        stt_ms = int((time.monotonic() - t0) * 1000)
        self._needs_stale_drain = True

        # Check if key arrived during STT
        if self.hung_up:
            return Hangup()
        taken = self._take_key()
        if taken is not None:
            self.silence_count = 0
            self.last_discarded_transcript = stt_res.transcript
            self._log(f"<- key {taken.digit} (won over completed STT)")
            return taken

        if stt_res.success and stt_res.transcript:
            self._log(f'<- speech "{stt_res.transcript}" ({stt_res.lang}, stt {stt_res.latency_s:.2f}s)')
            # The code is kept always: at the greeting the talk call takes its language from it.
            return Speech(text=stt_res.transcript, lang=stt_res.lang, english=stt_res.english,
                          end_ms=end_ms, stt_ms=stt_ms)

        # Speech started but yielded no valid transcript or failed/timed out: NOISE
        if not stt_res.success:
            self.stt_failed = True
            self.failures += 1
        self._log(f"<- noise (started=True, stt_err={stt_res.error}, peak={self.vad.peak_rms})")
        return Noise()

    async def alisten(
        self,
        timeout: float = 6.0,
        lang: str = "",
        hint: str = "",
    ) -> Input:
        """Async variant of listen() that offloads blocking I/O to a worker thread."""
        return await asyncio.to_thread(self.listen, timeout=timeout, lang=lang, hint=hint)
