"""Deterministic LLM for LLM_MODE=stub and tests: keyword planner, canned outputs, hash embeddings."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel

from getnet_multi_agent.contracts import (
    CriticVerdict,
    LLMResult,
    LLMRole,
    Plan,
    Step,
    ToolSpec,
    TraceCall,
    hash_embed,
)
from getnet_multi_agent.core.llm import check_budget, record_call
from getnet_multi_agent.format.lang import detect_language

_REFUSE = re.compile(r"\b(?:poems?|poemas?|jokes?|piadas?|games?|jogos?)\b")
_ESCALATE = re.compile(r"talk to a person|falar com um atendente|\bhumano\b|\bhuman\b")
_SUPPORT = ("sales", "vendas", "deposit", "receb", "money", "dinheiro", "machine", "maquininha",
            "terminal", "decline", "recusad", "connect", "conect", "internet")
_WEB = ("weather", "previsão", "clima", "exchange", "câmbio", "cotação", "euro", "dólar",
        "dollar", "news", "notícia")
_RAG = ("how does", "como funciona", "antecipação", "advance", "pix", "crediário", "installments",
        "parcel", "link", "whatsapp", "get smart", "get clássica")
_BLOCK = re.compile(r"<(draft|data)>(.*?)</\1>", re.DOTALL)


def _last_text(contents: list[Any]) -> str:
    return next((c for c in reversed(contents) if isinstance(c, str)), "")


def stub_plan(message: str) -> Plan:
    low = message.lower()
    plan = Plan(language=detect_language(message), standalone=message)
    if _REFUSE.search(low):
        plan.refusal_reason = "out_of_scope"
        return plan
    if _ESCALATE.search(low):
        plan.escalate = True
        return plan
    if any(k in low for k in _SUPPORT):
        plan.steps.append(Step(agent="support", query=message, reason="account data"))
    if any(k in low for k in _WEB):
        plan.steps.append(Step(agent="knowledge", source="web", query=message, reason="live facts"))
    if not plan.steps or any(k in low for k in _RAG):
        plan.steps.append(Step(agent="knowledge", source="rag", query=message, reason="product docs"))
    return plan


class StubLLM:
    def generate(
        self,
        *,
        purpose: str,
        role: LLMRole,
        system: str,
        contents: list[Any],
        schema: type[BaseModel] | None = None,
        tools: list[ToolSpec] | None = None,
        search: bool = False,
    ) -> LLMResult:
        if search and (tools or schema):
            raise ValueError("search grounding cannot share a request with tools or schema")
        check_budget()
        message = _last_text(contents)
        parsed: Any = None
        calls: list[dict[str, Any]] = []
        content: Any = None
        text = ""
        if purpose == "plan":
            parsed = stub_plan(message)
        elif purpose == "critic":
            parsed = CriticVerdict(complete=True)
        elif schema is not None:
            try:
                parsed = schema()
            except Exception:  # noqa: BLE001 - schema without defaults
                parsed = None
        elif tools and not any(isinstance(c, dict) and "function_response" in c for c in contents):
            calls = [{"name": t.name, "args": {}} for t in tools]
            content = {"stub_model_turn": calls}
        else:
            blocks = _BLOCK.findall(message)
            text = " ".join(blocks[-1][1].split())[:600] if blocks else "Stub answer."
        if parsed is not None:
            text = parsed.model_dump_json()
        usage = TraceCall(purpose=purpose, model="stub", prompt_tokens=10 + len(message) // 4,
                          output_tokens=5 + len(text) // 4)
        record_call(usage)
        return LLMResult(text=text, parsed=parsed, function_calls=calls, content=content,
                         usage=usage)

    def embed(self, texts: list[str], task: Literal["document", "query"]) -> list[list[float]]:
        return [hash_embed(t) for t in texts]
