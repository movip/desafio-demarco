from datetime import date, datetime
from decimal import Decimal

import pytest

from demarco.parsing import calendar_date, identifier, number


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("R$ 2.500,50", "2500.50"),
        ("2500,50", "2500.50"),
        (2500.5, "2500.5"),
        ("2500.50", "2500.50"),
        ("-0,25", "-0.25"),
    ],
)
def test_numbers_from_brazilian_and_excel_formats(raw, expected):
    assert number(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["A combinar", "R$ 2.50,00", "12 reais", True, float("nan")])
def test_invalid_number_cannot_become_zero(raw):
    with pytest.raises(ValueError):
        number(raw)


@pytest.mark.parametrize("raw", [None, " NULL ", "", "N/A"])
def test_nulls_remain_unknown(raw):
    assert number(raw) is None
    assert calendar_date(raw) is None
    assert identifier(raw) is None


@pytest.mark.parametrize(
    "raw",
    [45809, "01/06/2025", "2025-06-01", date(2025, 6, 1), datetime(2025, 6, 1)],
)
def test_excel_serial_and_text_dates(raw):
    assert calendar_date(raw) == date(2025, 6, 1)


def test_invalid_date_is_not_inferred():
    with pytest.raises(ValueError):
        calendar_date("31/06/2025")
