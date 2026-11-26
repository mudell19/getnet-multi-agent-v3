"""Hybrid retrieval: Chroma vector top-k + glossary-expanded lexical matching, rule boost and
per-product sub-queries (FR-017, FR-019, FR-020)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from getnet_multi_agent.core.settings import Settings, get_settings
from getnet_multi_agent.rag import glossary
from getnet_multi_agent.rag.chunk import Chunk
from getnet_multi_agent.rag.store import Store

VECTOR_WEIGHT = 0.6
LEXICAL_WEIGHT = 0.4
RULE_BOOST = 0.1
GLOSSARY_TERM_WEIGHT = 2.0
RULE_MARKERS = ["precisa", "é necessário", "necessário", "deve", "até", "obrigatório",
                "required", "must", "only", "need"]
STOPWORDS = set(glossary.norm(
    "the and for with what whats what's which how does can are you your the between difference "
    "about from that this have has get getnet is it to of in on a an or do my me i "
    "o a os as de da do das dos e em no na nos nas um uma para por com que qual quais como "
    "meu minha seu sua ser sao entre diferenca posso pode tem ter mais menos")
    .split())
_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float
    vector_score: float
    lexical_score: float


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _terms(query: str) -> list[tuple[set[str], float]]:
    """Each glossary group named is one term (any alias matches); other content words are
    single-word terms."""
    groups = glossary.matched_groups(query)
    terms = [({glossary.norm(a) for a in glossary.GROUPS[i]}, GLOSSARY_TERM_WEIGHT)
             for i in groups]
    rest = glossary.strip_aliases(query, groups)
    words = [w for w in dict.fromkeys(_WORD.findall(rest)) if len(w) >= 3 and w not in STOPWORDS]
    terms.extend(({w}, 1.0) for w in words)
    return terms


def _unique(results: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Drop repeats of the same text (FAQs appear on /duvidas and on their topic page)."""
    seen: set[str] = set()
    out = []
    for r in results:
        if r.chunk.text not in seen:
            seen.add(r.chunk.text)
            out.append(r)
    return out


def _has_rule(text_norm: str) -> bool:
    return any(glossary.contains(text_norm, m) for m in RULE_MARKERS)


class Retriever:
    def __init__(self, store: Store | None = None, llm=None, settings: Settings | None = None):
        self.store = store or Store()
        self._llm = llm
        self.settings = settings or get_settings()
        self._chunks: list[tuple[Chunk, str]] | None = None

    @property
    def llm(self):
        if self._llm is None:
            from getnet_multi_agent.core.llm import get_llm

            self._llm = get_llm()
        return self._llm

    def _all(self) -> list[tuple[Chunk, str]]:
        if self._chunks is None:
            self._chunks = [(c, glossary.norm(c.text)) for c in self.store.all_chunks()]
        return self._chunks

    def _embed(self, text: str) -> list[float]:
        return self.llm.embed([text], "query")[0]

    def _vector(self, query: str, k: int) -> tuple[list[float], dict[str, tuple[Chunk, float]]]:
        vec = self._embed(query)
        hits = self.store.query(vec, k)
        keep = {c.id: (c, s) for c, s in hits if s >= self.settings.RAG_MIN_SIMILARITY}
        return vec, keep

    def _lexical(self, query: str) -> dict[str, tuple[Chunk, float, bool]]:
        terms = _terms(query)
        total = sum(w for _, w in terms)
        if not total:
            return {}
        out = {}
        for chunk, text in self._all():
            got = sum(w for aliases, w in terms if any(glossary.contains(text, a) for a in aliases))
            if got:
                out[chunk.id] = (chunk, got / total, _has_rule(text))
        return out

    def _hybrid(self, query: str, k: int) -> list[RetrievedChunk]:
        vec, vector_hits = self._vector(query, k)
        lexical = self._lexical(query)
        top_lexical = sorted(lexical, key=lambda cid: lexical[cid][1], reverse=True)[:k * 3]
        candidates = set(vector_hits) | set(top_lexical)
        missing = [cid for cid in candidates if cid not in vector_hits]
        stored = self.store.vectors(missing)
        results = []
        for cid in candidates:
            if cid in vector_hits:
                chunk, v = vector_hits[cid]
            else:
                chunk = lexical[cid][0]
                v = max(0.0, _cosine(vec, stored[cid])) if cid in stored else 0.0
            lex = lexical.get(cid, (chunk, 0.0, False))[1]
            rule = lexical[cid][2] if cid in lexical else _has_rule(glossary.norm(chunk.text))
            score = VECTOR_WEIGHT * v + LEXICAL_WEIGHT * lex + (RULE_BOOST if rule else 0.0)
            results.append(RetrievedChunk(chunk, min(score, 1.0), v, lex))
        results.sort(key=lambda r: r.score, reverse=True)
        return _unique(results)[:k]

    def _per_product(self, query: str, products: list[str], k: int) -> list[RetrievedChunk]:
        groups = [glossary.PRODUCTS[p] for p in products]
        rest = glossary.strip_aliases(query, groups)
        per_k = max(1, math.ceil(k / len(products)))
        merged: dict[str, RetrievedChunk] = {}
        reserved: list[str] = []
        for product in products:
            aliases = " ".join(glossary.GROUPS[glossary.PRODUCTS[product]])
            hits = self._hybrid(f"{aliases} {rest}".strip(), k)
            for r in hits:
                if r.chunk.id not in merged or r.score > merged[r.chunk.id].score:
                    merged[r.chunk.id] = r
            # Each product keeps its best chunks in the final list.
            reserved.extend(r.chunk.id for r in hits[:per_k] if r.chunk.id not in reserved)
        ranked = _unique(sorted(merged.values(), key=lambda r: r.score, reverse=True))
        chosen = _unique([merged[cid] for cid in reserved])[:k]
        texts = {r.chunk.text for r in chosen}
        chosen.extend(r for r in ranked if r.chunk.text not in texts)
        return sorted(chosen[:k], key=lambda r: r.score, reverse=True)

    def retrieve(self, query: str, mode: Literal["hybrid", "vector"] = "hybrid",
                 k: int | None = None) -> list[RetrievedChunk]:
        k = k or self.settings.RAG_TOP_K
        if mode == "vector":
            # Over-fetch so that dropping repeated FAQ texts still leaves k results.
            _, hits = self._vector(query, k * 2)
            ranked = sorted(hits.values(), key=lambda h: h[1], reverse=True)
            return _unique([RetrievedChunk(c, s, s, 0.0) for c, s in ranked])[:k]
        products = glossary.products_in(query)
        if len(products) >= 2:
            return self._per_product(query, products, k)
        return self._hybrid(query, k)


_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever
