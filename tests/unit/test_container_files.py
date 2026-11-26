from getnet_multi_agent.core.settings import ROOT


def test_fr071_dockerfile_pinned_nonroot_frozen_healthcheck():
    d = (ROOT / "Dockerfile").read_text()
    assert "python:3.12-slim@sha256:" in d
    assert "uv sync --frozen" in d
    assert "USER app" in d and "HEALTHCHECK" in d


def test_fr071_dockerignore_excludes_secrets_and_state():
    ign = (ROOT / ".dockerignore").read_text().splitlines()
    for entry in (".env", ".venv", ".git", "data/state"):
        assert entry in ign


def test_fr071_compose_has_volume_healthcheck_and_log_limits():
    c = (ROOT / "compose.yaml").read_text()
    assert "/app/data/state" in c and "healthcheck" in c and "max-size" in c
