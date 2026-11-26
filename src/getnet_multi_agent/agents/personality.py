"""Personality: the final answer in Getnet's voice, checked by code against the draft."""

from __future__ import annotations

import re

from getnet_multi_agent.agents.prompts import personality as prompt
from getnet_multi_agent.contracts import LLM, Lang, LLMUnavailable, TraceCall

_NUM = re.compile(r"\d+")
_URL = re.compile(r"https?://\S+")


def violations(draft: str, out: str, ticket_id: str | None) -> list[str]:
    v = []
    if not set(_NUM.findall(out)) <= set(_NUM.findall(draft)):
        v.append("personality_new_number")
    if not set(_URL.findall(out)) <= set(_URL.findall(draft)):
        v.append("personality_new_url")
    if ticket_id and ticket_id not in out:
        v.append("personality_dropped_ticket")
    if not out.strip():
        v.append("personality_empty")
    return v


def rewrite(llm: LLM, question: str, draft: str, lang: Lang, today: str,
            ticket_id: str | None = None) -> tuple[str, list[str], TraceCall | None]:
    """Returns (answer, violations, usage). On violation or failure the draft is returned."""
    try:
        res = llm.generate(purpose="personality", role="answer", system=prompt.system(today, lang),
                           contents=[prompt.user(question, draft)])
    except LLMUnavailable:
        return draft, ["personality_failed"], None
    out = res.text.strip()
    v = violations(draft, out, ticket_id)
    return (draft if v else out), v, res.usage
