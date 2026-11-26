"""Knowledge agent: RAG over the Getnet snapshot, or Google Search grounding for general facts."""

from __future__ import annotations

import re
import time

from getnet_multi_agent.agents.prompts import knowledge as prompt
from getnet_multi_agent.contracts import (
    LLM,
    AgentResult,
    Evidence,
    Lang,
    Observation,
    Source,
    Step,
)
from getnet_multi_agent.rag import glossary

NO_ANSWER = "NO_ANSWER"
_TOK = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {t for t in _TOK.findall(text.lower()) if len(t) > 2 or t.isdigit()}


def _obs(step, status, answer, evidence, calls, t0, facts=None) -> Observation:
    return Observation(
        step=step, status=status, answer=answer, evidence=evidence, facts=facts or {},
        model=calls[-1].model if calls else "", latency_ms=int((time.monotonic() - t0) * 1000),
        tokens=sum(c.prompt_tokens + c.output_tokens + c.thinking_tokens for c in calls),
        cost_usd=sum(c.cost_usd for c in calls),
    )


def run_rag(llm: LLM, retriever, step: Step, lang: Lang, today: str) -> AgentResult:
    t0 = time.monotonic()
    hits = list(retriever.retrieve(step.query, mode="hybrid"))
    products = glossary.products_in(step.query)
    if len(products) >= 2:
        # Comparisons also need what each product does, described on the global site.
        names = " and ".join(" ".join(glossary.GROUPS[glossary.PRODUCTS[p]]) for p in products)
        seen = {h.chunk.id for h in hits}
        extra = retriever.retrieve(f"{names} POS: what each machine does, features", mode="hybrid")
        hits += [h for h in extra if h.chunk.id not in seen][:4]
    evidence = [Evidence(kind="rag", url=h.chunk.url, title=h.chunk.title, score=round(h.score, 3),
                         excerpt=h.chunk.text) for h in hits]
    if not hits:
        return AgentResult(observation=_obs(step, "ungrounded", "", [], [], t0))
    chunks = [(h.chunk.url, h.chunk.title, h.chunk.text) for h in hits]
    res = llm.generate(purpose="knowledge_rag", role="answer",
                       system=prompt.rag_system(today, lang),
                       contents=[prompt.rag_user(step.query, chunks)])
    answer = res.text.strip()
    if not answer or NO_ANSWER in answer:
        return AgentResult(observation=_obs(step, "ungrounded", "", evidence, [res.usage], t0),
                           calls=[res.usage])
    # Cite the pages whose text shares the most words and numbers with the answer.
    ans = _tokens(answer)
    ranked = sorted(hits, key=lambda h: len(ans & _tokens(h.chunk.text)), reverse=True)
    sources: list[Source] = []
    for h in ranked:
        if len(ans & _tokens(h.chunk.text)) < 3:
            continue
        if h.chunk.url not in {s.url for s in sources}:
            sources.append(Source(title=h.chunk.title, url=h.chunk.url))
        if len(sources) == 3:
            break
    if not sources:
        sources = [Source(title=hits[0].chunk.title, url=hits[0].chunk.url)]
    return AgentResult(observation=_obs(step, "answered", answer, evidence, [res.usage], t0),
                       sources=sources, calls=[res.usage])


def run_web(llm: LLM, step: Step, lang: Lang, today: str) -> AgentResult:
    t0 = time.monotonic()
    res = llm.generate(purpose="knowledge_web", role="answer",
                       system=prompt.web_system(today, lang), contents=[step.query], search=True)
    answer = res.text.strip()
    evidence = [Evidence(kind="web", url=s.url, title=s.title) for s in res.sources]
    status = "answered" if answer else "ungrounded"
    return AgentResult(observation=_obs(step, status, answer, evidence, [res.usage], t0),
                       sources=res.sources[:3], calls=[res.usage])
