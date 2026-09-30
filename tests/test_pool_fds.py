"""Plan 2.2 (F12) — the pool must not hold one open file per clip.

macOS gives a process 256 open files by default. The old tier 1 kept an mmap (and Python's mmap
keeps its own copy of the handle) per clip, so a real call with 400 clips would die mid-call.
Runs in a child process so the lowered limit cannot hurt the rest of the test run.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap


def test_400_clips_load_under_256_open_files(tmp_path):
    code = textwrap.dedent(f"""
        import resource
        from pathlib import Path
        from haqdaar.audio.pool import AudioPool
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, hard))
        d = Path({str(tmp_path)!r})
        keys = []
        for i in range(400):
            key = f"{{i:064x}}"
            (d / f"{{key}}.ulaw").write_bytes(bytes([i % 250 + 1]) * 800)
            keys.append(key)
        pool = AudioPool(audio_dir=d, cache_mb=64, tier2="none")
        views = [pool.get(k) for k in keys]          # all 400 held at once
        pool.pin(keys[:150])                          # pinning reads too
        views += [pool.get(k) for k in keys]
        assert pool.tier1_count + pool.tier0_count == 400
        assert bytes(views[399][:1]) == bytes([399 % 250 + 1])
        print("ok")
    """)
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-2000:]
    assert run.stdout.strip() == "ok"
