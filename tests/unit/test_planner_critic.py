import pytest

from getnet_multi_agent.agents import critic, planner
from getnet_multi_agent.contracts import CriticVerdict, LLMUnavailable, Observation, Plan, Step
from tests.conftest import FakeLLM


def test_fr001_planner_returns_typed_plan_with_rewrite():
    p = Plan(steps=[Step(agent="knowledge", query="q")], language="pt", standalone="")
    out, usage = planner.plan(FakeLLM({"plan": p}), "e quanto custa?", "", [], "T")
    assert out.steps[0].source == "rag" and out.standalone == "e quanto custa?"


def test_fr042_planner_receives_summary_and_turns():
    llm = FakeLLM({"plan": Plan(standalone="x")})
    planner.plan(llm, "and how much is it?", "talked about Get Smart",
                 [{"role": "user", "text": "what is Get Smart?"}], "T")
    content = llm.calls[0]["contents"][0]
    assert "Get Smart" in content and "<conversation>" in content


def test_fr001_invalid_plan_raises():
    with pytest.raises(LLMUnavailable):
        planner.plan(FakeLLM({"plan": "not json"}), "x", "", [], "T")


def _obs(step, status="answered", **facts):
    return Observation(step=step, status=status, answer="a", facts=facts)


def test_fr004_offline_terminal_adds_rag_step():
    s = Step(agent="support", query="q")
    acts = critic.rules([_obs(s, terminal_offline=True)], [], set(), "en")
    assert acts[0][0] == "add" and acts[0][1].label() == "knowledge:rag"


def test_fr004_decline_drops_knowledge_step_about_decline():
    s = Step(agent="support", query="q")
    pending = [Step(agent="knowledge", source="rag", query="why was the transaction declined")]
    acts = critic.rules([_obs(s, decline=True)], pending, set(), "en")
    assert ("drop", pending[0]) == acts[0][:2]


def test_fr005_ungrounded_retried_once():
    s = Step(agent="knowledge", source="rag", query="pix bank account")
    retried: set[str] = set()
    first = critic.rules([_obs(s, "ungrounded")], [], retried, "en")
    assert first[0][0] == "retry"
    retry_obs = _obs(first[0][1], "ungrounded")
    assert critic.rules([_obs(s, "ungrounded"), retry_obs], [], retried, "en") == []


def test_fr003_lite_check_parses_verdict():
    v, _ = critic.check(FakeLLM({"critic": CriticVerdict(complete=False, unanswered=["b"])}),
                        "a and b", ["a"], "T")
    assert v.unanswered == ["b"]


def test_fr032_router_refusal_reason_is_typed():
    assert Plan(refusal_reason="out_of_scope").refusal_reason == "out_of_scope"
