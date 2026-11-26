from datetime import date

import pytest

from getnet_multi_agent.format.money_date import format_amount, format_date, format_weekday_date


@pytest.mark.parametrize(
    ("cents", "pt", "en"),
    [
        (125000, "R$ 1.250,00", "R$ 1,250.00"),
        (5, "R$ 0,05", "R$ 0.05"),
        (99, "R$ 0,99", "R$ 0.99"),
        (123456789, "R$ 1.234.567,89", "R$ 1,234,567.89"),
        (100000, "R$ 1.000,00", "R$ 1,000.00"),
        (0, "R$ 0,00", "R$ 0.00"),
        (-1000, "-R$ 10,00", "-R$ 10.00"),
    ],
)
def test_fr027_format_amount(cents, pt, en):
    assert format_amount(cents, "pt") == pt
    assert format_amount(cents, "en") == en


def test_fr027_format_date():
    assert format_date(date(2026, 11, 25), "pt") == "25/11/2026"
    assert format_date(date(2026, 11, 25), "en") == "25 Nov 2026"
    assert format_date(date(2026, 1, 5), "pt") == "05/01/2026"
    assert format_date(date(2026, 1, 5), "en") == "5 Jan 2026"


def test_fr027_format_weekday_date():
    assert format_weekday_date(date(2026, 11, 27), "pt") == "sexta-feira, 27/11/2026"
    assert format_weekday_date(date(2026, 11, 27), "en") == "Friday, 27 Nov 2026"
    assert format_weekday_date(date(2026, 11, 29), "pt") == "domingo, 29/11/2026"
