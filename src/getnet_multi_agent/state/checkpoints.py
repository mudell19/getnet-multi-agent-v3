"""Run checkpoints: the paused supervisor state an operator resumes."""

from __future__ import annotations

import uuid

from getnet_multi_agent.contracts import RunCheckpoint
from getnet_multi_agent.state.db import Database, now_iso


def save_checkpoint(
    db: Database, conversation_id: str, request_id: str, cp: RunCheckpoint
) -> str:
    checkpoint_id = "k_" + uuid.uuid4().hex[:12]
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO checkpoints (id, conversation_id, request_id, state_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (checkpoint_id, conversation_id, request_id, cp.model_dump_json(), now_iso()),
        )
    return checkpoint_id


def load_checkpoint(db: Database, checkpoint_id: str) -> RunCheckpoint | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT state_json FROM checkpoints WHERE id = ?", (checkpoint_id,)
        ).fetchone()
    return RunCheckpoint.model_validate_json(row["state_json"]) if row else None
