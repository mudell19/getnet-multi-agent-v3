from getnet_multi_agent.contracts import (
    ChatRequest,
    ChatResponse,
    Plan,
    Step,
    Trace,
    hash_embed,
)
from getnet_multi_agent.format.lang import detect_language
from tests.conftest import FakeLLM


def test_fr001_plan_is_typed_with_steps_language_and_rewrite():
    p = Plan(steps=[Step(agent="knowledge", source="rag", query="q")], language="pt",
             standalone="quanto custa a Get Smart?")
    assert p.steps[0].label() == "knowledge:rag"
    assert Step(agent="support", query="x").label() == "support"
    assert Plan.model_validate_json(p.model_dump_json()) == p


def test_fr049_chat_request_and_response_shape():
    r = ChatRequest(message="hi", user_id="cliente1988")
    assert r.conversation_id is None
    resp = ChatResponse(answer="a", status="answered", route="support", conversation_id="c",
                        request_id="r")
    assert set(resp.model_dump()) >= {"answer", "status", "refusal_reason", "route", "sources",
                                      "ticket_id", "conversation_id", "request_id", "trace"}


def test_fr050_trace_has_revisions_observations_calls_totals():
    assert set(Trace().model_dump()) >= {"plan_revisions", "critic_notes", "observations",
                                         "calls", "total_tokens", "total_cost_usd"}


def test_fr001_fake_llm_returns_parsed_model():
    llm = FakeLLM({"plan": Plan(standalone="x")})
    out = llm.generate(purpose="plan", role="router", system="s", contents=["x"], schema=Plan)
    assert isinstance(out.parsed, Plan)
    assert len(hash_embed("abc")) == 768


def test_fr030_language_detection():
    assert detect_language("Quando vou receber o dinheiro das minhas vendas?") == "pt"
    assert detect_language("When will the money from yesterday's sales be deposited?") == "en"
