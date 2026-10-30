import copy
from pathlib import Path

import pytest

from demarco.ingestion import Record, Table, read_source
from demarco.quality import diagnose
from demarco.sources import SOURCES

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


@pytest.fixture
def tables():
    return {source.name: read_source(RAW, source) for source in SOURCES}


def test_received_inputs_have_reproducible_diagnosis_and_are_not_mutated(tables):
    before = copy.deepcopy(tables)
    report = diagnose(tables)
    assert {name: t["rows"] for name, t in report["tables"].items()} == {
        "colaboradores": 46,
        "escalas": 4,
        "ponto": 3779,
        "gestao": 40,
    }
    point = report["tables"]["ponto"]
    assert point["exact_duplicate_extra_rows"] == 82
    assert point["conflicting_keys"] == 10
    assert point["repeated_keys"] == 92
    assert point["distinct_keys"] == 3687
    assert report["management"]["manual_filled_cells"] == {
        "Data_Conversa_1on1": 7,
        "Advertencia_Aplicada_SN": 9,
        "Observacoes_Gestor": 10,
    }
    assert report["reconciliation"]["point_date_min"] == "2025-06-01"
    assert report["reconciliation"]["point_date_max"] == "2025-08-31"
    assert report["issue_counts"]["hours_out_of_range"] == 1
    assert report["issue_counts"]["dsr_with_expected_hours"] == 3
    assert report["issue_counts"]["weekly_hours_mismatch"] == 1
    assert tables == before
    assert diagnose(tables) == report


def test_same_employee_and_date_with_different_hours_is_conflict(tables):
    source = tables["ponto"].source
    values = {
        "data_registro": "2025-06-02",
        "id_colaborador": "UNKNOWN",
        "jornada_esperada_horas": 8,
        "horas_trabalhadas": 8,
        "flag_dsr": 0,
        "codigo_abono": None,
    }
    tables["ponto"] = Table(
        source,
        "Sheet",
        "hash",
        [
            Record(2, values),
            Record(3, {**values, "horas_trabalhadas": 0}),
            Record(4, values.copy()),
        ],
        0,
    )
    report = diagnose(tables)
    assert report["tables"]["ponto"]["exact_duplicate_extra_rows"] == 1
    assert report["tables"]["ponto"]["conflicting_keys"] == 1
    issue = next(
        i for i in report["issues"] if i["table"] == "ponto" and i["code"] == "conflicting_key"
    )
    assert issue["source_rows"] == [2, 3, 4]
    assert report["issue_counts"]["unknown_employee"] == 3


def test_bad_date_or_salary_is_reported_with_original_row(tables):
    row = tables["colaboradores"].records[0]
    row.values["data_admissao"] = "31/02/2025"
    row.values["salario_mensal"] = "A combinar"
    report = diagnose(tables)
    fields = {
        i["detail"]
        for i in report["issues"]
        if i["table"] == "colaboradores"
        and i["code"] == "invalid_value"
        and i["source_rows"] == [row.row]
    }
    assert fields == {"data_admissao", "salario_mensal"}
    assert row.values["salario_mensal"] == "A combinar"
