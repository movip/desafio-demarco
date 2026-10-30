import copy
import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
import sqlglot
from sqlglot import exp

from demarco.ingestion import InputError
from demarco.reverse_etl import (
    make_plan,
    parse_snapshot,
    save_private_json,
    update_requests,
    verify_after,
)
from demarco.sheets import SheetsClient, SheetsError
from demarco.sheets_cli import run_sheets_sync
from demarco.sources import CALCULATED_COLUMNS, SOURCES

TITLE = "Gestão d'Operações"
HEADERS = next(s.columns for s in SOURCES if s.name == "gestao")


def literal(value):
    return {"numberValue": value} if isinstance(value, (int, float)) else {"stringValue": value}


def cell(value):
    return {"userEnteredValue": literal(value), "effectiveValue": literal(value)}


@pytest.fixture
def raw_sheet():
    header = [cell(name) for name in HEADERS]
    rows = [{"values": header}]
    for i in range(1, 4):
        values = [cell(f"EMP_{i:03d}"), cell(f"Pessoa {i}"), cell("Operações"), cell("Gestor")]
        values += [
            {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0"}}}
            for _ in CALCULATED_COLUMNS
        ]
        values += [cell(45813), cell("S"), cell(f"Conversa {i}\nNão apagar: ação já aplicada.")]
        values[8]["userEnteredFormat"] = {"numberFormat": {"type": "DATE", "pattern": "dd/mm/yyyy"}}
        values[10]["note"] = "Nota manual adicional"
        values[10]["dataValidation"] = {
            "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "Conversa"}]}
        }
        rows.append({"values": values})
    # Um registro não elegível já contém cálculos: precisam permanecer iguais.
    for col, value in zip(range(4, 8), [7, 5, "Recomendação anterior", "2025-01-01"], strict=True):
        rows[3]["values"][col].update(cell(value))
    return {
        "spreadsheetId": "s" * 30,
        "sheets": [
            {
                "properties": {
                    "sheetId": 123,
                    "title": TITLE,
                    "gridProperties": {"rowCount": 100, "columnCount": 11},
                },
                "data": [{"rowData": rows}],
            }
        ],
    }


@pytest.fixture
def records():
    return [
        {
            "ID_Colaborador": "EMP_001",
            "Total_Faltas_Injustificadas": 0,
            "Total_DSR_Perdido": 0,
            "Acao_Disciplinar_Recomendada": "Sem ação requerida",
            "elegivel_reverse_etl": True,
        },
        {
            "ID_Colaborador": "EMP_002",
            "Total_Faltas_Injustificadas": 2,
            "Total_DSR_Perdido": 2,
            "Acao_Disciplinar_Recomendada": "Advertência Escrita",
            "elegivel_reverse_etl": True,
        },
        {
            "ID_Colaborador": "EMP_003",
            "Total_Faltas_Injustificadas": None,
            "Total_DSR_Perdido": None,
            "Acao_Disciplinar_Recomendada": None,
            "elegivel_reverse_etl": False,
            "status_recomendacao": "PENDENTE_VALIDACAO",
        },
    ]


def apply_requests(raw, requests):
    result = copy.deepcopy(raw)
    rows = result["sheets"][0]["data"][0]["rowData"]
    for request in requests:
        update = request["updateCells"]
        assert update["fields"] == "userEnteredValue"
        row, col = update["start"]["rowIndex"], update["start"]["columnIndex"]
        value = copy.deepcopy(update["rows"][0]["values"][0]["userEnteredValue"])
        rows[row]["values"][col]["userEnteredValue"] = value
        rows[row]["values"][col]["effectiveValue"] = value
    return result


def test_only_four_columns_change_and_existing_history_is_preserved(raw_sheet, records):
    before = parse_snapshot(raw_sheet, TITLE)
    plan = make_plan(before, records, "2026-10-29T20:00:00-03:00")
    requests = update_requests(before, plan)
    assert len(requests) == 8
    assert plan["skipped"] == [{"id": "EMP_003", "reason": "PENDENTE_VALIDACAO"}]
    for request in requests:
        assert set(request) == {"updateCells"}
        update = request["updateCells"]
        assert update["start"]["columnIndex"] in {4, 5, 6, 7}
        assert update["start"]["rowIndex"] in {1, 2}
        assert "range" not in update
        assert len(update["rows"]) == len(update["rows"][0]["values"]) == 1
    after_raw = apply_requests(raw_sheet, requests)
    result = verify_after(before, parse_snapshot(after_raw, TITLE), plan)
    assert result["protected_fields_preserved"]
    assert result["manual_filled_cells"] == {
        "Data_Conversa_1on1": 3,
        "Advertencia_Aplicada_SN": 3,
        "Observacoes_Gestor": 3,
    }
    assert (
        after_raw["sheets"][0]["data"][0]["rowData"][3]
        == raw_sheet["sheets"][0]["data"][0]["rowData"][3]
    )


def test_reordered_rows_and_columns_are_matched_by_id_and_header(raw_sheet, records):
    rows = raw_sheet["sheets"][0]["data"][0]["rowData"]
    rows[1:] = reversed(rows[1:])
    for row in rows:
        row["values"] = row["values"][8:] + row["values"][:8]
    before = parse_snapshot(raw_sheet, TITLE)
    plan = make_plan(before, list(reversed(records)), "now")
    after = parse_snapshot(apply_requests(raw_sheet, update_requests(before, plan)), TITLE)
    verify_after(before, after, plan)
    for record in records[:2]:
        row = after.row_by_id[record["ID_Colaborador"]]
        assert after.cells[row, after.headers["Acao_Disciplinar_Recomendada"]][
            "userEnteredValue"
        ] == literal(record["Acao_Disciplinar_Recomendada"])


def test_second_run_has_no_updates_or_new_processing_timestamp(raw_sheet, records):
    before = parse_snapshot(raw_sheet, TITLE)
    plan = make_plan(before, records, "first")
    after_raw = apply_requests(raw_sheet, update_requests(before, plan))
    after = parse_snapshot(after_raw, TITLE)
    second = make_plan(after, records, "later")
    assert second["changes"] == []
    assert set(second["unchanged_ids"]) == {"EMP_001", "EMP_002"}
    assert len(second["skipped"]) == 1


def test_manual_formula_is_preserved_even_if_its_result_recalculates(raw_sheet, records):
    note = raw_sheet["sheets"][0]["data"][0]["rowData"][1]["values"][10]
    note["userEnteredValue"] = {"formulaValue": "=E2"}
    note["effectiveValue"] = {"numberValue": 99}
    before = parse_snapshot(raw_sheet, TITLE)
    plan = make_plan(before, records, "now")
    after_raw = apply_requests(raw_sheet, update_requests(before, plan))
    after_raw["sheets"][0]["data"][0]["rowData"][1]["values"][10]["effectiveValue"] = {
        "numberValue": 0
    }
    assert verify_after(before, parse_snapshot(after_raw, TITLE), plan)[
        "protected_fields_preserved"
    ]


def test_mutation_of_history_is_detected_without_restoring_old_notes(raw_sheet, records):
    before = parse_snapshot(raw_sheet, TITLE)
    plan = make_plan(before, records, "now")
    after_raw = apply_requests(raw_sheet, update_requests(before, plan))
    after_raw["sheets"][0]["data"][0]["rowData"][1]["values"][10].update(cell("Nota alterada"))
    with pytest.raises(InputError, match="Campos protegidos"):
        verify_after(before, parse_snapshot(after_raw, TITLE), plan)
    assert after_raw["sheets"][0]["data"][0]["rowData"][1]["values"][10][
        "userEnteredValue"
    ] == literal("Nota alterada")


@pytest.mark.parametrize("invalid", [None, -1, True, "2"])
def test_invalid_eligible_count_stops_plan(raw_sheet, records, invalid):
    records[0]["Total_DSR_Perdido"] = invalid
    with pytest.raises(InputError, match="Contagem inválida"):
        make_plan(parse_snapshot(raw_sheet, TITLE), records, "now")


def test_duplicate_warehouse_ids_stop_plan(raw_sheet, records):
    with pytest.raises(InputError, match="ID vazio ou duplicado"):
        make_plan(parse_snapshot(raw_sheet, TITLE), records + [records[0]], "now")


def test_missing_worksheet_ids_do_not_create_rows(raw_sheet, records):
    records[0]["ID_Colaborador"] = "EMP_NEW"
    plan = make_plan(parse_snapshot(raw_sheet, TITLE), records, "now")
    assert {"id": "EMP_NEW", "reason": "SEM_LINHA_NA_GESTAO"} in plan["skipped"]
    assert {"id": "EMP_001", "reason": "SEM_RESULTADO_ANALITICO"} in plan["skipped"]


def test_duplicate_sheet_id_is_rejected(raw_sheet):
    rows = raw_sheet["sheets"][0]["data"][0]["rowData"]
    rows[2]["values"][0] = copy.deepcopy(rows[1]["values"][0])
    with pytest.raises(InputError, match="ID vazio ou duplicado"):
        parse_snapshot(raw_sheet, TITLE)


def test_missing_header_is_rejected(raw_sheet):
    raw_sheet["sheets"][0]["data"][0]["rowData"][0]["values"][10] = cell("Outro nome")
    with pytest.raises(InputError, match="Colunas ausentes"):
        parse_snapshot(raw_sheet, TITLE)


def test_nonempty_row_without_id_is_rejected(raw_sheet):
    raw_sheet["sheets"][0]["data"][0]["rowData"][1]["values"][0] = {}
    with pytest.raises(InputError, match="ID vazio ou duplicado"):
        parse_snapshot(raw_sheet, TITLE)


def test_cannot_generate_request_for_manual_column(raw_sheet, records):
    snapshot = parse_snapshot(raw_sheet, TITLE)
    plan = make_plan(snapshot, records, "now")
    plan["changes"][0]["field"] = "Observacoes_Gestor"
    with pytest.raises(InputError, match="fora das colunas"):
        update_requests(snapshot, plan)


def test_private_backup_is_not_overwritten(tmp_path):
    path = tmp_path / "backup.json"
    save_private_json(path, {"manual": "Não apagar"})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        save_private_json(path, {"manual": "outro"})
    assert json.loads(path.read_text())["manual"] == "Não apagar"


def test_sheets_error_identifies_disabled_api():
    from demarco.config import ManagementConfig

    response = Mock(ok=False, status_code=403)
    response.json.return_value = {
        "error": {
            "status": "PERMISSION_DENIED",
            "message": "Disabled",
            "details": [{"reason": "SERVICE_DISABLED"}],
        }
    }
    session = MagicMock()
    session.request.return_value = response
    client = SheetsClient(session, ManagementConfig("s" * 30, TITLE))
    with pytest.raises(SheetsError) as error:
        client.metadata()
    assert error.value.reason == "SERVICE_DISABLED"


class FakeSheetService:
    def __init__(self, raw):
        self.raw = copy.deepcopy(raw)
        self.writes = 0
        self.reads = 0
        self.closed = False
        self.change_on_preflight = False
        self.deny_write = False

    def snapshot(self):
        self.reads += 1
        if self.change_on_preflight and self.reads == 2:
            self.raw["sheets"][0]["data"][0]["rowData"][1]["values"][10].update(
                cell("Edição recente do gestor")
            )
        return copy.deepcopy(self.raw)

    def write_cells(self, requests):
        self.writes += 1
        if self.deny_write:
            raise SheetsError(403, "PERMISSION_DENIED", "Precisa de Editor")
        self.raw = apply_requests(self.raw, requests)
        return {"spreadsheetId": self.raw["spreadsheetId"], "replies": [{} for _ in requests]}

    def close(self):
        self.closed = True


def setup_sync(tmp_path, monkeypatch, raw_sheet, records, execute):
    from demarco.config import CloudConfig, ManagementConfig

    service = FakeSheetService(raw_sheet)
    monkeypatch.setattr(
        "demarco.sheets_cli.cloud_config",
        lambda _: CloudConfig("example-project", "example", "US", 1073741824),
    )
    monkeypatch.setattr(
        "demarco.sheets_cli.management_config", lambda _: ManagementConfig("s" * 30, TITLE)
    )
    monkeypatch.setattr("demarco.sheets_cli.create_sheets_client", lambda *_: service)
    monkeypatch.setattr("demarco.sheets_cli.create_client", lambda *_: MagicMock())
    monkeypatch.setattr(
        "demarco.sheets_cli.run_staging",
        lambda *_: {"job_id": "example-job", "completed": True, "rows": records},
    )
    return service, Namespace(
        env_file=tmp_path / ".env", output_dir=tmp_path / "runs", execute=execute
    )


def test_preview_reads_sources_but_never_writes(tmp_path, monkeypatch, raw_sheet, records):
    service, args = setup_sync(tmp_path, monkeypatch, raw_sheet, records, False)
    assert run_sheets_sync(args) == 0
    assert service.writes == 0
    assert service.raw == raw_sheet
    run = next(args.output_dir.iterdir())
    report = json.loads((run / "report.json").read_text())
    assert report["status"] == "PREVIEW"
    assert report["cells_to_update"] == 8
    assert json.loads((run / "snapshot-before.json").read_text()) == raw_sheet


def test_execution_is_verified_and_rerun_sends_no_second_batch(
    tmp_path, monkeypatch, raw_sheet, records
):
    service, args = setup_sync(tmp_path, monkeypatch, raw_sheet, records, True)
    assert run_sheets_sync(args) == 0
    assert service.writes == 1
    report = json.loads(next(args.output_dir.glob("*/report.json")).read_text())
    assert report["status"] == "UPDATED_AND_VERIFIED"
    assert report["protected_fields_preserved"]
    assert (Path(report["run_directory"]) / "snapshot-after.json").is_file()
    assert run_sheets_sync(args) == 0
    assert service.writes == 1
    reports = [json.loads(p.read_text()) for p in args.output_dir.glob("*/report.json")]
    assert {r["status"] for r in reports} == {"UPDATED_AND_VERIFIED", "NO_CHANGES"}


def test_preflight_detects_changes_and_preserves_recent_notes(
    tmp_path, monkeypatch, raw_sheet, records
):
    service, args = setup_sync(tmp_path, monkeypatch, raw_sheet, records, True)
    service.change_on_preflight = True
    with pytest.raises(InputError, match="planilha mudou"):
        run_sheets_sync(args)
    assert service.writes == 0
    assert (
        json.loads(next(args.output_dir.glob("*/report.json")).read_text())["status"]
        == "ABORTED_CONCURRENT_CHANGE"
    )
    assert service.raw["sheets"][0]["data"][0]["rowData"][1]["values"][10][
        "userEnteredValue"
    ] == literal("Edição recente do gestor")


def test_write_access_failure_keeps_backup_and_never_reports_success(
    tmp_path, monkeypatch, raw_sheet, records
):
    service, args = setup_sync(tmp_path, monkeypatch, raw_sheet, records, True)
    service.deny_write = True
    with pytest.raises(SheetsError):
        run_sheets_sync(args)
    run = next(args.output_dir.iterdir())
    assert (run / "snapshot-before.json").is_file()
    assert (run / "plan.json").is_file()
    assert json.loads((run / "report.json").read_text())["status"] == "WRITE_NOT_CONFIRMED"
    assert service.raw == raw_sheet


def test_rich_text_in_calculated_cell_stops_before_writing(raw_sheet, records):
    raw_sheet["sheets"][0]["data"][0]["rowData"][1]["values"][6]["textFormatRuns"] = [
        {"startIndex": 0, "format": {"bold": True}}
    ]
    before = parse_snapshot(raw_sheet, TITLE)
    with pytest.raises(InputError, match="formatação em trechos"):
        update_requests(before, make_plan(before, records, "now"))


def test_reverse_etl_query_exposes_the_expected_contract_and_only_reads():
    from demarco.bigquery import staging_sql
    from demarco.config import CloudConfig

    root = Path(__file__).resolve().parents[1]
    sql = staging_sql(
        root / "sql/11_reverse_etl_source.sql",
        CloudConfig("example-project", "example", "US", 1073741824),
    )
    query = sqlglot.parse_one(sql, read="bigquery")
    assert isinstance(query, exp.Select)
    aliases = {field.alias_or_name for field in query.expressions}
    assert {"ID_Colaborador", *CALCULATED_COLUMNS[:3], "elegivel_reverse_etl"} <= aliases
    assert {t.name for t in query.find_all(exp.Table)} == {"mart_gestao_colaboradores"}
