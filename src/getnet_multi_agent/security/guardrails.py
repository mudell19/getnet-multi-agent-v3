"""Input guardrails run by code before any LLM call, with refusal texts in en and pt."""

from __future__ import annotations

import re
from dataclasses import dataclass

from getnet_multi_agent.contracts import Lang, Principal
from getnet_multi_agent.format.lang import detect_language
from getnet_multi_agent.security.dlp import find_cards, find_cpfs, other_merchant_ids

REFUSAL_TEXTS: dict[str, dict[str, str]] = {
    "sensitive_data": {
        "en": "I did not process your message because it contains a card number or a CPF. "
              "Please never share card numbers or CPF here. Send your question again without "
              "them and I will help you.",
        "pt": "Não processei sua mensagem porque ela contém um número de cartão ou um CPF. "
              "Por favor, nunca compartilhe números de cartão ou CPF aqui. Envie sua pergunta "
              "de novo sem esses dados e eu te ajudo.",
    },
    "other_merchant": {
        "en": "I can only help with your own account. Ask me about your own sales, "
              "receivables or machines and I will help you.",
        "pt": "Só posso ajudar com a sua própria conta. Pergunte sobre as suas vendas, "
              "recebimentos ou maquininhas e eu te ajudo.",
    },
    "prompt_injection": {
        "en": "I can only help with Getnet products and your account. Ask me about your "
              "sales, receivables, machines or Getnet products.",
        "pt": "Só posso ajudar com produtos Getnet e com a sua conta. Pergunte sobre suas "
              "vendas, recebimentos, maquininhas ou produtos Getnet.",
    },
    "out_of_scope": {
        "en": "I can only help with Getnet products and your account. You can ask me about "
              "your sales, receivables, machines, fees or Getnet products like Pix and payment links.",
        "pt": "Só posso ajudar com produtos Getnet e com a sua conta. Você pode perguntar sobre "
              "suas vendas, recebimentos, maquininhas, taxas ou produtos Getnet como Pix e link de pagamento.",
    },
    "unsafe": {
        "en": "I can't help with that request. You can ask me about your sales, receivables, "
              "machines or Getnet products.",
        "pt": "Não posso ajudar com esse pedido. Você pode perguntar sobre suas vendas, "
              "recebimentos, maquininhas ou produtos Getnet.",
    },
}

_INJECTION = re.compile(
    r"\b(?:ignore|disregard)\s+(?:all\s+)?(?:the\s+|your\s+)?(?:previous|above|prior)\s+instructions?"
    r"|\bignore\s+(?:suas|as|todas\s+as)\s+instru[cç][oõ]es"
    r"|\besque[cç]a\s+(?:as\s+|suas\s+)?instru[cç][oõ]es"
    r"|\bsystem\s+prompt\b|\bprompt\s+do\s+sistema\b"
    r"|\breveal\s+your\s+instructions\b|\brevele\s+suas\s+instru[cç][oõ]es"
    r"|\byou\s+are\s+now\b|\bagora\s+voc[eê]\s+[eé]\b"
    r"|\bact\s+as\b|\bfinja\s+que\b|\bjailbreak\b|\bdeveloper\s+mode\b",
    re.IGNORECASE,
)
_DAN = re.compile(r"\bDAN\b")


@dataclass
class GuardrailResult:
    refusal_reason: str | None
    language: Lang
    answer: str | None


def check_message(message: str, principal: Principal) -> GuardrailResult:
    lang = detect_language(message)
    reason = None
    if find_cards(message) or find_cpfs(message):
        reason = "sensitive_data"
    elif other_merchant_ids(message, principal.sub):
        reason = "other_merchant"
    elif _INJECTION.search(message) or _DAN.search(message):
        reason = "prompt_injection"
    return GuardrailResult(reason, lang, REFUSAL_TEXTS[reason][lang] if reason else None)
