"""haqdaar/data/pipeline/p6_snapshot.py

Snapshot builder (Step 11, 05-DATA-CONTRACT.md §2).
Build tools — NEVER imported by runtime code.

Produces:
  snapshots/<snapshot_id>/
    schemes.jsonl      one flat row per scheme
    masks.bin          packed (box, value) -> word
    vocab.json         closed value sets + code map + vocab_source per box
    templates.json     line_id -> {lang -> render_key}, values expanded
    manifest.json      the snapshot IS the manifest
  audio/<render_key>.ulaw  ONE FLAT POOL, shared across snapshots (audio/index.json)
  snapshots/CURRENT   atomic pointer to latest snapshot_id
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
from typing import Any, Mapping, Sequence

from contracts import tunables
from contracts.types import (
    ANY,
    HARD_BOXES,
    SCHEME_CHUNKS,
    SEVEN_BOXES,
    RenderKey,
    compute_render_key,
)


def _compute_file_sha256(filepath: Path) -> str:
    """Compute SHA256 hex digest of a file in streaming chunks (never loads whole file into memory)."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _normalize_text(text: str) -> str:
    """Lowercase and normalize whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def apply_alias_uniqueness_gate(
    schemes: list[dict[str, Any]],
    langs: Sequence[str] = ("en", "hi", "mr"),
) -> tuple[list[dict[str, Any]], dict[str, dict[str, list[str]]]]:
    """Gate 1: Alias uniqueness gate (05-DATA-CONTRACT §3).

    - Alias on >= 3 schemes: dropped from all of them (category word: yojana, sarkari).
    - Alias on exactly 2 schemes: kept (Door A disambiguation pair).
    - Alias on 1 scheme: kept.
    Returns:
        (schemes_with_filtered_aliases, alias_map_per_lang)
    """
    alias_counts: dict[str, dict[str, int]] = {lang: defaultdict(int) for lang in langs}
    alias_to_schemes: dict[str, dict[str, list[str]]] = {lang: defaultdict(list) for lang in langs}

    # Pass 1: count occurrences per language
    for scheme in schemes:
        scheme_id = scheme["scheme_id"]
        for lang in langs:
            raw_aliases = scheme.get(f"aliases_{lang}", [])
            seen_for_this_scheme: set[str] = set()
            for alias in raw_aliases:
                norm = _normalize_text(alias)
                if not norm or norm in seen_for_this_scheme:
                    continue
                seen_for_this_scheme.add(norm)
                alias_counts[lang][norm] += 1
                alias_to_schemes[lang][norm].append(scheme_id)

    # Pass 2: filter aliases per scheme and build alias lookup table
    filtered_alias_map: dict[str, dict[str, list[str]]] = {lang: {} for lang in langs}
    for lang in langs:
        for alias_norm, count in alias_counts[lang].items():
            if count < tunables.ALIAS_FLOOR:
                filtered_alias_map[lang][alias_norm] = sorted(alias_to_schemes[lang][alias_norm])

    updated_schemes: list[dict[str, Any]] = []
    for scheme in schemes:
        updated = dict(scheme)
        for lang in langs:
            raw_aliases = scheme.get(f"aliases_{lang}", [])
            kept: list[str] = []
            seen: set[str] = set()
            for alias in raw_aliases:
                norm = _normalize_text(alias)
                if norm and norm in filtered_alias_map[lang] and norm not in seen:
                    seen.add(norm)
                    kept.append(norm)
            updated[f"aliases_{lang}"] = kept
        updated_schemes.append(updated)

    return updated_schemes, filtered_alias_map


def derive_keypad_bands(
    schemes: list[dict[str, Any]],
    box: str,
    max_bands: int | None = None,
) -> list[str]:
    """Derive keypad band edges from cutoffs present in scheme facets (<= 9 bands)."""
    if max_bands is None:
        max_bands = tunables.KEYPAD_CARDINALITY_MAX
    cutoffs: set[int] = set()
    for scheme in schemes:
        val = scheme.get(box)
        if val is None and "facets" in scheme:
            val = scheme["facets"].get(box)
        if isinstance(val, (int, float)):
            cutoffs.add(int(val))
        elif isinstance(val, str) and val.isdigit():
            cutoffs.add(int(val))
        elif isinstance(val, dict):
            # min / max numeric cutoffs
            if "min" in val and isinstance(val["min"], (int, float)):
                cutoffs.add(int(val["min"]))
            if "max" in val and isinstance(val["max"], (int, float)):
                cutoffs.add(int(val["max"]))

    sorted_cutoffs = sorted(cutoffs)
    if not sorted_cutoffs:
        if box == "age":
            return ["<18", "18-25", "26-35", "36-50", "51-60", ">60"]
        elif box == "income_band":
            return ["<50000", "50000-100000", "100001-250000", "250001-500000", ">500000"]
        return ["band_1", "band_2", "band_3"]

    # Limit to max_bands - 1 split points
    if len(sorted_cutoffs) >= max_bands:
        step = len(sorted_cutoffs) / (max_bands - 1)
        sampled = [sorted_cutoffs[int(i * step)] for i in range(max_bands - 1)]
    else:
        sampled = sorted_cutoffs

    bands: list[str] = []
    bands.append(f"<{sampled[0]}")
    for i in range(len(sampled) - 1):
        bands.append(f"{sampled[i]}-{sampled[i+1]-1}")
    bands.append(f">={sampled[-1]}")
    return bands[:max_bands]


def build_snapshot(
    schemes_data: list[dict[str, Any]],
    templates_data: dict[str, Any] | None = None,
    snapshot_id: str | None = None,
    snapshots_dir: str | Path | None = None,
    audio_dir: str | Path | None = None,
    render_stubs: bool = True,
) -> str:
    """Build a complete snapshot adhering to 05-DATA-CONTRACT.md §2.

    Writes:
      snapshots/<snapshot_id>/schemes.jsonl
      snapshots/<snapshot_id>/masks.bin
      snapshots/<snapshot_id>/vocab.json
      snapshots/<snapshot_id>/templates.json
      snapshots/<snapshot_id>/manifest.json
      snapshots/CURRENT
      audio/index.json
    Returns:
      snapshot_id (str)
    """
    if snapshot_id is None:
        snapshot_id = datetime.now(timezone.utc).strftime("snap_%Y%m%d_%H%M%S")

    snapshots_path = Path(snapshots_dir if snapshots_dir is not None else tunables.SNAPSHOTS_DIR)
    audio_path = Path(audio_dir if audio_dir is not None else tunables.AUDIO_DIR)
    snap_dir = snapshots_path / snapshot_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    audio_path.mkdir(parents=True, exist_ok=True)

    # 1. Alias uniqueness gate
    schemes, alias_map = apply_alias_uniqueness_gate(schemes_data)
    num_schemes = len(schemes)

    # 2. Derive bit index and word width
    word_bytes = max(8, (num_schemes + 7) // 8)
    for bit_idx, scheme in enumerate(schemes):
        scheme["bit"] = bit_idx
        if "scheme_id" not in scheme:
            scheme["scheme_id"] = f"S{bit_idx + 1}"

    # 3. Discover closed vocabulary per box
    boxes = list(SEVEN_BOXES)
    # also add any additional facet boxes present
    for s in schemes:
        for k in s.keys():
            if k not in (
                "scheme_id", "bit", "myscheme_slug", "source_url", "level", "state", "department",
                "fetched_on", "source_sha256", "facets_source", "facets_verified_by", "facets_verified_on",
                "en_sections_origin", "hi_sections_origin", "mr_sections_origin",
                "en_summary_origin", "hi_summary_origin", "mr_summary_origin",
                "en_verified_by", "en_verified_on", "hi_verified_by", "hi_verified_on", "mr_verified_by", "mr_verified_on",
                "scheme_name_en", "scheme_name_hi", "scheme_name_mr",
                "aliases_en", "aliases_hi", "aliases_mr", "gate_notes", "chunks", "facets",
            ) and not k.startswith("chunk_"):
                if k not in boxes:
                    boxes.append(k)

    vocab_boxes: dict[str, dict[str, Any]] = {}
    for box in boxes:
        values_set: set[str] = set()
        for s in schemes:
            val = s.get(box)
            if val is None and "facets" in s:
                val = s["facets"].get(box)
            if val is not None and val != ANY and val != "ANY":
                if isinstance(val, (list, tuple, set)):
                    for v in val:
                        if v != ANY:
                            values_set.add(str(v))
                else:
                    values_set.add(str(val))
        sorted_values = sorted(values_set)
        code_map = {v: idx for idx, v in enumerate(sorted_values)}
        vocab_source = "corpus_prose_cut" if box == "occupation" else "authored"
        vocab_boxes[box] = {
            "values": sorted_values,
            "code_map": code_map,
            "vocab_source": vocab_source,
        }

    keypad_age_bands = derive_keypad_bands(schemes, "age", max_bands=tunables.KEYPAD_CARDINALITY_MAX)
    keypad_income_bands = derive_keypad_bands(schemes, "income_band", max_bands=tunables.KEYPAD_CARDINALITY_MAX)

    # 4. Build masks.bin: packed (box, value) -> word
    # Rule: ANY sets a scheme's bit in every mask for that column.
    masks_bin_data = bytearray()
    mask_offsets: dict[str, int] = {}
    mask_entry_count = 0

    # Header: Magic b"MSKB", word_bytes (uint32), num_schemes (uint32), num_masks (uint32 placeholder)
    header_format = "<4sIII"
    header_size = struct.calcsize(header_format)
    masks_bin_data.extend(b"\x00" * header_size)

    for box in sorted(vocab_boxes.keys()):
        for val in vocab_boxes[box]["values"]:
            mask_word = 0
            for i, scheme in enumerate(schemes):
                scheme_val = scheme.get(box)
                if scheme_val is None and "facets" in scheme:
                    scheme_val = scheme["facets"].get(box)

                # Hard constraint: ANY sets a scheme's bit in every mask for that column
                if scheme_val == ANY or scheme_val == "ANY" or scheme_val is None:
                    mask_word |= (1 << i)
                elif isinstance(scheme_val, (list, tuple, set)):
                    if ANY in scheme_val or "ANY" in scheme_val or val in scheme_val:
                        mask_word |= (1 << i)
                elif str(scheme_val) == str(val):
                    mask_word |= (1 << i)

            offset = len(masks_bin_data)
            mask_offsets[f"{box}:{val}"] = offset
            masks_bin_data.extend(mask_word.to_bytes(word_bytes, byteorder="little"))
            mask_entry_count += 1

    # Write actual header
    struct.pack_into(
        header_format,
        masks_bin_data,
        0,
        b"MSKB",
        word_bytes,
        num_schemes,
        mask_entry_count,
    )

    masks_bin_path = snap_dir / "masks.bin"
    with open(masks_bin_path, "wb") as f:
        f.write(masks_bin_data)

    # 5. Write vocab.json
    vocab_json_data = {
        "snapshot_id": snapshot_id,
        "num_schemes": num_schemes,
        "word_bytes": word_bytes,
        "boxes": vocab_boxes,
        "mask_offsets": mask_offsets,
        "keypad_bands": {
            "age": keypad_age_bands,
            "income_band": keypad_income_bands,
        },
    }
    vocab_path = snap_dir / "vocab.json"
    with open(vocab_path, "w", encoding="utf-8") as f:
        json.dump(vocab_json_data, f, indent=2, ensure_ascii=False)

    # 6. Build templates.json and collect manifest render_keys
    # Fixed lines: 46 lines, plus value chips (values expanded)
    from contracts.types import FIXED_LINE_IDS

    templates: dict[str, Any] = {}

    # Seed default fixed lines
    for line_id in FIXED_LINE_IDS:
        templates[line_id] = {}
        if line_id == "greeting_trilingual":
            # The one non-per-language file (plays hi -> mr -> en)
            rk = compute_render_key("greeting_trilingual_audio", "all")
            templates[line_id]["all"] = rk
            templates[line_id]["hi"] = rk
            templates[line_id]["mr"] = rk
            templates[line_id]["en"] = rk
        else:
            for lang in ("en", "hi", "mr"):
                rk = compute_render_key(f"{line_id}_{lang}", lang)
                templates[line_id][lang] = rk

    if templates_data:
        templates.update(templates_data)

    # Add default chips if not provided
    for box, box_meta in vocab_boxes.items():
        for val in box_meta["values"]:
            chip_id = f"chip_{box}_{val}"
            if chip_id not in templates:
                templates[chip_id] = {}
                for lang in ("en", "hi", "mr"):
                    text = f"{val}"
                    rk = compute_render_key(text, lang)
                    templates[chip_id][lang] = rk

    templates_path = snap_dir / "templates.json"
    with open(templates_path, "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=2, ensure_ascii=False)

    # 7. Render/ensure audio files in shared pool and build manifest
    pool_index_path = audio_path / "index.json"
    pool_index: dict[str, dict[str, Any]] = {}
    if pool_index_path.exists():
        try:
            with open(pool_index_path, "r", encoding="utf-8") as f:
                pool_index = json.load(f)
        except Exception:
            pool_index = {}

    manifest_render_keys: dict[str, dict[str, Any]] = {}
    scheme_chunks_map: dict[str, dict[str, list[str]]] = {}

    # Chunks for each scheme: 6 chunks × 3 languages = 18 files per scheme
    for scheme in schemes:
        sid = scheme["scheme_id"]
        scheme_chunks_map[sid] = {}
        for lang in ("en", "hi", "mr"):
            chunk_rks: list[str] = []
            for chunk_name in SCHEME_CHUNKS:
                # Text from scheme or default
                text = ""
                if "chunks" in scheme and lang in scheme["chunks"] and chunk_name in scheme["chunks"][lang]:
                    text = scheme["chunks"][lang][chunk_name]
                elif f"{chunk_name}_{lang}" in scheme:
                    text = scheme[f"{chunk_name}_{lang}"]
                elif chunk_name == "name":
                    text = scheme.get(f"scheme_name_{lang}", f"Scheme {sid}")
                else:
                    text = f"{sid} {chunk_name} in {lang}"

                rk = compute_render_key(text, lang)
                chunk_rks.append(rk)

                # Ensure file exists in audio pool
                audio_file = audio_path / f"{rk}.ulaw"
                if not audio_file.exists() and render_stubs:
                    # Write 120 ms tail-padded μ-law stub (8000 Hz mono = 8000 bytes/sec)
                    stub_len = max(16, int(tunables.SAMPLE_RATE * (tunables.TAIL_PAD_MS / 1000.0)))
                    with open(audio_file, "wb") as f:
                        f.write(b"\xff" * stub_len)

                if audio_file.exists():
                    file_sha = _compute_file_sha256(audio_file)
                    file_size = audio_file.stat().st_size
                else:
                    file_sha = ""
                    file_size = 0

                meta = {
                    "digest": file_sha,
                    "size": file_size,
                    "type": "chunk",
                    "scheme_id": sid,
                    "chunk": chunk_name,
                    "lang": lang,
                }
                manifest_render_keys[rk] = meta
                pool_index[rk] = {
                    "digest": file_sha,
                    "size": file_size,
                    "path": f"{rk}.ulaw",
                }

            scheme_chunks_map[sid][lang] = chunk_rks

    # Add template render keys to manifest
    def _collect_template_keys(d: Any, prefix: str = ""):
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v):
                    rk = v
                    audio_file = audio_path / f"{rk}.ulaw"
                    if not audio_file.exists() and render_stubs:
                        stub_len = max(16, int(tunables.SAMPLE_RATE * (tunables.TAIL_PAD_MS / 1000.0)))
                        with open(audio_file, "wb") as f:
                            f.write(b"\xff" * stub_len)
                    if audio_file.exists():
                        file_sha = _compute_file_sha256(audio_file)
                        file_size = audio_file.stat().st_size
                    else:
                        file_sha = ""
                        file_size = 0
                    meta = {
                        "digest": file_sha,
                        "size": file_size,
                        "type": "template",
                        "line_id": f"{prefix}{k}",
                    }
                    manifest_render_keys[rk] = meta
                    pool_index[rk] = {
                        "digest": file_sha,
                        "size": file_size,
                        "path": f"{rk}.ulaw",
                    }
                else:
                    _collect_template_keys(v, f"{prefix}{k}.")

    _collect_template_keys(templates)

    # Write audio pool index (audio/index.json)
    with open(pool_index_path, "w", encoding="utf-8") as f:
        json.dump(pool_index, f, indent=2, ensure_ascii=False)

    # 8. Write schemes.jsonl
    schemes_jsonl_path = snap_dir / "schemes.jsonl"
    with open(schemes_jsonl_path, "w", encoding="utf-8") as f:
        for s in schemes:
            row = dict(s)
            sid = s["scheme_id"]
            if sid in scheme_chunks_map:
                row["chunk_keys"] = scheme_chunks_map[sid]
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # 9. Write manifest.json
    manifest_data = {
        "snapshot_id": snapshot_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "num_schemes": num_schemes,
        "word_bytes": word_bytes,
        "keypad_bands": {
            "age": keypad_age_bands,
            "income_band": keypad_income_bands,
        },
        "vocab_source": {box: meta["vocab_source"] for box, meta in vocab_boxes.items()},
        "render_keys": manifest_render_keys,
        "chunks": scheme_chunks_map,
        "templates": templates,
    }
    manifest_path = snap_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    # 10. Flip CURRENT pointer
    current_path = snapshots_path / "CURRENT"
    with open(current_path, "w", encoding="utf-8") as f:
        f.write(snapshot_id.strip() + "\n")

    return snapshot_id


if __name__ == "__main__":
    import sys
    snap = build_snapshot([], snapshot_id="snap_initial")
    print(f"Created snapshot {snap}")
