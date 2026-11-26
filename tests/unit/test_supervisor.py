from getnet_multi_agent.contracts import (
    BudgetExceeded,
    CriticVerdict,
    LLMResult,
    Plan,
    Principal,
    Step,
    TraceCall,
)
from getnet_multi_agent.state.db import Database
from getnet_multi_agent.supervisor import Supervisor, excerpt
from tests.conftest import FakeLLM
from tests.integration.conftest import FakeRetriever

P = Principal(sub="cliente1988", role="merchant", pseudonym="u_x")


def _sup(llm, tmp_path, hits=None):
    from getnet_multi_agent.state import conversations
    db = Database(tmp_path / "s.db")
    cid = conversations.create_conversation(db, "u_x")
    return Supervisor(llm, lambda: FakeRetriever(hits), db), cid


def test_fr006_fr005_ungrounded_retry_then_partial_escalation(tmp_path, monkeypatch):
    monkeypatch.setenv("MAX_SUPERVISOR_ITERATIONS", "3")
    plan = Plan(steps=[Step(agent="support", query="deposits"),
                       Step(agent="knowledge", source="rag", query="pix account")],
                standalone="q")
    usage = TraceCall(purpose="s")
    llm = FakeLLM({"plan": plan,
                   "support": [LLMResult(text="R$ 1,250.00 on 27 Nov 2026.", usage=usage)],
                   "knowledge_rag": ["NO_ANSWER", "NO_ANSWER"],
                   "personality": lambda **kw: kw["contents"][0].split("<draft>")[1]
                   .split("</draft>")[0]})
    sup, cid = _sup(llm, tmp_path)
    r = sup.run("q", P, cid, "r_1", "", [], "T")
    assert r.status == "awaiting_human" and r.ticket_id
    assert "R$ 1,250.00" in r.answer and r.ticket_id in r.answer
    assert [p.action for p in r.trace.plan_revisions] == ["initial", "retry"]


def test_fr009_global_source_gets_brazil_caveat(tmp_path):
    from tests.integration.conftest import _Chunk, _Hit
    hits = [_Hit(_Chunk("https://www.getnet.net/en/our-solutions/in-person-payments",
                        "In-person", "Get Smart is the POS to make your business grow with "
                        "Android stock and cashier integrated."), 0.9)]
    llm = FakeLLM({"plan": Plan(steps=[Step(agent="knowledge", source="rag", query="smart")],
                                standalone="q"),
                   "knowledge_rag": "Get Smart runs Android with stock and cashier integrated.",
                   "critic": CriticVerdict(complete=True),
                   "personality": "Get Smart runs Android with stock and cashier integrated."})
    sup, cid = _sup(llm, tmp_path, hits)
    r = sup.run("q", P, cid, "r_1", "", [], "T")
    assert r.answer.endswith("may differ for Brazil.") and r.route == "knowledge:rag"


def test_fr050_excerpt_window_contains_cited_fact():
    text = "intro " * 200 + "parcelamento em até 48x no crediário " + "fim " * 200
    ex = excerpt(text, "Up to 48x with crediário")
    assert "48x" in ex and len(ex) <= 300


def test_fr033_fr035_answer_fixed_and_dlp(tmp_path):
    llm = FakeLLM({"plan": Plan(steps=[Step(agent="knowledge", source="rag", query="x")],
                                standalone="q"),
                   "knowledge_rag": "**Yes** — test 60 option 2 manutenção teste comunicação",
                   "critic": CriticVerdict(complete=True)})
    llm.responses["personality"] = llm.responses["knowledge_rag"]
    sup, cid = _sup(llm, tmp_path)
    r = sup.run("q", P, cid, "r_1", "", [], "T")
    assert "**" not in r.answer and "—" not in r.answer
    assert "dash" in r.trace.quality_violations


def test_fr006_budget_exceeded_escalates(tmp_path):
    def boom(**kw):
        raise BudgetExceeded()
    sup, cid = _sup(FakeLLM({"plan": boom}), tmp_path)
    r = sup.run("q", P, cid, "r_1", "", [], "T")
    assert r.status == "awaiting_human"
