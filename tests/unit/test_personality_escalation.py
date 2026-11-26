from getnet_multi_agent.agents import escalation, personality, synthesis
from getnet_multi_agent.contracts import Plan, RunCheckpoint
from getnet_multi_agent.state import tickets
from getnet_multi_agent.state.db import Database
from tests.conftest import FakeLLM


def test_fr008_personality_cannot_add_numbers_or_drop_ticket():
    draft = "Deposit of R$ 1,250.00 on 27 Nov 2026. Ticket t_1."
    llm = FakeLLM({"personality": "You get R$ 9,999.00 tomorrow."})
    out, v, _ = personality.rewrite(llm, "q", draft, "en", "T", ticket_id="t_1")
    assert out == draft and "personality_new_number" in v
    llm = FakeLLM({"personality": "Your R$ 1,250.00 arrives on 27 Nov 2026 (t_1)."})
    out, v, _ = personality.rewrite(llm, "q", draft, "en", "T", ticket_id="t_1")
    assert v == [] and out.startswith("Your")


def test_fr007_synthesis_merges_more_than_one_answer():
    text, usage = synthesis.merge(FakeLLM({"synthesis": "A and B"}), "q", ["A", "B"], "en", "T")
    assert text == "A and B" and usage is not None
    assert synthesis.merge(FakeLLM(), "q", ["A"], "en", "T") == ("A", None)


def test_fr044_escalation_opens_ticket_with_checkpoint(tmp_path):
    db = Database(tmp_path / "a.db")
    from getnet_multi_agent.state import conversations
    cid = conversations.create_conversation(db, "u")
    tid = escalation.escalate(db, cid, "r_1", RunCheckpoint(plan=Plan(standalone="q"), draft="d"),
                              "human_requested", "q")
    assert tickets.get_ticket(db, tid).status == "open"


def test_fr036_escalation_message_says_what_happens_next():
    assert "reply here" in escalation.message("en", "t_9", False)
    assert "nesta conversa" in escalation.message("pt", "t_9", True)
