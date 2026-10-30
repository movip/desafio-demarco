import hashlib
import json
import re
from datetime import datetime
from zipfile import ZipFile

import pytest
from openpyxl import Workbook

from demarco.ingestion import InputError, export_table, read_source
from demarco.sources import Source

SOURCE = Source("example", "example.xlsx", ("id", "value"), ("id",))


def workbook(tmp_path, rows):
    path = tmp_path / SOURCE.filename
    wb = Workbook()
    for row in rows:
        wb.active.append(row)
    wb.save(path)
    wb.close()
    return path


def test_reading_preserves_values_row_numbers_types_and_source_bytes(tmp_path):
    path = workbook(
        tmp_path, [("value", "id"), (" NULL ", "001"), (None, None), (datetime(2025, 6, 1), "002")]
    )
    before = path.read_bytes()
    table = read_source(tmp_path, SOURCE)
    assert [r.row for r in table.records] == [2, 4]
    assert table.records[0].values == {"id": "001", "value": " NULL "}
    assert table.records[1].values["value"] == datetime(2025, 6, 1)
    assert table.skipped_blank_rows == 1
    assert table.sha256 == hashlib.sha256(before).hexdigest()
    assert path.read_bytes() == before
    output = tmp_path / "output.jsonl"
    export_table(table, output)
    exported = [json.loads(line) for line in output.read_text().splitlines()]
    assert exported[1]["source_row"] == 4
    assert exported[1]["value_types"]["value"] == "datetime"
    assert exported[0]["values"]["value"] == " NULL "


@pytest.mark.parametrize("headers", [("id",), ("id", "id"), ("id", "value", "extra")])
def test_invalid_schema_stops_ingestion(tmp_path, headers):
    workbook(tmp_path, [headers, ("001",)])
    with pytest.raises(InputError, match="cabeçalhos"):
        read_source(tmp_path, SOURCE)


@pytest.mark.parametrize("cell", ["=1+1", "#DIV/0!"])
def test_formula_or_excel_error_is_not_silently_read_as_null(tmp_path, cell):
    workbook(tmp_path, [("id", "value"), ("001", cell)])
    with pytest.raises(InputError, match="fórmula ou erro"):
        read_source(tmp_path, SOURCE)


def test_missing_file_has_actionable_error(tmp_path):
    with pytest.raises(InputError, match="Arquivo não encontrado"):
        read_source(tmp_path, SOURCE)


def test_sheets_export_without_dimensions_keeps_trailing_empty_cells(tmp_path):
    path = workbook(tmp_path, [("id", "value"), ("001", "filled"), ("002",)])
    with ZipFile(path) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    sheet = "xl/worksheets/sheet1.xml"
    contents[sheet] = re.sub(rb"<dimension[^>]*/>", b"", contents[sheet])
    with ZipFile(path, "w") as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
    table = read_source(tmp_path, SOURCE)
    assert table.records[1].values == {"id": "002", "value": None}
