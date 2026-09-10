"""haqdaar/data/corpus.py

Runtime Corpus implementation (04-INTERFACES.md § Data — runtime · Corpus).
Frozen verbatim — no added methods, no changed names.

CRITICAL:
- Corpus.load verifies existence AND digest of every manifest render_key against the pool index.
  It must NOT read audio bytes into memory. It raises here and only here.
- Corpus.audio and Corpus.chunks return RenderKey, never bytes.
- corpus.py must NOT import pool.py. Only haqdaar/audio/ imports pool.py.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Any, Mapping

from contracts import tunables
from contracts.types import (
    ANY,
    BoxId,
    Lang,
    RenderKey,
    SCHEME_CHUNKS,
    SEVEN_BOXES,
    ValueCode,
)


class CorpusError(Exception):
    """Raised at Corpus.load when snapshot, manifest, or audio pool index validation fails."""
    pass


def _normalize_text(text: str) -> str:
    """Lowercase and normalize whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _stream_file_sha256(filepath: Path) -> str:
    """Compute sha256 digest in chunks without loading audio bytes into memory."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class Corpus:
    """Frozen Corpus interface verbatim from 04-INTERFACES.md.

    Corpus.load(snapshot_id)                  -> Corpus
    Corpus.snapshot_id                        -> str
    Corpus.mask(box, value)                   -> int
    Corpus.values(box)                        -> tuple[ValueCode, ...]
    Corpus.specificity(scheme_ix)             -> int
    Corpus.scheme_id(scheme_ix)               -> str
    Corpus.alias_lookup(text, lang)           -> tuple[str, ...]            # <=2, by the uniqueness gate
    Corpus.alias_set(lang)                    -> Mapping[str, tuple[str, ...]]
    Corpus.audio(line_id, lang, value=None)   -> RenderKey
    Corpus.chunks(scheme_id, lang)            -> tuple[RenderKey, ...]      # 6, ordered
    Corpus.gate_notes(scheme_id)              -> tuple[str, ...]
    """

    def __init__(
        self,
        snapshot_id: str,
        masks: dict[tuple[BoxId, ValueCode], int],
        vocab_boxes: dict[BoxId, tuple[ValueCode, ...]],
        scheme_ids: tuple[str, ...],
        specificities: tuple[int, ...],
        alias_maps: dict[str, dict[str, tuple[str, ...]]],
        templates: dict[str, Any],
        chunks_map: dict[str, dict[str, tuple[RenderKey, ...]]],
        gate_notes_map: dict[str, tuple[str, ...]],
    ) -> None:
        self._snapshot_id = snapshot_id
        self._masks = masks
        self._vocab_boxes = vocab_boxes
        self._scheme_ids = scheme_ids
        self._specificities = specificities
        self._alias_maps = alias_maps
        self._templates = templates
        self._chunks_map = chunks_map
        self._gate_notes_map = gate_notes_map

    @classmethod
    def load(cls, snapshot_id: str) -> Corpus:
        """Load snapshot and verify existence AND digest of every manifest render_key against pool index.

        Raises here and only here if any file is missing, corrupt, or digest mismatches.
        Must NOT read audio bytes into memory.
        """
        snapshots_path = Path(tunables.SNAPSHOTS_DIR)
        audio_path = Path(tunables.AUDIO_DIR)

        # Resolve CURRENT pointer if requested
        if snapshot_id == "CURRENT":
            current_pointer_path = snapshots_path / "CURRENT"
            if not current_pointer_path.exists():
                raise CorpusError(f"CURRENT pointer file not found at {current_pointer_path}")
            with open(current_pointer_path, "r", encoding="utf-8") as f:
                snapshot_id = f.read().strip()

        snap_dir = snapshots_path / snapshot_id
        if not snap_dir.exists() or not snap_dir.is_dir():
            raise CorpusError(f"Snapshot directory not found: {snap_dir}")

        manifest_path = snap_dir / "manifest.json"
        if not manifest_path.exists():
            raise CorpusError(f"manifest.json missing in snapshot {snap_dir}")

        schemes_jsonl_path = snap_dir / "schemes.jsonl"
        if not schemes_jsonl_path.exists():
            raise CorpusError(f"schemes.jsonl missing in snapshot {snap_dir}")

        vocab_path = snap_dir / "vocab.json"
        if not vocab_path.exists():
            raise CorpusError(f"vocab.json missing in snapshot {snap_dir}")

        masks_bin_path = snap_dir / "masks.bin"
        if not masks_bin_path.exists():
            raise CorpusError(f"masks.bin missing in snapshot {snap_dir}")

        templates_path = snap_dir / "templates.json"
        if not templates_path.exists():
            raise CorpusError(f"templates.json missing in snapshot {snap_dir}")

        # 1. Load manifest.json
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            raise CorpusError(f"Failed to parse manifest.json: {e}") from e

        # 2. Verify existence AND digest against audio pool index (audio/index.json) and local files
        pool_index_path = audio_path / "index.json"
        if not pool_index_path.exists():
            raise CorpusError(f"Pool index missing at {pool_index_path}")
        try:
            with open(pool_index_path, "r", encoding="utf-8") as f:
                pool_index = json.load(f)
        except Exception as e:
            raise CorpusError(f"Failed to read pool index {pool_index_path}: {e}") from e

        declared_render_keys: dict[str, Any] = manifest.get("render_keys", {})
        for rk, rk_meta in declared_render_keys.items():
            expected_digest = rk_meta.get("digest") if isinstance(rk_meta, dict) else None

            # Existence check against pool index
            if rk not in pool_index:
                raise CorpusError(f"Render key {rk} declared in manifest missing from pool index {pool_index_path}")

            # Existence check on disk
            audio_file = audio_path / f"{rk}.ulaw"
            if not audio_file.exists():
                raise CorpusError(f"Audio file missing from pool: {audio_file}")

            # Verify digest without keeping audio bytes in memory
            actual_digest = _stream_file_sha256(audio_file)
            if expected_digest and actual_digest != expected_digest:
                raise CorpusError(
                    f"Digest mismatch for render key {rk}: expected {expected_digest}, got {actual_digest}"
                )
            pool_digest = pool_index[rk].get("digest")
            if pool_digest and actual_digest != pool_digest:
                raise CorpusError(
                    f"Pool index digest mismatch for {rk}: pool says {pool_digest}, file is {actual_digest}"
                )

        # 3. Load schemes.jsonl
        scheme_records: list[dict[str, Any]] = []
        try:
            with open(schemes_jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        scheme_records.append(json.loads(line))
        except Exception as e:
            raise CorpusError(f"Failed to read schemes.jsonl: {e}") from e

        scheme_ids = tuple(s.get("scheme_id", f"S{i+1}") for i, s in enumerate(scheme_records))

        # Calculate specificities: count of non-ANY boxes in SEVEN_BOXES
        specificities_list: list[int] = []
        gate_notes_map: dict[str, tuple[str, ...]] = {}
        for s in scheme_records:
            sid = s.get("scheme_id", "")
            facets = s.get("facets", s)
            spec_count = 0
            for b in SEVEN_BOXES:
                val = facets.get(b)
                if val is not None and val != ANY and val != "ANY":
                    spec_count += 1
            specificities_list.append(spec_count)
            notes = s.get("gate_notes", [])
            gate_notes_map[sid] = tuple(notes) if isinstance(notes, list) else ()

        specificities = tuple(specificities_list)

        # 4. Load vocab.json
        try:
            with open(vocab_path, "r", encoding="utf-8") as f:
                vocab_data = json.load(f)
        except Exception as e:
            raise CorpusError(f"Failed to read vocab.json: {e}") from e

        vocab_boxes: dict[BoxId, tuple[ValueCode, ...]] = {}
        for box, box_meta in vocab_data.get("boxes", {}).items():
            vocab_boxes[box] = tuple(box_meta.get("values", []))

        mask_offsets = vocab_data.get("mask_offsets", {})
        word_bytes = vocab_data.get("word_bytes", max(8, (len(scheme_ids) + 7) // 8))

        # 5. Load masks.bin
        try:
            with open(masks_bin_path, "rb") as f:
                masks_bytes = f.read()
        except Exception as e:
            raise CorpusError(f"Failed to read masks.bin: {e}") from e

        header_fmt = "<4sIII"
        header_size = struct.calcsize(header_fmt)
        if len(masks_bytes) < header_size:
            raise CorpusError("masks.bin file too small to contain header")

        magic, wb, num_s, num_m = struct.unpack_from(header_fmt, masks_bytes, 0)
        if magic != b"MSKB":
            raise CorpusError(f"masks.bin invalid magic: {magic!r}")

        masks: dict[tuple[BoxId, ValueCode], int] = {}
        for key_str, offset in mask_offsets.items():
            if ":" in key_str:
                b, v = key_str.split(":", 1)
                mask_val = int.from_bytes(masks_bytes[offset : offset + wb], byteorder="little")
                masks[(b, v)] = mask_val

        # 6. Load templates.json
        try:
            with open(templates_path, "r", encoding="utf-8") as f:
                templates = json.load(f)
        except Exception as e:
            raise CorpusError(f"Failed to read templates.json: {e}") from e

        # 7. Extract scheme chunks from manifest
        manifest_chunks = manifest.get("chunks", {})
        chunks_map: dict[str, dict[str, tuple[RenderKey, ...]]] = {}
        for sid, lang_chunks in manifest_chunks.items():
            chunks_map[sid] = {}
            for lang, rk_list in lang_chunks.items():
                chunks_map[sid][lang] = tuple(rk_list)

        # 8. Build alias lookup maps
        alias_maps: dict[str, dict[str, tuple[str, ...]]] = {"en": {}, "hi": {}, "mr": {}}
        for scheme in scheme_records:
            sid = scheme.get("scheme_id", "")
            for lang in ("en", "hi", "mr"):
                for alias in scheme.get(f"aliases_{lang}", []):
                    norm = _normalize_text(alias)
                    if norm:
                        existing = alias_maps[lang].get(norm, ())
                        if sid not in existing:
                            alias_maps[lang][norm] = existing + (sid,)

        return cls(
            snapshot_id=snapshot_id,
            masks=masks,
            vocab_boxes=vocab_boxes,
            scheme_ids=scheme_ids,
            specificities=specificities,
            alias_maps=alias_maps,
            templates=templates,
            chunks_map=chunks_map,
            gate_notes_map=gate_notes_map,
        )

    @property
    def snapshot_id(self) -> str:
        """The snapshot identifier bound to this Corpus."""
        return self._snapshot_id

    def mask(self, box: BoxId, value: ValueCode) -> int:
        """Return the precomputed scheme bitmask for (box, value)."""
        if value == ANY:
            # All schemes match ANY
            return (1 << len(self._scheme_ids)) - 1
        return self._masks.get((box, value), 0)

    def values(self, box: BoxId) -> tuple[ValueCode, ...]:
        """Return closed-set values for box."""
        return self._vocab_boxes.get(box, ())

    def specificity(self, scheme_ix: int) -> int:
        """Return count of non-ANY boxes defined for scheme at scheme_ix."""
        if 0 <= scheme_ix < len(self._specificities):
            return self._specificities[scheme_ix]
        return 0

    def scheme_id(self, scheme_ix: int) -> str:
        """Return scheme_id for scheme at scheme_ix."""
        if 0 <= scheme_ix < len(self._scheme_ids):
            return self._scheme_ids[scheme_ix]
        return ""

    def alias_lookup(self, text: str, lang: Lang) -> tuple[str, ...]:
        """Look up normalized alias text in lang. Returns <= 2 scheme_ids by construction."""
        norm = _normalize_text(text)
        return self._alias_maps.get(lang, {}).get(norm, ())

    def alias_set(self, lang: Lang) -> Mapping[str, tuple[str, ...]]:
        """Return mapping of alias -> candidate scheme_ids for language."""
        return self._alias_maps.get(lang, {})

    def audio(self, line_id: str, lang: Lang, value: ValueCode | None = None) -> RenderKey:
        """Return RenderKey (sha256 name) for line or value chip. Never returns bytes."""
        if value is None:
            entry = self._templates.get(line_id)
            if isinstance(entry, dict):
                return entry.get(lang, "")
            elif isinstance(entry, str):
                return entry
            return ""
        # Value chip lookup
        for key_candidate in (
            f"chip_{line_id}_{value}",
            f"{line_id}_{value}",
            f"{line_id}:{value}",
        ):
            entry = self._templates.get(key_candidate)
            if isinstance(entry, dict) and lang in entry:
                return entry[lang]
        entry = self._templates.get(line_id)
        if isinstance(entry, dict) and value in entry and isinstance(entry[value], dict):
            return entry[value].get(lang, "")
        return ""

    def chunks(self, scheme_id: str, lang: Lang) -> tuple[RenderKey, ...]:
        """Return 6 ordered RenderKeys (name, summary, benefit_text, who_can_apply, documents, how_to_apply)."""
        scheme_entry = self._chunks_map.get(scheme_id, {})
        return scheme_entry.get(lang, ())

    def gate_notes(self, scheme_id: str) -> tuple[str, ...]:
        """Return negative exclusion notes for scheme_id."""
        return self._gate_notes_map.get(scheme_id, ())
