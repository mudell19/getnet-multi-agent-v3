"""Refresh command: rebuilds data/crawl_cache from the live sites (FR-014). Not used by tests
or ingestion; run it only on purpose."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from getnet_multi_agent.core.settings import CACHE_DIR, get_settings
from getnet_multi_agent.rag.chunk import normalize_url
from getnet_multi_agent.rag.ingest import allowed

log = logging.getLogger(__name__)

START_PAGES = [
    "https://site.getnet.com.br/",
    "https://site.getnet.com.br/duvidas/",
    "https://site.getnet.com.br/crediario/",
    "https://site.getnet.com.br/link-de-pagamento/",
    "https://site.getnet.com.br/pix/",
    "https://site.getnet.com.br/todas-as-maquininhas/",
    "https://www.getnet.net/en",
]
DUVIDAS = "https://site.getnet.com.br/duvidas"
DELAY_S = 2
STOP_STATUSES = {403, 429}
SKIP_EXT = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip", ".mp4", ".xml",
            ".css", ".js", ".ico")
USER_AGENT = "getnet-multi-agent-refresh/0.1"


def cache_key(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


def _links(base: str, html: str) -> list[str]:
    host = urlsplit(base).netloc.lower()
    out = []
    for a in BeautifulSoup(html, "lxml").find_all("a", href=True):
        url = urljoin(base, a["href"]).split("#")[0].split("?")[0]
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or parts.netloc.lower() != host:
            continue
        if parts.path.lower().endswith(SKIP_EXT) or not allowed(url):
            continue
        out.append(url)
    return out


def _write(cache_dir: Path, url: str, resp: httpx.Response) -> None:
    key = cache_key(url)
    content_type = resp.headers.get("content-type", "")
    meta = {"url": url, "final_url": str(resp.url), "status": resp.status_code,
            "content_type": content_type}
    (cache_dir / f"{key}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    if resp.status_code == 200 and "text/html" in content_type:
        (cache_dir / f"{key}.html").write_text(resp.text, encoding="utf-8")


def refresh(max_pages: int | None = None, client: httpx.Client | None = None,
            sleep: Callable[[float], None] = time.sleep, cache_dir: Path = CACHE_DIR) -> int:
    """Crawl the start pages and one level below them; returns the number of pages fetched."""
    max_pages = max_pages if max_pages is not None else get_settings().RAG_MAX_PAGES
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    own_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=20,
                                    headers={"User-Agent": USER_AGENT})
    # Start pages, then /duvidas topic pages (required content), then other level-1 links.
    queues: list[list[tuple[str, int]]] = [[(u, 0) for u in START_PAGES], [], []]
    seen = {normalize_url(u) for u in START_PAGES}
    blocked: set[str] = set()
    fetched = 0
    try:
        while any(queues) and fetched < max_pages:
            url, depth = next(q for q in queues if q).pop(0)
            host = urlsplit(url).netloc.lower()
            if host in blocked:
                continue
            if fetched:
                sleep(DELAY_S)
            try:
                resp = client.get(url)
            except httpx.HTTPError as exc:
                log.warning("fetch failed %s: %s", url, exc)
                continue
            fetched += 1
            if resp.status_code in STOP_STATUSES:
                log.warning("stopping host %s after HTTP %d", host, resp.status_code)
                blocked.add(host)
                continue
            _write(cache_dir, url, resp)
            if depth > 0 or resp.status_code != 200:
                continue
            for link in _links(str(resp.url), resp.text):
                key = normalize_url(link)
                if key not in seen:
                    seen.add(key)
                    queues[1 if key.startswith(DUVIDAS + "/") else 2].append((link, depth + 1))
    finally:
        if own_client:
            client.close()
    return fetched
