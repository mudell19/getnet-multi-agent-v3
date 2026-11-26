"""Documentation coverage: README sections (FR-074) and threat model (FR-075)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _headings(text: str) -> list[str]:
    return [m.group(1).strip().lower() for m in re.finditer(r"^#{1,6}\s+(.+)$", text, re.M)]


def test_fr074_readme_has_required_sections():
    readme = _read("README.md")
    low = " ".join(readme.lower().split())
    headings = _headings(readme)

    required_headings = [
        "quick start", "configuration", "run and test", "architecture", "supervisor loop",
        "message workflow", "rag pipeline", "tools", "identity, memory and human in the loop",
        "testing strategy", "evaluation", "observability", "ci", "security", "known limits",
        "not built in this session",
    ]
    missing = [h for h in required_headings if not any(h in x for x in headings)]
    assert not missing, f"README missing sections: {missing}"

    assert "![agent workflow](docs/agent-workflow.png)" in low
    assert (ROOT / "docs" / "agent-workflow.png").exists()
    assert "docs/threat-model.md" in readme
    assert "—" not in readme and "–" not in readme, "no em or en dashes"

    keywords = {
        "quick start": ["cp .env.example .env", "docker compose up --build --wait",
                        "getnet-multi-agent token --sub cliente1988 --role merchant",
                        "post", "/chat", "docker build -t getnet-multi-agent .",
                        "docker run --env-file .env", "llm_mode=stub"],
        "configuration": ["gemini_model_thinking", "price_flash_input_per_m", "jwt_secret",
                          "pseudonym_key", "request_token_budget", "max_supervisor_iterations"],
        "run and test": ["uv sync --frozen", "uv run pytest", "uv run ruff check .", "promtool"],
        "architecture": ["router", "knowledge", "customer support", "get_receivables",
                         "get_terminal_status", "human escalation", "critic", "synthesis",
                         "personality", "plain python"],
        "supervisor": ["observation", "knowledge:rag", "decline", "retried once",
                       "completeness", "budget", "ticket id", "brazil", "dlp"],
        "workflow": ["guardrails before any llm", "masked", "request_id", "trace"],
        "rag": ["ingestion", "storage", "retrieval", "generation", "30%", "cosine", "768",
                "retrieval_document", "glossary", "no_answer", "refresh"],
        "tools": ["function calling", "thought signatures", "google search grounding"],
        "hitl": ["conversation_id", "/conversations/", "--role operator", "/claim", "/resolve",
                 "approve", "edit", "reject", "409"],
        "testing": ["fakellm", "testclient", "stub"],
        "evaluation": ["judge", "clarity", "calibrat", "hit@k", "vector-only", "held-out",
                       "heldout.sha256"],
        "observability": ["request_id", "app_rev", "/metrics", "alerts",
                          "docker compose --profile observability up -d", "3000", "9090"],
        "ci": ["ci.yml", "live-eval.yml", "sessao-*"],
        "limits": ["sqlite", "chroma", "postgres", "hs256", "rs256", "jwks",
                   "same family", "data/crawl_cache", "november 2026", "paid-tier",
                   "simulated"],
    }
    missing_kw = {k: [w for w in ws if w not in low] for k, ws in keywords.items()}
    missing_kw = {k: v for k, v in missing_kw.items() if v}
    assert not missing_kw, f"README missing keywords: {missing_kw}"


def test_fr075_threat_model_lists_threats_and_controls():
    doc = _read("docs/threat-model.md")
    low = " ".join(doc.lower().split())
    headings = _headings(doc)
    for h in ("assets", "actors", "threats and controls", "residual risks"):
        assert any(h in x for x in headings), f"threat model missing section {h!r}"

    for asset in ("merchant data", "tokens", "secrets", "knowledge base integrity", "llm budget"):
        assert asset in low, asset
    for actor in ("merchant", "operator", "external attacker", "malicious content"):
        assert actor in low, actor

    # Each threat row must name its control.
    threats = {
        "cross-merchant data leakage": ["principal", "other_merchant", "pseudonym", "404"],
        "direct prompt injection": ["english and portuguese", "router"],
        "indirect injection": ["<data>", "never to follow", "dlp"],
        "sensitive data": ["luhn", "cpf", "masked"],
        "token misuse": ["hs256", "iss", "aud", "exp", "role", "cli"],
        "cost abuse": ["request_token_budget", "max_message_chars", "max_tool_iterations",
                       "max_supervisor_iterations", "cost"],
        "hallucination": ["no_answer", "escalat", "personality"],
        "operator misuse": ["409", "audit"],
    }
    rows = [line.lower() for line in doc.splitlines() if line.startswith("|")]
    for threat, controls in threats.items():
        row = next((r for r in rows if r.startswith(f"| {threat}")), None)
        assert row is not None, f"threat model missing threat {threat!r}"
        missing = [c for c in controls if c not in row]
        assert not missing, f"{threat}: controls not stated {missing}"
