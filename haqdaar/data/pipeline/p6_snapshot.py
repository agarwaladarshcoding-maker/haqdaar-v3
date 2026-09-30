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

from haqdaar.contracts import tunables
from haqdaar.contracts import vocab
from haqdaar.contracts.types import (
    ANY,
    HARD_BOXES,
    SCHEME_CHUNKS,
    SEVEN_BOXES,
    RenderKey,
    compute_render_key,
)
from haqdaar.data.pipeline.p1_scrape import DEFAULT_PRIORITY


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
            if count < tunables.ALIAS_CATEGORY_WORD_MIN:
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


class BuildGateError(Exception):
    """Raised when a scheme fails snapshot build gates (05-DATA-CONTRACT §3, T17 §2)."""
    pass


def validate_readback_completeness(scheme: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Gate 3: Read-back completeness - all 6 chunks in 3 languages (T15, T17 §2).

    Returns (True, None) if all 6 chunks (name, summary, benefit_text,
    who_can_apply, documents, how_to_apply) are present and non-empty
    across all 3 languages ('en', 'hi', 'mr').
    Otherwise returns (False, error_reason).
    """
    chunks = scheme.get("chunks")
    scheme_id = scheme.get("scheme_id", "UNKNOWN")
    if not isinstance(chunks, dict):
        return False, f"Scheme {scheme_id} missing 'chunks' dictionary"

    for lang in ("en", "hi", "mr"):
        lang_chunks = chunks.get(lang)
        if not isinstance(lang_chunks, dict):
            return False, f"Scheme {scheme_id} missing chunks for language '{lang}'"
        for chunk_name in SCHEME_CHUNKS:
            val = lang_chunks.get(chunk_name)
            if not val or not str(val).strip():
                return False, f"Scheme {scheme_id} missing '{chunk_name}' chunk in language '{lang}'"

    return True, None


def apply_readback_completeness_gate(
    schemes: Sequence[Mapping[str, Any]],
    strict: bool = False,
) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], str]]]:
    """Applies Gate 3 across a sequence of schemes.

    Returns:
        (accepted_schemes, rejected_schemes_with_reasons)
    If strict=True and any scheme fails Gate 3, raises BuildGateError.
    """
    accepted: list[dict[str, Any]] = []
    rejected: list[tuple[dict[str, Any], str]] = []
    for s in schemes:
        ok, reason = validate_readback_completeness(s)
        if ok:
            accepted.append(dict(s))
        else:
            rejected.append((dict(s), reason or "failed Gate 3"))
            if strict:
                raise BuildGateError(f"Gate 3 rejection: {reason}")
    return accepted, rejected


def _parse_range_value(scheme_id: str, box: str, val: Any) -> tuple[int | None, int | None] | None:
    """Parse a scheme's age/income_band facet into a (lo, hi) range, step 1.5b.

    Returns None when the scheme is unconstrained on this box (ANY / missing):
    it then matches every band. Otherwise returns (lo, hi), either end None
    when that end is open. `{"min": a, "max": b}` is the production shape;
    a bare number `n` (fixtures only) is the point range (n, n).
    """
    if val is None or val == ANY or val == "ANY":
        return None
    if isinstance(val, dict):
        lo = val.get("min")
        hi = val.get("max")
        if lo is not None and not isinstance(lo, (int, float)):
            raise ValueError(f"{scheme_id}: {box} min {lo!r} is not a usable range")
        if hi is not None and not isinstance(hi, (int, float)):
            raise ValueError(f"{scheme_id}: {box} max {hi!r} is not a usable range")
        return (int(lo) if lo is not None else None, int(hi) if hi is not None else None)
    if isinstance(val, bool):
        raise ValueError(f"{scheme_id}: {box} value {val!r} is not a usable range")
    if isinstance(val, (int, float)):
        n = int(val)
        return (n, n)
    if isinstance(val, str) and val.lstrip("-").isdigit():
        n = int(val)
        return (n, n)
    raise ValueError(f"{scheme_id}: {box} value {val!r} is not a usable range")


def _band_wholly_inside(band_lo: int, band_hi: int | None, scheme_lo: int | None, scheme_hi: int | None) -> bool:
    """True iff [band_lo, band_hi] lies wholly inside [scheme_lo, scheme_hi] (None = open end).

    A scheme may be missed by an honest band boundary, but must never be named
    for a band that reaches outside its own range (step 1.5b honesty rule).
    """
    if scheme_lo is not None and band_lo < scheme_lo:
        return False
    if scheme_hi is not None and (band_hi is None or band_hi > scheme_hi):
        return False
    return True


def build_range_bands(
    schemes: list[dict[str, Any]],
    box: str,
    max_bands: int | None = None,
) -> list[dict[str, Any]]:
    """Build keypad bands for a range box (age, income_band), step 1.5b.

    Edges are each scheme's `min` and `max + 1` (an inclusive max becomes the
    start of the NEXT band, fixing the old off-by-one). Bands cover 0..infinity
    with no gaps. When more than `max_bands` result, the edge used by the
    fewest schemes is dropped first (ties: the larger edge) until the count
    fits — this can only ever merge bands, never widen what a scheme matches,
    because masks are computed separately by the wholly-inside rule.

    Returns a list of {"code", "lo", "hi"} dicts, ascending, hi=None on the
    open top band. Empty when no scheme constrains this box.
    """
    if max_bands is None:
        max_bands = tunables.KEYPAD_CARDINALITY_MAX

    edge_votes: dict[int, int] = defaultdict(int)
    for scheme in schemes:
        val = scheme.get(box)
        if val is None and "facets" in scheme:
            val = scheme["facets"].get(box)
        rng = _parse_range_value(scheme.get("scheme_id"), box, val)
        if rng is None:
            continue
        lo, hi = rng
        if lo is not None and lo > 0:
            edge_votes[lo] += 1
        if hi is not None and (hi + 1) > 0:
            edge_votes[hi + 1] += 1

    edges = sorted(edge_votes)
    if not edges:
        return []

    while len(edges) > max_bands - 1:
        worst = min(edges, key=lambda e: (edge_votes[e], -e))
        edges.remove(worst)

    bounds: list[int | None] = [0, *edges, None]
    bands: list[dict[str, Any]] = []
    for i in range(len(bounds) - 1):
        lo = bounds[i]
        next_bound = bounds[i + 1]
        hi = None if next_bound is None else next_bound - 1
        code = f"{lo}+" if hi is None else f"{lo}-{hi}"
        bands.append({"code": code, "lo": lo, "hi": hi})
    return bands


def scheme_has_all_clips(scheme: Mapping[str, Any], audio_path: Path) -> bool:
    """True when every one of a scheme's 18 chunks (6 chunks x 3 langs) has a .ulaw file."""
    sid = scheme.get("scheme_id", "")
    for lang in ("en", "hi", "mr"):
        for chunk_name in SCHEME_CHUNKS:
            text = ""
            if "chunks" in scheme and lang in scheme["chunks"] and chunk_name in scheme["chunks"][lang]:
                text = scheme["chunks"][lang][chunk_name]
            elif f"{chunk_name}_{lang}" in scheme:
                text = scheme[f"{chunk_name}_{lang}"]
            elif chunk_name == "name":
                text = scheme.get(f"scheme_name_{lang}", f"Scheme {sid}")
            rk = compute_render_key(text, lang)
            if not (audio_path / f"{rk}.ulaw").exists():
                return False
    return True


def build_snapshot(
    schemes_data: list[dict[str, Any]],
    templates_data: dict[str, Any] | None = None,
    snapshot_id: str | None = None,
    snapshots_dir: str | Path | None = None,
    audio_dir: str | Path | None = None,
    render_stubs: bool = False,
    enforce_readback_gate: bool = False,
    only_with_audio: bool = False,
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

    if only_with_audio:
        schemes_data = [s for s in schemes_data if scheme_has_all_clips(s, audio_path)]

    if enforce_readback_gate:
        for s in schemes_data:
            ok, reason = validate_readback_completeness(s)
            if not ok:
                raise BuildGateError(f"Gate 3 rejected scheme {s.get('scheme_id')}: {reason}")

    # 1. Alias uniqueness gate
    schemes, alias_map = apply_alias_uniqueness_gate(schemes_data)
    num_schemes = len(schemes)

    # 1b. Priority ordering (D8, step 1.8): bit index breaks ties (terminals.py
    # sorts by specificity, then bit index), so ordering the bits by
    # (priority, slug) gives specificity -> priority -> slug without any
    # change to Corpus (frozen) or terminals.py. Fixtures without scheme_id
    # (S1..) keep input order: they have no slug to sort by and no priority
    # story of their own.
    if all("scheme_id" in s for s in schemes):
        schemes.sort(key=lambda s: (s.get("priority", DEFAULT_PRIORITY), s.get("scheme_id", "")))

    # 2. Derive bit index and word width
    word_bytes = max(8, (num_schemes + 7) // 8)
    for bit_idx, scheme in enumerate(schemes):
        scheme["bit"] = bit_idx
        if "scheme_id" not in scheme:
            scheme["scheme_id"] = f"S{bit_idx + 1}"

    # 3. Discover closed vocabulary per box
    # Allow-list only: boxes are exactly SEVEN_BOXES. A skip list here would let any
    # unlisted record key (evidence_quotes, a later priority field, ...) become a
    # keypad box by accident.
    boxes = list(SEVEN_BOXES)

    vocab_boxes: dict[str, dict[str, Any]] = {}
    for box in boxes:
        if box in vocab.KEYPAD_LISTS:
            # Closed-list boxes (D6, step 1.5a): values = vocab.py's list, in vocab
            # order, every value, even ones no scheme on this snapshot holds. This is
            # what the keypad menu reads aloud, so the order must be fixed and known,
            # not "whatever happens to appear on schemes" (see plan step 1.5a).
            values_list = list(vocab.KEYPAD_LISTS[box])
            for s in schemes:
                val = s.get(box)
                if val is None and "facets" in s:
                    val = s["facets"].get(box)
                if val is None or val == ANY or val == "ANY":
                    continue
                candidates = val if isinstance(val, (list, tuple, set)) else (val,)
                for v in candidates:
                    if v == ANY or v == "ANY":
                        continue
                    if str(v) not in values_list:
                        raise ValueError(
                            f"{s.get('scheme_id')}: {box} value {v!r} not in vocab"
                        )
            code_map = {v: idx for idx, v in enumerate(values_list)}
            vocab_source = "corpus_prose_cut" if box == "occupation" else "authored"
            vocab_boxes[box] = {
                "values": values_list,
                "code_map": code_map,
                "vocab_source": vocab_source,
            }
        else:
            # age / income_band: range boxes. The keypad values ARE the band
            # codes (step 1.5b) — a caller picks a band, never a raw number.
            bands = build_range_bands(schemes, box, max_bands=tunables.KEYPAD_CARDINALITY_MAX)
            values_list = [b["code"] for b in bands]
            code_map = {v: idx for idx, v in enumerate(values_list)}
            vocab_boxes[box] = {
                "values": values_list,
                "code_map": code_map,
                "vocab_source": "authored",
                "bands": bands,
            }

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
        is_range_box = box not in vocab.KEYPAD_LISTS
        band_by_code = (
            {b["code"]: b for b in vocab_boxes[box]["bands"]} if is_range_box else {}
        )
        for val in vocab_boxes[box]["values"]:
            mask_word = 0
            if is_range_box:
                # age / income_band (step 1.5b): a scheme's bit is set only
                # when the band lies wholly inside the scheme's own range, or
                # the scheme is ANY for this box. A scheme may be missed by
                # a band boundary, but is never wrongly named.
                band = band_by_code[val]
                for i, scheme in enumerate(schemes):
                    scheme_val = scheme.get(box)
                    if scheme_val is None and "facets" in scheme:
                        scheme_val = scheme["facets"].get(box)
                    rng = _parse_range_value(scheme.get("scheme_id"), box, scheme_val)
                    if rng is None:
                        mask_word |= (1 << i)
                    elif _band_wholly_inside(band["lo"], band["hi"], rng[0], rng[1]):
                        mask_word |= (1 << i)
            else:
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
    }
    vocab_path = snap_dir / "vocab.json"
    with open(vocab_path, "w", encoding="utf-8") as f:
        json.dump(vocab_json_data, f, indent=2, ensure_ascii=False)

    # 6. Build templates.json and collect manifest render_keys
    # Fixed lines: 46 lines, plus value chips (values expanded)
    from haqdaar.contracts.types import FIXED_LINE_IDS

    templates: dict[str, Any] = {}

    # Seed default fixed lines from the one text list, so the key the snapshot records is the
    # key of the words the renderer will actually speak. Hashing f"{line_id}_{lang}" here meant
    # the pool was keyed on a line's NAME while the audio held its TEXT, and nothing compared
    # the two. A line with no text yet keeps the id-based key, so the snapshot still has a slot
    # for it and texts.missing() is what reports that it is empty.
    from haqdaar.data.pipeline.texts import fixed_line_texts

    line_keys: dict[str, dict[str, str]] = {}
    for item in fixed_line_texts():
        line_keys.setdefault(item.ref, {})[item.lang] = item.key

    for line_id in FIXED_LINE_IDS:
        templates[line_id] = {}
        if line_id == "greeting_trilingual":
            # The one non-per-language file (plays hi -> mr -> en)
            rk = line_keys.get(line_id, {}).get("all") or compute_render_key(
                "greeting_trilingual_audio", "all"
            )
            templates[line_id]["all"] = rk
            templates[line_id]["hi"] = rk
            templates[line_id]["mr"] = rk
            templates[line_id]["en"] = rk
        else:
            for lang in ("en", "hi", "mr"):
                rk = line_keys.get(line_id, {}).get(lang) or compute_render_key(
                    f"{line_id}_{lang}", lang
                )
                templates[line_id][lang] = rk

    if templates_data:
        templates.update(templates_data)

    # Chips and bands take their keys from the same text list as the render, like the lines
    # above. Hashing the raw value ("farmer", "0-13") here gave 87 keys no clip was ever made
    # for, and would have spoken the code instead of the label. A value with no label keeps
    # the old key, so texts.missing() and Corpus.load still see the gap.
    from haqdaar.data.pipeline.texts import band_texts, chip_texts, key_texts

    chip_keys: dict[str, dict[str, str]] = {}
    bands_by_box = {box: meta["bands"] for box, meta in vocab_boxes.items() if "bands" in meta}
    for item in (*chip_texts(), *band_texts(bands_by_box)):
        chip_keys.setdefault(item.ref, {})[item.lang] = item.key

    # "press 1." .. "press 9.", played after each chip of a keypad menu (plan 2.7).
    for item in key_texts():
        if item.ref not in templates:
            templates[item.ref] = {}
        templates[item.ref].setdefault(item.lang, item.key)

    for box, box_meta in vocab_boxes.items():
        for val in box_meta["values"]:
            chip_id = f"chip_{box}_{val}"
            if chip_id not in templates:
                templates[chip_id] = {}
                for lang in ("en", "hi", "mr"):
                    rk = chip_keys.get(chip_id, {}).get(lang) or compute_render_key(f"{val}", lang)
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

                # No placeholder. This used to fall back to the literal string
                # f"{sid} {chunk_name} in {lang}", hash it, and write a silent stub, so a
                # scheme with no Hindi benefit text still got a key, a pool entry and a file
                # that said nothing. The key is now the key of the empty text, the readback
                # completeness gate sees the gap, and texts.missing() names it out loud.
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


def main(argv: list[str] | None = None) -> int:
    """Build a snapshot from the real schemes (what p2..p5 wrote) and flip CURRENT to it.

    When only_with_audio is True (default), schemes missing any .ulaw clip are skipped,
    so CURRENT only flips to a snapshot that Corpus.load can load.
    """
    import argparse
    from haqdaar.data.pipeline.texts import _load_schemes, missing

    parser = argparse.ArgumentParser(description="Build snapshot from derived schemes.")
    parser.add_argument(
        "--only-with-audio",
        dest="only_with_audio",
        action="store_true",
        default=True,
        help="Skip schemes missing audio clips (default).",
    )
    parser.add_argument(
        "--all-schemes",
        dest="only_with_audio",
        action="store_false",
        help="Include all schemes even if missing audio clips.",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    schemes = _load_schemes(Path(tunables.CARDS_FILE).parent)
    snap = build_snapshot(
        schemes,
        enforce_readback_gate=True,
        only_with_audio=args.only_with_audio,
    )
    manifest = json.loads(
        (Path(tunables.SNAPSHOTS_DIR) / snap / "manifest.json").read_text(encoding="utf-8")
    )
    keys = manifest["render_keys"]
    no_audio = sum(1 for meta in keys.values() if not meta.get("digest"))
    print(f"snapshot: {snap}  schemes: {manifest['num_schemes']}  clips: {len(keys)}")
    print(f"clips not rendered yet: {no_audio}  texts missing: {len(missing(schemes))}")
    return 1 if no_audio else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
