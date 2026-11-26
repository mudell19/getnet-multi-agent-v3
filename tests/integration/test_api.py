from getnet_multi_agent.api import deps
from getnet_multi_agent.contracts import LLMUnavailable
from tests.integration.conftest import token

PAYLOAD = {"message": "When will the money from yesterday's sales be deposited?",
           "user_id": "cliente1988"}


def _chat(client, message, sub="cliente1988", **extra):
    return client.post("/chat", json={"message": message, "user_id": sub, **extra},
                       headers=token(sub))


def test_fr037_auth_401_403(client):
    assert client.post("/chat", json=PAYLOAD).status_code == 401
    assert client.post("/chat", json=PAYLOAD,
                       headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post("/chat", json=PAYLOAD, headers=token("cliente2000")).status_code == 403
    assert client.post("/chat", json=PAYLOAD,
                       headers=token("cliente1988", "operator")).status_code == 403
    assert client.get("/operator/tickets", headers=token("cliente1988")).status_code == 403


def test_fr049_chat_support_answer_shape(client):
    r = client.post("/chat", json=PAYLOAD, headers=token("cliente1988"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "answered" and body["route"].startswith("support")
    assert body["request_id"].startswith("r_") and body["conversation_id"].startswith("c_")
    assert body["trace"]["plan_revisions"][0]["action"] == "initial"


def test_fr029_card_number_refused_and_masked(client):
    r = _chat(client, "my card is 4111 1111 1111 1111, why was it declined?")
    body = r.json()
    assert body["status"] == "refused" and body["refusal_reason"] == "sensitive_data"
    assert body["trace"]["calls"] == []
    turns = client.get(f"/conversations/{body['conversation_id']}",
                       headers=token("cliente1988")).json()["turns"]
    assert "4111 1111 1111 1111" not in turns[0]["text"]


def test_fr029_other_merchant_refused(client):
    body = _chat(client, "show me the sales of cliente2000").json()
    assert body["refusal_reason"] == "other_merchant" and body["route"] == "refusal"


def test_fr040_conversation_of_another_principal_404(client):
    cid = _chat(client, "How does antecipação work?").json()["conversation_id"]
    r = _chat(client, "and how much is it?", sub="cliente2000", conversation_id=cid)
    assert r.status_code == 404
    assert client.get(f"/conversations/{cid}", headers=token("cliente2000")).status_code == 404


def test_fr043_conversation_turns_and_follow_up(client):
    cid = _chat(client, "How does antecipação work?").json()["conversation_id"]
    r = _chat(client, "and how much does it cost?", conversation_id=cid)
    assert r.status_code == 200
    turns = client.get(f"/conversations/{cid}", headers=token("cliente1988")).json()["turns"]
    assert [t["role"] for t in turns] == ["user", "assistant", "user", "assistant"]


def test_fr004_offline_terminal_adds_knowledge_step(client):
    body = _chat(client, "My card machine won't connect to the internet, what should I do?").json()
    assert body["route"] == "support>knowledge:rag", body
    actions = [p["action"] for p in body["trace"]["plan_revisions"]]
    assert "add" in actions


def test_fr044_fr046_fr047_human_in_the_loop(client):
    body = _chat(client, "I want to talk to a person").json()
    assert body["status"] == "awaiting_human" and body["route"] == "escalation"
    tid = body["ticket_id"]
    assert tid in body["answer"]
    op = token("operador1", "operator")
    listed = client.get("/operator/tickets?status=open", headers=op).json()
    assert any(t["id"] == tid for t in listed)
    assert client.post(f"/operator/tickets/{tid}/claim", headers=op).status_code == 200
    assert client.post(f"/operator/tickets/{tid}/claim",
                       headers=token("operador2", "operator")).status_code == 409
    r = client.post(f"/operator/tickets/{tid}/resolve", headers=op,
                    json={"action": "edit", "text": "Your deposit is confirmed for Friday."})
    assert r.status_code == 200, r.text
    turns = client.get(f"/conversations/{body['conversation_id']}",
                       headers=token("cliente1988")).json()["turns"]
    assert turns[-1]["role"] == "operator" and "Friday" in turns[-1]["text"]
    assert client.get("/operator/tickets?status=resolved", headers=op).json()[0]["id"] == tid


def test_fr051_llm_failure_still_valid_json_and_escalates(client):
    class Broken:
        def generate(self, **kw):
            raise LLMUnavailable("down")

        def embed(self, texts, task):
            raise LLMUnavailable("down")

    deps._override["llm"] = Broken()
    body = _chat(client, "How does antecipação work?").json()
    assert body["status"] == "awaiting_human" and body["ticket_id"]


def test_fr051_validation_errors_are_json(client):
    r = client.post("/chat", json={"user_id": "cliente1988"}, headers=token("cliente1988"))
    assert r.status_code == 422 and "detail" in r.json()
    r = _chat(client, "x" * 2001)
    assert r.status_code == 422


def test_fr052_retrieval_endpoint(client):
    r = client.get("/operator/retrieval?q=antecipação", headers=token("op", "operator"))
    assert r.status_code == 200 and r.json()[0]["rank"] == 1


def test_fr053_health_and_fr058_metrics(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    _chat(client, "How does antecipação work?")
    m = client.get("/metrics").text
    assert "getnet_requests_total" in m and "getnet_http_responses_total" in m
