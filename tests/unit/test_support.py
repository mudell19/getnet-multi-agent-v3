import json
from datetime import date

from getnet_multi_agent.agents import support, tools
from getnet_multi_agent.contracts import LLMResult, Principal, Step, TraceCall
from tests.conftest import FakeLLM

P = Principal(sub="cliente1988", role="merchant", pseudonym="u_x")


def test_fr024_receivables_with_validated_period():
    r = tools.get_receivables(P, "yesterday")
    assert r.found and r.sales and all(s.settlement_date > s.sale_date for s in r.sales)
    assert tools.get_receivables(P, "2026-01-01").error


def test_fr025_terminal_status_flags():
    facts = tools.facts_from_terminals(tools.get_terminal_status(P))
    assert facts == {"terminal_offline": True, "connectivity_error": True, "decline": True}


def test_fr026_unknown_merchant_not_found():
    p = Principal(sub="cliente9999", role="merchant", pseudonym="u")
    assert not tools.get_receivables(p).found and not tools.get_terminal_status(p).found


def test_fr027_rendered_values_are_formatted_no_iso():
    out = json.dumps(tools.render_receivables(tools.get_receivables(P, "last_7_days"), "pt"),
                     ensure_ascii=False)
    assert "R$ 1.250,00" in out
    assert "-11-" not in out


def test_fr027_business_days():
    assert tools.add_business_days(date(2026, 11, 27), 2) == date(2026, 12, 1)


def test_fr056_fr028_tool_loop_uses_principal_not_model_args():
    usage = TraceCall(purpose="support")
    turns = [LLMResult(function_calls=[{"name": "get_terminal_status",
                                        "args": {"merchant_id": "cliente2000"}}],
                       content={"model": 1}, usage=usage),
             LLMResult(text="Your Caixa 1 machine is offline.", usage=usage)]
    llm = FakeLLM({"support": turns})
    r = support.run(llm, Step(agent="support", query="machine?"), P, "en", "T")
    assert r.observation.status == "answered" and r.observation.facts["terminal_offline"]
    sent = llm.calls[1]["contents"]
    assert sent[1] == {"model": 1}  # model content passed back whole
    assert "Caixa 1" in sent[2]["function_response"]["response"]["data"]
    assert "Mercearia" not in sent[2]["function_response"]["response"]["data"]
