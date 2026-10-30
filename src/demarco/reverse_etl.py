"""Plano de escrita por ID e célula, com preservação verificável dos demais dados."""

import copy
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from demarco.ingestion import InputError, encode_json
from demarco.parsing import identifier
from demarco.sources import CALCULATED_COLUMNS, MANUAL_COLUMNS, SOURCES

SOURCE = next(source for source in SOURCES if source.name == "gestao")
ALLOWED_ACTIONS = {
    "Sem ação requerida",
    "Alinhamento em 1-on-1",
    "Advertência Escrita",
    "Suspensão Disciplinar (1 a 3 dias)",
}


@dataclass
class Snapshot:
    spreadsheet_id: str
    sheet_id: int
    title: str
    properties: dict[str, Any]
    headers: dict[str, int]
    row_by_id: dict[str, int]
    cells: dict[tuple[int, int], dict[str, Any]]
    raw: dict[str, Any]


def cell_value(cell: dict[str, Any]) -> Any:
    value = cell.get("effectiveValue", cell.get("userEnteredValue", {}))
    return next(
        (value[key] for key in ("stringValue", "numberValue", "boolValue") if key in value), None
    )


def parse_snapshot(raw: dict[str, Any], title: str) -> Snapshot:
    raw = copy.deepcopy(raw)
    matches = [sheet for sheet in raw.get("sheets", []) if sheet["properties"]["title"] == title]
    if len(matches) != 1:
        raise InputError("A aba configurada não foi encontrada de forma única.")
    sheet = matches[0]
    cells = {}
    for grid in sheet.get("data", []):
        for row_index, row in enumerate(grid.get("rowData", []), grid.get("startRow", 0)):
            for col_index, cell in enumerate(row.get("values", []), grid.get("startColumn", 0)):
                if cell:
                    cells[row_index, col_index] = cell
    headers = {}
    for (row, col), cell in sorted(cells.items()):
        value = cell_value(cell)
        if row != 0 or value is None or value == "":
            continue
        if "formulaValue" in cell.get("userEnteredValue", {}):
            raise InputError("Cabeçalhos devem ser textos estáveis, sem fórmulas.")
        name = str(value).strip()
        if name in headers:
            raise InputError(f"Cabeçalho duplicado: {name}")
        headers[name] = col
    missing = set(SOURCE.columns) - headers.keys()
    if missing:
        raise InputError(f"Colunas ausentes na gestão: {', '.join(sorted(missing))}")
    rows = {}
    for row_index in sorted({r for r, _ in cells if r > 0}):
        values = [cell_value(cell) for (r, _), cell in cells.items() if r == row_index]
        if all(value in (None, "") for value in values):
            continue
        key_cell = cells.get((row_index, headers["ID_Colaborador"]), {})
        if "formulaValue" in key_cell.get("userEnteredValue", {}):
            raise InputError(f"ID na linha {row_index + 1} depende de fórmula.")
        key = identifier(cell_value(key_cell))
        if key is None or key in rows:
            raise InputError(f"ID vazio ou duplicado na linha {row_index + 1}.")
        rows[key] = row_index
    return Snapshot(
        raw["spreadsheetId"],
        sheet["properties"]["sheetId"],
        title,
        sheet["properties"],
        headers,
        rows,
        cells,
        raw,
    )


def protected_state(snapshot: Snapshot, changed_cells: set[tuple[int, int]]) -> dict[str, Any]:
    cells = {}
    for position, cell in snapshot.cells.items():
        # Valores calculados de fórmulas podem recalcular; sua expressão original é protegida.
        protected = {k: copy.deepcopy(v) for k, v in cell.items() if k != "effectiveValue"}
        if position in changed_cells:
            protected.pop("userEnteredValue", None)
        if protected:
            cells[f"{position[0]}:{position[1]}"] = protected
    return {
        "spreadsheet_id": snapshot.spreadsheet_id,
        "properties": snapshot.properties,
        "headers": snapshot.headers,
        "rows": snapshot.row_by_id,
        "cells": cells,
    }


def fingerprint(value: Any) -> str:
    return hashlib.sha256(encode_json(value).encode("utf-8")).hexdigest()


def make_plan(
    snapshot: Snapshot, records: list[dict[str, Any]], processed_at: str
) -> dict[str, Any]:
    changes, skipped, unchanged = [], [], []
    seen = set()
    for record in records:
        key = identifier(record.get("ID_Colaborador"))
        if key is None or key in seen:
            raise InputError("O resultado analítico contém ID vazio ou duplicado.")
        seen.add(key)
        if record.get("elegivel_reverse_etl") is not True:
            skipped.append({"id": key, "reason": record.get("status_recomendacao", "NAO_ELEGIVEL")})
            continue
        if key not in snapshot.row_by_id:
            skipped.append({"id": key, "reason": "SEM_LINHA_NA_GESTAO"})
            continue
        row = snapshot.row_by_id[key]
        desired = {}
        for field in CALCULATED_COLUMNS[:2]:
            value = record.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise InputError(f"Contagem inválida para {key}: {field}.")
            desired[field] = {"numberValue": value}
        action = record.get("Acao_Disciplinar_Recomendada")
        if action not in ALLOWED_ACTIONS:
            raise InputError(f"Ação fora do contrato para {key}.")
        desired[CALCULATED_COLUMNS[2]] = {"stringValue": action}
        business_changes = []
        for field, value in desired.items():
            col = snapshot.headers[field]
            old = snapshot.cells.get((row, col), {}).get("userEnteredValue", {})
            if old != value:
                business_changes.append(
                    {
                        "id": key,
                        "row": row,
                        "column": col,
                        "field": field,
                        "before": old,
                        "after": value,
                    }
                )
        time_field = CALCULATED_COLUMNS[3]
        old_time = snapshot.cells.get((row, snapshot.headers[time_field]), {}).get(
            "userEnteredValue", {}
        )
        if business_changes or not old_time:
            changes.extend(business_changes)
            changes.append(
                {
                    "id": key,
                    "row": row,
                    "column": snapshot.headers[time_field],
                    "field": time_field,
                    "before": old_time,
                    "after": {"stringValue": processed_at},
                }
            )
        else:
            unchanged.append(key)
    for key in sorted(snapshot.row_by_id.keys() - seen):
        skipped.append({"id": key, "reason": "SEM_RESULTADO_ANALITICO"})
    return {
        "spreadsheet_id": snapshot.spreadsheet_id,
        "sheet_id": snapshot.sheet_id,
        "worksheet": snapshot.title,
        "processed_at": processed_at,
        "sheet_rows": len(snapshot.row_by_id),
        "source_rows": len(records),
        "updated_ids": sorted({change["id"] for change in changes}),
        "changes": changes,
        "skipped": skipped,
        "unchanged_ids": unchanged,
        "baseline_sha256": fingerprint(protected_state(snapshot, set())),
    }


def update_requests(snapshot: Snapshot, plan: dict[str, Any]) -> list[dict[str, Any]]:
    if plan["spreadsheet_id"] != snapshot.spreadsheet_id or plan["sheet_id"] != snapshot.sheet_id:
        raise InputError("Plano aponta para outra planilha ou aba.")
    requests = []
    for change in plan["changes"]:
        if change["field"] not in CALCULATED_COLUMNS:
            raise InputError("Tentativa de escrever fora das colunas calculadas.")
        if (
            snapshot.headers[change["field"]] != change["column"]
            or snapshot.row_by_id[change["id"]] != change["row"]
        ):
            raise InputError("Endereço da célula não corresponde ao ID e cabeçalho do plano.")
        if snapshot.cells.get((change["row"], change["column"]), {}).get("textFormatRuns"):
            raise InputError(
                "Célula calculada com formatação em trechos exige revisão antes da escrita."
            )
        requests.append(
            {
                "updateCells": {
                    "start": {
                        "sheetId": snapshot.sheet_id,
                        "rowIndex": change["row"],
                        "columnIndex": change["column"],
                    },
                    "rows": [{"values": [{"userEnteredValue": change["after"]}]}],
                    "fields": "userEnteredValue",
                }
            }
        )
    return requests


def verify_after(before: Snapshot, after: Snapshot, plan: dict[str, Any]) -> dict[str, Any]:
    allowed = {(change["row"], change["column"]) for change in plan["changes"]}
    protected_before = fingerprint(protected_state(before, allowed))
    protected_after = fingerprint(protected_state(after, allowed))
    if protected_before != protected_after:
        raise InputError(
            "Campos protegidos ou estrutura mudaram durante a atualização; consulte os backups."
        )
    for change in plan["changes"]:
        actual = after.cells.get((change["row"], change["column"]), {}).get("userEnteredValue", {})
        if actual != change["after"]:
            raise InputError(f"Valor escrito não confere para {change['id']} / {change['field']}.")
    return {
        "protected_fields_preserved": True,
        "values_verified": len(plan["changes"]),
        "protected_sha256": protected_after,
        "manual_filled_cells": {
            field: sum(
                cell_value(after.cells.get((row, after.headers[field]), {})) not in (None, "")
                for row in after.row_by_id.values()
            )
            for field in MANUAL_COLUMNS
        },
    }


def save_private_json(path: Path, value: Any) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(encode_json(value) + "\n")
