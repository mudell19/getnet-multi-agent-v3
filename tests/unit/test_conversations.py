"""Conversation persistence (FR-040, FR-041, FR-043)."""

from __future__ import annotations

import sqlite3

import pytest

from getnet_multi_agent.contracts import Observation, Plan, RunCheckpoint, Step
from getnet_multi_agent.state import db as db_module
from getnet_multi_agent.state.checkpoints import load_checkpoint, save_checkpoint
from getnet_multi_agent.state.conversations import (
    append_turn,
    create_conversation,
    get_owner,
    get_summary,
    last_turns,
    list_turns,
    set_summary,
    turns_since_summary,
)
from getnet_multi_agent.state.db import Database, get_db, set_db


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "app.db")


def test_fr040_create_conversation_records_owner(db):
    cid = create_conversation(db, "p_owner")
    assert cid.startswith("c_") and len(cid) == 14
    assert get_owner(db, cid) == "p_owner"
    assert get_owner(db, "c_missing") is None


def test_fr043_append_and_list_turns_in_order(db):
    cid = create_conversation(db, "p_owner")
    assert append_turn(db, cid, "user", "hello", request_id="r1") == 1
    assert append_turn(db, cid, "assistant", "hi", request_id="r1", status="answered") == 2
    turns = list_turns(db, cid)
    assert [(t["seq"], t["role"], t["text"], t["status"]) for t in turns] == [
        (1, "user", "hello", None),
        (2, "assistant", "hi", "answered"),
    ]
    assert turns[0]["created_at"]


def test_fr043_seq_is_per_conversation(db):
    a = create_conversation(db, "p1")
    b = create_conversation(db, "p2")
    append_turn(db, a, "user", "x")
    assert append_turn(db, b, "user", "y") == 1


def test_fr041_invalid_role_rejected(db):
    cid = create_conversation(db, "p1")
    with pytest.raises(sqlite3.IntegrityError):
        append_turn(db, cid, "system", "nope")


def test_fr042_last_turns_chronological(db):
    cid = create_conversation(db, "p1")
    for i in range(1, 10):
        append_turn(db, cid, "user" if i % 2 else "assistant", f"t{i}")
    last = last_turns(db, cid)
    assert [t["seq"] for t in last] == [4, 5, 6, 7, 8, 9]
    assert [t["seq"] for t in last_turns(db, cid, n=2)] == [8, 9]


def test_fr041_summary_roundtrip_and_turns_since(db):
    cid = create_conversation(db, "p1")
    assert get_summary(db, cid) == ("", 0)
    for i in range(8):
        append_turn(db, cid, "user", f"t{i}")
    assert turns_since_summary(db, cid) == 8
    set_summary(db, cid, "first summary", 5)
    assert get_summary(db, cid) == ("first summary", 5)
    assert turns_since_summary(db, cid) == 3
    set_summary(db, cid, "second summary", 8)
    assert get_summary(db, cid) == ("second summary", 8)
    assert turns_since_summary(db, cid) == 0


def test_fr041_turns_survive_restart(tmp_path):
    path = tmp_path / "state" / "app.db"
    first = Database(path)
    cid = create_conversation(first, "p1")
    append_turn(first, cid, "user", "before restart")
    set_summary(first, cid, "s", 1)

    second = Database(path)
    assert get_owner(second, cid) == "p1"
    assert [t["text"] for t in list_turns(second, cid)] == ["before restart"]
    assert get_summary(second, cid) == ("s", 1)
    assert append_turn(second, cid, "assistant", "after restart") == 2


def test_fr041_checkpoint_roundtrip(db):
    cid = create_conversation(db, "p1")
    step = Step(agent="knowledge", source="rag", query="taxas")
    cp = RunCheckpoint(
        plan=Plan(steps=[step], language="pt", standalone="taxas"),
        observations=[Observation(step=step, status="answered", answer="2%")],
        draft="rascunho",
        language="pt",
        pending_parts=["prazo"],
    )
    kid = save_checkpoint(db, cid, "r1", cp)
    assert kid.startswith("k_")
    assert load_checkpoint(db, kid) == cp
    assert load_checkpoint(db, "k_missing") is None


def test_fr041_get_db_singleton_and_override(tmp_path):
    original = db_module._db
    try:
        custom = Database(tmp_path / "x.db")
        set_db(custom)
        assert get_db() is custom
        assert get_db() is get_db()
    finally:
        set_db(original)
