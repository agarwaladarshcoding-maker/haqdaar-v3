"""haqdaar/audio/render.py

Plan 2.1 — turn every text the call can say into a real voice clip.

The list comes from `texts.all_texts()`, the same list p6 builds its keys from, so what is
rendered and what the snapshot asks for cannot drift. Each clip lands at
`audio/<render_key>.ulaw` (8 kHz mu-law, the phone's own format, with a short quiet tail).

    make render            # count what is missing, spend nothing
    make render YES=1      # call Sarvam for what is missing

It resumes: a clip already on disk is never asked for again, so a second run makes 0 requests.
It stops on 402 (no credits): every later request would fail the same way. The Sarvam client
and `stretch()` are ported from the 15 Sep demo (`demo-15sep:haqdaar/voice_demo.py`).
"""
from __future__ import annotations

# audioop is deprecated in Python 3.11/3.12 and removed in 3.13+. Runtime is pinned to 3.11.
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*audioop.*")
import audioop

import base64
import io
import json
import os
import sys
import threading
import time
import wave
from array import array
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
from dotenv import load_dotenv

from haqdaar.contracts import tunables
from haqdaar.data.pipeline.texts import LANGS, TRILINGUAL_ORDER, Text, all_texts

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TTS_LANG = {"hi": "hi-IN", "mr": "mr-IN", "en": "en-IN"}
RANGE_BOXES = ("age", "income_band")
ULAW_SILENCE = b"\xff"


class RenderError(Exception):
    """One text could not be spoken. `fatal` means stop the whole run (402 no credits)."""

    def __init__(self, message: str, transient: bool = False, fatal: bool = False):
        super().__init__(message)
        self.transient = transient
        self.fatal = fatal
        self.rate_limited = False


def wav_to_ulaw(wav_bytes: bytes) -> bytes:
    """Any WAV Sarvam sends -> 8 kHz mono mu-law."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        pcm, rate = w.readframes(w.getnframes()), w.getframerate()
        width, channels = w.getsampwidth(), w.getnchannels()
    if width != 2:
        pcm = audioop.lin2lin(pcm, width, 2)
    if channels == 2:
        pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
    if rate != tunables.SAMPLE_RATE:
        pcm, _ = audioop.ratecv(pcm, 2, 1, rate, tunables.SAMPLE_RATE, None)
    return audioop.lin2ulaw(pcm, 2)


def ulaw_to_wav(ulaw: bytes) -> bytes:
    """8 kHz mu-law -> a WAV any player opens (tools/listen.py)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(tunables.SAMPLE_RATE)
        w.writeframes(audioop.ulaw2lin(ulaw, 2))
    return buf.getvalue()


def stretch(ulaw: bytes, speed: float) -> bytes:
    """Slow speech down without changing the pitch (WSOLA; audioop.findfit does the search in C).

    Used at play time for the slow repeat (plan 2.5); the normal pace is set at render time
    through Sarvam's own `pace`, which sounds better than stretching.
    """
    x = array("h", audioop.ulaw2lin(ulaw, 2))
    hop, delta = 160, 80  # 20 ms hop, 10 ms search each side
    if len(x) < 8 * hop:
        return ulaw
    out = x[:2 * hop]
    prev, k = 0, 1
    while True:
        nominal = int(k * hop * speed)
        if nominal + 2 * hop + delta >= len(x) or prev + 2 * hop > len(x):
            break
        lo = max(0, nominal - delta)
        off, _ = audioop.findfit(
            x[lo:nominal + delta + hop].tobytes(), x[prev + hop:prev + 2 * hop].tobytes()
        )
        pos = lo + off
        base = len(out) - hop
        for i in range(hop):  # cross-fade the overlap
            out[base + i] = int(out[base + i] * (hop - i) / hop + x[pos + i] * i / hop)
        out.extend(x[pos + hop:pos + 2 * hop])
        prev, k = pos, k + 1
    return audioop.lin2ulaw(out.tobytes(), 2)


class SarvamTTS:
    """Sarvam text-to-speech. Safe to call from a few threads at once."""

    endpoint = "https://api.sarvam.ai/text-to-speech"

    def __init__(self, api_key: Optional[str] = None, ledger_path: Optional[Path] = None):
        if api_key is None:
            load_dotenv(BASE_DIR / ".env")
            api_key = os.environ.get("SARVAM_API_KEY")
        if not api_key:
            raise ValueError("SARVAM_API_KEY must be set in environment or .env")
        self.api_key = api_key
        self.ledger_path = (
            Path(ledger_path) if ledger_path is not None
            else BASE_DIR / tunables.REPORTS_DIR / "sarvam_tts_usage.jsonl"
        )
        self._lock = threading.Lock()
        self._next_start = 0.0
        self.requests = 0
        self.chars = 0

    def speak(self, text: str, lang: str) -> bytes:
        """One text in one language -> 8 kHz mu-law. Retries only timeouts, 429 and 5xx."""
        last: Optional[RenderError] = None
        for attempt in range(tunables.TTS_MAX_ATTEMPTS):
            try:
                return self._attempt(text, lang)
            except RenderError as e:
                if not e.transient:
                    raise
                last = e
            wait = tunables.TTS_429_WAIT_S if last.rate_limited else tunables.TTS_RETRY_BACKOFF_S
            time.sleep(wait * (attempt + 1))
        assert last is not None
        raise RenderError(f"{last} (gave up after {tunables.TTS_MAX_ATTEMPTS} attempts)")

    def _wait_turn(self) -> None:
        """Space request starts TTS_MIN_GAP_S apart across every worker thread."""
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_start)
            self._next_start = start + tunables.TTS_MIN_GAP_S
        if start > now:
            time.sleep(start - now)

    def _attempt(self, text: str, lang: str) -> bytes:
        self._wait_turn()
        payload = {
            "text": text,
            "target_language_code": TTS_LANG[lang],
            "speaker": tunables.TTS_SPEAKERS[lang],
            "model": tunables.TTS_MODEL,
            "pace": tunables.TTS_PACE,
            "speech_sample_rate": tunables.SAMPLE_RATE,
        }
        try:
            response = httpx.post(
                self.endpoint,
                headers={"api-subscription-key": self.api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=tunables.TTS_TIMEOUT_S,
            )
        except Exception as e:
            raise RenderError(f"sarvam tts failed: {type(e).__name__}: {e}", transient=True) from e

        if response.status_code != 200:
            message = f"sarvam tts returned {response.status_code}: {response.text[:200]}"
            if response.status_code == 402:
                raise RenderError(message, fatal=True)
            error = RenderError(
                message, transient=response.status_code == 429 or response.status_code >= 500
            )
            error.rate_limited = response.status_code == 429
            raise error
        try:
            wav = base64.b64decode(response.json()["audios"][0])
            ulaw = wav_to_ulaw(wav)
        except Exception as e:
            raise RenderError(f"sarvam tts sent no usable audio: {e}") from e

        with self._lock:
            self.requests += 1
            self.chars += len(text)
            self._write_ledger(lang, len(text))
        return ulaw

    def _write_ledger(self, lang: str, chars: int) -> None:
        """Append one usage line. A ledger write must never break a render."""
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "lang": lang,
            "speaker": tunables.TTS_SPEAKERS[lang],
            "model": tunables.TTS_MODEL,
            "chars": chars,
        }
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


def _is_stub(data: bytes) -> bool:
    """p6's `--stubs` writes pure silence. A stub is not a recording and must be re-rendered."""
    return not data.strip(ULAW_SILENCE)


def clip_path(audio_dir: Path, key: str) -> Path:
    return audio_dir / f"{key}.ulaw"


def has_clip(audio_dir: Path, key: str) -> bool:
    path = clip_path(audio_dir, key)
    return path.exists() and not _is_stub(path.read_bytes())


def _parts(item: Text) -> list[tuple[str, str]]:
    """(lang, text) pieces to speak. Only greeting_trilingual has more than one."""
    if item.lang == "all":
        return list(zip(TRILINGUAL_ORDER, item.text.split("\n")))
    return [(item.lang, item.text)]


def _tail() -> bytes:
    return ULAW_SILENCE * int(tunables.SAMPLE_RATE * tunables.TAIL_PAD_MS / 1000)


@dataclass
class RenderResult:
    total: int = 0
    present: int = 0
    rendered: int = 0
    failed: list[str] = field(default_factory=list)
    stopped: Optional[str] = None  # the fatal error, if the run stopped early

    @property
    def missing(self) -> int:
        return self.total - self.present - self.rendered


def render(
    texts: list[Text],
    speak: Optional[Callable[[str, str], bytes]] = None,
    audio_dir: Path | str | None = None,
    workers: Optional[int] = None,
) -> RenderResult:
    """Speak every text that has no clip yet. `speak=None` only counts (no requests)."""
    audio_path = Path(audio_dir) if audio_dir is not None else BASE_DIR / tunables.AUDIO_DIR
    audio_path.mkdir(parents=True, exist_ok=True)
    result = RenderResult(total=len(texts))
    todo = [item for item in texts if not has_clip(audio_path, item.key)]
    result.present = result.total - len(todo)
    if speak is None or not todo:
        return result

    stop = threading.Event()
    lock = threading.Lock()

    def one(item: Text) -> None:
        if stop.is_set():
            return
        try:
            audio = b"".join(
                speak(text, lang) + _tail() for lang, text in _parts(item)
            )
        except RenderError as e:
            with lock:
                if e.fatal:
                    if not stop.is_set():
                        result.stopped = str(e)
                    stop.set()
                else:
                    result.failed.append(f"{item.ref} [{item.lang}]: {e}")
            return
        out = clip_path(audio_path, item.key)
        tmp = out.with_suffix(f".{threading.get_ident()}.part")
        tmp.write_bytes(audio)
        tmp.replace(out)
        with lock:
            result.rendered += 1
            done = result.rendered
        if done % 25 == 0:
            print(f"  rendered {done}/{len(todo)}", flush=True)

    with ThreadPoolExecutor(max_workers=workers or tunables.TTS_WORKERS) as pool:
        list(pool.map(one, todo))
    return result


def real_texts(schemes: Optional[list[dict[str, Any]]] = None) -> list[Text]:
    """All texts from the real inputs, with the bands p6 would build."""
    from haqdaar.data.pipeline.p6_snapshot import build_range_bands
    from haqdaar.data.pipeline.texts import _load_schemes

    if schemes is None:
        schemes = _load_schemes(BASE_DIR / Path(tunables.CARDS_FILE).parent)
    bands = {
        box: build_range_bands(schemes, box, max_bands=tunables.KEYPAD_CARDINALITY_MAX)
        for box in RANGE_BOXES
    }
    return all_texts(schemes, bands)


def _resolve_snapshot_dir(snapshot_arg: str) -> Path:
    p = Path(snapshot_arg)
    if not p.is_absolute():
        p = BASE_DIR / p
    if p.is_file():
        snap_id = p.read_text(encoding="utf-8").strip()
        p = p.parent / snap_id
    elif not p.exists() and (BASE_DIR / "snapshots" / snapshot_arg).exists():
        p = BASE_DIR / "snapshots" / snapshot_arg
    return p


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    snapshot_arg: Optional[str] = None
    cleaned_argv = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--snapshot" and i + 1 < len(argv):
            snapshot_arg = argv[i + 1]
            skip_next = True
        elif arg.startswith("--snapshot="):
            snapshot_arg = arg.split("=", 1)[1]
        else:
            cleaned_argv.append(arg)
    argv = cleaned_argv

    schemes: Optional[list[dict[str, Any]]] = None
    if snapshot_arg and snapshot_arg.lower() != "all":
        snap_dir = _resolve_snapshot_dir(snapshot_arg)
        from haqdaar.data.pipeline.texts import _load_schemes
        schemes = _load_schemes(snap_dir)
        print(f"snapshot: {snap_dir.name} ({len(schemes)} schemes)")

    texts = real_texts(schemes)
    counted = render(texts)
    todo = [t for t in texts if not has_clip(BASE_DIR / tunables.AUDIO_DIR, t.key)]
    chars = sum(len(t.text) for t in todo)
    by_lang = {lang: sum(1 for t in todo if t.lang == lang) for lang in (*LANGS, "all")}
    print(f"texts: {counted.total}  on disk: {counted.present}  missing: {counted.missing}")
    print(f"  missing by language: {by_lang}  chars to send: {chars}")
    if not todo:
        return 0
    if "--yes" not in argv:
        print("nothing sent. Run `make render YES=1` to call Sarvam for the missing clips.")
        return 0

    client = SarvamTTS()
    result = render(texts, speak=client.speak)
    print(f"rendered: {result.rendered}  failed: {len(result.failed)}  missing: {result.missing}")
    for line in result.failed[:20]:
        print(f"  {line}")
    print(f"sarvam tts requests: {client.requests}  chars: {client.chars}")
    if result.stopped:
        print(f"STOPPED: {result.stopped}")
        return 2
    return 1 if result.missing else 0


if __name__ == "__main__":
    sys.exit(main())
