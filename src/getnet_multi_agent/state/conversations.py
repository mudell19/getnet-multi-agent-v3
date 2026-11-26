"""Conversations, turns and the rolling summary. Callers pass already-masked text."""

from __future__ import annotations

import uuid

from getnet_multi_agent.state.db import Database, now_iso


def create_conversation(db: Database, owner: str) -> str:
    conversation_id = "c_" + uuid.uuid4().hex[:12]
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO conversations (id, owner, created_at) VALUES (?, ?, ?)",
            (conversation_id, owner, now_iso()),
        )
    return conversation_id


def get_owner(db: Database, conversation_id: str) -> str | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT owner FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    return row["owner"] if row else None


def append_turn(
    db: Database,
    conversation_id: str,
    role: str,
    text: str,
    request_id: str | None = None,
    status: str | None = None,
) -> int:
    """Appends a turn with seq = max + 1 in a single statement, so concurrent appends never
    reuse a seq. Returns the new seq."""
    with db.connect() as conn:
        row = conn.execute(
            "INSERT INTO turns (conversation_id, seq, role, text, request_id, status, created_at) "
            "SELECT ?, COALESCE(MAX(seq), 0) + 1, ?, ?, ?, ?, ? FROM turns "
            "WHERE conversation_id = ? RETURNING seq",
            (conversation_id, role, text, request_id, status, now_iso(), conversation_id),
        ).fetchone()
    return row["seq"]


_TURN_COLS = "seq, role, text, status, created_at"


def list_turns(db: Database, conversation_id: str) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT {_TURN_COLS} FROM turns WHERE conversation_id = ? ORDER BY seq",
            (conversation_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def last_turns(db: Database, conversation_id: str, n: int = 6) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT {_TURN_COLS} FROM turns WHERE conversation_id = ? ORDER BY seq DESC LIMIT ?",
            (conversation_id, n),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_summary(db: Database, conversation_id: str) -> tuple[str, int]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT text, upto_seq FROM summaries WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
    return (row["text"], row["upto_seq"]) if row else ("", 0)


def set_summary(db: Database, conversation_id: str, text: str, upto_seq: int) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO summaries (conversation_id, text, upto_seq, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (conversation_id) DO UPDATE SET "
            "text = excluded.text, upto_seq = excluded.upto_seq, updated_at = excluded.updated_at",
            (conversation_id, text, upto_seq, now_iso()),
        )


def turns_since_summary(db: Database, conversation_id: str) -> int:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM turns WHERE conversation_id = ? AND seq > "
            "COALESCE((SELECT upto_seq FROM summaries WHERE conversation_id = ?), 0)",
            (conversation_id, conversation_id),
        ).fetchone()
    return row["n"]
