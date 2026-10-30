"""Conferência pública e somente de leitura do template convertido em Google Sheets."""

import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.request import urlopen

from demarco.ingestion import InputError, Table, read_source
from demarco.parsing import calendar_date, identifier
from demarco.sources import CALCULATED_COLUMNS, SOURCES

MANAGEMENT_SOURCE = next(source for source in SOURCES if source.name == "gestao")


def download_template(spreadsheet_id: str) -> Table:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", spreadsheet_id):
        raise InputError("ID da planilha inválido; informe somente o trecho entre /d/ e /edit.")
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=xlsx"
    with urlopen(url, timeout=20) as response:
        content = response.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024 or not content.startswith(b"PK\x03\x04"):
        raise InputError("Resposta não é uma planilha XLSX válida de até 10 MiB; confira o acesso.")
    with TemporaryDirectory(prefix="demarco-template-") as directory:
        path = Path(directory)
        (path / MANAGEMENT_SOURCE.filename).write_bytes(content)
        return read_source(path, MANAGEMENT_SOURCE)


def compare_template(reference: Table, remote: Table) -> dict[str, Any]:
    def index(table: Table):
        result = {}
        for record in table.records:
            key = identifier(record.values["ID_Colaborador"])
            if key is None or key in result:
                raise InputError("A planilha de gestão contém IDs vazios ou duplicados.")
            result[key] = record
        return result

    local_rows, remote_rows = index(reference), index(remote)
    differences = []
    protected = [field for field in MANAGEMENT_SOURCE.columns if field not in CALCULATED_COLUMNS]
    for key in sorted(local_rows.keys() & remote_rows.keys()):
        local, online = local_rows[key], remote_rows[key]
        for field in protected:
            left, right = local.values[field], online.values[field]
            if field == "Data_Conversa_1on1":
                # Google pode exportar a mesma data como texto ou célula de data Excel.
                left, right = calendar_date(left), calendar_date(right)
            if left != right:
                differences.append(
                    {
                        "id_colaborador": key,
                        "column": field,
                        "reference_row": local.row,
                        "remote_row": online.row,
                    }
                )
    missing = sorted(local_rows.keys() - remote_rows.keys())
    extra = sorted(remote_rows.keys() - local_rows.keys())
    return {
        "matches": not differences and not missing and not extra,
        "reference_rows": len(local_rows),
        "remote_rows": len(remote_rows),
        "protected_columns": protected,
        "missing_ids": missing,
        "extra_ids": extra,
        "differences": differences,
        "read_only": True,
    }
