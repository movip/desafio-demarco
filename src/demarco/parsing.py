"""Conversões para diagnóstico; os valores brutos não são substituídos."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl.utils.datetime import from_excel

NULL_TEXTS = {"", "NULL", "NONE", "NAN", "N/A"}


def is_null(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().upper() in NULL_TEXTS)


def identifier(value: Any) -> str | None:
    return None if is_null(value) else str(value).strip().upper()


def number(value: Any) -> Decimal | None:
    if is_null(value):
        return None
    if isinstance(value, bool):
        raise ValueError("Booleano não é uma medida numérica.")
    text = str(value).strip().replace("R$", "").strip()
    if isinstance(value, str):
        if "," in text:
            if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+),\d+", text):
                raise ValueError(f"Número inválido: {value!r}")
            text = text.replace(".", "").replace(",", ".")
        elif not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
            raise ValueError(f"Número inválido: {value!r}")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Número inválido: {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"Número não finito: {value!r}")
    return result


def calendar_date(value: Any) -> date | None:
    if is_null(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = from_excel(value)
        if isinstance(result, datetime):
            return result.date()
        raise ValueError(f"Serial sem data válida: {value!r}")
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value).strip(), pattern).date()
        except ValueError:
            continue
    raise ValueError(f"Data inválida: {value!r}")
