"""haqdaar/data/chunk_index.py

Chunk-level search for HAQDAAR v2 (Step 1.5a).
Divides each scheme into 5 distinct parts (chunks):
  - summary: overview and description of the scheme
  - benefits: financial and material assistance details
  - papers needed: required documents, certificates, and proofs
  - how to apply: application process, portal, and procedure
  - details: eligibility criteria, who is eligible, and rules

Search and ranking:
  - Supports single query or multiple queries (best score across queries).
  - Fixed-code ranking combining:
      1. Vector score (fastembed multilingual ONNX on CPU)
      2. Pre-built name match (SchemeIndex / DoorA matchers kept on self)
      3. Caller-provided "fits" marks ("fits" = +0.15, "does not fit" = -0.5, "not known yet" = 0.0)
      4. Fixed-code part keyword bonus for targeted queries (whole words only)
  - Caches embeddings and text hashes in data_cache/chunk_index/.
  - Caps at most 2 chunks per scheme unless the scheme is named (0.85+).
  - Ignores chunks with empty English text.
  - Scales to 100+ schemes with sub-20ms search latency.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Optional, Sequence
import unicodedata

from haqdaar.contracts import tunables

logger = logging.getLogger(__name__)

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CACHE_DIR = Path("data_cache") / "chunk_index"
TEXT_LANGS = ("en", "hi")

Embed = Callable[[Sequence[str]], Any]

PARTS = ("summary", "benefits", "papers needed", "how to apply", "details")
PART_INDEX: dict[str, int] = {p: i for i, p in enumerate(PARTS)}

FIELD_TO_PART: dict[str, str] = {
    "summary": "summary",
    "benefit_text": "benefits",
    "documents": "papers needed",
    "how_to_apply": "how to apply",
    "who_can_apply": "details",
}

PART_TO_FIELD: dict[str, str] = {v: k for k, v in FIELD_TO_PART.items()}

PART_SPECS: list[tuple[str, str, str, str]] = [
    ("summary", "summary", "Summary overview", "सारांश विवरण"),
    ("benefits", "benefit_text", "Benefits and financial assistance", "लाभ और सहायता"),
    ("papers needed", "documents", "Required documents and papers needed", "जरूरी दस्तावेज और कागजात"),
    ("how to apply", "how_to_apply", "How to apply and application process", "आवेदन कैसे करें और आवेदन प्रक्रिया"),
    ("details", "who_can_apply", "Eligibility criteria and who is eligible", "पात्रता नियम और कौन पात्र है"),
]

PART_KEYWORDS: dict[str, set[str]] = {
    "papers needed": {
        "paper", "papers", "document", "documents", "proof", "proofs",
        "bring", "what to bring", "what should i bring", "ask for", "records", "certificates",
        "कागज", "कागजात", "दस्तावेज", "प्रमाण", "लाना", "क्या लाना होगा", "क्या लाना है",
        "कागदपत्रे", "कागदपत्र", "दाखला", "पुरावा", "काय आणावे लागेल",
    },
    "how to apply": {
        "apply", "applying", "application", "process", "procedure", "portal", "register",
        "registration", "sign up", "where do i go", "which office", "where to go", "how do i join",
        "where to sign up", "where to register", "how can i apply",
        "आवेदन", "फॉर्म", "पंजीकरण", "प्रक्रिया", "कहाँ जाना है", "कहाँ जाऊं", "कार्यालय", "दफ्तर",
        "अर्ज", "नोंदणी", "कुठे जायचे", "कुठे अर्ज करावा",
    },
    "benefits": {
        "benefit", "benefits", "amount", "money", "rupees", "rs", "installment",
        "सहायता", "लाभ", "रुपये", "पैसे", "रुपया", "किस्त",
    },
    "details": {
        "eligible", "eligibility", "criteria", "qualification", "who can", "who is eligible",
        "qualify", "conditions", "age limit",
        "पात्र", "पात्रता", "योग्यता", "शर्तें", "नियम", "कोण पात्र आहे", "अटी",
    },
}


def split_words(text: str) -> list[str]:
    """Split text into lower-cased words on whitespace and punctuation across scripts.
    Preserves Indic combining marks / vowel signs.
    """
    out: list[str] = []
    curr: list[str] = []
    for ch in str(text):
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("Z") or cat.startswith("S") or ch in " \t\n\r":
            if curr:
                out.append("".join(curr).lower())
                curr = []
        else:
            curr.append(ch)
    if curr:
        out.append("".join(curr).lower())
    return out


def _norm(text: str) -> str:
    return " ".join(split_words(text))


def match_part(text: str, kws: set[str]) -> bool:
    """Matches keyword or multi-word phrase against text on whole word boundaries."""
    words = split_words(text)
    if not words:
        return False
    words_set = set(words)
    joined = " " + " ".join(words) + " "
    for kw in kws:
        kw_words = split_words(kw)
        if not kw_words:
            continue
        if len(kw_words) == 1:
            if kw_words[0] in words_set:
                return True
        else:
            kw_joined = " " + " ".join(kw_words) + " "
            if kw_joined in joined:
                return True
    return False


class _Match:
    def __bool__(self) -> bool:
        return True


class PartMatcher:
    def __init__(self, part: str, kws: set[str]) -> None:
        self.part = part
        self.kws = kws

    def search(self, text: str) -> Optional[_Match]:
        return _Match() if match_part(text, self.kws) else None


PART_REGEX: dict[str, PartMatcher] = {
    part: PartMatcher(part, kws)
    for part, kws in PART_KEYWORDS.items()
}


def _hash_texts(texts: Sequence[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


@dataclass(frozen=True)
class Chunk:
    scheme_id: str
    part: str
    text: str


@dataclass(frozen=True)
class ChunkHit:
    scheme_id: str
    part: str
    text: str
    score: float
    by: str = "vector"


def default_embed() -> Embed:
    """Load default fastembed model."""
    import numpy as np
    from fastembed import TextEmbedding

    model = TextEmbedding(EMBED_MODEL)

    def embed(texts: Sequence[str]) -> Any:
        return np.asarray(list(model.embed(list(texts))), dtype="float32")

    return embed


def _unit(mat: Any) -> Any:
    import numpy as np

    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


class ChunkIndex:
    def __init__(
        self,
        snapshot_id: str,
        chunks: list[Chunk],
        scheme_ids: list[str],
        vectors: Any,
        passage_to_chunk: Any,
        embed: Optional[Embed],
        door_a: Any = None,
        scheme_index: Any = None,
    ) -> None:
        import numpy as np

        self.snapshot_id = snapshot_id
        self.chunks = chunks
        self.scheme_ids = tuple(scheme_ids)
        self._vectors = vectors
        self._passage_to_chunk = passage_to_chunk
        self._embed = embed
        self._door_a = door_a
        self._scheme_index = scheme_index

        self._scheme_id_to_idx = {sid: i for i, sid in enumerate(scheme_ids)}
        self._chunk_scheme_indices = np.array(
            [self._scheme_id_to_idx.get(c.scheme_id, -1) for c in chunks],
            dtype=np.int32,
        )
        self._chunk_part_indices = np.array(
            [PART_INDEX.get(c.part, -1) for c in chunks],
            dtype=np.int32,
        )
        self._chunk_valid_text_mask = np.array(
            [bool(c.text and c.text.strip()) for c in chunks],
            dtype=bool,
        )

    @property
    def ids(self) -> tuple[str, ...]:
        return self.scheme_ids

    @classmethod
    def from_rows(
        cls,
        rows: list[dict[str, Any]],
        snapshot_id: str = "CURRENT",
        embed: Optional[Embed] = None,
        cache: bool = True,
        door_a: Any = None,
        scheme_index_inst: Any = None,
    ) -> "ChunkIndex":
        from haqdaar.data import scheme_index

        scheme_ids = [str(r["scheme_id"]) for r in rows]

        chunks: list[Chunk] = []
        texts_to_embed: list[str] = []
        passage_to_chunk: list[int] = []

        for r in rows:
            sid = str(r["scheme_id"])
            name_en = r.get("scheme_name_en") or ""
            name_hi = r.get("scheme_name_hi") or ""
            aliases_en = " ".join(r.get("aliases_en") or [])
            aliases_hi = " ".join(r.get("aliases_hi") or [])
            cat = r.get("category") or ""
            occ = r.get("occupation") or ""

            for part_name, field_key, tag_en, tag_hi in PART_SPECS:
                txt_en = (r.get("chunks") or {}).get("en", {}).get(field_key) or ""
                txt_hi = (r.get("chunks") or {}).get("hi", {}).get(field_key) or ""

                chunk_idx = len(chunks)
                chunks.append(Chunk(scheme_id=sid, part=part_name, text=txt_en))

                p_en = f"{name_en}. {tag_en}: {txt_en}"
                p_hi = f"{name_hi}. {tag_hi}: {txt_hi}"
                p_label_en = f"{name_en}. {tag_en}."
                p_label_hi = f"{name_hi}. {tag_hi}."

                texts_to_embed.extend([txt_en, txt_hi, p_en, p_hi, p_label_en, p_label_hi])
                passage_to_chunk.extend([chunk_idx] * 6)

                if part_name == "summary":
                    head_en = f"{name_en}. {aliases_en}. Category: {cat}. For: {occ}."
                    head_hi = f"{name_hi}. {aliases_hi}."
                    texts_to_embed.extend([head_en, head_hi])
                    passage_to_chunk.extend([chunk_idx, chunk_idx])

        # Pre-build SchemeIndex instance if not provided
        if scheme_index_inst is None:
            names = [scheme_index._names(r) for r in rows]
            ids = [str(r["scheme_id"]) for r in rows]
            try:
                import numpy as np
                scheme_index_inst = scheme_index.SchemeIndex(
                    snapshot_id, ids, names, None, np.array([], dtype=np.int32), None
                )
            except Exception:
                scheme_index_inst = None

        # Pre-build DoorA instance if not provided
        if door_a is None:
            try:
                from haqdaar.data.door_a_sources import load_repo_scheme_entries
                from haqdaar.engine.door_a import DoorA
                door_a = DoorA(scheme_entries=load_repo_scheme_entries())
            except Exception as exc:
                logger.warning("Failed to initialize DoorA for ChunkIndex: %s", exc)
                door_a = None

        vectors = None
        try:
            import numpy as np

            path = CACHE_DIR / f"{snapshot_id}__chunks__{EMBED_MODEL.split('/')[-1]}.npy"
            hash_path = CACHE_DIR / f"{snapshot_id}__chunks__{EMBED_MODEL.split('/')[-1]}.hash"
            texts_hash = _hash_texts(texts_to_embed)
            use_cache = cache and embed is None
            if embed is None:
                embed = default_embed()

            if use_cache and path.exists() and hash_path.exists():
                try:
                    cached_hash = hash_path.read_text(encoding="utf-8").strip()
                    if cached_hash == texts_hash:
                        loaded = np.load(path)
                        if loaded.shape[0] == len(texts_to_embed):
                            vectors = loaded
                except Exception:
                    vectors = None

            if vectors is None and texts_to_embed:
                vectors = _unit(np.asarray(embed(texts_to_embed), dtype="float32"))
                if use_cache:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    np.save(path, vectors)
                    hash_path.write_text(texts_hash, encoding="utf-8")
            ptc_arr: Any = np.asarray(passage_to_chunk, dtype=np.int32)
        except Exception as exc:
            logger.warning("Failed to initialize vectors for ChunkIndex: %s", exc)
            vectors, ptc_arr, embed = None, np.asarray(passage_to_chunk, dtype=np.int32), None

        return cls(
            snapshot_id, chunks, scheme_ids, vectors, ptc_arr, embed,
            door_a=door_a, scheme_index=scheme_index_inst
        )

    @classmethod
    def load(
        cls,
        snapshot_id: str = "CURRENT",
        embed: Optional[Embed] = None,
        cache: bool = True,
    ) -> "ChunkIndex":
        from haqdaar.data import scheme_index

        snapshot_id, rows = scheme_index._rows(snapshot_id)
        return cls.from_rows(rows, snapshot_id=snapshot_id, embed=embed, cache=cache)

    @classmethod
    def make_100_schemes(
        cls,
        embed: Optional[Embed] = None,
        cache: bool = True,
    ) -> "ChunkIndex":
        """Make 100 schemes by replicating and varying the 17 real schemes with real text,
        real embedding model, and pre-built DoorA + SchemeIndex name matchers kept ON.
        """
        from haqdaar.data import scheme_index
        from haqdaar.data.door_a_sources import load_repo_scheme_entries
        from haqdaar.contracts.types import SchemeEntry
        from haqdaar.engine.door_a import DoorA

        _, base_rows = scheme_index._rows("CURRENT")
        base_entries = load_repo_scheme_entries()
        base_entries_by_slug = {e.slug: e for e in base_entries}

        rows_100: list[dict[str, Any]] = []
        entries_100: list[SchemeEntry] = []

        for i in range(100):
            b_row = base_rows[i % len(base_rows)]
            r = dict(b_row)
            base_sid = str(b_row["scheme_id"])
            sid_new = f"{base_sid}_var_{i:03d}"
            r["scheme_id"] = sid_new
            name_en = b_row.get("scheme_name_en") or ""
            name_hi = b_row.get("scheme_name_hi") or ""
            r["scheme_name_en"] = f"{name_en} {i}"
            r["scheme_name_hi"] = f"{name_hi} {i}"
            r["aliases_en"] = [f"{a} {i}" for a in b_row.get("aliases_en") or []]
            r["aliases_hi"] = [f"{a} {i}" for a in b_row.get("aliases_hi") or []]
            r["chunks"] = b_row.get("chunks")
            rows_100.append(r)

            b_ent = base_entries_by_slug.get(base_sid)
            if b_ent is not None:
                e = SchemeEntry(
                    slug=sid_new,
                    priority=b_ent.priority,
                    names={k: f"{v} {i}" for k, v in b_ent.names.items()},
                    aliases=[f"{a} {i}" for a in b_ent.aliases],
                    distinctive_tokens=b_ent.distinctive_tokens,
                )
            else:
                e = SchemeEntry(
                    slug=sid_new,
                    priority=100,
                    names={"en": f"{name_en} {i}", "hi": f"{name_hi} {i}"},
                    aliases=[f"{a} {i}" for a in b_row.get("aliases_en") or []],
                    distinctive_tokens=(),
                )
            entries_100.append(e)

        door_a_100 = DoorA(scheme_entries=entries_100)
        return cls.from_rows(
            rows_100,
            snapshot_id="100_SCHEMES_BENCHMARK",
            embed=embed,
            cache=cache,
            door_a=door_a_100,
        )

    def _get_name_scores(self, text: str) -> dict[str, float]:
        """Use pre-built name matchers without recreating them."""
        scores: dict[str, float] = {sid: 0.0 for sid in self.scheme_ids}

        # 1. Rapidfuzz-based SchemeIndex._name_scores
        if self._scheme_index is not None:
            try:
                from haqdaar.data.scheme_names import contains_word, short_names_for
                for sid, s in zip(self._scheme_index.ids, self._scheme_index._name_scores(text)):
                    if s > 0 and sid in scores:
                        # Verify that the query text actually contains the scheme's name or short form
                        # to avoid false partial matches on consonant-stripped strings
                        if s >= 0.85:
                            snames = list(short_names_for(sid))
                            if snames and not any(contains_word(text.lower(), sn.lower()) for sn in snames):
                                sid_norm = sid.replace("-", " ")
                                if sid_norm not in text.lower() and not any(contains_word(text.lower(), w) for w in sid.split("-")):
                                    continue
                        scores[sid] = max(scores[sid], float(s))
            except Exception:
                pass

        # 2. Phonetic token-based DoorA matching
        if self._door_a is not None:
            try:
                res = self._door_a.match(text)
                if res.confidence > 0:
                    for sid in res.scheme_ids:
                        if sid in scores:
                            scores[sid] = max(scores[sid], float(res.confidence))
            except Exception:
                pass

        return scores

    def search(
        self,
        query: str | Sequence[str],
        *,
        k: int = 5,
        fits: Optional[dict[str, Any] | set[str]] = None,
        max_chunks_per_scheme: int = 2,
    ) -> list[ChunkHit]:
        """Search top k chunks for English query or multiple queries.

        Multi-query: takes best score (max) across queries.
        Top k: at most max_chunks_per_scheme chunks from one scheme,
        unless the query names that scheme (name match 0.85+).
        Empty English texts are never returned.
        """
        if fits is not None:
            if isinstance(fits, bool) or not isinstance(fits, (dict, set)):
                raise TypeError(f"fits must be a dict or set of scheme ids, got {type(fits).__name__}")
        try:
            if isinstance(query, str):
                queries = [query]
            else:
                queries = list(query)

            clean_queries = [q.strip() for q in queries if q and _norm(q)]
            if not clean_queries or not self.chunks:
                return []

            import numpy as np

            n_chunks = len(self.chunks)
            n_schemes = len(self.scheme_ids)

            best_scores = np.full(n_chunks, -np.inf, dtype=np.float32)
            best_by_is_name = np.zeros(n_chunks, dtype=bool)
            scheme_is_named = np.zeros(n_schemes, dtype=bool)

            scheme_fits = np.zeros(n_schemes, dtype=np.float32)
            if fits is not None:
                if isinstance(fits, set):
                    for i, sid in enumerate(self.scheme_ids):
                        if sid in fits:
                            scheme_fits[i] = 0.15
                elif isinstance(fits, dict):
                    for i, sid in enumerate(self.scheme_ids):
                        m = fits.get(sid, "not known yet")
                        if isinstance(m, bool):
                            scheme_fits[i] = 0.15 if m else -0.50
                        elif isinstance(m, (int, float)):
                            scheme_fits[i] = float(m)
                        elif m == "fits":
                            scheme_fits[i] = 0.15
                        elif m == "does not fit":
                            scheme_fits[i] = -0.50
            chunk_fits_adj = scheme_fits[self._chunk_scheme_indices]

            for q_text in clean_queries:
                # 1. Vector scores
                chunk_vec = np.zeros(n_chunks, dtype=np.float32)
                if self._vectors is not None and self._embed is not None:
                    try:
                        q_vec = _unit(np.asarray(self._embed([q_text]), dtype="float32"))[0]
                        sims = self._vectors @ q_vec
                        np.maximum.at(chunk_vec, self._passage_to_chunk, sims)
                    except Exception:
                        pass

                # 2. Name match scores
                name_scores_dict = self._get_name_scores(q_text)
                scheme_name_scores = np.array(
                    [name_scores_dict.get(sid, 0.0) for sid in self.scheme_ids],
                    dtype=np.float32,
                )
                chunk_name_scores = scheme_name_scores[self._chunk_scheme_indices]
                scheme_is_named |= (scheme_name_scores >= 0.85)

                # 3. Fixed-code part keyword bonus (whole words only)
                part_boosts = np.zeros(len(PARTS), dtype=np.float32)
                for part, matcher in PART_REGEX.items():
                    if matcher.search(q_text):
                        part_boosts[PART_INDEX[part]] = 0.25
                chunk_part_boost = part_boosts[self._chunk_part_indices]

                # 4. Total query score
                q_score = chunk_vec + 0.35 * chunk_name_scores + chunk_part_boost + chunk_fits_adj
                by_is_name = chunk_name_scores >= 0.85

                improved = q_score > best_scores
                best_scores = np.where(improved, q_score, best_scores)
                best_by_is_name = np.where(improved, by_is_name, best_by_is_name)

            # Mask out chunks with empty English text (Point 10)
            best_scores[~self._chunk_valid_text_mask] = -np.inf

            # Rank and select top k with scheme cap (Point 5)
            sorted_indices = np.argsort(-best_scores)
            hits: list[ChunkHit] = []
            scheme_chunk_counts: dict[str, int] = {}

            for idx in sorted_indices:
                if len(hits) >= k:
                    break
                score = float(best_scores[idx])
                if score <= -1e8:
                    break
                c = self.chunks[idx]
                sid = c.scheme_id
                s_idx = self._chunk_scheme_indices[idx]
                is_named = scheme_is_named[s_idx]
                count = scheme_chunk_counts.get(sid, 0)

                if max_chunks_per_scheme is not None and max_chunks_per_scheme > 0 and not is_named:
                    if count >= max_chunks_per_scheme:
                        continue

                scheme_chunk_counts[sid] = count + 1
                hits.append(
                    ChunkHit(
                        scheme_id=sid,
                        part=c.part,
                        text=c.text,
                        score=score,
                        by="name" if best_by_is_name[idx] else "vector",
                    )
                )

            return hits
        except Exception as exc:
            logger.warning("Chunk search failed: %s", exc)
            return []


_loaded_chunks: dict[str, ChunkIndex] = {}


def get(snapshot_id: str = "CURRENT") -> ChunkIndex:
    """One chunk index per snapshot for the application lifecycle."""
    if snapshot_id not in _loaded_chunks:
        _loaded_chunks[snapshot_id] = ChunkIndex.load(snapshot_id)
        _loaded_chunks[snapshot_id].search("warm up", k=1)
    return _loaded_chunks[snapshot_id]


def search(
    query: str | Sequence[str],
    *,
    k: int = 5,
    fits: Optional[dict[str, Any] | set[str]] = None,
    max_chunks_per_scheme: int = 2,
    snapshot_id: str = "CURRENT",
) -> list[ChunkHit]:
    """Top k chunks for query across the specified snapshot."""
    return get(snapshot_id).search(
        query, fits=fits, k=k, max_chunks_per_scheme=max_chunks_per_scheme
    )
