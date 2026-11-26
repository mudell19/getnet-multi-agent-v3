"""LLM judge (FR-064): typed verdict per answered or escalated case, evidence from the same run."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CRITERIA = ("correctness", "groundedness", "relevance", "helpfulness", "clarity")


class JudgeItem(BaseModel):
    criterion: str
    kind: Literal["must_mention", "must_not"]
    passed: bool
    rationale: str = ""


class JudgeVerdict(BaseModel):
    correctness: int = Field(ge=1, le=5)
    groundedness: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    helpfulness: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    items: list[JudgeItem] = Field(default_factory=list)


SYSTEM = """You are a strict evaluator of a Getnet merchant support assistant.
Score the ANSWER from 1 (very poor) to 5 (excellent) on five criteria:
- correctness: facts agree with the EVIDENCE and the expected criteria.
- groundedness: every factual claim is supported by the EVIDENCE. [tool] lines are the merchant's
  own account data; RAG lines are excerpts from Getnet pages; [web] lines only carry the title and
  URL of a web source (page text is not available), so time-sensitive web facts (weather, exchange
  rates) are judged on being specific, dated and attributed to a named source.
- relevance: answers the merchant's question and nothing unrelated.
- helpfulness: the merchant can act on it (next step, value, date).
- clarity: written for a Brazilian merchant reading on a phone; the first sentence answers; short;
  one language only; no status dump or field-by-field listing; plain words.
Then rate each criterion in MUST_MENTION (passed = the answer states it) and each in MUST_NOT
(passed = the answer does NOT contain it), one item per criterion, copying the criterion text, with
a one-sentence rationale. Return only the JSON object."""


def build_evidence(response: dict[str, Any]) -> str:
    """Evidence lines from one /chat response trace: RAG excerpts, [tool] results, [web] sources."""
    lines: list[str] = []
    trace = response.get("trace") or {}
    for obs in trace.get("observations") or []:
        for ev in obs.get("evidence") or []:
            kind = ev.get("kind")
            if kind == "rag":
                lines.append(f"RAG {ev.get('url', '')}: {ev.get('excerpt', '')}")
            elif kind == "tool":
                lines.append(f"[tool] {ev.get('title', '')}: {ev.get('excerpt', '')}".strip())
            elif kind == "web":
                lines.append(f"[web] {ev.get('title', '')} {ev.get('url', '')}".strip())
    seen = {ln.split()[-1] for ln in lines if ln.startswith("[web]")}
    for src in response.get("sources") or []:
        url = src.get("url", "")
        if url and url not in seen and "getnet.com" not in url:
            lines.append(f"[web] {src.get('title', '')} {url}".strip())
            seen.add(url)
    return "\n".join(lines) or "(no evidence)"


def build_prompt(case: dict[str, Any], question: str, answer: str, evidence: str) -> str:
    mm = "\n".join(f"- {c}" for c in case.get("must_mention") or []) or "(none)"
    mn = "\n".join(f"- {c}" for c in case.get("must_not") or []) or "(none)"
    return (f"LANGUAGE EXPECTED: {case.get('lang', 'en')}\nQUESTION: {question}\n\n"
            f"EVIDENCE:\n{evidence}\n\nMUST_MENTION:\n{mm}\n\nMUST_NOT:\n{mn}\n\n"
            f"ANSWER:\n{answer}")


def judge(case: dict[str, Any], question: str, answer: str,
          evidence: str) -> tuple[JudgeVerdict, float]:
    """One judge call in a fresh request context. Returns the verdict and its cost in USD."""
    from getnet_multi_agent.core.context import request_context
    from getnet_multi_agent.core.llm import get_llm

    with request_context(budget=60000):
        res = get_llm().generate(
            purpose="judge", role="judge", system=SYSTEM,
            contents=[build_prompt(case, question, answer, evidence)], schema=JudgeVerdict,
        )
    verdict = res.parsed if isinstance(res.parsed, JudgeVerdict) else \
        JudgeVerdict.model_validate(res.parsed)
    return verdict, res.usage.cost_usd
