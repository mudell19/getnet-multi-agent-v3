"""FR-061, FR-062, FR-066: eval datasets parse with the required keys and coverage."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from evals.run import load_jsonl

ROOT = Path(__file__).resolve().parents[2]
ROUTES = {"support", "knowledge:rag", "knowledge:web", "support>knowledge:rag", "refusal",
          "escalation"}
REASONS = {"sensitive_data", "other_merchant", "prompt_injection", "unsafe", "out_of_scope"}
REQUIRED = {"id", "lang", "category", "user_id", "message", "expected_route", "must_mention",
            "must_not", "source_url"}
OFFICIAL = [
    "What's the difference between the Get Clássica and the Get Smart?",
    "What's the weather forecast in Porto Alegre tomorrow?",
    "When will the money from yesterday's sales be deposited?",
    "Do I need a bank account to receive my sales via Pix?",
    "My card machine won't connect to the internet, what should I do?",
    "How does receivables advance (antecipação) work with Getnet?",
    "What's the euro exchange rate today?",
    "My card machine is showing a transaction decline error.",
    "How many installments can I split a sale into with the crediário?",
    "Can I sell through WhatsApp using the Payment Link?",
]


def _cases():
    return load_jsonl(ROOT / "evals" / "dataset.jsonl")


def test_fr061_dataset_required_keys_and_vocabulary():
    cases = _cases()
    assert 35 <= len(cases) <= 60
    assert len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        assert REQUIRED <= c.keys(), c["id"]
        assert c["lang"] in ("en", "pt")
        assert isinstance(c["must_mention"], list) and isinstance(c["must_not"], list)
        if c["category"] == "auth":
            assert c["auth"] in ("wrong_user", "no_token")
            continue
        assert c["expected_route"] in ROUTES, c["id"]
        if c["expected_route"] == "refusal":
            assert c["expected_refusal_reason"] in REASONS
        for a in c.get("operator_actions") or []:
            assert a["action"] in ("approve", "edit", "reject")
            if a["action"] in ("edit", "reject"):
                assert a["text"]
        if c["source_url"]:
            assert c["source_url"].startswith("https://site.getnet.com.br/")


def test_fr061_ten_official_scenarios_present():
    by_msg = {c["message"]: c for c in _cases()}
    for msg in OFFICIAL:
        assert msg in by_msg, msg
        assert by_msg[msg]["user_id"] == "cliente1988" and by_msg[msg]["lang"] == "en"
    assert sum(c["category"] == "official" for c in _cases()) == 10


def test_fr062_portuguese_and_category_coverage():
    cases = _cases()
    assert sum(c["lang"] == "pt" for c in cases) >= 10
    cats = Counter(c["category"] for c in cases)
    for cat in ("official", "adversarial", "auth", "memory", "hitl", "compound"):
        assert cats[cat] >= 1, cat
    reasons = {c.get("expected_refusal_reason") for c in cases}
    assert REASONS <= reasons
    assert {c["auth"] for c in cases if c["category"] == "auth"} == {"wrong_user", "no_token"}
    assert {a["action"] for c in cases for a in c.get("operator_actions") or []} == {
        "approve", "edit", "reject"}
    assert any(c.get("turns") and c["lang"] == "pt" for c in cases)
    assert any(c["user_id"] == "cliente2000" and c["expected_route"] == "support" for c in cases)


def test_fr066_retrieval_set_keys():
    rows = load_jsonl(ROOT / "evals" / "retrieval.jsonl")
    assert len(rows) >= 14
    assert {r["lang"] for r in rows} == {"en", "pt"}
    for r in rows:
        assert {"id", "lang", "query", "relevant_urls", "expected_fact"} <= r.keys()
        assert r["relevant_urls"] and r["expected_fact"]
        for u in r["relevant_urls"]:
            assert u.startswith("https://") and not u.endswith("/")
