"""Answer-quality checks and fixes enforced by code (constitution principle V)."""

from __future__ import annotations

import re

from getnet_multi_agent.contracts import Lang
from getnet_multi_agent.format.lang import detect_language

MAX_WORDS = 120

_DASHES = "—–"
_DIGIT_RANGE = re.compile(rf"(?<=\d)\s*[{_DASHES}]\s*(?=\d)")
_LINE_DASH = re.compile(rf"^([ \t]*)[{_DASHES}][ \t]+", re.MULTILINE)
_OTHER_DASH = re.compile(rf"[ \t]*[{_DASHES}][ \t]*")
_BULLET = re.compile(r"^([ \t]*)[*•][ \t]+", re.MULTILINE)
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)
_ITALIC = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
_HEADER = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)

_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_AMOUNT = re.compile(r"R\$\s*\d(?:[\d.,]*\d)?")
_AMOUNT_OK = {
    "pt": re.compile(r"R\$ \d{1,3}(\.\d{3})*,\d{2}"),
    "en": re.compile(r"R\$ \d{1,3}(,\d{3})*\.\d{2}"),
}
_MIN_WORDS_FOR_LANG = 6


def word_count(text: str) -> int:
    return len(text.split())


def _tidy(text: str) -> str:
    text = re.sub(r"(?<=\S)[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+,", ",", text)
    text = re.sub(r",(?:\s*,)+", ",", text)
    text = re.sub(r",\s*([.!?;:])", r"\1", text)
    text = re.sub(r"^[ \t]*,[ \t]*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()


def fix_answer(text: str) -> tuple[str, list[str]]:
    """Replace em/en dashes, remove markdown bold and headers. Returns (fixed text, violations)."""
    violations: list[str] = []
    if any(c in text for c in _DASHES):
        violations.append("dash")
        text = _DIGIT_RANGE.sub("-", text)
        text = _LINE_DASH.sub(r"\1- ", text)
        text = _OTHER_DASH.sub(", ", text)
    text = _BULLET.sub(r"\1- ", text)
    if _BOLD.search(text) or _ITALIC.search(text):
        violations.append("bold")
        text = _BOLD.sub(lambda m: m.group(1) or m.group(2), text)
        text = _ITALIC.sub(r"\1", text)
    if _HEADER.search(text):
        violations.append("header")
        text = _HEADER.sub("", text)
    return _tidy(text), violations


def check_answer(text: str, lang: Lang) -> list[str]:
    """Violations left after fixing: dash, bold, iso_date, unformatted_amount, language_mismatch,
    table."""
    violations: list[str] = []
    if any(c in text for c in _DASHES):
        violations.append("dash")
    if "**" in text or "__" in text:
        violations.append("bold")
    if _ISO_DATE.search(text):
        violations.append("iso_date")
    if any(not _AMOUNT_OK[lang].fullmatch(m.group()) for m in _AMOUNT.finditer(text)):
        violations.append("unformatted_amount")
    if word_count(text) >= _MIN_WORDS_FOR_LANG and detect_language(text, default=lang) != lang:
        violations.append("language_mismatch")
    if any(line.count("|") >= 2 for line in text.splitlines()):
        violations.append("table")
    return violations
