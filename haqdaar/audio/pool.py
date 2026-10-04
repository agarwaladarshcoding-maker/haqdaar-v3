"""haqdaar/audio/pool.py

Audio storage — one flat pool, three tiers, read lazily (03-ARCHITECTURE.md §10.1).
Internal to haqdaar/audio. NOT imported by corpus.py.

Tiers:
  tier 0: RAM, pinned (139 fixed lines + ~600 chips, ~35 MB, never evicted)
  tier 1: Local SSD, read once + byte-bounded LRU at AUDIO_CACHE_MB. No file stays open:
          Python's mmap keeps its own copy of the file handle, so 400 mapped clips were 400
          open files, over macOS's default limit of 256 (F12). Clips are small (a scheme
          chunk is ~100 KB), so reading them into the LRU costs little and holds no handle.
  tier 2: S3 / R2, read-through into tier 1 behind AUDIO_TIER2 (default "none")

Runtime imports no TTS client and no S3 client when AUDIO_TIER2=none.
"""
from __future__ import annotations
from collections import OrderedDict
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from haqdaar.contracts import tunables
from haqdaar.contracts.types import RenderKey


def _quiet_bytes() -> bytes:
    """Every mu-law byte at or under TRIM_QUIET_LEVEL, both signs (0xFF and 0x7F are zero)."""
    n = tunables.TRIM_QUIET_LEVEL
    return bytes([0xFF - k for k in range(n + 1)] + [0x7F - k for k in range(n + 1)])


def trim_edges(data: bytes) -> bytes:
    """Cut quiet at the start and end of a mu-law clip down to TRIM_EDGE_MS. Middle is never touched.

    A clip that is all quiet (a stub) or shorter than two gaps comes back as it is, so nothing
    loads empty. bytes.strip runs in C: one fast pass, nothing blocks the mouth.
    """
    gap = tunables.SAMPLE_RATE * tunables.TRIM_EDGE_MS // 1000
    if len(data) < 2 * gap:
        return data
    quiet = _quiet_bytes()
    body = data.strip(quiet)
    if not body:
        return data
    lead = len(data) - len(data.lstrip(quiet))
    tail = len(data) - lead - len(body)
    if lead <= gap and tail <= gap:
        return data
    return data[max(lead - gap, 0):len(data) - max(tail - gap, 0)]


class AudioPool:
    """Internal audio pool implementing three-tier storage with LRU and prefetching."""

    def __init__(
        self,
        audio_dir: str | Path | None = None,
        cache_mb: int | None = None,
        tier2: str | None = None,
        tier2_bucket: str | None = None,
    ) -> None:
        self._audio_dir = Path(audio_dir if audio_dir is not None else tunables.AUDIO_DIR)
        self._cache_mb = cache_mb if cache_mb is not None else tunables.AUDIO_CACHE_MB
        self._tier2_mode = tier2 if tier2 is not None else tunables.AUDIO_TIER2
        self._tier2_bucket = tier2_bucket or os.environ.get("AUDIO_TIER2_BUCKET", "")

        # Tier 0: Pinned in RAM (never evicted)
        self._tier0_pinned: dict[RenderKey, bytes] = {}

        # Tier 1: clips read from local disk + byte-bounded LRU
        # Maps render_key -> (clip bytes, size_bytes)
        self._tier1_lru: OrderedDict[RenderKey, tuple[bytes, int]] = OrderedDict()
        self._tier1_current_bytes: int = 0
        self._tier1_max_bytes: int = self._cache_mb * 1024 * 1024

        # Tier 2 client handle (lazily loaded ONLY if tier2_mode != "none")
        self._s3_client: Any = None

    @property
    def audio_dir(self) -> Path:
        return self._audio_dir

    @property
    def tier1_bytes_used(self) -> int:
        return self._tier1_current_bytes

    @property
    def tier0_count(self) -> int:
        return len(self._tier0_pinned)

    @property
    def tier1_count(self) -> int:
        return len(self._tier1_lru)

    def pin(self, keys: Iterable[RenderKey]) -> None:
        """Pin given render_keys into Tier 0 (RAM). Never evicted."""
        for key in keys:
            if key in self._tier0_pinned:
                continue
            file_path = self._audio_dir / f"{key}.ulaw"
            if file_path.exists():
                with open(file_path, "rb") as f:
                    self._tier0_pinned[key] = trim_edges(f.read())
                # If it was in tier 1, remove and reclaim tier 1 LRU space
                if key in self._tier1_lru:
                    _, size = self._tier1_lru.pop(key)
                    self._tier1_current_bytes -= size

    def _evict_tier1_if_needed(self, new_bytes: int) -> None:
        """Evict oldest LRU entries until new_bytes fits under max_bytes."""
        while (self._tier1_current_bytes + new_bytes > self._tier1_max_bytes) and self._tier1_lru:
            _, (_, old_size) = self._tier1_lru.popitem(last=False)
            self._tier1_current_bytes -= old_size

    def _fetch_tier2(self, render_key: RenderKey) -> bool:
        """Read-through from object store (Tier 2).

        Only imported/called if self._tier2_mode != 'none'.
        """
        if self._tier2_mode == "none":
            return False

        # Lazy import of boto3 ONLY when AUDIO_TIER2 != 'none'
        try:
            import boto3  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                f"AUDIO_TIER2={self._tier2_mode} configured but boto3 is not installed"
            ) from e

        if self._s3_client is None:
            self._s3_client = boto3.client("s3")

        local_file = self._audio_dir / f"{render_key}.ulaw"
        try:
            self._s3_client.download_file(
                self._tier2_bucket,
                f"{render_key}.ulaw",
                str(local_file),
            )
            return local_file.exists()
        except Exception:
            return False

    def get(self, render_key: RenderKey) -> bytes | memoryview:
        """Get audio bytes/memoryview for render_key through the three tiers."""
        # 1. Tier 0 check (RAM pinned)
        if render_key in self._tier0_pinned:
            return self._tier0_pinned[render_key]

        # 2. Tier 1 check (cache hit)
        if render_key in self._tier1_lru:
            data, _ = self._tier1_lru[render_key]
            self._tier1_lru.move_to_end(render_key)
            return memoryview(data)

        # 3. Local SSD file load (Tier 1 miss)
        local_file = self._audio_dir / f"{render_key}.ulaw"
        if not local_file.exists():
            # 4. Tier 2 read-through
            if not self._fetch_tier2(render_key):
                raise KeyError(f"Render key {render_key} not found in pool {self._audio_dir}")

        try:
            data = trim_edges(local_file.read_bytes())  # opens, reads, closes: no handle is kept
        except OSError as e:
            raise RuntimeError(f"Failed to read {local_file}: {e}") from e
        size = len(data)
        self._evict_tier1_if_needed(size)

        self._tier1_lru[render_key] = (data, size)
        self._tier1_current_bytes += size
        return memoryview(data)

    def prefetch(self, keys: Iterable[RenderKey]) -> None:
        """Prefetch scheme chunks into Tier 1.

        Called when Planner returns Stop(reason) ~2 s before first byte.
        """
        if not tunables.AUDIO_PREFETCH_ON_STOP:
            return
        for k in keys:
            if k not in self._tier0_pinned and k not in self._tier1_lru:
                try:
                    self.get(k)
                except Exception:
                    pass

    def warm(
        self,
        pinned_keys: Iterable[RenderKey] | None = None,
        manifest: Mapping[str, Any] | None = None,
    ) -> None:
        """Warm Tier 0 (pinned) and optionally Tier 1 at snapshot flip/boot."""
        to_pin: set[RenderKey] = set()
        if pinned_keys:
            to_pin.update(pinned_keys)

        # If manifest provided, extract fixed lines and chips for Tier 0
        if manifest:
            templates = manifest.get("templates", {})

            def _find_keys(d: Any):
                if isinstance(d, dict):
                    for k, v in d.items():
                        if isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v):
                            to_pin.add(v)
                        else:
                            _find_keys(v)

            _find_keys(templates)

        if to_pin:
            self.pin(to_pin)

        # If warm on boot, pre-load local pool files up to ceiling
        if tunables.AUDIO_WARM_ON_BOOT and self._audio_dir.exists():
            for f in self._audio_dir.glob("*.ulaw"):
                rk = f.stem
                if rk not in self._tier0_pinned and rk not in self._tier1_lru:
                    if self._tier1_current_bytes >= self._tier1_max_bytes:
                        break
                    try:
                        self.get(rk)
                    except Exception:
                        pass

    def close(self) -> None:
        """Drop every cached clip. Nothing holds a file open, so there is nothing else to close."""
        self._tier1_lru.clear()
        self._tier1_current_bytes = 0
        self._tier0_pinned.clear()

    def __enter__(self) -> AudioPool:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
