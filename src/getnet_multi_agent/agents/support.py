"""Customer Support agent: function-calling loop over the merchant's own data."""

from __future__ import annotations

import json
import time

from getnet_multi_agent.agents import tools
from getnet_multi_agent.agents.prompts import support as prompt
from getnet_multi_agent.contracts import (
    LLM,
    AgentResult,
    Evidence,
    Lang,
    Observation,
    Principal,
    Step,
)
from getnet_multi_agent.core.settings import get_settings


def run(llm: LLM, step: Step, principal: Principal, lang: Lang, today: str) -> AgentResult:
    t0 = time.monotonic()
    contents: list = [step.query]
    evidence: list[Evidence] = []
    facts: dict = {}
    calls = []
    found = True
    answer = ""
    for _ in range(get_settings().MAX_TOOL_ITERATIONS + 1):
        res = llm.generate(purpose="support", role="answer", system=prompt.system(today, lang),
                           contents=contents, tools=tools.TOOL_SPECS)
        calls.append(res.usage)
        if not res.function_calls:
            answer = res.text.strip()
            break
        contents.append(res.content)
        for fc in res.function_calls:
            # The merchant id comes from the authenticated principal, never from model args.
            if fc["name"] == "get_receivables":
                r = tools.get_receivables(principal, fc.get("args", {}).get("period", "upcoming"))
                found = found and r.found
                data = tools.render_receivables(r, lang)
            elif fc["name"] == "get_terminal_status":
                r = tools.get_terminal_status(principal)
                found = found and r.found
                facts.update(tools.facts_from_terminals(r))
                data = tools.render_terminals(r, lang)
            else:
                data = {"error": "unknown tool"}
            text = json.dumps(data, ensure_ascii=False)
            evidence.append(Evidence(kind="tool", title=fc["name"], excerpt=text[:1200]))
            contents.append({"function_response": {"name": fc["name"],
                                                   "response": {"data": text}}})
    status = "answered" if answer else "failed"
    if not found:
        status = "not_found" if answer else "failed"
    obs = Observation(
        step=step, status=status, answer=answer, evidence=evidence, facts=facts,
        model=calls[-1].model if calls else "", latency_ms=int((time.monotonic() - t0) * 1000),
        tokens=sum(c.prompt_tokens + c.output_tokens + c.thinking_tokens for c in calls),
        cost_usd=sum(c.cost_usd for c in calls),
    )
    return AgentResult(observation=obs, calls=calls)
