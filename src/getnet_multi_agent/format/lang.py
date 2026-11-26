"""Language detection by code (en or pt), shared by guardrails and quality checks."""

from __future__ import annotations

import re

from getnet_multi_agent.contracts import Lang

_PT = {
    "que", "não", "nao", "para", "com", "uma", "um", "minha", "meu", "minhas", "meus", "como",
    "quando", "quanto", "vendas", "maquininha", "dinheiro", "posso", "preciso", "está", "esta",
    "é", "por", "favor", "do", "da", "dos", "das", "no", "na", "em", "de", "o", "a", "os", "as",
    "e", "você", "voce", "seu", "sua", "qual", "quais", "tem", "ter", "pra", "receber", "conta",
    "obrigado", "olá", "ola", "oi", "também", "ainda", "mais", "isso", "esse", "essa", "aqui",
}
_EN = {
    "the", "what", "when", "how", "my", "is", "are", "do", "does", "can", "i", "to", "of", "and",
    "a", "an", "in", "on", "for", "with", "will", "be", "it", "this", "that", "you", "your", "me",
    "from", "sales", "money", "machine", "card", "need", "get", "today", "tomorrow", "which",
    "there", "please", "thanks", "hello", "hi", "should", "won't", "isn't", "about", "work",
}
_WORD = re.compile(r"[a-zà-ú']+", re.IGNORECASE)


def detect_language(text: str, default: Lang = "en") -> Lang:
    words = [w.lower() for w in _WORD.findall(text)]
    pt = sum(w in _PT for w in words) + 2 * len(re.findall(r"[ãõçáéíóúâêô]", text.lower()))
    en = sum(w in _EN for w in words)
    if pt == en:
        return default
    return "pt" if pt > en else "en"
