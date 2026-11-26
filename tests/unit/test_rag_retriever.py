from __future__ import annotations

import pytest

from getnet_multi_agent.core.settings import Settings
from getnet_multi_agent.rag.chunk import Chunk
from getnet_multi_agent.rag.ingest import ingest
from getnet_multi_agent.rag.retriever import Retriever
from getnet_multi_agent.rag.store import Store
from tests.conftest import FakeLLM


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    s = Store(tmp_path_factory.mktemp("kb") / "chroma")
    ingest(llm=FakeLLM(), store=s)
    return s


@pytest.fixture
def settings():
    return Settings(_env_file=None, RAG_MIN_SIMILARITY=0.05, RAG_TOP_K=6)


def test_fr020_comparison_retrieves_both_product_sources(store, settings):
    r = Retriever(store=store, llm=FakeLLM(), settings=settings)
    hits = r.retrieve("What's the difference between the Get Clássica and the Get Smart?")
    urls = {h.chunk.url for h in hits}
    assert "https://www.getnet.net/en/our-solutions/in-person-payments" in urls
    assert "https://site.getnet.com.br/todas-as-maquininhas" in urls
    assert len(hits) == 6
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_fr017_vector_mode_respects_threshold_and_top_k(store):
    high = Settings(_env_file=None, RAG_MIN_SIMILARITY=0.99)
    assert Retriever(store=store, llm=FakeLLM(), settings=high).retrieve(
        "taxa crediário", mode="vector") == []
    low = Settings(_env_file=None, RAG_MIN_SIMILARITY=0.0, RAG_TOP_K=6)
    hits = Retriever(store=store, llm=FakeLLM(), settings=low).retrieve(
        "taxa crediário", mode="vector")
    assert len(hits) == 6
    assert all(h.score == h.vector_score and 0 <= h.score <= 1 for h in hits)


def test_fr017_hybrid_uses_glossary_aliases(store, settings):
    r = Retriever(store=store, llm=FakeLLM(), settings=settings)
    hits = r.retrieve("How do I use the Payment Link?", k=4)
    assert hits and all(h.lexical_score > 0 for h in hits)
    assert any("link de pagamento" in h.chunk.text.lower() for h in hits)


def test_fr019_rule_chunk_ranks_above_mention(tmp_path, settings):
    s = Store(tmp_path / "chroma")
    mention = Chunk("a" * 16, "https://site.getnet.com.br/a", "A", "Pix", "br", "section",
                    "Pix\nO Pix chegou na maquininha Getnet para seus clientes.")
    rule = Chunk("b" * 16, "https://site.getnet.com.br/b", "B", "Pix", "br", "section",
                 "Pix\nPara usar o Pix é necessário ter a Get Conta ativa na maquininha.")
    llm = FakeLLM()
    s.add([mention, rule], llm.embed([mention.text, rule.text], "document"))
    hits = Retriever(store=s, llm=llm, settings=settings).retrieve("Pix na maquininha")
    assert [h.chunk.id for h in hits][0] == rule.id
