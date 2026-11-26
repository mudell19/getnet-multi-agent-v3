"""Amount and date rendering in the answer language. Tools return raw values; this renders them."""

from __future__ import annotations

from datetime import date

from getnet_multi_agent.contracts import Lang


def format_amount(cents: int, lang: Lang) -> str:
    """pt: R$ 1.250,00 ; en: R$ 1,250.00"""
    raise NotImplementedError


def format_date(d: date, lang: Lang) -> str:
    """pt: 25/11/2026 ; en: 25 Nov 2026"""
    raise NotImplementedError
