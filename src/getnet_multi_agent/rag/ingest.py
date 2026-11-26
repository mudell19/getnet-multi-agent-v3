"""Ingestion from the committed crawl cache only: no network."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from getnet_multi_agent.core.settings import CACHE_DIR
from getnet_multi_agent.rag.chunk import Chunk, chunk_page, normalize_url, site_of
from getnet_multi_agent.rag.extract import Extracted, parse, repeated_texts, strip_repeated
from getnet_multi_agent.rag.store import Store

log = logging.getLogger(__name__)
EMBED_BATCH = 50
HOSTS = {"site.getnet.com.br", "www.getnet.net"}


@dataclass
class RawPage:
    url: str  # normalized final URL
    site: str
    html: str
    page: Extracted


def allowed(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host not in HOSTS:
        return False
    if host == "www.getnet.net":
        return parts.path == "/en" or parts.path.startswith("/en/")
    return True


def load_cache(cache_dir: Path = CACHE_DIR) -> list[RawPage]:
    """Status 200 text/html entries, deduplicated by final URL and by visible-text hash."""
    entries = []
    for meta_file in sorted(Path(cache_dir).glob("*.json")):
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        html_file = meta_file.with_suffix(".html")
        if meta.get("status") != 200 or "text/html" not in (meta.get("content_type") or ""):
            continue
        final = normalize_url(meta.get("final_url") or meta["url"])
        if not allowed(final) or not html_file.exists():
            continue
        # Pages fetched at their own URL win over redirects to the same final URL.
        redirected = normalize_url(meta["url"]) != final
        entries.append((redirected, final, html_file))
    entries.sort(key=lambda e: (e[0], e[1]))

    pages: list[RawPage] = []
    seen_urls: set[str] = set()
    seen_text: set[str] = set()
    for _, final, html_file in entries:
        if final in seen_urls:
            continue
        html = html_file.read_text(encoding="utf-8", errors="replace")
        page = parse(html)
        digest = hashlib.sha256(page.visible_text().encode()).hexdigest()
        if digest in seen_text:
            continue
        seen_urls.add(final)
        seen_text.add(digest)
        pages.append(RawPage(url=final, site=site_of(final), html=html, page=page))
    return pages


def build_chunks(pages: list[RawPage]) -> list[Chunk]:
    repeated = repeated_texts([p.page for p in pages])
    chunks: dict[str, Chunk] = {}
    for p in pages:
        for c in chunk_page(p.url, strip_repeated(p.page, repeated)):
            chunks.setdefault(c.id, c)
    return list(chunks.values())


def ingest(rebuild: bool = False, llm=None, store: Store | None = None,
           cache_dir: Path = CACHE_DIR) -> int:
    """Index the cache into the store; returns the number of chunks indexed."""
    store = store or Store()
    if store.count() and not rebuild:
        return store.count()
    if rebuild:
        store.reset()
    if llm is None:
        from getnet_multi_agent.core.llm import get_llm

        llm = get_llm()
    pages = load_cache(cache_dir)
    chunks = build_chunks(pages)
    for i in range(0, len(chunks), EMBED_BATCH):
        part = chunks[i:i + EMBED_BATCH]
        vectors = llm.embed([c.text for c in part], "document")
        if len(vectors) != len(part):
            raise ValueError(f"embed returned {len(vectors)} vectors for {len(part)} texts")
        store.add(part, vectors)
    log.info("ingested %d chunks from %d pages", store.count(), len(pages))
    return store.count()
