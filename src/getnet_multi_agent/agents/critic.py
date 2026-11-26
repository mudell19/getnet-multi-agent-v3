"""Critic: deterministic rules first, then a lite-model completeness check."""

from __future__ import annotations

import re

from getnet_multi_agent.agents.prompts import critic as prompt
from getnet_multi_agent.contracts import LLM, CriticVerdict, Lang, Observation, Step, TraceCall
from getnet_multi_agent.rag.glossary import expand

# The site's troubleshooting text is in Portuguese, so the query is too, whatever the answer
# language; the knowledge agent still answers in the planned language.
CONNECTIVITY_QUERY = ("Chip Algar: como insiro o chip na máquina e faço o teste de comunicação "
                      "para a maquininha voltar a conectar")
_DECLINE = re.compile(r"declin|recus|negad|denied", re.I)
_CONNECT = re.compile(r"internet|connect|conect|conex|sinal|signal|offline|wi-?fi|chip|rede",
                      re.I)


def rules(executed: list[Observation], pending: list[Step], retried: set[str],
          lang: Lang, question: str = "") -> list[tuple[str, Step, str]]:
    """Returns (action, step, reason) with action in add | retry | drop."""
    actions: list[tuple[str, Step, str]] = []
    labels = {o.step.label() for o in executed} | {s.label() for s in pending}
    for o in executed:
        f = o.facts
        about_decline = bool(_DECLINE.search(question)) and not _CONNECT.search(question)
        if o.step.agent == "support" and (f.get("terminal_offline") or f.get("connectivity_error")):
            if "knowledge:rag" not in labels and not about_decline:
                step = Step(agent="knowledge", source="rag", query=CONNECTIVITY_QUERY,
                            reason="terminal offline or connectivity error")
                actions.append(("add", step, "support observed an offline terminal or a "
                                "connectivity error: add the site's troubleshooting steps"))
                labels.add("knowledge:rag")
        if o.step.agent == "support" and f.get("decline"):
            for s in pending:
                if s.agent == "knowledge" and _DECLINE.search(s.query):
                    actions.append(("drop", s, "a decline is answered by support alone from the "
                                    "tool's reason and suggested actions"))
        if o.status == "ungrounded" and o.step.agent == "knowledge" and o.step.query not in retried:
            aliases = " ".join(a for a in expand(o.step.query) if a.lower()
                               not in o.step.query.lower())
            q = (CONNECTIVITY_QUERY if _CONNECT.search(o.step.query)
                 else f"Getnet {o.step.query} {aliases}".strip())
            retried.add(o.step.query)
            retried.add(q)
            actions.append(("retry", Step(agent="knowledge", source=o.step.source, query=q,
                                          reason="retry with rewritten query"),
                            "no grounding: retry once with a rewritten query"))
    return actions


def check(llm: LLM, message: str, answers: list[str], today: str) -> tuple[CriticVerdict, TraceCall]:
    res = llm.generate(purpose="critic", role="router", system=prompt.SYSTEM.format(today=today),
                       contents=[prompt.user(message, answers)], schema=CriticVerdict)
    v = res.parsed if isinstance(res.parsed, CriticVerdict) else CriticVerdict(complete=False)
    return v, res.usage
