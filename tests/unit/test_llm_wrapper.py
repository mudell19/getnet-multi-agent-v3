"""FR-021, FR-054, FR-055: Gemini wrapper with a fake client, and the stub LLM."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from google.genai import errors, types
from pydantic import BaseModel

from getnet_multi_agent.contracts import (
    BudgetExceeded,
    CriticVerdict,
    LLMUnavailable,
    Plan,
    ToolSpec,
)
from getnet_multi_agent.core import llm as llm_mod
from getnet_multi_agent.core.context import current, request_context
from getnet_multi_agent.core.llm import GeminiLLM, get_llm, reset_llm
from getnet_multi_agent.core.settings import Settings
from getnet_multi_agent.core.stub import StubLLM


def resp(text="ok", prompt=100, cand=20, thoughts=None, queries=None, chunks=None, calls=None,
         parsed=None):
    gm = NS(grounding_chunks=chunks, web_search_queries=queries)
    content = types.Content(role="model", parts=[types.Part(text=text)])
    return NS(text=text, parsed=parsed, function_calls=calls,
              candidates=[NS(content=content, grounding_metadata=gm)],
              usage_metadata=NS(prompt_token_count=prompt, candidates_token_count=cand,
                                thoughts_token_count=thoughts))


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, **kw):
        self.calls.append(kw)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    def embed_content(self, **kw):
        self.calls.append(kw)
        n = len(kw["contents"])
        return NS(embeddings=[NS(values=[0.1] * 768) for _ in range(n)], metadata=None)


def make(outcomes=()):
    llm = GeminiLLM(Settings(_env_file=None, GEMINI_API_KEY="x"))
    llm._client = NS(models=FakeModels(outcomes))
    return llm


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(llm_mod, "RETRY_DELAY_S", 0)


def gen(llm, **kw):
    base = dict(purpose="t", role="answer", system="s", contents=["hi"])
    base.update(kw)
    return llm.generate(**base)


def test_fr055_cost_with_none_thoughts_and_search_queries():
    llm = make([resp(prompt=1_000_000, cand=1_000_000, thoughts=None, queries=["a", "b"])])
    r = gen(llm, search=True)
    # flash: 0.75 in + 3.75 out per M, plus 2 searches at 14 per 1K
    assert r.usage.cost_usd == pytest.approx(0.75 + 3.75 + 2 * 14 / 1000)
    assert r.usage.thinking_tokens == 0 and r.search_queries == 2
    cfg = llm._client.models.calls[0]["config"]
    assert cfg.tools[0].google_search is not None


def test_fr054_router_uses_lite_prices_and_thinking():
    llm = make([resp(prompt=1_000_000, cand=0, thoughts=1_000_000)])
    r = gen(llm, role="router")
    assert r.usage.model == "gemini-3.5-flash-lite"
    assert r.usage.cost_usd == pytest.approx(0.30 + 2.50)
    cfg = llm._client.models.calls[0]["config"]
    assert cfg.thinking_config.thinking_level.value == "MINIMAL"


def test_fr021_web_sources_from_grounding_chunks():
    chunks = [NS(web=NS(title="Clima", uri="https://redirect/1"))]
    r = gen(make([resp(chunks=chunks, queries=["q"])]), search=True)
    assert r.sources[0].title == "Clima" and r.sources[0].url == "https://redirect/1"


def test_fr055_budget_enforced_inside_request_context_only():
    llm = make([resp(prompt=500, cand=0), resp(), resp()])
    with request_context(budget=400) as ctx:
        gen(llm)
        assert ctx.tokens == 500 and len(ctx.calls) == 1 and ctx.cost_usd > 0
        with pytest.raises(BudgetExceeded):
            gen(llm)
    assert current() is None
    gen(llm)  # no context: no budget, nothing accumulates
    gen(llm)


def test_fr055_retry_once_on_429_then_success():
    llm = make([errors.APIError(429, {}), resp(text="done")])
    assert gen(llm).text == "done"
    assert len(llm._client.models.calls) == 2


def test_fr055_two_failures_raise_llm_unavailable():
    llm = make([errors.APIError(503, {}), errors.APIError(500, {})])
    with pytest.raises(LLMUnavailable):
        gen(llm)


def test_fr055_400_is_not_retried():
    llm = make([errors.APIError(400, {}), resp()])
    with pytest.raises(LLMUnavailable):
        gen(llm)
    assert len(llm._client.models.calls) == 1


def test_fr021_search_with_tools_or_schema_raises_value_error():
    tool = ToolSpec(name="f", description="d", parameters={"type": "object", "properties": {}})
    with pytest.raises(ValueError):
        gen(make(), search=True, tools=[tool])
    with pytest.raises(ValueError):
        gen(make(), search=True, schema=CriticVerdict)


def test_fr055_model_content_passed_back_unchanged_and_function_responses_merged():
    model_turn = types.Content(role="model", parts=[types.Part(text="x", thought_signature=b"sig")])
    tool = ToolSpec(name="get_sales", description="d",
                    parameters={"type": "object", "properties": {"day": {"type": "string"}}})
    llm = make([resp()])
    gen(llm, tools=[tool], contents=[
        "q", model_turn,
        {"function_response": {"name": "get_sales", "response": {"total": 1}}},
        {"function_response": {"name": "get_fees", "response": {"fee": 2}}},
    ])
    call = llm._client.models.calls[0]
    sent = call["contents"]
    assert sent[1] is model_turn
    assert len(sent) == 3 and len(sent[2].parts) == 2 and sent[2].role == "user"
    assert call["config"].automatic_function_calling.disable is True
    assert call["config"].tools[0].function_declarations[0].name == "get_sales"


def test_fr055_function_calls_and_schema_fallback():
    class Out(BaseModel):
        a: int

    calls = [NS(name="get_sales", args={"day": "today"})]
    r = gen(make([resp(calls=calls)]), tools=[ToolSpec(name="get_sales", description="d",
                                                       parameters={"type": "object"})])
    assert r.function_calls == [{"name": "get_sales", "args": {"day": "today"}}]
    r = gen(make([resp(text='{"a": 3}', parsed=None)]), schema=Out)
    assert r.parsed == Out(a=3)
    with pytest.raises(LLMUnavailable):
        gen(make([resp(text="not json", parsed=None)]), schema=Out)


def test_fr055_embed_one_content_per_text():
    llm = make()
    vecs = llm.embed(["a", "b", "c"], "document")
    call = llm._client.models.calls[0]
    assert len(vecs) == 3 and len(call["contents"]) == 3
    assert all(isinstance(c, types.Content) for c in call["contents"])
    assert call["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert call["config"].output_dimensionality == 768


def test_fr055_embed_count_mismatch_raises():
    llm = make()
    llm._client.models.embed_content = lambda **kw: NS(embeddings=[NS(values=[0.0])])
    with pytest.raises(LLMUnavailable):
        llm.embed(["a", "b"], "query")


def test_fr054_get_llm_stub_mode(monkeypatch):
    monkeypatch.setattr(llm_mod, "get_settings", lambda: Settings(_env_file=None, LLM_MODE="stub"))
    reset_llm()
    try:
        assert isinstance(get_llm(), StubLLM) and get_llm() is get_llm()
    finally:
        reset_llm()


@pytest.mark.parametrize("msg,expect", [
    ("Write me a poem", "refuse"),
    ("Quero falar com um atendente", "escalate"),
    ("Where is my money from yesterday's sales?", ["support"]),
    ("Qual a previsão do tempo em São Paulo?", ["knowledge:web"]),
    ("How does Pix work?", ["knowledge:rag"]),
    ("Minha maquininha não conecta, como funciona a antecipação?", ["support", "knowledge:rag"]),
])
def test_fr054_stub_plan_rules(msg, expect):
    r = StubLLM().generate(purpose="plan", role="router", system="", contents=[msg], schema=Plan)
    plan = r.parsed
    assert isinstance(plan, Plan) and plan.standalone == msg
    if expect == "refuse":
        assert plan.refusal_reason == "out_of_scope" and not plan.steps
    elif expect == "escalate":
        assert plan.escalate and plan.language == "pt"
    else:
        assert [s.label() for s in plan.steps] == expect


def test_fr054_stub_tools_then_text_from_data_block():
    stub = StubLLM()
    tool = ToolSpec(name="get_sales", description="d", parameters={"type": "object"})
    r = stub.generate(purpose="support", role="answer", system="", contents=["q"], tools=[tool])
    assert r.function_calls == [{"name": "get_sales", "args": {}}]
    r = stub.generate(purpose="support", role="answer", system="", tools=[tool], contents=[
        "q <data>  total   R$ 10 </data>", r.content,
        {"function_response": {"name": "get_sales", "response": {}}}])
    assert r.text == "total R$ 10" and not r.function_calls
    assert stub.generate(purpose="critic", role="router", system="", contents=["x"]).parsed.complete
    assert len(stub.embed(["a", "b"], "query")[1]) == 768
