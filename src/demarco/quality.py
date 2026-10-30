"""Diagnóstico reproduzível; identifica problemas sem escolher correções de negócio."""

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from demarco.ingestion import Table, encode_json
from demarco.parsing import calendar_date, identifier, is_null, number
from demarco.sources import CALCULATED_COLUMNS, MANUAL_COLUMNS

START = date(2025, 6, 1)
END = date(2025, 8, 31)
DATE_COLUMNS = {
    "colaboradores": ("data_admissao", "data_desligamento"),
    "ponto": ("data_registro",),
    "gestao": ("Data_Conversa_1on1", "Data_Ultimo_Processamento"),
}
NUMBER_COLUMNS = {
    "colaboradores": ("salario_mensal",),
    "escalas": ("horas_diarias", "horas_sabado", "divisor_folha"),
    "ponto": ("jornada_esperada_horas", "horas_trabalhadas", "flag_dsr"),
}
REQUIRED_VALUES = {
    "colaboradores": ("id_colaborador", "nome", "salario_mensal", "id_escala", "data_admissao"),
    "escalas": (
        "id_escala",
        "dias_trabalho",
        "dia_dsr",
        "horas_diarias",
        "horas_sabado",
        "divisor_folha",
    ),
    "ponto": (
        "id_colaborador",
        "data_registro",
        "jornada_esperada_horas",
        "horas_trabalhadas",
        "flag_dsr",
    ),
    "gestao": ("ID_Colaborador",),
}


def diagnose(tables: dict[str, Table]) -> dict[str, Any]:
    issues = []
    profiles = {}
    parsed: dict[str, list[dict[str, Any]]] = {}

    def issue(code: str, table: str, rows: list[int], detail: str) -> None:
        issues.append({"code": code, "table": table, "source_rows": rows, "detail": detail})

    for name, table in tables.items():
        exact = Counter(encode_json(r.values) for r in table.records)
        grouped = defaultdict(list)
        parsed[name] = []
        for record in table.records:
            values = record.values.copy()
            for field in REQUIRED_VALUES[name]:
                if is_null(values[field]):
                    issue("required_value_missing", name, [record.row], field)
            converters = {
                **dict.fromkeys(DATE_COLUMNS.get(name, ()), calendar_date),
                **dict.fromkeys(NUMBER_COLUMNS.get(name, ()), number),
            }
            for field, converter in converters.items():
                try:
                    values[field] = converter(values[field])
                except (ValueError, OverflowError):
                    values[field] = None
                    issue("invalid_value", name, [record.row], field)
            key = tuple(identifier(values[field]) for field in table.source.key)
            grouped[key].append(record)
            values["_source_row"] = record.row
            parsed[name].append(values)
            for field, value in record.values.items():
                if isinstance(value, str) and any(mark in value for mark in ("Ã", "Â", "\ufffd")):
                    issue("possible_encoding_error", name, [record.row], field)
        for key, records in grouped.items():
            if any(part is None for part in key):
                issue("missing_key", name, [r.row for r in records], "Chave incompleta.")
            if len(records) > 1:
                distinct = {encode_json(r.values) for r in records}
                code = "conflicting_key" if len(distinct) > 1 else "duplicate_key"
                issue(
                    code, name, [r.row for r in records], "Chave não única; nenhuma linha removida."
                )
        profiles[name] = {
            "filename": table.source.filename,
            "sheet": table.sheet,
            "sha256": table.sha256,
            "rows": len(table.records),
            "blank_rows_skipped": table.skipped_blank_rows,
            "distinct_keys": len(grouped),
            "exact_duplicate_extra_rows": sum(count - 1 for count in exact.values()),
            "repeated_keys": sum(len(group) > 1 for group in grouped.values()),
            "conflicting_keys": sum(
                len({encode_json(r.values) for r in group}) > 1 for group in grouped.values()
            ),
            "columns": {
                field: {
                    "nulls": sum(is_null(r.values[field]) for r in table.records),
                    "types": dict(Counter(type(r.values[field]).__name__ for r in table.records)),
                }
                for field in table.source.columns
            },
        }

    employees = defaultdict(list)
    for row in parsed["colaboradores"]:
        employees[identifier(row["id_colaborador"])].append(row)
    shifts = {identifier(row["id_escala"]) for row in parsed["escalas"]}
    for row in parsed["colaboradores"]:
        line = [row["_source_row"]]
        if identifier(row["id_escala"]) not in shifts and not is_null(row["id_escala"]):
            issue("unknown_shift", "colaboradores", line, "Escala sem correspondência.")
        if row["salario_mensal"] is not None and row["salario_mensal"] <= 0:
            issue("nonpositive_salary", "colaboradores", line, "Salário não positivo.")
        if row["data_admissao"] and row["data_desligamento"]:
            if row["data_admissao"] > row["data_desligamento"]:
                issue(
                    "invalid_employment_dates", "colaboradores", line, "Admissão após desligamento."
                )

    dates = []
    for row in parsed["ponto"]:
        line = [row["_source_row"]]
        employee_id = identifier(row["id_colaborador"])
        if employee_id not in employees:
            issue("unknown_employee", "ponto", line, "ID sem correspondência no cadastro.")
        day = row["data_registro"]
        if day is not None:
            dates.append(day)
            if not START <= day <= END:
                issue("outside_analysis_period", "ponto", line, "Data fora de jun–ago/2025.")
            candidates = employees.get(employee_id, [])
            # Sem escolher arbitrariamente uma versão do cadastro repetido.
            if candidates and all(
                candidate["data_admissao"] is not None for candidate in candidates
            ):
                active = any(
                    candidate["data_admissao"] <= day
                    and (
                        candidate["data_desligamento"] is None
                        or day <= candidate["data_desligamento"]
                    )
                    for candidate in candidates
                )
                if not active:
                    issue("outside_employment", "ponto", line, "Ponto fora do vínculo informado.")
        for field in ("jornada_esperada_horas", "horas_trabalhadas"):
            value = row[field]
            if value is not None and not Decimal(0) <= value <= Decimal(24):
                issue("hours_out_of_range", "ponto", line, field)
        flag = row["flag_dsr"]
        if flag is not None and flag not in (Decimal(0), Decimal(1)):
            issue("invalid_dsr_flag", "ponto", line, "Flag deve ser 0 ou 1.")
        expected = row["jornada_esperada_horas"]
        if flag == 1 and expected is not None and expected > 0:
            issue("dsr_with_expected_hours", "ponto", line, "DSR com jornada esperada positiva.")
        code = identifier(row["codigo_abono"])
        if code not in {None, "ATESTADO MEDICO", "FOLGA_COMPENSATORIA", "DECLARACAO_HORAS"}:
            issue("unknown_allowance_code", "ponto", line, "Código de abono não mapeado.")
        if code == "DECLARACAO_HORAS":
            issue("allowance_duration_unknown", "ponto", line, "Declaração sem duração informada.")

    for row in parsed["escalas"]:
        line = [row["_source_row"]]
        divisor = row["divisor_folha"]
        if divisor is not None and divisor <= 0:
            issue("nonpositive_divisor", "escalas", line, "Divisor deve ser positivo.")
        for field in ("horas_diarias", "horas_sabado"):
            if row[field] is not None and not Decimal(0) <= row[field] <= Decimal(24):
                issue("hours_out_of_range", "escalas", line, field)
        shift_id = identifier(row["id_escala"])
        if shift_id in {"ESC_40H", "ESC_44H", "ESC_36H_NOT"}:
            days = str(row["dias_trabalho"]).strip().upper().split(",")
            if row["horas_diarias"] is not None and row["horas_sabado"] is not None:
                total = sum(
                    (row["horas_sabado"] if d == "SAB" else row["horas_diarias"] for d in days),
                    Decimal(0),
                )
                declared = Decimal(shift_id.split("_")[1].split("H")[0])
                if abs(total - declared) > Decimal("0.000001"):
                    issue(
                        "weekly_hours_mismatch",
                        "escalas",
                        line,
                        f"Declarado: {declared}h; soma diária: {total.quantize(Decimal('0.01'))}h.",
                    )

    for row in parsed["gestao"]:
        if identifier(row["ID_Colaborador"]) not in employees:
            issue("unknown_employee", "gestao", [row["_source_row"]], "ID sem cadastro.")

    point_ids = {identifier(row["id_colaborador"]) for row in parsed["ponto"]}
    management_ids = {identifier(row["ID_Colaborador"]) for row in parsed["gestao"]}
    manual = {
        field: sum(not is_null(r.values[field]) for r in tables["gestao"].records)
        for field in MANUAL_COLUMNS
    }
    return {
        "schema_version": 1,
        "period": {"start": START.isoformat(), "end": END.isoformat()},
        "tables": profiles,
        "reconciliation": {
            "point_ids": len(point_ids),
            "management_ids": len(management_ids),
            "point_ids_without_registration": len(point_ids - employees.keys()),
            "management_ids_without_registration": len(management_ids - employees.keys()),
            "point_ids_without_management_row": len(point_ids - management_ids),
            "registration_ids_without_point": len(employees.keys() - point_ids),
            "point_date_min": min(dates).isoformat() if dates else None,
            "point_date_max": max(dates).isoformat() if dates else None,
        },
        "management": {
            "manual_filled_cells": manual,
            "calculated_columns": list(CALCULATED_COLUMNS),
            "manual_columns": list(MANUAL_COLUMNS),
        },
        "issue_counts": dict(sorted(Counter(i["code"] for i in issues).items())),
        "issues": issues,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Diagnóstico das entradas",
        "",
        "Gerado pelo comando `demarco diagnose`. Nenhum dado de origem foi alterado.",
        "",
        "Os problemas listados não são faltas nem descontos calculados.",
        "",
        "| Fonte | Linhas | Chaves distintas | Duplicatas exatas | Chaves conflitantes |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, profile in report["tables"].items():
        lines.append(
            f"| {name} | {profile['rows']} | {profile['distinct_keys']} | "
            f"{profile['exact_duplicate_extra_rows']} | {profile['conflicting_keys']} |"
        )
    lines += [
        "",
        "## Ocorrências por regra",
        "",
        "Contagens por ocorrência; grupos duplicados contam uma vez por chave.",
        "",
    ]
    lines += [f"- `{code}`: {count}" for code, count in report["issue_counts"].items()]
    lines += ["", "## Reconciliação", ""]
    lines += [f"- `{key}`: {value}" for key, value in report["reconciliation"].items()]
    lines += ["", "## Histórico manual existente", ""]
    lines += [
        f"- `{field}`: {count} células preenchidas"
        for field, count in report["management"]["manual_filled_cells"].items()
    ]
    lines += [
        "",
        "Consulte `quality.json` para arquivo, hash e linhas Excel de cada ocorrência.",
        "",
    ]
    return "\n".join(lines)
