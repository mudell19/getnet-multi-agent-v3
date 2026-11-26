"""Chunking by heading and by FAQ question; no fixed-size windows."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from getnet_multi_agent.rag.extract import Extracted

MIN_CHARS = 40
MAX_CHARS = 1500


@dataclass
class Chunk:
    id: str
    url: str
    title: str
    heading: str
    site: Literal["br", "global"]
    kind: Literal["faq", "section", "table"]
    text: str


def normalize_url(url: str) -> str:
    """scheme://host + path without trailing slash ('/' for the root); no query or fragment."""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{path}"


def site_of(url: str) -> Literal["br", "global"]:
    return "br" if urlsplit(url).netloc.lower() == "site.getnet.com.br" else "global"


def _make(url: str, title: str, heading: str, kind: str, text: str) -> Chunk:
    cid = hashlib.sha256(f"{url}{heading}{text}".encode()).hexdigest()[:16]
    return Chunk(id=cid, url=url, title=title, heading=heading, site=site_of(url),
                 kind=kind, text=text)  # type: ignore[arg-type]


def _split(paras: list[str]) -> list[list[str]]:
    """Group paragraphs into parts of about MAX_CHARS, breaking only between paragraphs."""
    parts: list[list[str]] = [[]]
    size = 0
    for p in paras:
        if parts[-1] and size + len(p) > MAX_CHARS:
            parts.append([])
            size = 0
        parts[-1].append(p)
        size += len(p) + 1
    return parts


def chunk_page(url: str, page: Extracted) -> list[Chunk]:
    url = normalize_url(url)
    title = page.title
    chunks: list[Chunk] = []
    heading = title
    paras: list[str] = []

    def flush() -> None:
        unique = list(dict.fromkeys(paras))
        for part in _split(unique):
            if not part:
                continue
            text = "\n".join([heading, *part]) if heading else "\n".join(part)
            chunks.append(_make(url, title, heading, "section", text))
        paras.clear()

    for block in page.blocks:
        if block.kind == "heading":
            flush()
            heading = block.text
        elif block.kind == "text":
            paras.append(block.text)
        elif block.kind == "table":
            flush()
            text = f"{heading}\n{block.text}" if heading else block.text
            chunks.append(_make(url, title, heading, "table", text))
        elif block.kind == "faq":
            flush()
            prefix = f"{heading}: " if heading and heading != title else ""
            text = f"{prefix}{block.text}\n{block.answer}"
            chunks.append(_make(url, title, block.text, "faq", text))
    flush()

    seen: set[str] = set()
    out = []
    for c in chunks:
        if len(c.text) < MIN_CHARS or c.id in seen:
            continue
        seen.add(c.id)
        out.append(c)
    return out
