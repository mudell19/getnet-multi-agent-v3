"""Operator queue: list, claim and resolve tickets; retrieval inspection for evals."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from getnet_multi_agent.agents import personality
from getnet_multi_agent.api import deps
from getnet_multi_agent.contracts import Principal, Ticket
from getnet_multi_agent.core import metrics
from getnet_multi_agent.core.context import request_context
from getnet_multi_agent.core.logging import log_event
from getnet_multi_agent.format.quality import fix_answer
from getnet_multi_agent.security.auth import require_operator
from getnet_multi_agent.security.dlp import mask
from getnet_multi_agent.state import checkpoints, tickets
from getnet_multi_agent.state import conversations as conv

router = APIRouter(prefix="/operator")

REJECT = {
    "en": "A Getnet specialist reviewed your request and could not complete it: {text} "
          "You can reply here if you need anything else.",
    "pt": "Um especialista da Getnet analisou o seu pedido e não foi possível atender: {text} "
          "Se precisar de mais alguma coisa, é só responder aqui.",
}


class Resolve(BaseModel):
    action: Literal["approve", "edit", "reject"]
    text: str | None = None


def _stats() -> None:
    n, age = tickets.open_stats(deps.db())
    metrics.TICKETS_OPEN.set(n)
    metrics.TICKET_OLDEST_AGE.set(age)


@router.get("/tickets", response_model=list[Ticket])
def list_tickets(status: Literal["open", "claimed", "resolved", "rejected"] | None = None,
                 _: Principal = Depends(require_operator)) -> list[Ticket]:
    _stats()
    return tickets.list_tickets(deps.db(), status)


@router.post("/tickets/{ticket_id}/claim", response_model=Ticket)
def claim(ticket_id: str, op: Principal = Depends(require_operator)) -> Ticket:
    try:
        t = tickets.claim(deps.db(), ticket_id, op.pseudonym)
    except tickets.TicketNotFound:
        raise HTTPException(404, "ticket not found") from None
    except tickets.TicketConflict:
        raise HTTPException(409, "ticket already claimed") from None
    _stats()
    return t


@router.post("/tickets/{ticket_id}/resolve")
def resolve(ticket_id: str, body: Resolve, op: Principal = Depends(require_operator)) -> dict:
    db = deps.db()
    try:
        current = tickets.get_ticket(db, ticket_id)
        kid = tickets.get_checkpoint_id(db, ticket_id)
        t = tickets.resolve(db, ticket_id, op.pseudonym, body.action,
                            mask(body.text) if body.text else body.text)
    except tickets.TicketNotFound:
        raise HTTPException(404, "ticket not found") from None
    except tickets.TicketConflict:
        raise HTTPException(409, "ticket is not claimed by you or is already resolved") from None
    except tickets.TicketInvalid as e:
        raise HTTPException(422, str(e) or "invalid resolution") from None
    cp = checkpoints.load_checkpoint(db, kid) if kid else None
    lang = cp.language if cp else "en"
    if body.action == "approve":
        draft = current.draft
    elif body.action == "edit":
        draft = body.text or ""
    else:
        draft = REJECT[lang].format(text=(body.text or "").rstrip(".") + ".")
    question = cp.plan.standalone if cp else current.question
    with request_context() as ctx:
        answer, viol, _ = personality.rewrite(deps.llm(), question, draft, lang,
                                              deps.today_str())
        answer, fixed = fix_answer(answer)
        conv.append_turn(db, t.conversation_id, "operator", mask(answer), ctx.request_id,
                         "answered")
    for v in viol + fixed:
        metrics.QUALITY_VIOLATIONS.labels(rule=v).inc()
    log_event("ticket_resolved", ticket_id=ticket_id, action=body.action,
              operator=op.pseudonym)
    _stats()
    return {"ticket": t.model_dump(mode="json"), "answer": answer,
            "conversation_id": t.conversation_id}


@router.get("/retrieval")
def retrieval(q: str = Query(min_length=1), mode: Literal["hybrid", "vector"] = "hybrid",
              k: int | None = None, _: Principal = Depends(require_operator)) -> list[dict]:
    hits = deps.retriever().retrieve(q, mode=mode, k=k)
    return [{"rank": i + 1, "url": h.chunk.url, "title": h.chunk.title,
             "score": round(h.score, 4), "text": h.chunk.text} for i, h in enumerate(hits)]
