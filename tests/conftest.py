"""Shared fixtures. FakeLLM is the scripted stand-in for the LLM wrapper in unit tests."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from getnet_multi_agent.contracts import LLMResult, TraceCall, hash_embed


class FakeLLM:
    """responses: purpose -> value | list of values (consumed in order) | callable(**kw).
    A value may be an LLMResult, a BaseModel (returned as parsed) or a str (returned as text)."""

    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = dict(responses or {})
        self.calls: list[dict[str, Any]] = []

    def generate(self, *, purpose, role, system, contents, schema=None, tools=None, search=False):
        kw = dict(purpose=purpose, role=role, system=system, contents=contents, schema=schema,
                  tools=tools, search=search)
        self.calls.append(kw)
        r = self.responses.get(purpose)
        if isinstance(r, list):
            r = r.pop(0) if r else None
        if callable(r) and not isinstance(r, type):
            r = r(**kw)
        usage = TraceCall(purpose=purpose, model=f"fake-{role}", prompt_tokens=10, output_tokens=5)
        if isinstance(r, LLMResult):
            return r
        if isinstance(r, BaseModel):
            return LLMResult(parsed=r, text=r.model_dump_json(), usage=usage)
        return LLMResult(text=r or "", usage=usage)

    def embed(self, texts, task):
        return [hash_embed(t) for t in texts]


@pytest.fixture
def fake_llm():
    return FakeLLM()
