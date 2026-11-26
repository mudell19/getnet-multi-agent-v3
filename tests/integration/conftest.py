"""HTTP integration fixtures: real app, LLM stubbed at the wrapper, temp database."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from getnet_multi_agent.core import settings as settings_mod


@dataclass
class _Chunk:
    url: str
    title: str
    text: str

    @property
    def id(self) -> str:
        return f"{self.url}#{hash(self.text)}"


@dataclass
class _Hit:
    chunk: _Chunk
    score: float


class FakeRetriever:
    def __init__(self, hits=None):
        self.hits = hits if hits is not None else [
            _Hit(_Chunk("https://site.getnet.com.br/duvidas/algar", "Chip Algar",
                        "Faça um teste de comunicação: pressione F, 60, opção 2 manutenção, "
                        "opção 1 teste de comunicação."), 0.8),
            _Hit(_Chunk("https://site.getnet.com.br/duvidas/antecipacao-de-vendas",
                        "Antecipação de vendas",
                        "O cliente pode receber antecipadamente os valores das vendas realizadas "
                        "na função de crédito, sejam à vista ou parceladas."), 0.7),
        ]

    def retrieve(self, query, mode="hybrid", k=None):
        return list(self.hits)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "stub")
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret-test-secret")
    monkeypatch.setenv("PSEUDONYM_KEY", "test-pseudonym-key")
    settings_mod.get_settings.cache_clear()
    from getnet_multi_agent.api import deps
    from getnet_multi_agent.api.app import app
    from getnet_multi_agent.core.llm import reset_llm
    from getnet_multi_agent.core.stub import StubLLM
    from getnet_multi_agent.state.db import Database

    reset_llm()
    db = Database(tmp_path / "app.db")
    deps.override(llm=StubLLM(), db=db, retriever=FakeRetriever())
    c = TestClient(app)
    c.db = db
    yield c
    deps.override()
    settings_mod.get_settings.cache_clear()


def token(sub: str, role: str = "merchant") -> dict:
    from getnet_multi_agent.security.auth import issue_token
    return {"Authorization": f"Bearer {issue_token(sub, role)}"}
