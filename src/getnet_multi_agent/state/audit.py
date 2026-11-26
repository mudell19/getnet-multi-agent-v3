"""Audit trail for ticket lifecycle events (FR-048)."""

from __future__ import annotations

import sqlite3

from getnet_multi_agent.state.db import Database, now_iso


def insert_audit(
    conn: sqlite3.Connection, actor: str, action: str, ticket_id: str | None, detail: str = ""
) -> None:
    """Writes inside the caller's transaction, so the audit row commits with the change."""
    conn.execute(
        "INSERT INTO audit (ts, actor, action, ticket_id, detail) VALUES (?, ?, ?, ?, ?)",
        (now_iso(), actor, action, ticket_id, detail),
    )


def write_audit(
    db: Database, actor: str, action: str, ticket_id: str | None, detail: str = ""
) -> None:
    with db.connect() as conn:
        insert_audit(conn, actor, action, ticket_id, detail)


def list_audit(db: Database, ticket_id: str | None = None) -> list[dict]:
    sql = "SELECT id, ts, actor, action, ticket_id, detail FROM audit"
    params: tuple = ()
    if ticket_id is not None:
        sql += " WHERE ticket_id = ?"
        params = (ticket_id,)
    with db.connect() as conn:
        rows = conn.execute(sql + " ORDER BY id", params).fetchall()
    return [dict(r) for r in rows]
