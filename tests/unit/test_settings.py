from pathlib import Path

from getnet_multi_agent.core.settings import ROOT, Settings


def _example_keys() -> dict[str, str]:
    out = {}
    for line in (ROOT / ".env.example").read_text().splitlines():
        if line and not line.startswith("#"):
            k, _, v = line.partition("=")
            out[k] = v
    return out


def test_fr072_env_example_lists_every_setting():
    assert set(Settings.model_fields) == set(_example_keys())


def test_fr072_env_example_secrets_empty():
    keys = _example_keys()
    for secret in ("GEMINI_API_KEY", "JWT_SECRET", "PSEUDONYM_KEY"):
        assert keys[secret] == ""


def test_fr054_models_and_thinking_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_ROUTER_THINKING", "minimal")
    monkeypatch.setenv("GEMINI_MODEL", "m-x")
    s = Settings(_env_file=None)
    assert s.GEMINI_MODEL == "m-x"
    assert s.GEMINI_ROUTER_THINKING == "minimal"
    assert s.GEMINI_MODEL_THINKING == "low"
    assert s.REQUEST_TOKEN_BUDGET == 30000


def test_fr054_root_points_to_repo():
    assert (ROOT / "pyproject.toml").exists()
    assert isinstance(ROOT, Path)
