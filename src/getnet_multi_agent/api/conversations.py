"""GET /conversations/{id}: the owner's turns."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from getnet_multi_agent.api import deps
from getnet_multi_agent.contracts import Principal
from getnet_multi_agent.security.auth import require_merchant
from getnet_multi_agent.state import conversations as conv

router = APIRouter()


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str,
                     principal: Principal = Depends(require_merchant)) -> dict:
    db = deps.db()
    if conv.get_owner(db, conversation_id) != principal.pseudonym:
        raise HTTPException(404, "conversation not found")
    return {"id": conversation_id, "turns": conv.list_turns(db, conversation_id)}
