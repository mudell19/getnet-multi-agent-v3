"""Per-request accounting: token budget, cost and the LLM call trace."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from getnet_multi_agent.contracts import BudgetExceeded, TraceCall
from getnet_multi_agent.core.settings import get_settings


@dataclass
class RequestContext:
    request_id: str
    budget: int
    tokens: int = 0
    cost_usd: float = 0.0
    calls: list[TraceCall] = field(default_factory=list)

    def check_budget(self) -> None:
        if self.tokens >= self.budget:
            raise BudgetExceeded(f"token budget {self.budget} spent ({self.tokens})")

    def charge(self, call: TraceCall) -> None:
        self.tokens += call.prompt_tokens + call.output_tokens + call.thinking_tokens
        self.cost_usd += call.cost_usd
        self.calls.append(call)


_CURRENT: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


def current() -> RequestContext | None:
    return _CURRENT.get()


@contextmanager
def request_context(
    request_id: str | None = None, budget: int | None = None
) -> Iterator[RequestContext]:
    """Always opens a fresh context; outside one nothing accumulates and no budget applies."""
    ctx = RequestContext(
        request_id=request_id or "r_" + uuid.uuid4().hex[:12],
        budget=budget if budget is not None else get_settings().REQUEST_TOKEN_BUDGET,
    )
    token = _CURRENT.set(ctx)
    try:
        yield ctx
    finally:
        _CURRENT.reset(token)
