"""Detection and masking of card numbers, CPFs and other merchants' ids."""

from __future__ import annotations

import json
import re
from functools import lru_cache

from getnet_multi_agent.contracts import Principal
from getnet_multi_agent.core.settings import MERCHANTS_FILE

_RUN = re.compile(r"(?<!\d)\d+(?:[ -]\d+)*(?!\d)")
_GROUP = re.compile(r"\d+")
_CPF = re.compile(r"(?<![\d.])(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?![\d-])")
_MERCHANT = re.compile(r"\bcliente\d+\b", re.IGNORECASE)


def luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def valid_cpf(text: str) -> bool:
    d = [int(c) for c in re.sub(r"\D", "", text)]
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        check = sum(d[i] * (n + 1 - i) for i in range(n)) * 10 % 11 % 10
        if check != d[n]:
            return False
    return True


def find_cards(text: str) -> list[tuple[int, int, str]]:
    """(start, end, digits) of Luhn-valid 13 to 19 digit numbers, groups split by space or dash."""
    found: list[tuple[int, int, str]] = []
    for run in _RUN.finditer(text):
        groups = [(run.start() + g.start(), run.start() + g.end(), g.group())
                  for g in _GROUP.finditer(run.group())]
        i = 0
        while i < len(groups):
            digits, hit = "", None
            for j in range(i, len(groups)):
                digits += groups[j][2]
                if len(digits) > 19:
                    break
                if len(digits) >= 13 and luhn(digits):
                    hit = (groups[i][0], groups[j][1], digits, j)
            if hit:
                found.append(hit[:3])
                i = hit[3] + 1
            else:
                i += 1
    return found


def find_cpfs(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _CPF.finditer(text) if valid_cpf(m.group())]


@lru_cache
def _known_merchants() -> frozenset[str]:
    try:
        data = json.loads(MERCHANTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    return frozenset(k.lower() for k in data) if isinstance(data, dict) else frozenset()


def other_merchant_ids(text: str, own: str) -> list[str]:
    own = own.lower()
    ids = {m.group().lower() for m in _MERCHANT.finditer(text)}
    low = text.lower()
    ids |= {k for k in _known_merchants() if re.search(rf"\b{re.escape(k)}\b", low)}
    return sorted(i for i in ids if i != own)


def mask(text: str) -> str:
    spans = [(s, e, f"[card ****{d[-4:]}]") for s, e, d in find_cards(text)]
    spans += [(s, e, "[cpf ***]") for s, e in find_cpfs(text)
              if not any(s < ce and cs < e for cs, ce, _ in spans)]
    for s, e, rep in sorted(spans, reverse=True):
        text = text[:s] + rep + text[e:]
    return text


def check_final(text: str, principal: Principal) -> list[str]:
    violations = []
    if find_cards(text):
        violations.append("card")
    if find_cpfs(text):
        violations.append("cpf")
    if other_merchant_ids(text, principal.sub):
        violations.append("other_merchant")
    return violations
