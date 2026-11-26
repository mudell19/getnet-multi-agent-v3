from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit

import httpx

from getnet_multi_agent.rag.chunk import normalize_url
from getnet_multi_agent.rag.crawler import START_PAGES, refresh

BR = "https://site.getnet.com.br"


def _page(*links: str) -> str:
    anchors = "".join(f'<a href="{u}">x</a>' for u in links)
    return f"<html><head><title>T</title></head><body><p>conteúdo</p>{anchors}</body></html>"


def make_client(requested: list[str], blocked_global: bool = True) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        host = request.url.host
        if host == "www.getnet.net" and blocked_global:
            return httpx.Response(403, headers={"content-type": "text/html"}, text="no")
        if host == "www.getnet.net":
            return httpx.Response(200, headers={"content-type": "text/html"},
                                  text=_page("/en/a", "/es/b", "https://www.getnet.net/en/c"))
        path = request.url.path
        if path == "/":
            html = _page("/duvidas/pix/", "/sobre/", "https://evil.example.com/x",
                         "/arquivo.pdf", "/sobre/#top", "mailto:a@b.c")
        elif path == "/duvidas/":
            html = _page("/duvidas/pix/", "/duvidas/crediario/", "/duvidas/taxas/")
        elif path == "/sobre/":
            html = _page("/deeper/")
        else:
            html = _page()
        return httpx.Response(200, headers={"content-type": "text/html; charset=UTF-8"},
                              text=html)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fr014_same_host_one_level_and_cache_format(tmp_path):
    requested: list[str] = []
    sleeps: list[float] = []
    n = refresh(max_pages=50, client=make_client(requested, blocked_global=False),
                sleep=sleeps.append, cache_dir=tmp_path)
    hosts = {urlsplit(u).netloc for u in requested}
    assert hosts == {"site.getnet.com.br", "www.getnet.net"}
    assert not any("/deeper" in u or u.endswith(".pdf") for u in requested)
    assert not any(urlsplit(u).netloc == "www.getnet.net" and not urlsplit(u).path.startswith("/en")
                   for u in requested)
    assert f"{BR}/duvidas/taxas/" in requested and f"{BR}/sobre/" in requested
    assert len(requested) == len({normalize_url(u) for u in requested}) == n
    assert sleeps == [2] * (n - 1)
    for url in requested:
        key = hashlib.sha256(normalize_url(url).encode()).hexdigest()
        meta = json.loads((tmp_path / f"{key}.json").read_text())
        assert set(meta) == {"url", "final_url", "status", "content_type"}
        assert meta["status"] == 200 and "text/html" in meta["content_type"]
        assert (tmp_path / f"{key}.html").exists()


def test_fr014_stops_host_at_first_403(tmp_path):
    requested: list[str] = []
    refresh(max_pages=50, client=make_client(requested), sleep=lambda s: None, cache_dir=tmp_path)
    global_requests = [u for u in requested if "www.getnet.net" in u]
    assert global_requests == ["https://www.getnet.net/en"]


def test_fr014_respects_max_pages(tmp_path):
    requested: list[str] = []
    n = refresh(max_pages=3, client=make_client(requested), sleep=lambda s: None,
                cache_dir=tmp_path)
    assert n == 3 and len(requested) == 3
    assert requested == START_PAGES[:3]
