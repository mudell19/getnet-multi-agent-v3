"""FR-066: retrieval metric math on small examples."""

from __future__ import annotations

import math

import pytest

from evals.retrieval import (
    context_precision,
    context_recall,
    hit_at_k,
    mrr,
    ndcg_at_k,
    recall_at_k,
    score_query,
)

A, B, C, D = (f"https://site.getnet.com.br/{p}" for p in ("a", "b", "c", "d"))


def test_fr066_hit_recall_mrr():
    ranked = [C, A, A, D, B]
    assert hit_at_k(ranked, {A}, 5) == 1.0
    assert hit_at_k(ranked, {A}, 1) == 0.0
    assert recall_at_k(ranked, {A, B}, 5) == 1.0
    assert recall_at_k(ranked, {A, B}, 3) == 0.5
    assert mrr(ranked, {A, B}, 5) == 0.5
    assert mrr(ranked, {"https://x"}, 5) == 0.0


def test_fr066_ndcg_counts_each_relevant_url_once():
    assert ndcg_at_k([A, B, C], {A, B}, 3) == pytest.approx(1.0)
    expected = (1 / math.log2(3)) / (1 + 1 / math.log2(3))
    assert ndcg_at_k([C, A, A], {A, B}, 3) == pytest.approx(expected)
    assert ndcg_at_k([C, D], {A}, 2) == 0.0


def test_fr066_context_precision_and_recall():
    assert context_precision([A, C, A, D], {A}, 4) == 0.5
    assert context_precision([], {A}, 5) == 0.0
    assert context_recall(["nada aqui", "Faça o Teste de Comunicação"], "teste de comunicação",
                          5) == 1.0
    assert context_recall(["nada aqui"], "48", 5) == 0.0


def test_fr066_score_query_normalizes_urls():
    hits = [{"url": "https://site.getnet.com.br/crediario/", "text": "em até 48 parcelas"},
            {"url": "https://site.getnet.com.br/pix", "text": "chave"}]
    s = score_query(hits, ["https://site.getnet.com.br/crediario"], "48", 5)
    assert s["hit"] == 1.0 and s["mrr"] == 1.0 and s["context_recall"] == 1.0
    assert s["context_precision"] == 0.5
