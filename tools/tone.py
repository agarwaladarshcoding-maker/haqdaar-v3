"""tools/tone.py

Generates raw 8 kHz μ-law audio tone (G.711 PCMU) with no header.
"""
from __future__ import annotations
import math
from haqdaar.contracts.tunables import (
    SAMPLE_RATE,
    TONE_FREQ_HZ,
    TONE_DURATION_S,
    TONE_AMPLITUDE,
)

BIAS = 0x84
CLIP = 32635


def pcm16_to_ulaw(sample: int) -> int:
    """Encode a 16-bit signed linear PCM sample to an 8-bit ITU-T G.711 μ-law byte."""
    sign = 0
    if sample < 0:
        sign = 0x80
        sample = -sample
    if sample > CLIP:
        sample = CLIP
    sample += BIAS

    exponent = 7
    mask = 0x4000
    while exponent > 0 and (sample & mask) == 0:
        exponent -= 1
        mask >>= 1
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


def ulaw_to_pcm16(u: int) -> int:
    """Decode an 8-bit ITU-T G.711 μ-law byte to a 16-bit signed linear PCM sample."""
    u = ~u & 0xFF
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    sample = ((mantissa << 3) + BIAS) << exponent
    sample -= BIAS
    return -sample if sign else sample


def generate_tone(
    freq_hz: float = TONE_FREQ_HZ,
    duration_s: float = TONE_DURATION_S,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = TONE_AMPLITUDE,
) -> bytes:
    """Generate a pure sine wave tone encoded as raw 8-bit μ-law bytes without header."""
    num_samples = int(duration_s * sample_rate)
    max_amp = 32767.0 * amplitude
    raw = bytearray(num_samples)
    for i in range(num_samples):
        val = int(max_amp * math.sin(2.0 * math.pi * freq_hz * i / sample_rate))
        raw[i] = pcm16_to_ulaw(val)
    return bytes(raw)


if __name__ == "__main__":
    import sys

    sys.stdout.buffer.write(generate_tone())
