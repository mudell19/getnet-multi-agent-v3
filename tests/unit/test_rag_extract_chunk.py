from __future__ import annotations

import hashlib

import pytest

from getnet_multi_agent.core.settings import CACHE_DIR
from getnet_multi_agent.rag import glossary
from getnet_multi_agent.rag.chunk import chunk_page, normalize_url
from getnet_multi_agent.rag.extract import extract_pages, parse
from getnet_multi_agent.rag.ingest import build_chunks, load_cache


def _html(url: str) -> str:
    key = hashlib.sha256(url.encode()).hexdigest()
    return (CACHE_DIR / f"{key}.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def chunks():
    return build_chunks(load_cache())


def test_fr015_drops_chrome_and_keeps_tables():
    html = """<html><head><title>T</title><style>.x{}</style></head><body>
    <header>Menu topo</header><nav>Links</nav><script>var a=1</script>
    <h2>Taxas</h2><p>Texto da seção sobre taxas da maquininha.</p>
    <table><tr><th>Plano</th><th>Taxa</th></tr><tr><td>Débito</td><td>1,69%</td></tr></table>
    <footer>Rodapé</footer></body></html>"""
    page = parse(html)
    text = page.visible_text()
    assert "Menu topo" not in text and "Links" not in text and "var a" not in text
    assert "Rodapé" not in text
    assert "Plano | Taxa\nDébito | 1,69%" in text
    assert page.title == "T"


def test_fr015_drops_text_repeated_in_30_percent_of_pages():
    pages = [f"<html><body><p>Já é cliente? Fale conosco</p><h2>Página {i}</h2>"
             f"<p>Conteúdo único número {i} desta página.</p></body></html>" for i in range(5)]
    out = extract_pages(pages)
    for i, page in enumerate(out):
        text = page.visible_text()
        assert "Fale conosco" not in text
        assert f"Conteúdo único número {i}" in text


def test_fr015_faq_question_and_answer_kept_from_duvidas_page():
    page = parse(_html("https://site.getnet.com.br/duvidas/crediario"))
    faqs = [b for b in page.blocks if b.kind == "faq"]
    assert any("Até quantas parcelas" in b.text and "emissor" in b.answer for b in faqs)


def test_fr016_faq_chunks_from_duvidas_crediario(chunks):
    faq = [c for c in chunks
           if c.url == "https://site.getnet.com.br/duvidas/crediario" and c.kind == "faq"]
    assert len(faq) >= 4
    assert all(c.text.split("\n")[0].endswith(c.heading) for c in faq)
    assert any("2 dias úteis" in c.text for c in faq)


def test_fr016_crediario_states_48_installments(chunks):
    # The 48x limit lives on /crediario; /duvidas/crediario says the issuer sets the limit.
    hits = [c for c in chunks if c.url == "https://site.getnet.com.br/crediario" and "48" in c.text]
    assert hits
    assert any(c.kind == "faq" and "parcelas" in c.text for c in chunks
               if c.url == "https://site.getnet.com.br/crediario")


def test_fr015_product_card_price_kept(chunks):
    hits = [c for c in chunks
            if c.url == "https://site.getnet.com.br/todas-as-maquininhas" and "129,90" in c.text]
    assert hits


def test_fr016_chunks_carry_url_title_heading_and_no_windows(chunks):
    for c in chunks:
        assert c.url == normalize_url(c.url) and c.title
        assert c.site in ("br", "global") and c.kind in ("faq", "section", "table")
        assert len(c.text) >= 40
        assert c.text.startswith(c.heading) or c.kind == "faq"
        assert c.id == hashlib.sha256(f"{c.url}{c.heading}{c.text}".encode()).hexdigest()[:16]
    assert len({c.id for c in chunks}) == len(chunks)


def test_fr016_long_sections_split_at_paragraphs():
    paras = "".join(f"<p>{'Parágrafo número %d com bastante texto. ' % i * 8}</p>" for i in range(12))
    page = parse(f"<html><head><title>T</title></head><body><h2>Seção</h2>{paras}</body></html>")
    out = chunk_page("https://site.getnet.com.br/x/", page)
    assert len(out) > 1
    assert all(c.text.startswith("Seção\n") and c.url == "https://site.getnet.com.br/x" for c in out)


def test_fr018_glossary_aliases_and_products():
    assert {"Get Clássica", "Get Classic"} <= set(glossary.expand("quanto custa a get classica?"))
    assert "Payment Link" in glossary.expand("Como uso o link de pagamento")
    assert "receivables advance" in glossary.expand("quero antecipação")
    assert "installments" in glossary.expand("até quantas parcelas")
    assert {"bank account", "domicílio bancário"} <= set(glossary.expand("mudar conta bancária"))
    assert "teste de comunicação" in glossary.expand("my POS has no connection")
    assert "social media" in glossary.expand("atendimento por WhatsApp")
    assert glossary.expand("smartphone") == []
    q = "What's the difference between the Get Clássica and the Get Smart?"
    assert glossary.products_in(q) == ["Get Clássica", "Get Smart"]
    assert glossary.products_in("pix e crediário") == ["Pix", "Crediário"]
