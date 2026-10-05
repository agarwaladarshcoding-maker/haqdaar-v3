"""haqdaar/data/scheme_index.py

Scheme search for the talk loop (step 7.13, B2). Two searches over ALL schemes of a snapshot:
  - vector search: a multilingual embedding model (fastembed, ONNX, CPU), so Hindi words
    find English scheme text with no translate step;
  - name search: rapidfuzz over names + other names (English and Hindi).
Score of a scheme = the best of the two. No vector database: one numpy array in memory,
cached on disk per snapshot id. One caller at a time.
Never raises from search(): a broken model or an empty snapshot gives name search only, or [].
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from haqdaar.contracts import tunables
from haqdaar.data import scheme_names

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CACHE_DIR = Path("data_cache") / "scheme_index"
TEXT_LANGS = ("en", "hi")
TEXT_FIELDS = ("summary", "who_can_apply", "benefit_text")

Embed = Callable[[Sequence[str]], Any]   # texts -> array of shape (n, dim)

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class Hit:
    scheme_id: str
    score: float
    by: str              # "name" or "vector"


def _norm(text: str) -> str:
    return scheme_names.norm(text)


def _contains(hay: list[str], needle: list[str]) -> bool:
    """The needle's whole words standing in a row in the haystack."""
    return bool(needle) and any(
        hay[i:i + len(needle)] == needle for i in range(len(hay) - len(needle) + 1))


def _marked_beside(hay: list[str], needle: list[str]) -> bool:
    """A marker word (योजना / लोन / scheme / loan) right before or after the name."""
    n = len(needle)
    for i in range(len(hay) - n + 1):
        if hay[i:i + n] == needle:
            near = hay[i - 1:i] + hay[i + n:i + n + 1]
            if scheme_names.has_marker(near):
                return True
    return False


def _rows(snapshot_id: str) -> tuple[str, list[dict[str, Any]]]:
    root = Path(tunables.SNAPSHOTS_DIR)
    if snapshot_id == "CURRENT":
        snapshot_id = (root / "CURRENT").read_text(encoding="utf-8").strip()
    rows: list[dict[str, Any]] = []
    with open(root / snapshot_id / "schemes.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                str(row["scheme_id"])
                rows.append(row)
            except (ValueError, KeyError, TypeError):
                continue
    return snapshot_id, rows


def _names(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for lang in TEXT_LANGS:
        for name in [row.get(f"scheme_name_{lang}")] + list(row.get(f"aliases_{lang}") or []):
            name = _norm(name or "")
            if name and name not in out:
                out.append(name)
    # 1.3a: the short names people say, kept next to the scheme data by scheme id.
    for name in scheme_names.short_names_for(row.get("scheme_id", "")):
        name = _norm(name)
        if name and name not in out:
            out.append(name)
    return out


def _passages(row: dict[str, Any]) -> list[str]:
    """Short texts for one scheme. Each is embedded on its own; the best one scores."""
    out: list[str] = []
    for lang in TEXT_LANGS:
        chunk = (row.get("chunks") or {}).get(lang) or {}
        names = [row.get(f"scheme_name_{lang}") or ""] + list(row.get(f"aliases_{lang}") or [])
        head = ". ".join(n for n in names if n)
        if lang == "en":
            head += f". Category: {row.get('category', '')}. For: {row.get('occupation', '')}."
        out.append(head)
        out += [str(chunk[f]) for f in TEXT_FIELDS if chunk.get(f)]
    return [p for p in out if p.strip()]


def default_embed() -> Embed:
    """The real model. The first use downloads it once (about 220 MB), then it is local."""
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


class SchemeIndex:
    def __init__(self, snapshot_id: str, ids: list[str], names: list[list[str]],
                 vectors: Any, owner: Any, embed: Optional[Embed]) -> None:
        self.snapshot_id = snapshot_id
        self.ids = ids
        self._names = names
        self._vectors = vectors      # (passages, dim), unit length; None = name search only
        self._owner = owner          # passage row -> place in ids
        self._embed = embed

    @classmethod
    def load(cls, snapshot_id: str = "CURRENT", embed: Optional[Embed] = None,
             cache: bool = True) -> "SchemeIndex":
        snapshot_id, rows = _rows(snapshot_id)
        ids = [str(r["scheme_id"]) for r in rows]
        names = [_names(r) for r in rows]
        texts: list[str] = []
        owner: list[int] = []
        for n, row in enumerate(rows):
            for passage in _passages(row):
                texts.append(passage)
                owner.append(n)
        vectors = None
        try:
            import numpy as np

            path = CACHE_DIR / f"{snapshot_id}__{EMBED_MODEL.split('/')[-1]}.npy"
            use_cache = cache and embed is None
            if embed is None:
                embed = default_embed()
            if use_cache and path.exists():
                vectors = np.load(path)
                if vectors.shape[0] != len(texts):
                    vectors = None
            if vectors is None and texts:
                vectors = _unit(np.asarray(embed(texts), dtype="float32"))
                if use_cache:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    np.save(path, vectors)
            owner_arr: Any = np.asarray(owner)
        except Exception:
            vectors, owner_arr, embed = None, owner, None
        return cls(snapshot_id, ids, names, vectors, owner_arr, embed)

    def _name_scores(self, text: str) -> list[float]:
        # 1.3b: a name counts only when its whole words stand in the caller's
        # words ("समुद्र" is not "मुद्रा"; `\b` misses Hindi vowel-sign tails,
        # so words are split on spaces and punctuation instead). A short name
        # that is also a common word ("मुद्रा", "आजीविका") needs योजना / लोन /
        # scheme / loan next to it. A short name is the whole name people say,
        # never one common word of it.
        qtoks = _norm(text).split()
        out: list[float] = []
        for names in self._names:
            hit = False
            for name in names:
                ntoks = name.split()
                if ntoks and _contains(qtoks, ntoks) and (
                        not scheme_names.needs_marker(name)
                        or _marked_beside(qtoks, ntoks)):
                    hit = True
                    break
            out.append(1.0 if hit else 0.0)
        return out

    def _vector_scores(self, text: str) -> list[float]:
        if self._vectors is None or self._embed is None:
            return [0.0] * len(self.ids)
        import numpy as np

        q = _unit(np.asarray(self._embed([text]), dtype="float32"))[0]
        sims = self._vectors @ q
        out = [0.0] * len(self.ids)
        for row, n in enumerate(self._owner):
            out[int(n)] = max(out[int(n)], float(sims[row]))
        return out

    def search(self, text: str, k: int = 4) -> list[Hit]:
        """The k best schemes for the caller's words, best first."""
        try:
            if not _norm(text) or not self.ids:
                return []
            by_name = self._name_scores(text)
            try:
                by_vec = self._vector_scores(text)
            except Exception:
                by_vec = [0.0] * len(self.ids)
            hits = [
                Hit(sid, max(n, v), "name" if n >= v and n > 0 else "vector")
                for sid, n, v in zip(self.ids, by_name, by_vec)
            ]
            hits.sort(key=lambda h: -h.score)
            return hits[:k]
        except Exception:
            return []


_loaded: dict[str, SchemeIndex] = {}


def get(snapshot_id: str = "CURRENT") -> SchemeIndex:
    """One index per snapshot for the life of the server (built at start-up or first use)."""
    if snapshot_id not in _loaded:
        _loaded[snapshot_id] = SchemeIndex.load(snapshot_id)
        _loaded[snapshot_id].search("warm up", 1)   # the first model run is slow; pay it here
    return _loaded[snapshot_id]
