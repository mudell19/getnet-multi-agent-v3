"""Router agent: typed plan with steps, language and standalone rewrite."""

from __future__ import annotations

from getnet_multi_agent.agents.prompts import router as prompt
from getnet_multi_agent.contracts import LLM, LLMUnavailable, Plan, TraceCall


def plan(llm: LLM, message: str, summary: str, turns: list[dict],
         today: str) -> tuple[Plan, TraceCall]:
    res = llm.generate(purpose="plan", role="router", system=prompt.SYSTEM.format(today=today),
                       contents=[prompt.user(message, summary, turns)], schema=Plan)
    p = res.parsed
    if not isinstance(p, Plan):
        raise LLMUnavailable("router returned no valid plan")
    if not p.standalone:
        p.standalone = message
    for s in p.steps:
        if s.agent == "knowledge" and s.source is None:
            s.source = "rag"
        if s.agent == "support":
            s.source = None
    return p, res.usage
