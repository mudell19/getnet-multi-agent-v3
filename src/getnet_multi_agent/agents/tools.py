"""Support tools over the simulated merchant data. The merchant always comes from the principal."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

from getnet_multi_agent.contracts import Lang, Principal, ToolSpec
from getnet_multi_agent.core.settings import BRT, MERCHANTS_FILE
from getnet_multi_agent.format.money_date import format_amount, format_weekday_date

Period = Literal["yesterday", "today", "last_7_days", "last_30_days", "upcoming"]
PERIODS: tuple[str, ...] = ("yesterday", "today", "last_7_days", "last_30_days", "upcoming")


class Sale(BaseModel):
    sale_date: date
    amount_cents: int
    method: str
    installments: int
    settlement_date: date


class Receivables(BaseModel):
    found: bool
    error: str | None = None
    period: str = ""
    sales: list[Sale] = []
    total_cents: int = 0


class TerminalError(BaseModel):
    type: str
    code: str
    when: datetime
    reason: dict[str, str]
    amount_cents: int | None = None


class Terminal(BaseModel):
    id: str
    model: str
    label: str
    status: str
    last_seen_hours_ago: int
    last_errors: list[TerminalError]
    suggested_actions: dict[str, list[str]]


class TerminalStatus(BaseModel):
    found: bool
    terminals: list[Terminal] = []


def today() -> date:
    return datetime.now(BRT).date()


def add_business_days(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


@lru_cache
def _data() -> dict:
    return json.loads(MERCHANTS_FILE.read_text())


def get_receivables(principal: Principal, period: str = "upcoming") -> Receivables:
    if period not in PERIODS:
        return Receivables(found=True, error=f"invalid period, use one of {', '.join(PERIODS)}")
    m = _data().get(principal.sub)
    if m is None:
        return Receivables(found=False)
    t = today()
    sales = []
    for s in m["sales"]:
        sd = t - timedelta(days=s["days_ago"])
        sales.append(Sale(sale_date=sd, amount_cents=s["amount_cents"], method=s["method"],
                          installments=s["installments"], settlement_date=add_business_days(sd, 2)))
    keep = {
        "yesterday": lambda s: s.sale_date == t - timedelta(days=1),
        "today": lambda s: s.sale_date == t,
        "last_7_days": lambda s: s.sale_date >= t - timedelta(days=7),
        "last_30_days": lambda s: s.sale_date >= t - timedelta(days=30),
        "upcoming": lambda s: s.settlement_date >= t,
    }[period]
    chosen = [s for s in sales if keep(s)]
    return Receivables(found=True, period=period, sales=chosen,
                       total_cents=sum(s.amount_cents for s in chosen))


def get_terminal_status(principal: Principal) -> TerminalStatus:
    m = _data().get(principal.sub)
    if m is None:
        return TerminalStatus(found=False)
    t = datetime.now(BRT)
    terms = []
    for x in m["terminals"]:
        errs = []
        for e in x["last_errors"]:
            hh, mm = (int(v) for v in e["hour"].split(":"))
            when = (t - timedelta(days=e["days_ago"])).replace(hour=hh, minute=mm, second=0,
                                                              microsecond=0)
            errs.append(TerminalError(type=e["type"], code=e["code"], when=when,
                                      reason=e["reason"], amount_cents=e.get("amount_cents")))
        terms.append(Terminal(id=x["id"], model=x["model"], label=x["label"], status=x["status"],
                              last_seen_hours_ago=x["last_seen_hours_ago"], last_errors=errs,
                              suggested_actions=x["suggested_actions"]))
    return TerminalStatus(found=True, terminals=terms)


# ------------------------------------------------------------- rendering for the model

_METHOD = {"pt": {"credit": "crédito", "debit": "débito", "pix": "Pix"},
           "en": {"credit": "credit", "debit": "debit", "pix": "Pix"}}


def _when(dt: datetime, lang: Lang) -> str:
    d = format_weekday_date(dt.date(), lang)
    return f"{d} {'às' if lang == 'pt' else 'at'} {dt:%H:%M}"


def render_receivables(r: Receivables, lang: Lang) -> dict:
    if not r.found:
        return {"merchant_found": False, "note": "no account data found for this merchant"}
    if r.error:
        return {"error": r.error}
    return {
        "today": format_weekday_date(today(), lang),
        "period": r.period,
        "sales": [{"sale_date": format_weekday_date(s.sale_date, lang),
                   "amount": format_amount(s.amount_cents, lang),
                   "payment": _METHOD[lang].get(s.method, s.method),
                   "installments": s.installments,
                   "deposit_date": format_weekday_date(s.settlement_date, lang),
                   "already_deposited": s.settlement_date < today()} for s in r.sales],
        "total": format_amount(r.total_cents, lang),
        "deposit_rule": "sales are deposited in the Getnet account 2 business days after the sale",
    }


def render_terminals(r: TerminalStatus, lang: Lang) -> dict:
    if not r.found:
        return {"merchant_found": False, "note": "no account data found for this merchant"}
    out = []
    for t in r.terminals:
        out.append({
            "machine": f"{t.model} ({t.label})",
            "status": t.status,
            "problems": [{"type": e.type, "when": _when(e.when, lang),
                          "what_happened": e.reason.get(lang, ""),
                          **({"amount": format_amount(e.amount_cents, lang)}
                             if e.amount_cents else {})} for e in t.last_errors],
            "what_to_do": t.suggested_actions.get(lang, []),
        })
    return {"machines": out}


def facts_from_terminals(r: TerminalStatus) -> dict:
    errs = [e for t in r.terminals for e in t.last_errors]
    return {
        "terminal_offline": any(t.status == "offline" for t in r.terminals),
        "connectivity_error": any(e.type == "connectivity" for e in errs),
        "decline": any(e.type == "decline" for e in errs),
    }


TOOL_SPECS = [
    ToolSpec(
        name="get_receivables",
        description="Sales of this merchant with amounts and the day each will be deposited.",
        parameters={"type": "object", "properties": {"period": {
            "type": "string", "enum": list(PERIODS),
            "description": "Which sales: yesterday, today, last_7_days, last_30_days, or "
                           "upcoming (not yet deposited)."}}, "required": ["period"]},
    ),
    ToolSpec(
        name="get_terminal_status",
        description="Status of this merchant's card machines: connectivity, recent errors "
                    "including declined transactions with the reason, and what to do.",
        parameters={"type": "object", "properties": {}},
    ),
]
