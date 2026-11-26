"""Synthesis: one draft that keeps every answered part."""

from __future__ import annotations

from getnet_multi_agent.agents.prompts import synthesis as prompt
from getnet_multi_agent.contracts import LLM, Lang, TraceCall


def merge(llm: LLM, question: str, answers: list[str], lang: Lang,
          today: str) -> tuple[str, TraceCall | None]:
    if len(answers) == 1:
        return answers[0], None
    res = llm.generate(purpose="synthesis", role="answer", system=prompt.system(today, lang),
                       contents=[prompt.user(question, answers)])
    text = res.text.strip()
    return (text or "\n\n".join(answers)), res.usage
