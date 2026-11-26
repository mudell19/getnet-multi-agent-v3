"""Shared contracts: every module builds against these models and the LLM protocol."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

Lang = Literal["en", "pt"]
Role = Literal["merchant", "operator"]
RefusalReason = Literal[
    "sensitive_data", "other_merchant", "prompt_injection", "unsafe", "out_of_scope"
]
PlannedRefusal = Literal["out_of_scope", "unsafe", "other_merchant", "prompt_injection"]
TicketStatus = Literal["open", "claimed", "resolved", "rejected"]
LLMRole = Literal["router", "answer", "judge"]


class Principal(BaseModel):
    sub: str
    role: Role
    pseudonym: str


class Step(BaseModel):
    agent: Literal["support", "knowledge"]
    source: Literal["rag", "web"] | None = None
    query: str
    reason: str = ""

    def label(self) -> str:
        return "support" if self.agent == "support" else f"knowledge:{self.source or 'rag'}"


class Plan(BaseModel):
    """Router output. `standalone` resolves references to earlier turns."""

    steps: list[Step] = Field(default_factory=list)
    language: Lang = "en"
    standalone: str = ""
    refusal_reason: PlannedRefusal | None = None
    escalate: bool = False


class PlanRevision(BaseModel):
    iteration: int
    action: Literal["initial", "add", "retry", "drop"]
    step: Step | None = None
    reason: str


class Evidence(BaseModel):
    kind: Literal["rag", "tool", "web"]
    url: str = ""
    title: str = ""
    score: float | None = None
    excerpt: str = ""


class TraceCall(BaseModel):
    purpose: str
    model: str = ""
    latency_ms: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    search_queries: int = 0
    cost_usd: float = 0.0


class Observation(BaseModel):
    step: Step
    status: Literal["answered", "ungrounded", "failed", "not_found"]
    answer: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    unanswered: list[str] = Field(default_factory=list)
    # Flags read by the critic's deterministic rules, e.g. {"terminal_offline": True}.
    facts: dict[str, Any] = Field(default_factory=dict)
    model: str = ""
    latency_ms: int = 0
    tokens: int = 0
    cost_usd: float = 0.0


class CriticVerdict(BaseModel):
    """Lite-model completeness check over the observations."""

    complete: bool
    unanswered: list[str] = Field(default_factory=list)
    notes: str = ""


class Source(BaseModel):
    title: str = ""
    url: str


class AgentResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    observation: Observation
    sources: list[Source] = Field(default_factory=list)
    calls: list[TraceCall] = Field(default_factory=list)


class Trace(BaseModel):
    plan_revisions: list[PlanRevision] = Field(default_factory=list)
    critic_notes: list[str] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    calls: list[TraceCall] = Field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    quality_violations: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    user_id: str = Field(min_length=1, max_length=128)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    status: Literal["answered", "awaiting_human", "refused"]
    refusal_reason: RefusalReason | None = None
    route: str
    sources: list[Source] = Field(default_factory=list)
    ticket_id: str | None = None
    conversation_id: str
    request_id: str
    trace: Trace = Field(default_factory=Trace)


class Ticket(BaseModel):
    id: str
    conversation_id: str
    status: TicketStatus
    reason: str
    question: str = ""
    draft: str = ""
    claimed_by: str | None = None
    created_at: datetime | None = None
    claimed_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution_action: Literal["approve", "edit", "reject"] | None = None
    resolution_text: str | None = None


class RunCheckpoint(BaseModel):
    plan: Plan
    revisions: list[PlanRevision] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    draft: str = ""
    language: Lang = "en"
    pending_parts: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- LLM interface


class BudgetExceeded(Exception):
    """The per-request token budget is spent."""


class LLMUnavailable(Exception):
    """The model failed after the single retry, timed out or returned invalid output."""


class ToolSpec(BaseModel):
    """A function the model may call. `parameters` is a JSON schema object."""

    name: str
    description: str
    parameters: dict[str, Any]


class LLMResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str = ""
    parsed: Any = None
    # [{"name": str, "args": dict}]
    function_calls: list[dict[str, Any]] = Field(default_factory=list)
    # Whole model content (google.genai types.Content); sent back unchanged in tool loops.
    content: Any = None
    sources: list[Source] = Field(default_factory=list)
    search_queries: int = 0
    usage: TraceCall


class LLM(Protocol):
    """`contents` items: str (user text), an LLMResult.content (model turn, passed back whole),
    or {"function_response": {"name": str, "response": dict}}."""

    def generate(
        self,
        *,
        purpose: str,
        role: LLMRole,
        system: str,
        contents: list[Any],
        schema: type[BaseModel] | None = None,
        tools: list[ToolSpec] | None = None,
        search: bool = False,
    ) -> LLMResult: ...

    def embed(self, texts: list[str], task: Literal["document", "query"]) -> list[list[float]]: ...


_TOKEN = re.compile(r"\w+", re.UNICODE)


def hash_embed(text: str, dim: int = 768) -> list[float]:
    """Deterministic bag-of-words embedding for stub mode and tests."""
    vec = [0.0] * dim
    for tok in _TOKEN.findall(text.lower()):
        h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:4], "big")
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
