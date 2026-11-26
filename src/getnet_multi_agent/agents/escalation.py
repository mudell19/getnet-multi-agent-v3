"""Human Escalation agent: checkpoint, ticket and a message that says what happens next."""

from __future__ import annotations

from getnet_multi_agent.contracts import Lang, RunCheckpoint
from getnet_multi_agent.state import checkpoints, tickets

MESSAGES = {
    "en": "I've passed this to a Getnet specialist (ticket {tid}). They will reply here in this "
          "conversation as soon as possible.",
    "pt": "Encaminhei para um especialista da Getnet (protocolo {tid}). A resposta vai chegar "
          "aqui nesta conversa assim que possível.",
}
PARTIAL = {
    "en": "For the rest of your question, I've passed it to a Getnet specialist (ticket {tid}), "
          "who will reply here in this conversation.",
    "pt": "Sobre o restante da sua pergunta, encaminhei para um especialista da Getnet "
          "(protocolo {tid}), que vai responder aqui nesta conversa.",
}


def escalate(db, conversation_id: str, request_id: str, cp: RunCheckpoint, reason: str,
             question: str) -> str:
    """Saves the checkpoint, opens the ticket and returns its id."""
    kid = checkpoints.save_checkpoint(db, conversation_id, request_id, cp)
    t = tickets.create_ticket(db, conversation_id, kid, reason, question, cp.draft)
    return t.id


def message(lang: Lang, ticket_id: str, partial: bool) -> str:
    return (PARTIAL if partial else MESSAGES)[lang].format(tid=ticket_id)
