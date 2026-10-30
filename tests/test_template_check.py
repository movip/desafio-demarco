import copy
from datetime import datetime
from pathlib import Path

import pytest

from demarco.ingestion import InputError, read_source
from demarco.sources import MANUAL_COLUMNS
from demarco.template_check import MANAGEMENT_SOURCE, compare_template, download_template

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


@pytest.fixture
def reference():
    return read_source(RAW, MANAGEMENT_SOURCE)


def test_comparison_uses_ids_instead_of_row_order(reference):
    online = copy.deepcopy(reference)
    online.records.reverse()
    for record in online.records:
        record.values["Acao_Disciplinar_Recomendada"] = "Texto calculado de exemplo"
        value = record.values["Data_Conversa_1on1"]
        if isinstance(value, datetime):
            record.values["Data_Conversa_1on1"] = value.date().isoformat()
    assert compare_template(reference, online)["matches"]


@pytest.mark.parametrize("field", MANUAL_COLUMNS)
def test_each_manual_field_is_compared_even_if_originally_empty(reference, field):
    online = copy.deepcopy(reference)
    online.records[0].values[field] = "2025-01-01" if field.startswith("Data_") else "Alterado"
    result = compare_template(reference, online)
    assert not result["matches"]
    assert result["differences"][0]["column"] == field


def test_missing_management_row_is_reported(reference):
    online = copy.deepcopy(reference)
    online.records.pop()
    result = compare_template(reference, online)
    assert not result["matches"]
    assert len(result["missing_ids"]) == 1


def test_duplicate_id_stops_comparison(reference):
    online = copy.deepcopy(reference)
    online.records.append(copy.deepcopy(online.records[0]))
    with pytest.raises(InputError, match="vazios ou duplicados"):
        compare_template(reference, online)


def test_invalid_spreadsheet_id_cannot_change_download_host():
    with pytest.raises(InputError, match="ID da planilha inválido"):
        download_template("../../outro-host")
