"""tools/intake_build.py  (N7, builder half)

Turns the team's schemes (source.md + index.json + annot/<slug>.json) into talk-only rows, checks them hard, and builds an
ISOLATED snapshot: the live schemes plus the new ones. It never flips snapshots/CURRENT, never writes into snapshots/
or audio/ of the repo, and makes no network or model call. Spec: .agent/INTAKE-FORMAT.md.

    python -m tools.intake_build [--annot-dir data_cache/intake/annot] [--out-dir data_cache/intake]   (or: make intake)

Writes under --out-dir:  report.txt, schemes_intake.jsonl, snaps/<id>/ + snaps/CURRENT, audio/ (links to the live clips).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from haqdaar.contracts import tunables, vocab
from haqdaar.contracts.types import SCHEME_CHUNKS, SEVEN_BOXES, UNASKED

CHUNK_CAP = 320     # the live English chunks run to 307 characters; a new chunk is cut at a sentence end below this
NOT_LISTED = "The scheme text does not list this."
ROLES = ("needs", "bars")
EVIDENCE_KEYS = ("age", "gender", "social_category", "occupation", "home_state", "income_max_inr")
ANNOT_KEYS = {
    "slug", "name_en", "name_hi", "aliases_en", "aliases_hi", "category", "category_why", "gender", "social_category",
    "age", "income_max_inr", "occupation", "state", "home_state", "gives", "sub_kind", "for_organisation", "facts",
    "gate_notes", "evidence", "confidence", "notes",
}
REQUIRED_KEYS = ANNOT_KEYS - {"category_why", "income_max_inr", "for_organisation", "confidence", "notes"}
SUB_KIND = re.compile(r"^[a-z0-9_]+$")
DEVANAGARI = re.compile("[ऀ-ॿ]")
ZERO_WIDTH = re.compile("[​-‏⁠﻿­]")
LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
URL = re.compile(r"https?://\S+")
# A full stop that ends a sentence: not the dot of "Rs.", "No.", "i.e." (the "3." of a numbered list is left out in cut()).
SENTENCE_END = re.compile(r"(?<!\bRs)(?<!\bNo)(?<!\bSh)(?<!\bSmt)(?<!\bDr)(?<!\bi\.e)(?<!\be\.g)[.!?।](?=\s|$)")
LIST_NUMBER = re.compile(r"(^|[.!?\u0964]\s)\d{1,2}\.$")
SECTIONS = {
    "details": "details", "benefits": "benefits", "eligibility": "eligibility", "exclusions": "exclusions",
    "documents required": "documents", "application process": "how", "frequently asked questions": "faq",
}
HEADING = re.compile(r"^#{1,3}\s*[\s*_​-‏⁠﻿]*([A-Za-z ]+?)[\s*_​-‏⁠﻿]*$")


# --- text ---------------------------------------------------------------------------------------------------------

def norm(text: str) -> str:
    """The one form both a quote and the scheme text are brought to before they are compared."""
    text = ZERO_WIDTH.sub("", text)
    text = LINK.sub(r"\1", text)
    text = text.replace("\\", "").translate({ord(c): None for c in "*_#>"})
    return re.sub(r"\s+", " ", text).strip().lower()


def clean(lines: list[str]) -> str:
    """Section lines as plain sentences: no marks, no zero-width marks, no long raw links."""
    out = []
    for line in lines:
        line = ZERO_WIDTH.sub("", line)
        line = LINK.sub(r"\1", line)
        line = URL.sub(lambda m: m.group(0) if len(m.group(0)) <= 60 else "", line)
        line = line.replace("\\", "").translate({ord(c): None for c in "*_#>"})
        line = re.sub(r"\s+", " ", line).strip(" |-•")
        if not line:
            continue
        out.append(line if line[-1] in ".!?:;।" else line + ".")
    return " ".join(out)


def cut(text: str, cap: int = CHUNK_CAP) -> tuple[str, bool]:
    """Cut at the last sentence end that fits (else the last space). Returns (text, was_cut)."""
    if len(text) <= cap:
        return text, False
    ends = [m.end() for m in SENTENCE_END.finditer(text)
            if m.end() <= cap and not LIST_NUMBER.search(text[: m.end()])]
    if ends and ends[-1] >= cap // 4:
        return text[: ends[-1]].strip(), True
    head = text[:cap].rsplit(" ", 1)[0].rstrip(",;:")
    return head + ".", True


def sections_of(lines: list[str]) -> dict[str, list[str]]:
    """The scheme's lines split at its `### Details / Benefits / ...` headings (other headings stay in the text)."""
    out: dict[str, list[str]] = {}
    current = None
    for line in lines:
        m = HEADING.match(ZERO_WIDTH.sub("", line).strip())
        key = SECTIONS.get(m.group(1).strip().lower()) if m else None
        if key:
            current = key
            out.setdefault(key, [])
        elif current:
            out[current].append(line)
    return out


def faq_answers(lines: list[str]) -> str:
    return clean([re.sub(r"^\W*A\)\s*", "", ZERO_WIDTH.sub("", ln).replace("*", "").strip()) for ln in lines
                  if re.match(r"^\W*A\)", ZERO_WIDTH.sub("", ln).replace("*", "").strip())])


def make_chunks(name_en: str, lines: list[str]) -> tuple[dict[str, str], list[str], list[str]]:
    """The six English chunks from the scheme's own sections. Returns (chunks, cut notes, fallback notes).
    A section the text lacks falls back to the next best one (details, then the FAQ answers), at last to NOT_LISTED."""
    sec = sections_of(lines)
    text = {k: clean(v) for k, v in sec.items()}
    who = text.get("eligibility", "")
    if text.get("exclusions"):
        who = (who + " Exclusions: " + text["exclusions"]).strip()
    faq = faq_answers(sec.get("faq", []))
    want = {
        "summary": [("details", text.get("details", ""))],
        "benefit_text": [("benefits", text.get("benefits", "")), ("details", text.get("details", ""))],
        "who_can_apply": [("eligibility", who), ("faq", faq)],
        "documents": [("documents", text.get("documents", "")), ("faq", faq)],
        "how_to_apply": [("how", text.get("how", "")), ("faq", faq)],
    }
    chunks = {"name": name_en}
    cuts, fallbacks = [], []
    for chunk in SCHEME_CHUNKS:
        if chunk == "name":
            continue
        for i, (source, body) in enumerate(want[chunk]):
            if body:
                if i:
                    fallbacks.append(f"{chunk} from {source}")
                chunks[chunk], was_cut = cut(body)
                if was_cut:
                    cuts.append(f"{chunk} ({len(body)} -> {len(chunks[chunk])})")
                break
        else:
            chunks[chunk] = NOT_LISTED
            fallbacks.append(f"{chunk} not in the text")
    return {c: chunks[c] for c in SCHEME_CHUNKS}, cuts, fallbacks


# --- the check ----------------------------------------------------------------------------------------------------

def _pick(val: Any, allowed: tuple[str, ...], what: str, problems: list[str]) -> None:
    """ANY, one allowed code, or a non-empty list of allowed codes."""
    if val == "ANY":
        return
    items = val if isinstance(val, list) else [val]
    if not items:
        problems.append(f"{what}: empty list")
    for v in items:
        if not isinstance(v, str) or v not in allowed:
            problems.append(f"{what}: {v!r} is not in the vocab")


def check_annot(annot: Any, slug: str, lines: list[str]) -> list[str]:
    """Every problem of one annotation (empty list = OK). Does not stop at the first."""
    if not isinstance(annot, dict):
        return ["the file is not a JSON object"]
    p: list[str] = []
    for k in sorted(set(annot) - ANNOT_KEYS):
        p.append(f"unknown key {k!r}")
    for k in sorted(REQUIRED_KEYS - set(annot)):
        p.append(f"missing key {k!r}")
    if annot.get("slug") != slug:
        p.append(f"slug {annot.get('slug')!r} is not {slug!r}")
    for k in ("name_en", "name_hi"):
        if k in annot and not (isinstance(annot[k], str) and annot[k].strip()):
            p.append(f"{k} is empty")
    for k in ("aliases_en", "aliases_hi"):
        if k in annot:
            a = annot[k]
            good = [x for x in a if isinstance(x, str) and x.strip()] if isinstance(a, list) else []
            if len(good) < 3:
                p.append(f"{k}: {len(good)} usable aliases, need at least 3")
    if "category" in annot and annot["category"] not in vocab.CATEGORY:
        p.append(f"category {annot['category']!r} is not in the vocab")
    if "gender" in annot:
        _pick(annot["gender"], vocab.GENDER, "gender", p)
    if "social_category" in annot:
        _pick(annot["social_category"], vocab.SOCIAL_CATEGORY, "social_category", p)
    if "occupation" in annot:
        _pick(annot["occupation"], vocab.OCCUPATION, "occupation", p)
    if "state" in annot and annot["state"] not in ("ANY", "OTHER"):
        p.append(f"state {annot['state']!r} must be ANY or OTHER")
    if "home_state" in annot:
        _pick(annot["home_state"], vocab.HOME_STATE, "home_state", p)
    if "gives" in annot:
        if isinstance(annot["gives"], list) and annot["gives"]:
            _pick(annot["gives"], vocab.GIVES, "gives", p)
        else:
            p.append("gives must be a non-empty list")
    sub = annot.get("sub_kind")
    if "sub_kind" in annot and sub != "ANY" and not (isinstance(sub, str) and SUB_KIND.match(sub)):
        p.append(f"sub_kind {sub!r} is not a short code (a-z, 0-9, _)")
    age = annot.get("age")
    if "age" in annot and age != "ANY":
        lo, hi = (age.get("min"), age.get("max")) if isinstance(age, dict) else (None, None)
        if not (isinstance(age, dict) and set(age) == {"min", "max"} and all(isinstance(x, int) and not isinstance(x, bool) for x in (lo, hi))):
            p.append("age must be ANY or {min: int, max: int}")
        elif lo > hi:
            p.append(f"age min {lo} is above max {hi}")
        elif lo < 0:
            p.append(f"age min {lo} is below 0")
    inc = annot.get("income_max_inr")
    if inc is not None and not (isinstance(inc, int) and not isinstance(inc, bool) and inc > 0):
        p.append(f"income_max_inr {inc!r} must be null or a positive integer")
    if "for_organisation" in annot and not isinstance(annot["for_organisation"], bool):
        p.append("for_organisation must be true or false")
    if "confidence" in annot and annot["confidence"] not in ("high", "medium", "low"):
        p.append(f"confidence {annot['confidence']!r} must be high, medium or low")
    if "gate_notes" in annot and not (isinstance(annot["gate_notes"], list)
                                     and all(isinstance(x, str) and x.strip() for x in annot["gate_notes"])):
        p.append("gate_notes must be a list of non-empty sentences")

    blob = norm("\n".join(lines))

    def found(quote: Any, what: str) -> None:
        if not isinstance(quote, str) or not norm(quote):
            p.append(f"{what}: the quote is empty")
        elif norm(quote) not in blob:
            p.append(f"{what}: quote not found in the scheme text: {quote[:80]!r}")

    facts = annot.get("facts")
    if "facts" in annot and not isinstance(facts, dict):
        p.append("facts must be a map")
        facts = {}
    for name, body in (facts or {}).items():
        if name not in vocab.FACTS:
            p.append(f"fact {name!r} is not in the vocab")
        if not isinstance(body, dict) or body.get("role") not in ROLES:
            p.append(f"fact {name}: role must be needs or bars")
        else:
            found(body.get("quote"), f"fact {name}")
    ev = annot.get("evidence")
    if "evidence" in annot and not isinstance(ev, dict):
        p.append("evidence must be a map")
        ev = {}
    ev = ev or {}
    have = {
        "age": annot.get("age", "ANY") != "ANY", "gender": annot.get("gender", "ANY") != "ANY",
        "social_category": annot.get("social_category", "ANY") != "ANY",
        "occupation": annot.get("occupation", "ANY") != "ANY", "home_state": annot.get("home_state", "ANY") != "ANY",
        "income_max_inr": inc is not None,
    }
    for k, quote in ev.items():
        if k not in have:
            p.append(f"evidence key {k!r} is not one of {', '.join(EVIDENCE_KEYS)}")
        elif not have[k]:
            p.append(f"evidence {k}: there is no value for it")
        else:
            found(quote, f"evidence {k}")
    for k, has in have.items():
        if has and k not in ev:
            p.append(f"evidence {k}: the value has no quote")
    return p


# --- the row ------------------------------------------------------------------------------------------------------

def inr(n: int) -> str:
    """Rupees in the Indian grouping: 300000 -> 3,00,000."""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + parts + [tail])


def _department(src: list[str], start: int) -> str:
    for ln in src[max(0, start - 6): start - 1]:
        m = re.match(r"^###\s*\**\s*(.+?)\s*\**\s*$", ZERO_WIDTH.sub("", ln).strip())
        if m:
            return m.group(1)
    return ""


def make_row(annot: dict, lines: list[str], department: str, live_keys: list[str], today: str) -> dict:
    slug = annot["slug"]
    age = annot["age"]
    if age != "ANY":
        age = {"min": age["min"], "max": None if age["max"] >= 120 else age["max"]}
    notes = list(annot["gate_notes"])
    if annot.get("income_max_inr"):
        notes.append(f"Yearly family income must be up to Rs {inr(annot['income_max_inr'])}.")
    if annot.get("for_organisation"):
        notes.append("This scheme is for organisations, not for a person.")
    ev = annot["evidence"]
    quotes = {"category": annot.get("category_why", ""), "gender": ev.get("gender", ""),
              "social_category": ev.get("social_category", ""), "age": ev.get("age", ""),
              "income_band": ev.get("income_max_inr", ""), "occupation": ev.get("occupation", "")}
    if ev.get("home_state"):
        quotes["home_state"] = ev["home_state"]
    chunks, _, _ = make_chunks(annot["name_en"], lines)
    row = {
        "scheme_id": slug, "myscheme_slug": slug, "source_url": f"intake:{slug}", "level": "CENTRAL", "priority": 3,
        "state": annot["state"], "department": department, "fetched_on": today,
        "source_sha256": hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(),
        "facets_source": "intake", "facets_verified_by": None, "facets_verified_on": None,
        "scheme_name_en": annot["name_en"], "scheme_name_hi": annot["name_hi"], "scheme_name_mr": annot["name_hi"],
        "aliases_en": annot["aliases_en"], "aliases_hi": annot["aliases_hi"], "aliases_mr": annot["aliases_hi"],
        "category": annot["category"], "gender": annot["gender"], "social_category": annot["social_category"],
        "age": age, "income_band": "ANY", "occupation": annot["occupation"],
        "evidence_quotes": quotes, "gate_notes": notes, "chunks": {"en": chunks},
        "home_state": annot["home_state"], "gives": annot["gives"], "sub_kind": annot["sub_kind"],
        "facts": {name: body["role"] for name, body in annot["facts"].items()}, "talk_only": True,
    }
    for lang in ("en", "hi", "mr"):
        row[f"{lang}_sections_origin"] = "source" if lang == "en" else "none"
        row[f"{lang}_summary_origin"] = "source" if lang == "en" else "none"
        row[f"{lang}_verified_by"] = None
        row[f"{lang}_verified_on"] = None
    for k in live_keys:         # a key a live row has and this one lacks gets a neutral value, never a missing key
        row.setdefault(k, None)
    return row


# --- the run ------------------------------------------------------------------------------------------------------

def live_dir(snaps_root: Path) -> Path:
    return snaps_root / (snaps_root / "CURRENT").read_text(encoding="utf-8").strip()


def read_rows(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def check_all(index: dict, src: list[str], annot_dir: Path, live_keys: list[str], today: str):
    """Returns (rows, report lines, cut notes, fallback notes, counts)."""
    rows, report, cuts, falls = [], [], [], []
    counts = {"OK": 0, "REFUSED": 0, "MISSING": 0}
    known = set()
    for entry in index["schemes"]:
        slug = entry["slug"]
        known.add(slug)
        lines = src[entry["start"] - 1: entry["end"]]
        path = annot_dir / f"{slug}.json"
        if not path.exists():
            counts["MISSING"] += 1
            report.append(f"{slug}  MISSING (no annot file)")
            continue
        try:
            annot = json.loads(path.read_text(encoding="utf-8"))
            problems = check_annot(annot, slug, lines)
        except (ValueError, OSError) as e:
            annot, problems = None, [f"the file is not valid JSON: {e}"]
        if problems:
            counts["REFUSED"] += 1
            report.append(f"{slug}  REFUSED")
            report += [f"    - {x}" for x in problems]
            continue
        counts["OK"] += 1
        warn = [f"{k} has no Devanagari" for k in ("name_hi",) if not DEVANAGARI.search(annot[k])]
        report.append(f"{slug}  OK" + (f"  (warning: {'; '.join(warn)})" if warn else ""))
        rows.append(make_row(annot, lines, _department(src, entry["start"]), live_keys, today))
        _, c, f = make_chunks(annot["name_en"], lines)
        cuts += [f"{slug}: {x}" for x in c]
        falls += [f"{slug}: {x}" for x in f]
    for path in sorted(annot_dir.glob("*.json")) if annot_dir.exists() else []:
        if path.stem not in known:
            report.append(f"{path.stem}  NOT IN THE INDEX (file ignored)")
    return rows, report, cuts, falls, counts


def build_isolated(rows: list[dict], live_snaps: Path, live_audio: Path, out_dir: Path) -> str:
    """The live rows + the new ones into out_dir/snaps/<id>/ (own CURRENT there). The audio pool is out_dir/audio:
    links to the live clips and a COPY of the live index.json, so p6 writes nowhere near the repo's audio/."""
    from haqdaar.data.pipeline.p6_snapshot import build_snapshot

    audio = out_dir / "audio"
    audio.mkdir(parents=True, exist_ok=True)
    for f in live_audio.glob("*.ulaw"):
        link = audio / f.name
        if not link.exists():
            link.symlink_to(f.resolve())
    shutil.copyfile(live_audio / "index.json", audio / "index.json")
    live_rows = [{k: v for k, v in r.items() if k not in ("bit", "chunk_keys")}
                 for r in read_rows(live_dir(live_snaps) / "schemes.jsonl")]
    snap_id = datetime.now(timezone.utc).strftime("intake_%Y%m%d_%H%M%S")
    return build_snapshot(live_rows + rows, snapshot_id=snap_id, snapshots_dir=out_dir / "snaps", audio_dir=audio,
                          enforce_readback_gate=True, only_with_audio=True, talk_only_rest=True)


def _use(snaps: Path, audio: Path) -> None:
    tunables.SNAPSHOTS_DIR, tunables.AUDIO_DIR = str(snaps), str(audio)


def verify(live_snaps: Path, live_audio: Path, new_snaps: Path, new_audio: Path, snap_id: str, expect: int) -> list[str]:
    """Load the isolated snapshot and compare it with the live one. Lines starting FAIL are failures."""
    from haqdaar.data.corpus import Corpus
    from haqdaar.engine.filter import Filter
    from haqdaar.engine.planner import Planner

    out: list[str] = []
    old = (tunables.SNAPSHOTS_DIR, tunables.AUDIO_DIR)

    def line(ok: bool, text: str) -> None:
        out.append(("ok    " if ok else "FAIL  ") + text)

    try:
        _use(live_snaps, live_audio)
        live = Corpus.load("CURRENT")
        live_ids = [live.scheme_id(i) for i in range(len(live._scheme_ids))]
        _use(new_snaps, new_audio)
        new = Corpus.load(snap_id)
        new_ids = [new.scheme_id(i) for i in range(len(new._scheme_ids))]
    except Exception as e:
        _use(*old)
        return [f"FAIL  Corpus.load: {type(e).__name__}: {e}"]
    line(True, "Corpus.load works on the isolated snapshot")
    line(len(new_ids) == expect, f"schemes: {len(new_ids)} (expected {expect})")
    talk = {new.scheme_id(i) for i in new._talk_only}
    line(talk == set(new_ids) - set(live_ids), f"talk-only: {len(talk)}; the live {len(live_ids)} are all keys-path")

    lv = json.loads((live_dir(live_snaps) / "vocab.json").read_text(encoding="utf-8"))["boxes"]
    nv = json.loads((new_snaps / snap_id / "vocab.json").read_text(encoding="utf-8"))["boxes"]
    same = all(nv[b]["values"] == lv[b]["values"] for b in SEVEN_BOXES)
    line(same, "the seven keys-path boxes have exactly the live values (age bands: " + ", ".join(nv["age"]["values"]) + ")")
    bad = [f"{b}: {v}" for b, m in nv.items() for v in m["values"]
           if b in ("category", "gender", "social_category", "occupation", "state") and v not in (vocab.KEYPAD_LISTS[b])]
    line(not bad, "closed boxes hold vocab values only" + (f": {bad}" if bad else ""))
    out.append("info  new boxes p6 wrote: " + (", ".join(sorted(set(nv) - set(SEVEN_BOXES))) or "none"))

    def age_code(c: Corpus, lo: int) -> str:
        return next((v for v in c.values("age") if str(v).startswith(f"{lo}-")), str(next(iter(c.values("age")))))

    def vectors(c: Corpus) -> list[dict]:
        base = {b: UNASKED for b in SEVEN_BOXES}
        return [base | {"category": "pension"},
                base | {"category": "farming", "gender": "male", "occupation": "farmer"},
                base | {"category": "women_children", "gender": "female", "age": age_code(c, 18)}]

    for n, (vl, vn) in enumerate(zip(vectors(live), vectors(new)), 1):
        sl = {live_ids[i] for i in Filter.survivors(vl, live)}
        sn = {new_ids[i] for i in Filter.survivors(vn, new)}
        line(sl == sn & set(live_ids),
             f"vector {n}: live schemes left {len(sl)} (isolated: {len(sn & set(live_ids))}, new talk-only left: {len(sn - set(live_ids))})")
        al, an = Planner.next_action(vl, live), Planner.next_action(vn, new)
        line(repr(al) == repr(an), f"vector {n}: first keys-path action live {al!r} / isolated {an!r}")
    _use(*old)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the team's schemes into an isolated talk-only snapshot.")
    ap.add_argument("--annot-dir", default="data_cache/intake/annot")
    ap.add_argument("--out-dir", default="data_cache/intake")
    ap.add_argument("--source", help="default: <out-dir>/source.md")
    ap.add_argument("--index", help="default: <out-dir>/index.json")
    ap.add_argument("--live-snaps", default=tunables.SNAPSHOTS_DIR)
    ap.add_argument("--live-audio", default=tunables.AUDIO_DIR)
    ap.add_argument("--no-build", action="store_true", help="check and write the rows and the report only")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    live_snaps, live_audio = Path(args.live_snaps), Path(args.live_audio)
    src = Path(args.source or out_dir / "source.md").read_text(encoding="utf-8").split("\n")
    index = json.loads(Path(args.index or out_dir / "index.json").read_text(encoding="utf-8"))
    live_keys = [k for k in read_rows(live_dir(live_snaps) / "schemes.jsonl")[0] if k not in ("bit", "chunk_keys")]
    rows, report, cuts, falls, counts = check_all(index, src, Path(args.annot_dir), live_keys, date.today().isoformat())

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "schemes_intake.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                  encoding="utf-8")
    head = [f"INTAKE REPORT {datetime.now().isoformat(timespec='seconds')}",
            f"schemes in the index: {len(index['schemes'])}   OK {counts['OK']}   REFUSED {counts['REFUSED']}   "
            f"MISSING {counts['MISSING']}", ""]
    tail = ["", f"Chunks cut at {CHUNK_CAP} characters (at a sentence end): {len(cuts)}"] + [f"  {c}" for c in cuts]
    tail += ["", f"Chunks that fell back to another section: {len(falls)}"] + [f"  {f}" for f in falls]

    fail = False
    snap = []
    if rows and not args.no_build:
        try:
            snap_id = build_isolated(rows, live_snaps, live_audio, out_dir)
            snaps_abs, audio_abs = (out_dir / "snaps").resolve(), (out_dir / "audio").resolve()
            snap += ["", f"ISOLATED SNAPSHOT {snap_id}  ({snaps_abs / snap_id})"]
            checks = verify(live_snaps, live_audio, out_dir / "snaps", out_dir / "audio", snap_id,
                            len(read_rows(live_dir(live_snaps) / "schemes.jsonl")) + len(rows))
            snap += [f"  {c}" for c in checks]
            fail = any(c.startswith("FAIL") for c in checks)
            snap += ["", "Use it (nothing in snapshots/ or audio/ of the repo is touched):",
                     f"  SNAPSHOTS_DIR={snaps_abs} AUDIO_DIR={audio_abs} make mac-call",
                     f"  SNAPSHOTS_DIR={snaps_abs} AUDIO_DIR={audio_abs} make full",
                     "  (the repo's snapshots/CURRENT was not changed; unset the two to go back)"]
        except Exception as e:
            fail = True
            snap += ["", f"BUILD FAILED: {type(e).__name__}: {e}"]
    elif not rows:
        snap += ["", "No OK scheme: no snapshot built."]
    text = "\n".join(head + report + tail + snap) + "\n"
    (out_dir / "report.txt").write_text(text, encoding="utf-8")
    print(text)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
