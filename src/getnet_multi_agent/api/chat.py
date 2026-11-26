"""POST /chat: guardrails by code, then the supervisor; turns persisted masked."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException

from getnet_multi_agent.agents import summary as summary_agent
from getnet_multi_agent.api import deps
from getnet_multi_agent.contracts import ChatRequest, ChatResponse, Principal, Trace
from getnet_multi_agent.core import metrics
from getnet_multi_agent.core.context import request_context
from getnet_multi_agent.core.logging import log_event
from getnet_multi_agent.core.settings import LAST_TURNS, get_settings
from getnet_multi_agent.security.auth import require_merchant
from getnet_multi_agent.security.dlp import mask
from getnet_multi_agent.security.guardrails import check_message
from getnet_multi_agent.state import conversations as conv

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, principal: Principal = Depends(require_merchant)) -> ChatResponse:
    if req.user_id != principal.sub:
        raise HTTPException(403, "user_id does not match the authenticated subject")
    if len(req.message) > get_settings().MAX_MESSAGE_CHARS:
        raise HTTPException(422, f"message longer than {get_settings().MAX_MESSAGE_CHARS} chars")
    db = deps.db()
    if req.conversation_id:
        if conv.get_owner(db, req.conversation_id) != principal.pseudonym:
            raise HTTPException(404, "conversation not found")
        cid = req.conversation_id
    else:
        cid = conv.create_conversation(db, principal.pseudonym)
    t0 = time.monotonic()
    with request_context() as ctx:
        masked = mask(req.message)
        log_event("chat_request", user=principal.pseudonym, conversation_id=cid,
                  chars=len(req.message))
        g = check_message(req.message, principal)
        if g.refusal_reason:
            metrics.REFUSALS.labels(reason=g.refusal_reason).inc()
            resp = ChatResponse(answer=g.answer, status="refused", refusal_reason=g.refusal_reason,
                                route="refusal", conversation_id=cid, request_id=ctx.request_id,
                                trace=Trace())
        else:
            summary, _ = conv.get_summary(db, cid)
            turns = conv.last_turns(db, cid, LAST_TURNS)
            r = deps.supervisor().run(masked, principal, cid, ctx.request_id, summary, turns,
                                      deps.today_str())
            resp = ChatResponse(answer=r.answer, status=r.status, refusal_reason=r.refusal_reason,
                                route=r.route, sources=r.sources, ticket_id=r.ticket_id,
                                conversation_id=cid, request_id=ctx.request_id, trace=r.trace)
        conv.append_turn(db, cid, "user", masked, ctx.request_id)
        seq = conv.append_turn(db, cid, "assistant", mask(resp.answer), ctx.request_id,
                               resp.status)
        _refresh_summary(db, cid, seq)
    elapsed = time.monotonic() - t0
    metrics.REQUESTS.labels(route=resp.route, status=resp.status).inc()
    metrics.LATENCY.observe(elapsed)
    log_event("chat_response", request_id=resp.request_id, route=resp.route, status=resp.status,
              refusal_reason=resp.refusal_reason, ticket_id=resp.ticket_id,
              latency_ms=int(elapsed * 1000), tokens=resp.trace.total_tokens,
              cost_usd=resp.trace.total_cost_usd)
    return resp


def _refresh_summary(db, cid: str, seq: int) -> None:
    if conv.turns_since_summary(db, cid) <= LAST_TURNS:
        return
    try:
        previous, _ = conv.get_summary(db, cid)
        text = summary_agent.summarize(deps.llm(), previous, conv.list_turns(db, cid)[-12:],
                                       deps.today_str())
        conv.set_summary(db, cid, mask(text), seq)
    except Exception as e:  # the summary is an optimization; the turn is already stored
        log_event("summary_failed", level="warning", error=type(e).__name__)
