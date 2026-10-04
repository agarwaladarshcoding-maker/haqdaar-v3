"""Step 7.7a: tools/pace_samples writes three speeds per clip and leaves the source alone."""
import audioop
import math
import wave
from array import array

from tools.pace_samples import write_samples


def _clip() -> bytes:
    pcm = array("h", (int(8000 * math.sin(i * 0.2)) for i in range(16000)))  # 2 s tone
    return audioop.lin2ulaw(pcm.tobytes(), 2)


def test_pace_samples(tmp_path):
    src = _clip()
    before = bytes(src)
    rows = write_samples("menu", "hi", src, tmp_path, 0.9, 1.1)

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "menu.hi.faster.wav", "menu.hi.now.wav", "menu.hi.slower.wav",
    ]
    secs = {name.split(".")[2]: s for name, _, s in rows}
    assert secs["slower"] > secs["now"] > secs["faster"] > 0
    for p in tmp_path.iterdir():
        with wave.open(str(p)) as w:
            assert w.getnframes() > 0
    assert src == before
