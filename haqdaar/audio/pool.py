"""haqdaar/audio/pool.py

Audio storage — one flat pool, three tiers, read lazily (03-ARCHITECTURE.md §10.1).
Internal to haqdaar/audio. NOT imported by corpus.py.

Tiers:
  tier 0: RAM, pinned (139 fixed lines + ~600 chips, ~35 MB, never evicted)
  tier 1: Local SSD, mmap + byte-bounded LRU at AUDIO_CACHE_MB
  tier 2: S3 / R2, read-through into tier 1 behind AUDIO_TIER2 (default "none")

Runtime imports no TTS client and no S3 client when AUDIO_TIER2=none.
"""
from __future__ import annotations
from collections import OrderedDict
import mmap
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from contracts import tunables
from contracts.types import RenderKey


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

        # Tier 1: Local SSD mmap + byte-bounded LRU
        # Maps render_key -> (mmap_obj, file_obj, size_bytes)
        self._tier1_lru: OrderedDict[RenderKey, tuple[mmap.mmap, Any, int]] = OrderedDict()
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
                    self._tier0_pinned[key] = f.read()
                # If it was in tier 1, remove and reclaim tier 1 LRU space
                if key in self._tier1_lru:
                    mm, f_obj, size = self._tier1_lru.pop(key)
                    try:
                        mm.close()
                        f_obj.close()
                    except Exception:
                        pass
                    self._tier1_current_bytes -= size

    def _evict_tier1_if_needed(self, new_bytes: int) -> None:
        """Evict oldest LRU entries until new_bytes fits under max_bytes."""
        while (self._tier1_current_bytes + new_bytes > self._tier1_max_bytes) and self._tier1_lru:
            old_key, (old_mm, old_f, old_size) = self._tier1_lru.popitem(last=False)
            try:
                old_mm.close()
                old_f.close()
            except Exception:
                pass
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

        # 2. Tier 1 check (Local SSD mmap cache hit)
        if render_key in self._tier1_lru:
            mm, _, _ = self._tier1_lru[render_key]
            self._tier1_lru.move_to_end(render_key)
            return memoryview(mm)

        # 3. Local SSD file load (Tier 1 miss)
        local_file = self._audio_dir / f"{render_key}.ulaw"
        if not local_file.exists():
            # 4. Tier 2 read-through
            if not self._fetch_tier2(render_key):
                raise KeyError(f"Render key {render_key} not found in pool {self._audio_dir}")

        size = local_file.stat().st_size
        self._evict_tier1_if_needed(size)

        f_obj = open(local_file, "rb")
        try:
            if size == 0:
                mm = mmap.mmap(-1, 1)  # stub for empty
            else:
                mm = mmap.mmap(f_obj.fileno(), 0, access=mmap.ACCESS_READ)
        except Exception as e:
            f_obj.close()
            raise RuntimeError(f"Failed to mmap {local_file}: {e}") from e

        self._tier1_lru[render_key] = (mm, f_obj, size)
        self._tier1_current_bytes += size
        return memoryview(mm)

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

        # If warm on boot, pre-mmap local pool files up to ceiling
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
        """Close all open mmaps and file handles in Tier 1."""
        while self._tier1_lru:
            _, (mm, f, _) = self._tier1_lru.popitem()
            try:
                mm.close()
                f.close()
            except Exception:
                pass
        self._tier1_current_bytes = 0
        self._tier0_pinned.clear()

    def __enter__(self) -> AudioPool:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
