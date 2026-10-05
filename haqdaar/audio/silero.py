"""haqdaar/audio/silero.py

Step 7.14 (B5) — a noise is not a voice.

`SileroVAD` is the ear's `EnergyVAD` with one more test on each 20 ms frame: the Silero voice
detector (free, MIT, the file `silero_vad.onnx` next to this one, run on this machine with
onnxruntime; no torch, no network) must say "this is a voice". A frame that is loud but not a
voice (a door, a horn, a clap, music with no words) counts as quiet. A frame that is a voice but
too soft still counts as quiet: the loudness limits of `EnergyVAD` stay as they are.

The line gives 160 samples a frame at 8 kHz. Silero wants 256 samples at a time, so the frames
are kept in a small buffer and cut again. One window takes well under a millisecond.

`make()` gives None when the model can not be loaded; the ear then keeps its loudness check.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from haqdaar.audio.ear import EnergyVAD, frame_rms
from haqdaar.contracts import tunables

MODEL = Path(__file__).with_name("silero_vad.onnx")
WINDOW = 256            # samples Silero reads at 8 kHz
CONTEXT = 32            # samples of the window before, put in front of each window

_session: Any = None


def _load() -> Any:
    global _session
    if _session is None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        _session = ort.InferenceSession(str(MODEL), sess_options=opts, providers=["CPUExecutionProvider"])
    return _session


class SileroVAD(EnergyVAD):
    def __init__(self, session: Any = None, **kw: Any) -> None:
        import numpy as np

        self._np = np
        self._session = session or _load()
        self._sr = np.array(tunables.SAMPLE_RATE, dtype=np.int64)
        super().__init__(**kw)

    def reset(self) -> None:
        super().reset()
        np = self._np
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT, dtype=np.float32)
        self._buffer = np.zeros(0, dtype=np.float32)
        self.prob: float = 0.0

    def level(self, pcm_frame: bytes) -> int:
        """The frame's loudness when Silero hears a voice in it, else 0."""
        np = self._np
        samples = np.frombuffer(pcm_frame[: len(pcm_frame) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
        self._buffer = np.concatenate((self._buffer, samples))
        while len(self._buffer) >= WINDOW:
            window, self._buffer = self._buffer[:WINDOW], self._buffer[WINDOW:]
            out, self._state = self._session.run(None, {
                "input": np.concatenate((self._context, window))[None, :],
                "state": self._state, "sr": self._sr,
            })
            self._context = window[-CONTEXT:]
            self.prob = float(out[0][0])
        # Easier to stay a voice than to start one, so a soft end of a word does not end the turn.
        need = tunables.SILERO_OFF if self.started else tunables.SILERO_ON
        return frame_rms(pcm_frame) if self.prob >= need else 0


def make(log: Any = None) -> Optional[SileroVAD]:
    try:
        return SileroVAD()
    except Exception as e:
        if log:
            log(f"!! Silero voice check not loaded ({e!r}); the loudness check is used")
        return None


__all__ = ["SileroVAD", "make"]
