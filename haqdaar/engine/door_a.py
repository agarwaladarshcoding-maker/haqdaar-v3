"""haqdaar/engine/door_a.py

Door A matching engine for HAQDAAR v2.
Matches spoken scheme names at the opener, enabling direct navigation:
- 1 match -> read it immediately (Door A happy path)
- 2 matches -> pick by keypad (door_a_option_1 + door_a_option_2 + door_a_option_none)
- >=3 matches (or miss) -> downgrade to Door B (courtesy transition line door_a_downgrade_to_b)
- Top-10 shortlist for downstream LLM routing.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Sequence
import unicodedata

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Lang, SchemeEntry

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
    # Joined + short PM forms (df 10-15 across schemes: pure honorific noise).
    # Without these, "pradhanmantri"-style tokens inflate overlap and a generic
    # need can read the wrong scheme (pmsby-hi misread pmfby).
    "pm", "पीएम", "प्रधानमंत्री", "पंतप्रधान",
    "pradhanmantri", "pradhanamntri", "pantpradhan", "pntapradhan",
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

# Names callers say in English that the snapshot's alias lists lack (spelling variants,
# short forms). Kept in code so the snapshot is not rebuilt for them; the matcher reads
# it for every scheme with that slug. An alias the snapshot has already is not repeated.
_EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    "pmmy": ("mudra", "mudra loan", "mudra yojana", "pm mudra yojana", "pradhan mantri mudra yojana"),
    "pmay-g": (
        "pradhan mantri awas yojana", "pradhan mantri awaas yojana", "pm awas yojana", "pm awaas yojana",
        "pradhan mantri awas yojana gramin", "pradhan mantri awaas yojana gramin",
    ),
    "smam": (
        "agriculture mechanization", "agricultural mechanization", "agricultural mechanisation",
        "sub mission on agriculture mechanization",
    ),
    "apy": ("atal pension yojana", "atal pension"),
    "pmfby": ("pradhan mantri fasal bima yojana", "pm fasal bima yojana", "pm fasal bima", "fasal bima yojana"),
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
            # AUDIT #5: Engine reads no disk. Callers pass entries explicitly
            # (haqdaar.data.door_a_sources.load_repo_scheme_entries) or a corpus.
            raise ValueError("DoorA needs scheme_entries or corpus")

    def _load_from_corpus(self, corpus: Any) -> None:
        """Extract schemes and aliases from loaded Corpus."""
        scheme_ids = getattr(corpus, "_scheme_ids", ())
        for ix, sid in enumerate(scheme_ids):
            spec = corpus.specificity(ix) if hasattr(corpus, "specificity") else 2
            entry = SchemeEntry(slug=sid, priority=spec)
            # Slug spellings callers actually say (mirrors the roster loader).
            for variant in {sid, sid.replace("-", " "), sid.replace("-", "")}:
                norm = normalize_text(variant)
                if norm and norm not in entry.aliases:
                    entry.aliases.append(norm)
            for extra in _EXTRA_ALIASES.get(sid, ()):
                if extra not in entry.aliases:
                    entry.aliases.append(extra)
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

    def has_scheme(self, slug: str) -> bool:
        """True if slug is a registered (servable) scheme."""
        return slug in self._schemes

    def _score_scheme(self, query: str, scheme: SchemeEntry) -> tuple[float, str | None]:
        q_norm = normalize_text(query)
        q_lat = normalize_text(devanagari_to_latin(query))

        q_tokens = set(w for w in q_norm.split() if w not in GENERIC_STOP_WORDS and len(w) > 1)
        q_lat_tokens = set(w for w in q_lat.split() if w not in GENERIC_STOP_WORDS and len(w) > 1)
        all_q_tokens = q_tokens | q_lat_tokens

        best_alias_len = 0
        overlap = all_q_tokens & scheme.distinctive_tokens
        # Script-folded count: Devanagari + its Latin twin are one word.
        overlap_n = len({normalize_text(devanagari_to_latin(t)) for t in overlap})

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
            return tunables.DOOR_A_EXACT_SCORE, matched_alias, overlap_n
        if best_alias_len > 0:
            score = tunables.DOOR_A_ALIAS_SCORE_BASE + best_alias_len * 5.0 + (4 - scheme.priority)
            return score, matched_alias, overlap_n

        if overlap:
            extra_query_tokens = all_q_tokens - scheme.distinctive_tokens
            token_score = len(overlap) * 40.0
            precision = len(overlap) / max(1, len(all_q_tokens))
            recall = len(overlap) / max(1, len(scheme.distinctive_tokens))
            token_score += precision * 30.0 + recall * 20.0
            token_score -= len(extra_query_tokens) * 10.0
            score = token_score + (4 - scheme.priority) * 0.5
            return score, None, overlap_n

        return 0.0, None, 0

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
            norm_q = normalize_text(transcript)
            alias_hits = self.corpus.alias_lookup(norm_q, lang)
            if alias_hits:
                shortlist = tuple(alias_hits[:10])
                if len(alias_hits) == 1:
                    return DoorAResult(
                        action="read",
                        scheme_ids=tuple(alias_hits),
                        confidence=1.0,
                        matched_alias=norm_q,
                        shortlist=shortlist,
                    )
                elif len(alias_hits) == 2:
                    return DoorAResult(
                        action="keypad_pick",
                        scheme_ids=tuple(alias_hits[:2]),
                        confidence=1.0,
                        matched_alias=norm_q,
                        shortlist=shortlist,
                    )
                else:
                    return DoorAResult(
                        action="downgrade_to_b",
                        scheme_ids=tuple(alias_hits),
                        confidence=1.0,
                        matched_alias=norm_q,
                        shortlist=shortlist,
                    )

        # 2. Token match on registered schemes
        scored: list[tuple[str, float, str | None, int]] = []
        for slug, scheme in self._schemes.items():
            s, matched_al, ov_n = self._score_scheme(transcript, scheme)
            if s > 0:
                scored.append((slug, s, matched_al, ov_n))

        scored.sort(key=lambda x: x[1], reverse=True)
        shortlist = tuple(x[0] for x in scored[:10])

        if not scored:
            return DoorAResult(
                action="downgrade_to_b",
                scheme_ids=(),
                confidence=0.0,
                shortlist=(),
            )

        top_slug, top_score, top_alias, _ = scored[0]
        if top_score < tunables.DOOR_A_SCORE_FLOOR:
            return DoorAResult(
                action="downgrade_to_b",
                scheme_ids=(),
                confidence=0.0,
                shortlist=shortlist,
            )

        # T12: the code pass counts alias evidence (exact or substring match).
        # Token overlap alone is fuzzy matching, which is the model's job
        # (search #2 in the opener). Reading or picking without an alias
        # misfires on plain need-statements ("I need farming schemes" read
        # smam at 0.09). 1 grounded -> read, 2 -> pick, 3+ -> loud
        # downgrade, 0 -> silent Door B.
        close = [(x[0], x[2], x[3]) for x in scored
                 if x[1] >= tunables.DOOR_A_TIE_BAND * top_score]
        # A candidate counts with alias evidence, or with token overlap on
        # 2+ folded words. A single shared word ("agriculture", "krishi") is
        # a need-statement, not a naming; the model arbitrates those (T12 #2).
        grounded = [(slug, al) for slug, al, ov_n in close
                    if al or ov_n >= tunables.DOOR_A_MIN_TOKEN_OVERLAP]
        confidence = min(1.0, top_score / tunables.DOOR_A_ALIAS_SCORE_BASE)

        if len(grounded) == 1:
            return DoorAResult(
                action="read",
                scheme_ids=(grounded[0][0],),
                confidence=confidence,
                matched_alias=grounded[0][1],
                shortlist=shortlist,
            )
        elif len(grounded) == 2:
            return DoorAResult(
                action="keypad_pick",
                scheme_ids=(grounded[0][0], grounded[1][0]),
                confidence=confidence,
                matched_alias=grounded[0][1],
                shortlist=shortlist,
            )
        elif len(grounded) >= 3:
            return DoorAResult(
                action="downgrade_to_b",
                scheme_ids=tuple(s for s, _ in grounded),
                confidence=confidence,
                matched_alias=top_alias,
                shortlist=shortlist,
            )
        else:
            return DoorAResult(
                action="downgrade_to_b",
                scheme_ids=(),
                confidence=0.0,
                matched_alias=top_alias,
                shortlist=shortlist,
            )

    def shortlist(self, transcript: str, lang: str = "en", k: int = 10) -> tuple[str, ...]:
        """Return top-k candidate scheme IDs for downstream LLM routing."""
        scored: list[tuple[str, float]] = []
        for slug, scheme in self._schemes.items():
            s, _, _ = self._score_scheme(transcript, scheme)
            if s > 0:
                scored.append((slug, s))
        scored.sort(key=lambda x: x[1], reverse=True)
        return tuple(x[0] for x in scored[:k])


def unmatched_content(transcript: str, matched_alias: str | None) -> bool:
    """True if the transcript has content words beyond the matched alias.

    Used by the opener to tell a clean scheme naming ("PM Kisan", no model
    call needed) from a mixed utterance ("I'm a farmer, tell me about PM
    Kisan", whose box facts still need the model).
    """
    seen = set(normalize_text(matched_alias or "").split())
    seen |= set(normalize_text(devanagari_to_latin(matched_alias or "")).split())
    return any(
        t for t in normalize_text(transcript).split()
        if t not in seen and t not in GENERIC_STOP_WORDS
    )
