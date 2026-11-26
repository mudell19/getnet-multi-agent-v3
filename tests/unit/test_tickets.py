"""Ticket lifecycle, atomic claim and audit (FR-044..FR-048)."""

from __future__ import annotations

import threading

import pytest

from getnet_multi_agent.state.audit import list_audit, write_audit
from getnet_multi_agent.state.conversations import create_conversation
from getnet_multi_agent.state.db import Database
from getnet_multi_agent.state.tickets import (
    TicketConflict,
    TicketInvalid,
    TicketNotFound,
    claim,
    create_ticket,
    get_ticket,
    list_tickets,
    open_stats,
    resolve,
)


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "app.db")


@pytest.fixture
def cid(db):
    return create_conversation(db, "p_merchant")


def _ticket(db, cid, draft="partial answer"):
    return create_ticket(db, cid, None, "missing_grounding", "what is the fee?", draft)


def test_fr044_create_ticket_open(db, cid):
    t = _ticket(db, cid)
    assert t.id.startswith("t_") and len(t.id) == 12
    assert t.status == "open"
    assert t.conversation_id == cid
    assert (t.reason, t.question, t.draft) == ("missing_grounding", "what is the fee?",
                                               "partial answer")
    assert t.created_at is not None and t.created_at.tzinfo is not None
    assert get_ticket(db, t.id) == t


def test_fr045_get_missing_ticket_raises(db):
    with pytest.raises(TicketNotFound):
        get_ticket(db, "t_missing")


def test_fr045_list_tickets_by_status_oldest_first(db, cid):
    a = _ticket(db, cid)
    b = _ticket(db, cid)
    c = _ticket(db, cid)
    claim(db, b.id, "op1")
    claim(db, c.id, "op1")
    resolve(db, c.id, "op1", "reject", "not supported")
    assert [t.id for t in list_tickets(db)] == [a.id, b.id, c.id]
    assert [t.id for t in list_tickets(db, "open")] == [a.id]
    assert [t.id for t in list_tickets(db, "claimed")] == [b.id]
    assert [t.id for t in list_tickets(db, "rejected")] == [c.id]
    assert list_tickets(db, "resolved") == []


def test_fr046_claim_sets_operator(db, cid):
    t = claim(db, _ticket(db, cid).id, "op1")
    assert t.status == "claimed" and t.claimed_by == "op1" and t.claimed_at is not None


def test_fr046_claim_twice_conflicts(db, cid):
    t = _ticket(db, cid)
    claim(db, t.id, "op1")
    with pytest.raises(TicketConflict):
        claim(db, t.id, "op2")
    assert get_ticket(db, t.id).claimed_by == "op1"


def test_fr046_claim_missing_not_found(db):
    with pytest.raises(TicketNotFound):
        claim(db, "t_missing", "op1")


def test_fr046_concurrent_claim_exactly_one_wins(db, cid):
    t = _ticket(db, cid)
    barrier = threading.Barrier(2)
    results: dict[str, object] = {}

    def worker(op: str) -> None:
        barrier.wait()
        try:
            results[op] = claim(db, t.id, op)
        except TicketConflict as exc:
            results[op] = exc

    threads = [threading.Thread(target=worker, args=(op,)) for op in ("op1", "op2")]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    wins = [op for op, r in results.items() if not isinstance(r, Exception)]
    conflicts = [op for op, r in results.items() if isinstance(r, TicketConflict)]
    assert len(wins) == 1 and len(conflicts) == 1
    assert get_ticket(db, t.id).claimed_by == wins[0]
    assert [a["actor"] for a in list_audit(db, t.id) if a["action"] == "ticket_claimed"] == wins


def test_fr047_approve_sends_draft(db, cid):
    t = _ticket(db, cid)
    claim(db, t.id, "op1")
    done = resolve(db, t.id, "op1", "approve", None)
    assert done.status == "resolved"
    assert done.resolution_action == "approve"
    assert done.resolution_text == "partial answer"
    assert done.resolved_at is not None


def test_fr047_edit_stores_operator_text(db, cid):
    t = _ticket(db, cid)
    claim(db, t.id, "op1")
    done = resolve(db, t.id, "op1", "edit", "the fee is 2%")
    assert (done.status, done.resolution_action, done.resolution_text) == (
        "resolved", "edit", "the fee is 2%")


def test_fr047_reject_sets_rejected(db, cid):
    t = _ticket(db, cid)
    claim(db, t.id, "op1")
    done = resolve(db, t.id, "op1", "reject", "outside our scope")
    assert (done.status, done.resolution_action, done.resolution_text) == (
        "rejected", "reject", "outside our scope")


def test_fr047_resolve_by_other_operator_conflicts(db, cid):
    t = _ticket(db, cid)
    claim(db, t.id, "op1")
    with pytest.raises(TicketConflict):
        resolve(db, t.id, "op2", "edit", "hijack")
    assert get_ticket(db, t.id).status == "claimed"


def test_fr047_resolve_unclaimed_conflicts(db, cid):
    t = _ticket(db, cid)
    with pytest.raises(TicketConflict):
        resolve(db, t.id, "op1", "edit", "x")


def test_fr047_resolve_twice_conflicts(db, cid):
    t = _ticket(db, cid)
    claim(db, t.id, "op1")
    resolve(db, t.id, "op1", "approve", None)
    with pytest.raises(TicketConflict):
        resolve(db, t.id, "op1", "edit", "again")


def test_fr047_approve_without_draft_invalid(db, cid):
    t = _ticket(db, cid, draft="")
    claim(db, t.id, "op1")
    with pytest.raises(TicketInvalid):
        resolve(db, t.id, "op1", "approve", None)
    assert get_ticket(db, t.id).status == "claimed"


@pytest.mark.parametrize("action", ["edit", "reject"])
def test_fr047_edit_or_reject_without_text_invalid(db, cid, action):
    t = _ticket(db, cid)
    claim(db, t.id, "op1")
    with pytest.raises(TicketInvalid):
        resolve(db, t.id, "op1", action, "  ")


def test_fr047_resolve_missing_not_found(db):
    with pytest.raises(TicketNotFound):
        resolve(db, "t_missing", "op1", "approve", None)


@pytest.mark.parametrize(
    ("action", "text", "audit_action"),
    [("approve", None, "ticket_approved"), ("edit", "x", "ticket_edited"),
     ("reject", "y", "ticket_rejected")],
)
def test_fr048_audit_open_claim_resolution(db, cid, action, text, audit_action):
    t = _ticket(db, cid)
    claim(db, t.id, "op1")
    resolve(db, t.id, "op1", action, text)
    rows = list_audit(db, t.id)
    assert [(r["actor"], r["action"]) for r in rows] == [
        ("system", "ticket_opened"), ("op1", "ticket_claimed"), ("op1", audit_action)]
    assert all(r["ts"] and r["ticket_id"] == t.id for r in rows)


def test_fr048_failed_actions_write_no_audit(db, cid):
    t = _ticket(db, cid, draft="")
    claim(db, t.id, "op1")
    with pytest.raises(TicketConflict):
        claim(db, t.id, "op2")
    with pytest.raises(TicketInvalid):
        resolve(db, t.id, "op1", "approve", None)
    assert [r["action"] for r in list_audit(db, t.id)] == ["ticket_opened", "ticket_claimed"]


def test_fr048_write_and_list_audit(db):
    write_audit(db, "op1", "login", None, "detail")
    write_audit(db, "op1", "note", "t_x")
    assert [r["action"] for r in list_audit(db)] == ["login", "note"]
    assert [r["action"] for r in list_audit(db, "t_x")] == ["note"]


def test_fr045_open_stats(db, cid):
    assert open_stats(db) == (0, 0.0)
    a = _ticket(db, cid)
    b = _ticket(db, cid)
    c = _ticket(db, cid)
    claim(db, b.id, "op1")
    claim(db, c.id, "op1")
    resolve(db, c.id, "op1", "approve", None)
    count, age = open_stats(db)
    assert count == 2
    assert age >= 0
    assert a.created_at is not None
