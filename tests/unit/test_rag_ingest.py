from __future__ import annotations

import hashlib
import json
import socket

import pytest

from getnet_multi_agent.core.settings import CACHE_DIR
from getnet_multi_agent.rag.chunk import normalize_url
from getnet_multi_agent.rag.ingest import ingest, load_cache
from getnet_multi_agent.rag.store import Store
from tests.conftest import FakeLLM

REQUIRED = [
    "https://site.getnet.com.br/duvidas",
    "https://site.getnet.com.br/crediario",
    "https://site.getnet.com.br/link-de-pagamento",
    "https://site.getnet.com.br/pix",
    "https://site.getnet.com.br/todas-as-maquininhas",
    "https://site.getnet.com.br/duvidas/antecipacao-de-vendas",
    "https://site.getnet.com.br/duvidas/get-tap",
    "https://site.getnet.com.br/duvidas/parcelado",
    "https://www.getnet.net/en/our-solutions/in-person-payments",
]


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("network access attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


class CountingLLM(FakeLLM):
    def __init__(self):
        super().__init__()
        self.batches: list[int] = []

    def embed(self, texts, task):
        assert task == "document"
        self.batches.append(len(texts))
        return super().embed(texts, task)


def test_fr012_cache_file_names_are_sha256_of_normalized_url():
    metas = sorted(CACHE_DIR.glob("*.json"))
    assert len(metas) >= 90
    for f in metas:
        meta = json.loads(f.read_text(encoding="utf-8"))
        assert {"url", "final_url", "status", "content_type"} <= set(meta)
        assert f.stem == hashlib.sha256(normalize_url(meta["url"]).encode()).hexdigest()


def test_fr011_load_cache_filters_and_dedupes(no_network):
    pages = load_cache()
    urls = [p.url for p in pages]
    assert len(urls) == len(set(urls))
    assert "https://site.getnet.com.br/fale-conosco" not in urls  # the 404
    for url in urls:
        assert url == normalize_url(url)
        if url.startswith("https://www.getnet.net"):
            assert url == "https://www.getnet.net/en" or url.startswith("https://www.getnet.net/en/")
    assert set(REQUIRED) <= set(urls)


def test_fr011_dedupes_by_visible_text(tmp_path):
    html = "<html><head><title>A</title></head><body><p>Mesmo texto visível aqui.</p></body></html>"
    for url in ["https://site.getnet.com.br/a", "https://site.getnet.com.br/b"]:
        key = hashlib.sha256(url.encode()).hexdigest()
        meta = {"url": url, "final_url": url, "status": 200, "content_type": "text/html"}
        (tmp_path / f"{key}.json").write_text(json.dumps(meta))
        (tmp_path / f"{key}.html").write_text(html)
    other = "https://example.com/x"
    key = hashlib.sha256(other.encode()).hexdigest()
    (tmp_path / f"{key}.json").write_text(json.dumps(
        {"url": other, "final_url": other, "status": 200, "content_type": "text/html"}))
    (tmp_path / f"{key}.html").write_text(html.replace("Mesmo", "Outro"))
    assert [p.url for p in load_cache(tmp_path)] == ["https://site.getnet.com.br/a"]


def test_fr013_fr022_ingest_indexes_required_pages_and_persists(tmp_path, no_network):
    llm = CountingLLM()
    store = Store(tmp_path / "chroma")
    n = ingest(llm=llm, store=store)
    assert n == store.count() > 500
    assert max(llm.batches) <= 50
    urls = {c.url for c in store.all_chunks()}
    assert set(REQUIRED) <= urls
    assert "https://site.getnet.com.br/fale-conosco" not in urls

    # Non-empty collection: no work on the next start, and data survives a reopen.
    reopened = Store(tmp_path / "chroma")
    again = CountingLLM()
    assert ingest(llm=again, store=reopened) == n
    assert again.batches == []
