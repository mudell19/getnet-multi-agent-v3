from pathlib import Path

WF = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def test_fr073_ci_runs_lint_tests_smoke_and_alert_rules_on_push():
    ci = (WF / "ci.yml").read_text()
    for needle in (
        "on:\n  push:",
        "runs-on: ubuntu-latest",
        "actions/checkout@v7",
        "pip install uv==0.13.6",
        "uv sync --frozen",
        "uv run ruff check .",
        "uv run pytest -q",
        "openssl rand -hex 32",
        "LLM_MODE=stub",
        "docker compose -p gma-ci up --build --wait",
        "getnet-multi-agent token --sub cliente1988 --role merchant",
        "http://localhost:8000/chat",
        "request_id",
        "promtool",
        "test rules /p/alerts.test.yml",
        "docker compose -p gma-ci down -v",
    ):
        assert needle in ci, needle
    assert "if: always()" in ci


def test_fr073_live_eval_on_session_tags():
    ev = (WF / "live-eval.yml").read_text()
    for needle in (
        "tags:\n      - 'sessao-*'",
        "actions/checkout@v7",
        "pip install uv==0.13.6",
        "uv sync --frozen",
        "secrets.GEMINI_API_KEY",
        "openssl rand -hex 32",
        "id: up",
        "docker compose -p gma-eval up --build --wait",
        "evals/run.py --dataset evals/dataset.jsonl --rerun-failures",
        "evals/retrieval.py",
        "if: always() && steps.up.outcome == 'success'",
        "actions/upload-artifact@v7",
        "evals/report.md",
        "evals/retrieval_report.md",
        "docker compose -p gma-eval down -v",
    ):
        assert needle in ev, needle


def test_fr073_secrets_never_echoed():
    ev = (WF / "live-eval.yml").read_text()
    assert "echo $GEMINI_API_KEY" not in ev and 'echo "$GEMINI_API_KEY"' not in ev
    assert "set -x" not in ev
