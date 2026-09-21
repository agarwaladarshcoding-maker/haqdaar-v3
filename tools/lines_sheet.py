"""tools/lines_sheet.py

Step 1.13 (plan 1.11) — write the fixed lines out as a sheet for the owner to correct.

    python -m tools.lines_sheet                  # writes data_cache/reports/lines_sheet.md

The sheet is Markdown because it is read on a phone as often as on a laptop, and because a
correction is made by typing over a line, not by editing YAML. What comes back goes into
lines.yaml with `pinned: true`, which is how p4 knows to leave a human's wording alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

from haqdaar.audio.lines import BAND_TEMPLATES, TRILINGUAL_LINE_ID, band_label, load_lines
from haqdaar.contracts import vocab
from haqdaar.contracts.types import FIXED_LINE_IDS

SHEET_PATH = Path("data_cache/reports/lines_sheet.md")

LANGS = ("en", "hi", "mr")
LANG_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}


def _row(label: str, texts: dict[str, str]) -> list[str]:
    out = [f"### {label}", ""]
    for lang in LANGS:
        text = texts.get(lang, "")
        mark = "" if text else "  _(not translated yet)_"
        out.append(f"- **{LANG_NAMES[lang]}:** {text}{mark}")
    out.append("")
    return out


def build_sheet() -> str:
    lines = load_lines()
    out: list[str] = [
        "# Fixed lines — review sheet",
        "",
        "Every line the call can speak. Correct any line by typing over it.",
        "A line you correct is pinned, and the machine translation will not touch it again.",
        "",
        "Rules these lines must keep:",
        "",
        "- short words, short sentences, one idea per sentence;",
        "- never say the caller is eligible, qualifies, or will get anything;",
        "- `{...}` is filled in by the call. Leave it exactly as it is.",
        "",
        f"## Fixed lines ({len(FIXED_LINE_IDS)})",
        "",
    ]

    for line_id in FIXED_LINE_IDS:
        texts = lines[line_id]
        label = line_id
        if line_id == TRILINGUAL_LINE_ID:
            label = f"{line_id}  _(one recording: Hindi, then Marathi, then English)_"
        out += _row(label, texts)

    out += ["## Chips", "", "The words read out for each keypad key.", ""]
    for box, values in vocab.KEYPAD_LISTS.items():
        out += [f"### Box: {box}", ""]
        for value in values:
            label = vocab.LABELS.get(value)
            if label is None:
                continue
            parts = " · ".join(f"{LANG_NAMES[l]}: {label.get(l, '')}" for l in LANGS)
            out.append(f"- `{value}` — {parts}")
        out.append("")

    out += [
        "## Band labels",
        "",
        "Built from a template, because the bands change with the corpus.",
        "Correct the shape, not the numbers.",
        "",
    ]
    # Numbers a reader will recognise for that box, so the shape is judged and not the maths.
    examples = {"age": (18, 40, 60), "income_band": (0, 100000, 250000)}
    for box, by_lang in BAND_TEMPLATES.items():
        lo, hi, top = examples.get(box, (18, 40, 60))
        out += [f"### Box: {box}", ""]
        for lang in LANGS:
            closed = band_label(box, lo, hi, lang)
            open_top = band_label(box, top, None, lang)
            out.append(f"- **{LANG_NAMES[lang]}:** {closed}  /  {open_top}")
        out.append("")

    return "\n".join(out)


def main() -> int:
    sheet = build_sheet()
    SHEET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHEET_PATH.write_text(sheet, encoding="utf-8")
    print(f"wrote {SHEET_PATH}")
    print(f"lines: {len(FIXED_LINE_IDS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
