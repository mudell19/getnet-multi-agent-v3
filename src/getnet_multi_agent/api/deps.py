"""Process-wide dependencies, replaceable in tests."""

from __future__ import annotations

from datetime import datetime

from getnet_multi_agent.core.llm import get_llm
from getnet_multi_agent.core.settings import BRT
from getnet_multi_agent.state.db import get_db
from getnet_multi_agent.supervisor import Supervisor

_override: dict = {}


def llm():
    return _override.get("llm") or get_llm()


def db():
    return _override.get("db") or get_db()


def retriever():
    if "retriever" in _override:
        return _override["retriever"]
    from getnet_multi_agent.rag.retriever import get_retriever
    return get_retriever()


def supervisor() -> Supervisor:
    return Supervisor(llm(), retriever, db())


def today_str() -> str:
    now = datetime.now(BRT)
    return f"{now:%Y-%m-%d} ({now:%A}), {now:%H:%M} Brazil time"


def override(**kw) -> None:
    _override.clear()
    _override.update(kw)
