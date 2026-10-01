"""haqdaar/engine/door_a.py

Door A matching engine for HAQDAAR v2.
Matches spoken scheme names at the opener, enabling direct navigation:
- 1 match -> read it immediately (Door A happy path)
- 2 matches -> pick by keypad (door_a_option_1 + door_a_option_2 + door_a_option_none)
- >=3 matches (or miss) -> downgrade to Door B (courtesy transition line door_a_downgrade_to_b)
- Top-10 shortlist for downstream LLM routing.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Mapping, Optional, Sequence
import unicodedata

import yaml

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Lang

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Devanagari to Latin phonetic mapping table
_DEVA_MAPPING: dict[str, str] = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ॠ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "अं": "an", "अः": "ah",
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "ॄ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ं": "n", "ँ": "n", "ः": "h",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "ड़": "r", "ढ़": "rh", "फ़": "f", "ज़": "z", "क़": "q", "ख़": "kh", "ग़": "gh",
    "ळ": "l", "ज्ञ": "gya", "क्ष": "ksh", "त्र": "tr", "श्र": "shr",
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4", "५": "5", "६": "6", "७": "7", "८": "8", "९": "9"
}

_ABBREVIATIONS: dict[str, str] = {
    "पीएम": "pm", "पी.एम.": "pm", "सीएम": "cm", "केसीसी": "kcc", "एपीवाई": "apy",
    "मनरेगा": "mgnrega", "नॅप्स": "naps", "एनएपीएस": "naps", "जेएसवाई": "jsy",
    "जेएसवाय": "jsy", "पीएमईजीपी": "pmegp", "आरकेवीवाई": "rkvy", "आरकेव्हीवाय": "rkvy",
    "एसएमएएम": "smam", "विमा": "bima", "पेन्शन": "pension", "पेंशन": "pension",
    "क्रेडिट": "credit", "कार्ड": "card", "लोन": "loan", "कर्ज": "karj",
    "आयुष्मान": "ayushman", "आयुष्यमान": "ayushman", "उज्ज्वला": "ujjwala",
    "विश्वकर्मा": "vishwakarma", "आवास": "awas", "फसल": "fasal", "पीक": "peek"
}

_CONSONANTS: set[str] = set("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहड़ढ़फ़ज़क़ख़ग़ळज्ञक्षत्रश्र")
_MATRAS: set[str] = set("ािीुूृॄेैोौ्")

GENERIC_STOP_WORDS: set[str] = {
    # Generic scheme words
    "yojana", "yojna", "योजना", "योजनेची", "योजनेबद्दल", "योजनाएं", "scheme", "स्कीम", "schemes",
    "sarkari", "सरकारी", "government", "govt",
    "national", "rashtriya", "राष्ट्रीय",
    "bharat", "bharatiya", "भारत", "भारतीय",
    "central", "kendriya", "केंद्रीय",
    "state", "rajya", "राज्य",
    "pradhan", "mantri", "प्रधान", "मंत्री",
    "loan", "लोन", "कर्ज", "karj",
    "subsidy", "सब्सिडी", "अनुदान",
    "card", "कार्ड",
    # Conversational filler
    "i", "me", "my", "we", "want", "to", "apply", "for", "please", "tell", "about",
    "the", "a", "an", "give", "information", "details", "help", "with", "is", "there",
    "any", "which", "call", "desk", "helpline", "regarding", "know", "how", "what", "can",
    "get", "need", "looking",
    "मुझे", "के", "बारे", "में", "जानकारी", "चाहिए", "बताइए", "कृपया", "की", "का", "को",
    "से", "है", "आवेदन", "करना", "चाहता", "हूँ", "चाहती", "हेल्पलाइन", "मदद", "कॉल", "जानना",
    "पर", "और", "दीजिए", "बताएं", "दें", "बताओ",
    "मला", "बद्दल", "माहिती", "हवी", "आहे", "द्या", "सांगा", "कृपया", "ची", "चा", "चे",
    "करा", "अर्ज", "करायचा", "मदत", "कॉल", "सांग", "आम्हाला", "हवे", "होते",
    # Romanized conversational words
    "mujhe", "ke", "bare", "mein", "men", "jankari", "chahiye", "bataiye", "bataie",
    "kripya", "kripaya", "ki", "ka", "ko", "se", "hai", "avedan", "karna", "chahta",
    "chahati", "hun", "hoon", "aur", "dijiye", "batao", "bataen", "den", "janna", "par",
    "mala", "baddal", "mahiti", "havi", "aahe", "dya", "sanga", "kripya", "chi", "cha",
    "che", "kara", "arj", "karaycha", "aamhala", "have", "hote"
}

# Standard manual aliases for schemes without extracted alias cards (e.g. quarantined)
MANUAL_ALIASES: dict[str, dict[str, list[str]]] = {
    "pmsby": {
        "en": ["pradhan mantri suraksha bima yojana", "pmsby", "suraksha bima yojana", "pm suraksha bima", "suraksha bima"],
        "hi": ["प्रधानमंत्री सुरक्षा बीमा योजना", "सुरक्षा बीमा योजना", "पीएमएसबीवाई", "सुरक्षा बीमा"],
        "mr": ["प्रधानमंत्री सुरक्षा विमा योजना", "सुरक्षा विमा योजना", "पीएमएसबीवाय", "सुरक्षा विमा"]
    },
    "pm-sym": {
        "en": ["pradhan mantri shram yogi maan-dhan", "pm-sym", "shram yogi maandhan", "shram yogi pension", "pm shram yogi"],
        "hi": ["प्रधानमंत्री श्रम योगी मानधन योजना", "श्रम योगी मानधन योजना", "पीएम श्रम योगी मानधन", "श्रम योगी पेंशन"],
        "mr": ["प्रधानमंत्री श्रम योगी मानधन योजना", "श्रम योगी मानधन योजना", "पीएम श्रम योगी मानधन", "श्रम योगी पेन्शन"]
    }
}


def devanagari_to_latin(text: str) -> str:
    """Phonetically transliterate Devanagari text to Latin characters."""
    if not text:
        return ""
    res = text
    for k, v in _ABBREVIATIONS.items():
        res = res.replace(k, v)

    out: list[str] = []
    i = 0
    n = len(res)
    while i < n:
        c = res[i]
        if c in _DEVA_MAPPING:
            out.append(_DEVA_MAPPING[c])
            if c in _CONSONANTS:
                next_c = res[i + 1] if i + 1 < n else ""
                if (
                    next_c
                    and next_c not in _MATRAS
                    and next_c not in (" ", "\t", "\n", "-", "_")
                    and next_c in _CONSONANTS
                ):
                    out.append("a")
        elif c == "्":
            pass
        else:
            out.append(c)
        i += 1
    return "".join(out)


def normalize_text(text: str) -> str:
    """Normalize text: lowercase, remove punctuation including Devanagari dandas, collapse whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text.lower())
    # Explicitly remove Devanagari danda punctuation \u0964, \u0965
    text = text.replace("\u0964", " ").replace("\u0965", " ")
    cleaned = re.sub(r"[^\w\s\u0900-\u0963\u0966-\u097F]", " ", text)
    return re.sub(r"\s+", " ", cleaned).strip()


@dataclass(frozen=True)
class DoorAResult:
    """Result of Door A matching."""
    action: str  # "read" | "keypad_pick" | "downgrade_to_b"
    scheme_ids: tuple[str, ...]
    confidence: float
    matched_alias: str | None = None
    shortlist: tuple[str, ...] = ()


@dataclass
class SchemeEntry:
    """Scheme entry indexed for Door A matching."""
    slug: str
    priority: int = 2
    names: dict[str, str] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    distinctive_tokens: set[str] = field(default_factory=set)


class DoorA:
    """Door A scheme matching engine.
    
    1. Exact alias lookup in code (corpus or indexed aliases).
    2. Cross-script phonetic token matching (Devanagari -> Latin + stop list).
    3. Candidate branching: 1 -> read, 2 -> keypad_pick, >=3 -> downgrade_to_b.
    4. Top-10 shortlist for downstream LLM.
    """

    def __init__(
        self,
        scheme_entries: Sequence[SchemeEntry] | None = None,
        corpus: Any | None = None,
    ) -> None:
        self.corpus = corpus
        self._schemes: dict[str, SchemeEntry] = {}
        if scheme_entries:
            for s in scheme_entries:
                self._schemes[s.slug] = s
        elif corpus is not None:
            self._load_from_corpus(corpus)
        else:
            self._load_from_defaults()

    def _load_from_corpus(self, corpus: Any) -> None:
        """Extract schemes and aliases from loaded Corpus."""
        scheme_ids = getattr(corpus, "_scheme_ids", ())
        for ix, sid in enumerate(scheme_ids):
            spec = corpus.specificity(ix) if hasattr(corpus, "specificity") else 2
            entry = SchemeEntry(slug=sid, priority=spec)
            self._schemes[sid] = entry

        # Load aliases from alias sets across languages
        for lang in ("en", "hi", "mr"):
            alias_map = corpus.alias_set(lang) if hasattr(corpus, "alias_set") else {}
            for alias_text, sids in alias_map.items():
                norm = normalize_text(alias_text)
                lat = normalize_text(devanagari_to_latin(alias_text))
                for sid in sids:
                    if sid in self._schemes:
                        if norm not in self._schemes[sid].aliases:
                            self._schemes[sid].aliases.append(norm)
                        if lat and lat not in self._schemes[sid].aliases:
                            self._schemes[sid].aliases.append(lat)

        self._index_tokens()

    def _load_from_defaults(self) -> None:
        """Load 30-scheme roster from schemes.yaml + derived jsonl + candidates.csv."""
        schemes_yaml_path = BASE_DIR / "haqdaar/data/pipeline/schemes.yaml"
        if not schemes_yaml_path.exists():
            return

        schemes_yaml = yaml.safe_load(schemes_yaml_path.read_text(encoding="utf-8")).get("schemes", [])
        
        derived_map: dict[str, Any] = {}
        derived_path = BASE_DIR / "data_cache/derived/schemes.jsonl"
        if derived_path.exists():
            for line in derived_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    derived_map[item["scheme_id"]] = item

        candidates_map: dict[str, Any] = {}
        cand_path = BASE_DIR / "data_cache/derived/candidates.csv"
        if cand_path.exists():
            with open(cand_path, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    candidates_map[r["slug"]] = r

        for sc in schemes_yaml:
            slug = sc["slug"]
            priority = sc.get("priority", 2)
            d = derived_map.get(slug, {})
            c = candidates_map.get(slug, {})

            aliases: set[str] = set()
            aliases.add(slug)
            aliases.add(slug.replace("-", " "))
            aliases.add(slug.replace("-", ""))

            if c.get("short_title"):
                st = c["short_title"].lower()
                aliases.add(st)
                aliases.add(st.replace("-", " "))
                aliases.add(st.replace("-", ""))
            if c.get("name"):
                aliases.add(c["name"].lower())

            names = {}
            for f in ["scheme_name_en", "scheme_name_hi", "scheme_name_mr"]:
                if d.get(f):
                    names[f.replace("scheme_name_", "")] = d[f]
                    aliases.add(d[f].lower())

            for f in ["aliases_en", "aliases_hi", "aliases_mr"]:
                for a in d.get(f, []):
                    aliases.add(a.lower())

            if slug in MANUAL_ALIASES:
                for lang_aliases in MANUAL_ALIASES[slug].values():
                    for a in lang_aliases:
                        aliases.add(a.lower())

            # Expand common prefixes: "pradhan mantri" <-> "pm" and "प्रधानमंत्री" / "पंतप्रधान" <-> "पीएम"
            expanded: set[str] = set(aliases)
            for a in aliases:
                if a.startswith("pradhan mantri "):
                    expanded.add("pm " + a[15:])
                elif a.startswith("pm "):
                    expanded.add("pradhan mantri " + a[3:])
                if a.startswith("प्रधानमंत्री "):
                    expanded.add("पीएम " + a[12:])
                elif a.startswith("पंतप्रधान "):
                    expanded.add("पीएम " + a[10:])
                elif a.startswith("पीएम "):
                    expanded.add("प्रधानमंत्री " + a[5:])
                    expanded.add("पंतप्रधान " + a[5:])

            alias_entries: list[str] = []
            distinctive_tokens: set[str] = set()
            for a in expanded:
                norm = normalize_text(a)
                if norm:
                    alias_entries.append(norm)
                    words = [w for w in norm.split() if w not in GENERIC_STOP_WORDS and len(w) > 1]
                    distinctive_tokens.update(words)

                    lat = normalize_text(devanagari_to_latin(a))
                    if lat and lat != norm:
                        alias_entries.append(lat)
                        lat_words = [w for w in lat.split() if w not in GENERIC_STOP_WORDS and len(w) > 1]
                        distinctive_tokens.update(lat_words)

            self._schemes[slug] = SchemeEntry(
                slug=slug,
                priority=priority,
                names=names,
                aliases=alias_entries,
                distinctive_tokens=distinctive_tokens,
            )

    def _index_tokens(self) -> None:
        """Populate distinctive tokens for all registered schemes."""
        for entry in self._schemes.values():
            tokens: set[str] = set()
            for alias in entry.aliases:
                words = [w for w in alias.split() if w not in GENERIC_STOP_WORDS and len(w) > 1]
                tokens.update(words)
            entry.distinctive_tokens = tokens

    @classmethod
    def from_corpus(cls, corpus: Any) -> DoorA:
        """Create DoorA matcher from a loaded Corpus."""
        return cls(corpus=corpus)

    @classmethod
    def from_sources(cls) -> DoorA:
        """Create DoorA matcher from pipeline sources (schemes.yaml + derived data)."""
        return cls()

    def _score_scheme(self, query: str, scheme: SchemeEntry) -> tuple[float, str | None]:
        q_norm = normalize_text(query)
        q_lat = normalize_text(devanagari_to_latin(query))

        q_tokens = set(w for w in q_norm.split() if w not in GENERIC_STOP_WORDS and len(w) > 1)
        q_lat_tokens = set(w for w in q_lat.split() if w not in GENERIC_STOP_WORDS and len(w) > 1)
        all_q_tokens = q_tokens | q_lat_tokens

        best_alias_len = 0
        matched_alias: str | None = None
        exact_full = False

        for alias in scheme.aliases:
            if alias == q_norm or alias == q_lat:
                exact_full = True
                matched_alias = alias
                break
            if len(alias) >= 4:
                if f" {alias} " in f" {q_norm} " or f" {alias} " in f" {q_lat} ":
                    if len(alias) > best_alias_len:
                        best_alias_len = len(alias)
                        matched_alias = alias
                elif alias in q_norm or alias in q_lat:
                    if len(alias) > best_alias_len:
                        best_alias_len = len(alias)
                        matched_alias = alias

        if exact_full:
            return 1000.0, matched_alias
        if best_alias_len > 0:
            score = 500.0 + best_alias_len * 5.0 + (4 - scheme.priority)
            return score, matched_alias

        overlap = all_q_tokens & scheme.distinctive_tokens
        if overlap:
            extra_query_tokens = all_q_tokens - scheme.distinctive_tokens
            token_score = len(overlap) * 40.0
            precision = len(overlap) / max(1, len(all_q_tokens))
            recall = len(overlap) / max(1, len(scheme.distinctive_tokens))
            token_score += precision * 30.0 + recall * 20.0
            token_score -= len(extra_query_tokens) * 10.0
            score = token_score + (4 - scheme.priority) * 0.5
            return score, None

        return 0.0, None

    def match(self, transcript: str, lang: str = "en") -> DoorAResult:
        """Match transcript against schemes.
        
        Returns DoorAResult:
        - action: "read" (1 match), "keypad_pick" (2 matches), "downgrade_to_b" (>=3 or 0 matches)
        - scheme_ids: tuple of matched IDs
        - confidence: match score normalized (0.0 to 1.0)
        - shortlist: top-10 candidate scheme IDs for LLM
        """
        if not transcript or not transcript.strip():
            return DoorAResult(
                action="downgrade_to_b",
                scheme_ids=(),
                confidence=0.0,
                shortlist=(),
            )

        # 1. Corpus exact fast-path if corpus available
        if self.corpus is not None and hasattr(self.corpus, "alias_lookup"):
            alias_hits = self.corpus.alias_lookup(transcript, lang)
            if alias_hits:
                shortlist = tuple(alias_hits[:10])
                if len(alias_hits) == 1:
                    return DoorAResult(
                        action="read",
                        scheme_ids=tuple(alias_hits),
                        confidence=1.0,
                        matched_alias=transcript.strip(),
                        shortlist=shortlist,
                    )
                elif len(alias_hits) == 2:
                    return DoorAResult(
                        action="keypad_pick",
                        scheme_ids=tuple(alias_hits[:2]),
                        confidence=1.0,
                        matched_alias=transcript.strip(),
                        shortlist=shortlist,
                    )
                else:
                    return DoorAResult(
                        action="downgrade_to_b",
                        scheme_ids=tuple(alias_hits),
                        confidence=1.0,
                        matched_alias=transcript.strip(),
                        shortlist=shortlist,
                    )

        # 2. Token match on registered schemes
        scored: list[tuple[str, float, str | None]] = []
        for slug, scheme in self._schemes.items():
            s, matched_al = self._score_scheme(transcript, scheme)
            if s > 0:
                scored.append((slug, s, matched_al))

        scored.sort(key=lambda x: x[1], reverse=True)
        shortlist = tuple(x[0] for x in scored[:10])

        if not scored:
            return DoorAResult(
                action="downgrade_to_b",
                scheme_ids=(),
                confidence=0.0,
                shortlist=(),
            )

        top_slug, top_score, top_alias = scored[0]
        if top_score < 30.0:
            return DoorAResult(
                action="downgrade_to_b",
                scheme_ids=(),
                confidence=0.0,
                shortlist=shortlist,
            )

        # Candidates within 10% of top score are considered ambiguous/tied
        close_candidates = [x[0] for x in scored if x[1] >= 0.90 * top_score]
        confidence = min(1.0, top_score / 500.0)

        if len(close_candidates) == 1:
            return DoorAResult(
                action="read",
                scheme_ids=(close_candidates[0],),
                confidence=confidence,
                matched_alias=top_alias,
                shortlist=shortlist,
            )
        elif len(close_candidates) == 2:
            return DoorAResult(
                action="keypad_pick",
                scheme_ids=tuple(close_candidates[:2]),
                confidence=confidence,
                matched_alias=top_alias,
                shortlist=shortlist,
            )
        else:
            return DoorAResult(
                action="downgrade_to_b",
                scheme_ids=tuple(close_candidates),
                confidence=confidence,
                matched_alias=top_alias,
                shortlist=shortlist,
            )

    def shortlist(self, transcript: str, lang: str = "en", k: int = 10) -> tuple[str, ...]:
        """Return top-k candidate scheme IDs for downstream LLM routing."""
        scored: list[tuple[str, float]] = []
        for slug, scheme in self._schemes.items():
            s, _ = self._score_scheme(transcript, scheme)
            if s > 0:
                scored.append((slug, s))
        scored.sort(key=lambda x: x[1], reverse=True)
        return tuple(x[0] for x in scored[:k])
