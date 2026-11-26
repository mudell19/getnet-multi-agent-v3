"""Chroma persistent store for chunks (collection getnet_kb, cosine space)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from getnet_multi_agent.core.settings import STATE_DIR
from getnet_multi_agent.rag.chunk import Chunk

COLLECTION = "getnet_kb"
BATCH = 500


def _meta(c: Chunk) -> dict[str, str]:
    return {"url": c.url, "title": c.title, "heading": c.heading, "site": c.site,
            "kind": c.kind, "text_hash": hashlib.sha256(c.text.encode()).hexdigest()[:16]}


def _chunk(cid: str, doc: str, meta: dict) -> Chunk:
    return Chunk(id=cid, url=meta["url"], title=meta.get("title", ""),
                 heading=meta.get("heading", ""), site=meta.get("site", "br"),
                 kind=meta.get("kind", "section"), text=doc)


class Store:
    def __init__(self, path: Path | str = STATE_DIR / "chroma"):
        Path(path).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False))
        self.collection = self._open()

    def _open(self):
        return self.client.get_or_create_collection(
            COLLECTION, configuration={"hnsw": {"space": "cosine"}}, embedding_function=None)

    def count(self) -> int:
        return self.collection.count()

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors differ in length")
        for i in range(0, len(chunks), BATCH):
            part, vecs = chunks[i:i + BATCH], vectors[i:i + BATCH]
            self.collection.upsert(ids=[c.id for c in part], embeddings=vecs,
                                   documents=[c.text for c in part],
                                   metadatas=[_meta(c) for c in part])

    def query(self, vector: list[float], k: int) -> list[tuple[Chunk, float]]:
        n = self.count()
        if n == 0:
            return []
        res = self.collection.query(query_embeddings=[vector], n_results=min(k, n),
                                    include=["documents", "metadatas", "distances"])
        return [(_chunk(cid, doc, meta), 1.0 - dist) for cid, doc, meta, dist in
                zip(res["ids"][0], res["documents"][0], res["metadatas"][0],
                    res["distances"][0], strict=True)]

    def all_chunks(self) -> list[Chunk]:
        res = self.collection.get(include=["documents", "metadatas"])
        return [_chunk(cid, doc, meta) for cid, doc, meta in
                zip(res["ids"], res["documents"], res["metadatas"], strict=True)]

    def vectors(self, ids: list[str]) -> dict[str, list[float]]:
        if not ids:
            return {}
        res = self.collection.get(ids=ids, include=["embeddings"])
        return {cid: list(vec) for cid, vec in zip(res["ids"], res["embeddings"], strict=True)}

    def reset(self) -> None:
        self.client.delete_collection(COLLECTION)
        self.collection = self._open()
