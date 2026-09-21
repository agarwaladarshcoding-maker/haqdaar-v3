"""haqdaar/data/pipeline/texts.py

Step 1.14 (plan 1.12) — one list of everything the call can say.

Before this, two places decided what audio exists and they did not agree. p6 built its render
keys from `f"{line_id}_{lang}"` — the line's *name* — while the renderer would speak the line's
*text*. A missing scheme chunk was worse: p6 fell back to the literal string
`f"{sid} {chunk_name} in {lang}"`, hashed that, and wrote a silent stub, so a scheme with no
Hindi benefit text still got a render key, a pool entry, and a file. Nothing anywhere said so.

`all_texts()` is the single answer to "what must exist?". The render walks it to make audio,
the snapshot walks it to build keys, and because both walk the same list they cannot drift.
A text that is missing is missing loudly — it is simply not yielded, and `missing()` names it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterator, NamedTuple, Optional

from haqdaar.audio.lines import TRILINGUAL_LINE_ID, band_label, load_lines
from haqdaar.contracts import tunables, vocab
from haqdaar.contracts.types import (
    FIXED_LINE_IDS,
    SCHEME_CHUNKS,
    compute_render_key,
)

LANGS: tuple[str, ...] = ("en", "hi", "mr")


class Text(NamedTuple):
    """One thing the call can say, and the audio key that must hold it."""

    key: str       # the render key: sha over (text, lang, voice, model, rate)
    lang: str
    text: str
    kind: str      # "line" | "chip" | "band" | "chunk"
    ref: str       # line_id, chip id, band id, or "<scheme_id>/<chunk>"


def _text(lang: str, text: str, kind: str, ref: str) -> Text:
    return Text(compute_render_key(text, lang), lang, text, kind, ref)


def fixed_line_texts(lines_path: Path | str | None = None) -> Iterator[Text]:
    """The fixed lines, in every language they have been written or translated into.

    greeting_trilingual is one recording covering all three languages, so it is keyed on
    "all" exactly as p6 keys it, and never yielded per language.
    """
    lines = load_lines(lines_path)
    for line_id in FIXED_LINE_IDS:
        texts = lines[line_id]
        if line_id == TRILINGUAL_LINE_ID:
            text = texts.get("en", "")
            if text:
                yield _text("all", text, "line", line_id)
            continue
        for lang in LANGS:
            text = texts.get(lang, "").strip()
            if text:
                yield _text(lang, text, "line", line_id)


def chip_texts() -> Iterator[Text]:
    """The keypad chips, straight from vocab.LABELS — the labels are the text."""
    for box, values in vocab.KEYPAD_LISTS.items():
        for value in values:
            label = vocab.LABELS.get(value)
            if not label:
                continue
            for lang in LANGS:
                text = (label.get(lang) or "").strip()
                if text:
                    yield _text(lang, text, "chip", f"chip_{box}_{value}")


def band_texts(bands_by_box: dict[str, list[dict[str, Any]]]) -> Iterator[Text]:
    """The age and income bands this snapshot actually built.

    Bands are per snapshot, so they are passed in rather than read from anywhere: the corpus
    decides how many there are.
    """
    for box, bands in (bands_by_box or {}).items():
        for band in bands:
            for lang in LANGS:
                text = band_label(box, band["lo"], band.get("hi"), lang)
                yield _text(lang, text, "band", f"chip_{box}_{band['code']}")


def scheme_chunk_texts(schemes: list[dict[str, Any]]) -> Iterator[Text]:
    """Every scheme's spoken chunks, in every language that actually has them.

    A chunk with no text is NOT yielded. There is no placeholder and no stub: an empty
    Hindi benefit text means that scheme has no Hindi benefit audio, and the snapshot's
    completeness gate is what decides whether it may still be served.
    """
    for scheme in schemes:
        sid = scheme.get("scheme_id", "")
        chunks = scheme.get("chunks") or {}
        for lang in LANGS:
            lang_chunks = chunks.get(lang) or {}
            for chunk_name in SCHEME_CHUNKS:
                text = str(lang_chunks.get(chunk_name) or "").strip()
                if text:
                    yield _text(lang, text, "chunk", f"{sid}/{chunk_name}")


def all_texts(
    schemes: Optional[list[dict[str, Any]]] = None,
    bands_by_box: Optional[dict[str, list[dict[str, Any]]]] = None,
    lines_path: Path | str | None = None,
) -> list[Text]:
    """Everything the call can say, de-duplicated by (key, lang).

    Two texts that are the same words in the same language are one recording, which is the
    whole point of a content-addressed key: "Let us use the keypad." is written five times in
    lines.yaml and rendered once.
    """
    out: dict[tuple[str, str], Text] = {}
    for item in (
        *fixed_line_texts(lines_path),
        *chip_texts(),
        *band_texts(bands_by_box or {}),
        *scheme_chunk_texts(schemes or []),
    ):
        out.setdefault((item.key, item.lang), item)
    return list(out.values())


def missing(schemes: list[dict[str, Any]], lines_path: Path | str | None = None) -> list[str]:
    """Every text the call needs and does not have, as readable strings.

    This is what a build gate reads. It is the honest version of the silent stub: instead of
    writing 120 ms of quiet and calling the snapshot complete, say out loud what is absent.
    """
    gaps: list[str] = []
    lines = load_lines(lines_path)
    for line_id in FIXED_LINE_IDS:
        if line_id == TRILINGUAL_LINE_ID:
            continue
        for lang in LANGS:
            if not (lines[line_id].get(lang) or "").strip():
                gaps.append(f"line {line_id} has no {lang}")

    for scheme in schemes:
        sid = scheme.get("scheme_id", "")
        chunks = scheme.get("chunks") or {}
        for lang in LANGS:
            lang_chunks = chunks.get(lang) or {}
            for chunk_name in SCHEME_CHUNKS:
                if not str(lang_chunks.get(chunk_name) or "").strip():
                    gaps.append(f"scheme {sid} has no {lang} {chunk_name}")
    return gaps


def _load_schemes(derived_dir: Path) -> list[dict[str, Any]]:
    path = derived_dir / "schemes.jsonl"
    out: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main() -> int:
    """Count what the real inputs say must exist."""
    derived_dir = Path(tunables.CARDS_FILE).parent
    schemes = _load_schemes(derived_dir)
    texts = all_texts(schemes)

    by_kind: dict[str, int] = {}
    for item in texts:
        by_kind[item.kind] = by_kind.get(item.kind, 0) + 1

    print(f"schemes: {len(schemes)}")
    print(f"texts: {len(texts)}")
    for kind in sorted(by_kind):
        print(f"  {kind}: {by_kind[kind]}")
    gaps = missing(schemes)
    print(f"missing: {len(gaps)}")
    for gap in gaps[:20]:
        print(f"  {gap}")
    if len(gaps) > 20:
        print(f"  ... and {len(gaps) - 20} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
