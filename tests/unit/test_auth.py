"""FR-037, FR-038, FR-039: JWT issue/decode, role dependencies, pseudonyms, CLI token."""

from __future__ import annotations

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from getnet_multi_agent import cli
from getnet_multi_agent.core.settings import Settings
from getnet_multi_agent.security import auth
from getnet_multi_agent.security import pseudonym as pseudonym_mod
from getnet_multi_agent.security.auth import (
    AuthError,
    decode_token,
    issue_token,
    require_merchant,
    require_operator,
)
from getnet_multi_agent.security.pseudonym import pseudonym

SECRET = "test-secret-0123456789abcdef0123456789"


def use_settings(monkeypatch, **overrides) -> Settings:
    s = Settings(_env_file=None, **{"JWT_SECRET": SECRET, "PSEUDONYM_KEY": "pkey", **overrides})
    monkeypatch.setattr(auth, "get_settings", lambda: s)
    monkeypatch.setattr(pseudonym_mod, "get_settings", lambda: s)
    return s


@pytest.fixture(autouse=True)
def env(monkeypatch):
    return use_settings(monkeypatch)


def test_fr037_issue_and_decode_merchant():
    p = decode_token(issue_token("cliente1988", "merchant"))
    assert p.sub == "cliente1988" and p.role == "merchant"
    assert p.pseudonym == pseudonym("cliente1988") and p.pseudonym.startswith("u_")


def test_fr039_pseudonym_is_stable_and_hides_id():
    a = pseudonym("cliente1988")
    assert a == pseudonym("cliente1988") and a != pseudonym("cliente2000")
    assert "1988" not in a and len(a) == 18


def test_fr037_expired_token_raises():
    with pytest.raises(AuthError):
        decode_token(issue_token("cliente1988", "merchant", hours=-1))


def test_fr037_wrong_audience_raises(env):
    bad = jwt.encode({"iss": env.JWT_ISSUER, "aud": "other", "sub": "x", "role": "merchant",
                      "exp": 9999999999}, SECRET, algorithm="HS256")
    with pytest.raises(AuthError):
        decode_token(bad)


def test_fr037_missing_sub_and_bad_role_raise(env):
    base = {"iss": env.JWT_ISSUER, "aud": env.JWT_AUDIENCE, "exp": 9999999999}
    with pytest.raises(AuthError):
        decode_token(jwt.encode({**base, "role": "merchant"}, SECRET, algorithm="HS256"))
    with pytest.raises(AuthError):
        decode_token(jwt.encode({**base, "sub": "x", "role": "admin"}, SECRET, algorithm="HS256"))


def test_fr037_route_dependencies_401_403():
    app = FastAPI()

    @app.get("/m")
    def m(p=Depends(require_merchant)):  # noqa: B008
        return {"sub": p.sub}

    @app.get("/o")
    def o(p=Depends(require_operator)):  # noqa: B008
        return {"sub": p.sub}

    c = TestClient(app)
    merchant = {"Authorization": f"Bearer {issue_token('cliente1988', 'merchant')}"}
    operator = {"Authorization": f"Bearer {issue_token('op1', 'operator')}"}
    assert c.get("/m").status_code == 401
    assert c.get("/m", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert c.get("/m", headers=merchant).json() == {"sub": "cliente1988"}
    assert c.get("/o", headers=merchant).status_code == 403
    assert c.get("/o", headers=operator).status_code == 200
    assert c.get("/m", headers=operator).status_code == 403


def test_fr038_cli_token_prints_only_token(capsys):
    assert cli.main(["token", "--sub", "op1", "--role", "operator", "--hours", "1"]) == 0
    token = capsys.readouterr().out.strip()
    assert decode_token(token).role == "operator"


def test_fr038_empty_secret_refuses(monkeypatch):
    use_settings(monkeypatch, JWT_SECRET="")
    with pytest.raises(AuthError):
        issue_token("x", "merchant")
