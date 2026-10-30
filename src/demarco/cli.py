"""Interface local: valida todas as entradas antes de gerar os artefatos."""

import argparse
import json
import sys
from pathlib import Path
from urllib.error import URLError
from zipfile import BadZipFile

from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import DefaultCredentialsError, RefreshError
from openpyxl.utils.exceptions import InvalidFileException
from requests.exceptions import RequestException

from demarco.cloud_cli import add_cloud_commands, run_cloud_command
from demarco.ingestion import InputError, export_table, read_source
from demarco.quality import diagnose, markdown_report
from demarco.sheets_cli import add_sheets_command, run_sheets_sync
from demarco.sources import SOURCES
from demarco.template_check import MANAGEMENT_SOURCE, compare_template, download_template


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline de absenteísmo Demarco")
    commands = parser.add_subparsers(dest="command", required=True)
    diagnosis = commands.add_parser("diagnose", help="Ler planilhas e gerar diagnóstico rastreável")
    diagnosis.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    diagnosis.add_argument("--output-dir", type=Path, default=Path("artifacts/diagnostico"))
    template = commands.add_parser(
        "check-template",
        help="Comparar o Sheets acessível por link com o template original, sem escrever",
    )
    template.add_argument("--spreadsheet-id", required=True)
    template.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    template.add_argument("--output", type=Path, default=Path("artifacts/template-check.json"))
    add_cloud_commands(commands)
    add_sheets_command(commands)
    args = parser.parse_args()
    try:
        if args.command == "sheets-sync":
            return run_sheets_sync(args)
        if args.command.startswith("bq-"):
            return run_cloud_command(args)
        if args.command == "check-template":
            original = read_source(args.input_dir, MANAGEMENT_SOURCE)
            online = download_template(args.spreadsheet_id)
            report = compare_template(original, online)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(f"Conferência somente de leitura: {report['remote_rows']} colaboradores.")
            print(
                "Template preservado."
                if report["matches"]
                else "Divergências: consulte o relatório."
            )
            return 0 if report["matches"] else 2
        input_path = args.input_dir.resolve()
        output_path = args.output_dir.resolve()
        if input_path == output_path or input_path in output_path.parents:
            raise InputError("A saída não pode ficar na pasta de entrada ou dentro dela.")
        tables = {source.name: read_source(input_path, source) for source in SOURCES}
        report = diagnose(tables)
        output_path.mkdir(parents=True, exist_ok=True)
        for name, table in tables.items():
            export_table(table, output_path / f"{name}.jsonl")
        (output_path / "quality.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_path / "quality.md").write_text(markdown_report(report), encoding="utf-8")
    except DefaultCredentialsError:
        print(
            "Erro: autenticação Google ausente. Instale a Google Cloud CLI e execute "
            "`gcloud auth application-default login`. Consulte docs/execucao.md.",
            file=sys.stderr,
        )
        return 1
    except (
        InputError,
        OSError,
        ValueError,
        URLError,
        BadZipFile,
        InvalidFileException,
        GoogleAPIError,
        RefreshError,
        RequestException,
    ) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    for name, table in tables.items():
        print(f"{name}: {len(table.records)} linhas lidas")
    print(f"Diagnóstico gerado em {output_path / 'quality.md'}")
    print(
        "Entradas preservadas. Problemas de dados estão no relatório; "
        "não são corrigidos nesta etapa."
    )
    return 0
