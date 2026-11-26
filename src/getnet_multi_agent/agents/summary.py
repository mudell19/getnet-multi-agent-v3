"""Rolling conversation summary written by the lite model."""

from __future__ import annotations

from getnet_multi_agent.agents.prompts import summary as prompt
from getnet_multi_agent.contracts import LLM


def summarize(llm: LLM, previous: str, turns: list[dict], today: str) -> str:
    res = llm.generate(purpose="summary", role="router", system=prompt.SYSTEM.format(today=today),
                       contents=[prompt.user(previous, turns)])
    return res.text.strip() or previous
