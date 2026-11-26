"""Amount and date rendering in the answer language. Tools return raw values; this renders them."""

from __future__ import annotations

from datetime import date

from getnet_multi_agent.contracts import Lang

_EN_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_EN_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_PT_WEEKDAYS = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado",
    "domingo",
)


def format_amount(cents: int, lang: Lang) -> str:
    """pt: R$ 1.250,00 ; en: R$ 1,250.00 ; negatives get a leading minus: -R$ 10,00"""
    sign = "-" if cents < 0 else ""
    reais, rest = divmod(abs(cents), 100)
    body = f"{reais:,}.{rest:02d}"
    if lang == "pt":
        body = body.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{sign}R$ {body}"


def format_date(d: date, lang: Lang) -> str:
    """pt: 25/11/2026 ; en: 25 Nov 2026"""
    if lang == "pt":
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    return f"{d.day} {_EN_MONTHS[d.month - 1]} {d.year}"


def format_weekday_date(d: date, lang: Lang) -> str:
    """pt: sexta-feira, 27/11/2026 ; en: Friday, 27 Nov 2026"""
    names = _PT_WEEKDAYS if lang == "pt" else _EN_WEEKDAYS
    return f"{names[d.weekday()]}, {format_date(d, lang)}"
