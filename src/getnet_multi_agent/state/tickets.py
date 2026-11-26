"""Escalation tickets: open -> claimed -> resolved | rejected, every transition audited."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime

from getnet_multi_agent.contracts import Ticket
from getnet_multi_agent.state.audit import insert_audit
from getnet_multi_agent.state.db import Database, now_iso


class TicketNotFound(Exception):
    """No ticket with this id (404)."""


class TicketConflict(Exception):
    """The ticket is not in a state that allows this operator's action (409)."""


class TicketInvalid(Exception):
    """The request is incomplete for the action, e.g. approve with no draft (422)."""


_RESOLUTIONS = {
    "approve": ("resolved", "ticket_approved"),
    "edit": ("resolved", "ticket_edited"),
    "reject": ("rejected", "ticket_rejected"),
}


def _to_ticket(row: sqlite3.Row) -> Ticket:
    return Ticket(
        id=row["id"],
        conversation_id=row["conversation_id"],
        status=row["status"],
        reason=row["reason"],
        question=row["question"],
        draft=row["draft"],
        claimed_by=row["claimed_by"],
        created_at=row["created_at"],
        claimed_at=row["claimed_at"],
        resolved_at=row["resolved_at"],
        resolution_action=row["resolution_action"],
        resolution_text=row["resolution_text"],
    )


def _fetch(conn: sqlite3.Connection, ticket_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        raise TicketNotFound(ticket_id)
    return row


def create_ticket(
    db: Database,
    conversation_id: str,
    checkpoint_id: str | None,
    reason: str,
    question: str,
    draft: str,
) -> Ticket:
    ticket_id = "t_" + uuid.uuid4().hex[:10]
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO tickets (id, conversation_id, checkpoint_id, reason, question, draft, "
            "status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'open', ?)",
            (ticket_id, conversation_id, checkpoint_id, reason, question, draft or "", now_iso()),
        )
        insert_audit(conn, "system", "ticket_opened", ticket_id, reason)
        return _to_ticket(_fetch(conn, ticket_id))


def get_ticket(db: Database, ticket_id: str) -> Ticket:
    with db.connect() as conn:
        return _to_ticket(_fetch(conn, ticket_id))


def get_checkpoint_id(db: Database, ticket_id: str) -> str | None:
    with db.connect() as conn:
        return _fetch(conn, ticket_id)["checkpoint_id"]


def list_tickets(db: Database, status: str | None = None) -> list[Ticket]:
    sql = "SELECT * FROM tickets"
    params: tuple = ()
    if status is not None:
        sql += " WHERE status = ?"
        params = (status,)
    with db.connect() as conn:
        rows = conn.execute(sql + " ORDER BY created_at, id", params).fetchall()
    return [_to_ticket(r) for r in rows]


def claim(db: Database, ticket_id: str, operator: str) -> Ticket:
    """Atomic: the guarded UPDATE lets exactly one concurrent caller win (FR-046)."""
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE tickets SET status = 'claimed', claimed_by = ?, claimed_at = ? "
            "WHERE id = ? AND status = 'open'",
            (operator, now_iso(), ticket_id),
        )
        if cur.rowcount == 0:
            _fetch(conn, ticket_id)
            raise TicketConflict(f"{ticket_id} is not open")
        insert_audit(conn, operator, "ticket_claimed", ticket_id)
        return _to_ticket(_fetch(conn, ticket_id))


def resolve(
    db: Database, ticket_id: str, operator: str, action: str, text: str | None
) -> Ticket:
    if action not in _RESOLUTIONS:
        raise TicketInvalid(f"unknown action {action!r}")
    new_status, audit_action = _RESOLUTIONS[action]
    with db.connect() as conn:
        row = _fetch(conn, ticket_id)
        if row["status"] != "claimed" or row["claimed_by"] != operator:
            raise TicketConflict(f"{ticket_id} is not claimed by this operator")
        if action == "approve":
            if not (row["draft"] or "").strip():
                raise TicketInvalid("ticket has no draft to approve")
            resolution_text = row["draft"]
        else:
            if not (text or "").strip():
                raise TicketInvalid(f"{action} requires text")
            resolution_text = text
        cur = conn.execute(
            "UPDATE tickets SET status = ?, resolution_action = ?, resolution_text = ?, "
            "resolved_at = ? WHERE id = ? AND status = 'claimed' AND claimed_by = ?",
            (new_status, action, resolution_text, now_iso(), ticket_id, operator),
        )
        if cur.rowcount == 0:
            raise TicketConflict(f"{ticket_id} changed concurrently")
        insert_audit(conn, operator, audit_action, ticket_id)
        return _to_ticket(_fetch(conn, ticket_id))


def open_stats(db: Database) -> tuple[int, float]:
    """(open + claimed count, age in seconds of the oldest open or claimed ticket)."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n, MIN(created_at) AS oldest FROM tickets "
            "WHERE status IN ('open', 'claimed')"
        ).fetchone()
    if not row["n"]:
        return 0, 0.0
    oldest = datetime.fromisoformat(row["oldest"])
    return row["n"], (datetime.now(UTC) - oldest).total_seconds()
