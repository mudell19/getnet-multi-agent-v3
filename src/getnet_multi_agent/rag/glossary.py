"""Alias glossary (FR-018) and product names, matched case- and accent-insensitively."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

GROUPS: list[list[str]] = [
    ["Get Clássica", "Get Classica", "Get Classic"],
    ["Get Smart"],
    ["Get Mini"],
    ["Get Tap"],
    ["Link de Pagamento", "Payment Link", "link de pagamento"],
    ["antecipação", "antecipacao", "receivables advance", "advance", "antecipar"],
    ["crediário", "crediario", "parcelas", "parcelamento", "installments", "parcelado"],
    ["Pix"],
    ["conta bancária", "bank account", "conta de recebimento", "domicílio bancário",
     "domicilio bancario"],
    ["internet", "connection", "conexão", "conexao", "chip", "sinal", "wi-fi", "wifi",
     "teste de comunicação", "connect"],
    ["WhatsApp", "rede social", "redes sociais", "social media"],
]

# Canonical product name -> index in GROUPS.
PRODUCTS: dict[str, int] = {
    "Get Clássica": 0,
    "Get Smart": 1,
    "Get Mini": 2,
    "Get Tap": 3,
    "Link de Pagamento": 4,
    "Pix": 7,
    "Crediário": 6,
}


def norm(text: str) -> str:
    """Lowercase, accents removed, whitespace collapsed."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip()


@lru_cache(maxsize=None)
def _pattern(alias: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(norm(alias))}(?!\w)")


def contains(text_norm: str, alias: str) -> bool:
    """`text_norm` must already be passed through norm()."""
    return _pattern(alias).search(text_norm) is not None


def matched_groups(text: str) -> list[int]:
    t = norm(text)
    return [i for i, group in enumerate(GROUPS) if any(contains(t, a) for a in group)]


def expand(text: str) -> list[str]:
    """All aliases of every glossary group named in `text`."""
    out: list[str] = []
    for i in matched_groups(text):
        out.extend(a for a in GROUPS[i] if a not in out)
    return out


def products_in(text: str) -> list[str]:
    """Canonical names of the products named in `text`, in glossary order."""
    groups = set(matched_groups(text))
    return [name for name, i in PRODUCTS.items() if i in groups]


def strip_aliases(text: str, groups: list[int]) -> str:
    """`text` normalized with every alias of `groups` removed."""
    t = norm(text)
    for i in groups:
        for a in sorted(GROUPS[i], key=len, reverse=True):
            t = _pattern(a).sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()
