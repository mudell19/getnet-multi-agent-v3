"""FR-063, FR-064, FR-065, FR-067: runner code checks, held-out guard, judge schema, metrics."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evals import run
from evals.judge import JudgeVerdict, build_evidence


def _resp(**kw):
    base = {"answer": "", "status": "answered", "refusal_reason": None, "route": "knowledge:rag",
            "sources": [], "ticket_id": None, "conversation_id": "c_1", "request_id": "r_1",
            "trace": {"observations": [], "total_cost_usd": 0.001}}
    base.update(kw)
    return base


CASE = {"id": "x", "lang": "en", "category": "rag", "user_id": "cliente1988",
        "message": "How many installments with the crediário?", "expected_route": "knowledge:rag",
        "must_mention": ["up to 48"], "must_not": [],
        "source_url": "https://site.getnet.com.br/crediario", "must_contain": ["48"]}
GOOD = ("You can split a crediário sale into up to 48 installments, and the card issuer sets "
        "the limit and the rate.")


def test_fr063_code_checks_pass_on_good_response():
    resp = _resp(answer=GOOD, sources=[{"title": "Crediário",
                                        "url": "https://site.getnet.com.br/crediario/"}])
    ch = run.code_checks(CASE, resp, GOOD)
    assert ch["failures"] == []
    assert ch["route_ok"] and ch["status_ok"] and ch["source_ok"] and ch["has_sources"]


def test_fr063_code_checks_flag_route_source_literal_and_quality():
    bad = "**You** can split it into many installments — ask your bank."
    resp = _resp(answer=bad, route="knowledge:web",
                 sources=[{"url": "https://site.getnet.com.br/duvidas/pix"}])
    ch = run.code_checks(CASE, resp, bad)
    text = " ".join(ch["failures"])
    assert not ch["route_ok"] and not ch["source_ok"]
    assert "missing literal '48'" in text
    assert "dash" in ch["quality"] and "bold" in ch["quality"]


def test_fr063_refusal_reason_and_status_checked():
    case = {**CASE, "expected_route": "refusal", "expected_refusal_reason": "sensitive_data",
            "source_url": "", "must_contain": []}
    ok = run.code_checks(case, _resp(route="refusal", status="refused",
                                     refusal_reason="sensitive_data",
                                     answer="I can't handle card numbers here, please remove them."),
                         "I can't handle card numbers here, please remove them.")
    assert ok["refusal_ok"] and ok["failures"] == []
    wrong = run.code_checks(case, _resp(route="refusal", status="refused",
                                        refusal_reason="unsafe", answer="No."), "No.")
    assert not wrong["refusal_ok"]


def test_fr063_word_limit_and_language_checked():
    long = " ".join(["word"] * 170)
    ch = run.code_checks({**CASE, "source_url": "", "must_contain": []}, _resp(answer=long), long)
    assert any(q.startswith("words>") for q in ch["quality"])
    pt = "Você pode parcelar a venda em até 48 vezes no crediário com o emissor do cartão."
    ch = run.code_checks({**CASE, "source_url": "", "must_contain": []}, _resp(answer=pt), pt)
    assert "language_mismatch" in ch["quality"]


def test_fr063_auth_checks_by_http_status():
    assert run.auth_checks({"auth": "wrong_user"}, 403)["failures"] == []
    assert run.auth_checks({"auth": "no_token"}, 401)["refusal_ok"]
    assert run.auth_checks({"auth": "no_token"}, 200)["failures"]


def test_fr063_norm_url_and_expected_status():
    assert run.norm_url("HTTPS://Site.Getnet.com.br/pix/?a=1") == "https://site.getnet.com.br/pix"
    assert run.expected_status("refusal") == "refused"
    assert run.expected_status("escalation") == "awaiting_human"
    assert run.expected_status("support>knowledge:rag") == "answered"


def test_fr065_heldout_hash_mismatch_exits_2(tmp_path):
    data = tmp_path / "cases.jsonl"
    data.write_text('{"id": "a"}\n', encoding="utf-8")
    hash_file = tmp_path / "h.sha256"
    hash_file.write_text("0" * 64 + "  cases.jsonl\n", encoding="utf-8")
    assert run.main(["--heldout", str(data), "--hash-file", str(hash_file),
                     "--report", str(tmp_path / "r.md")]) == 2
    assert not (tmp_path / "r.md").exists()
    hash_file.write_text(run.sha256_file(data) + "  cases.jsonl\n", encoding="utf-8")
    assert run.heldout_ok(data, hash_file)


def test_fr064_judge_verdict_schema():
    v = JudgeVerdict.model_validate({
        "correctness": 5, "groundedness": 4, "relevance": 5, "helpfulness": 4, "clarity": 3,
        "items": [{"criterion": "up to 48", "kind": "must_mention", "passed": True,
                   "rationale": "states 48"}]})
    assert v.items[0].passed
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate({"correctness": 6, "groundedness": 4, "relevance": 5,
                                     "helpfulness": 4, "clarity": 3, "items": []})
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate({"correctness": 5, "groundedness": 4, "relevance": 5,
                                     "helpfulness": 4, "clarity": 3,
                                     "items": [{"criterion": "x", "kind": "maybe",
                                                "passed": True}]})


def test_fr064_evidence_marks_rag_tool_and_web():
    resp = _resp(trace={"observations": [{"evidence": [
        {"kind": "rag", "url": "https://site.getnet.com.br/crediario", "excerpt": "até 48"},
        {"kind": "tool", "title": "get_sales", "excerpt": "R$ 1.250,00"},
        {"kind": "web", "title": "Weather", "url": "https://weather.example/poa"}]}]},
        sources=[{"title": "Rates", "url": "https://rates.example/eur"}])
    ev = build_evidence(resp)
    assert "RAG https://site.getnet.com.br/crediario: até 48" in ev
    assert "[tool] get_sales: R$ 1.250,00" in ev
    assert "[web] Weather https://weather.example/poa" in ev
    assert "[web] Rates https://rates.example/eur" in ev


def _fake_judge(case, question, answer, evidence):
    return JudgeVerdict(correctness=5, groundedness=5, relevance=5, helpfulness=5, clarity=2,
                        items=[{"criterion": c, "kind": "must_mention", "passed": True,
                                "rationale": ""} for c in case["must_mention"]]), 0.0005


class _FakeHTTP:
    def __init__(self, resp):
        self.resp = resp

    def post(self, url, json=None, headers=None):
        return _R(200, self.resp)


class _R:
    def __init__(self, code, body):
        self.status_code, self.body = code, body

    def json(self):
        return self.body

    def raise_for_status(self):
        pass


def test_fr067_run_case_summary_thresholds_and_adjudication():
    resp = _resp(answer=GOOD, sources=[{"url": "https://site.getnet.com.br/crediario"}])
    row = run.run_case(_FakeHTTP(resp), CASE, {"cliente1988": "t"}, judge_fn=_fake_judge)
    assert row["error"] is None and run.row_passed(row)
    assert row["judge_cost_usd"] == 0.0005 and row["system_cost_usd"] == 0.001
    m = run.summarize([row])
    assert m["routing_accuracy"] == 1.0 and m["source_match_rate"] == 1.0
    assert m["citation_rate"] == 1.0 and m["must_mention_pass_rate"] == 1.0
    missed = run.missed_thresholds(m)
    assert missed == ["judge_clarity 2.000 < 4.0"]
    report = run.render_report([row], m, "test", missed, [])
    assert "Five lowest-clarity answers" in report and GOOD in report
    assert run.adjudication([row]) == []
