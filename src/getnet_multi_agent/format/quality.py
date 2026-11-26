"""Answer-quality checks and fixes enforced by code (constitution principle V)."""

from __future__ import annotations

from getnet_multi_agent.contracts import Lang


def fix_answer(text: str) -> tuple[str, list[str]]:
    """Replace em/en dashes and remove markdown bold. Returns (fixed text, violations found)."""
    raise NotImplementedError


def check_answer(text: str, lang: Lang) -> list[str]:
    """Violations left after fixing: iso_date, unformatted_amount, language_mismatch, dash, bold."""
    raise NotImplementedError
