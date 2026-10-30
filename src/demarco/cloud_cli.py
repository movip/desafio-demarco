"""Comandos de nuvem separados do diagnóstico local."""

import argparse
import json
from pathlib import Path

from demarco.bigquery import create_client, load_plan, load_raw, preflight, run_staging, staging_sql
from demarco.config import cloud_config
from demarco.ingestion import json_default, read_source
from demarco.sources import SOURCES


def add_cloud_commands(commands) -> None:
    for name, help_text in (
        ("bq-status", "Testar autenticação e consulta no BigQuery"),
        ("bq-load", "Preparar a carga bruta; --execute envia para o BigQuery"),
        ("bq-stage", "Preparar GoogleSQL de staging; --execute envia para o BigQuery"),
        ("bq-check", "Preparar reconciliação SQL; --execute confere no BigQuery"),
        ("bq-daily", "Preparar dimensões e ausências diárias; --execute executa no BigQuery"),
        ("bq-daily-check", "Preparar testes das ausências; --execute confere no BigQuery"),
        ("bq-finance", "Preparar DSR, descontos e recomendações; --execute executa no BigQuery"),
        (
            "bq-finance-check",
            "Preparar testes financeiros e da política; --execute confere no BigQuery",
        ),
        ("bq-dashboard", "Preparar views do Looker Studio; --execute cria no BigQuery"),
        ("bq-dashboard-check", "Conferir fontes e totais do dashboard no BigQuery"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--env-file", type=Path, default=Path(".env"))
        if name != "bq-status":
            command.add_argument("--execute", action="store_true")
            command.add_argument("--output-dir", type=Path, default=Path("artifacts/bigquery"))
        if name == "bq-load":
            command.add_argument("--input-dir", type=Path, default=Path("data/raw"))
        sql_defaults = {
            "bq-stage": "sql/01_staging.sql",
            "bq-check": "sql/02_staging_checks.sql",
            "bq-daily": "sql/04_daily_attendance.sql",
            "bq-daily-check": "sql/05_daily_checks.sql",
            "bq-finance": "sql/08_dsr_finance_policy.sql",
            "bq-finance-check": "sql/09_finance_checks.sql",
            "bq-dashboard": "sql/12_dashboard_sources.sql",
            "bq-dashboard-check": "sql/13_dashboard_checks.sql",
        }
        if name in sql_defaults:
            command.add_argument("--sql-file", type=Path, default=Path(sql_defaults[name]))


def run_cloud_command(args: argparse.Namespace) -> int:
    config = cloud_config(args.env_file)
    if args.command == "bq-status":
        with create_client(config) as client:
            result = preflight(client, config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.command == "bq-load":
        tables = {source.name: read_source(args.input_dir, source) for source in SOURCES}
        plan = load_plan(tables, config)
        (args.output_dir / "load-plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Destino: {config.dataset_id} ({config.location}).")
        print("Carga de quatro tabelas raw_*, substituindo apenas suas versões anteriores.")
        if not args.execute:
            print("Plano local gerado. Nenhum acesso Google realizado.")
            return 0
        with create_client(config) as client:
            result = load_raw(client, config, tables)
    else:
        sql = staging_sql(args.sql_file, config)
        (args.output_dir / args.sql_file.name).write_text(sql, encoding="utf-8")
        print(f"SQL preparado para {config.dataset_id}.")
        print(f"Limite por job: {config.max_bytes_billed} bytes.")
        if not args.execute:
            print("SQL local gerado. Nenhum acesso Google realizado.")
            return 0
        with create_client(config) as client:
            result = run_staging(client, config, sql)
    report_path = args.output_dir / f"{args.command}-result.json"
    report_path.write_text(
        json.dumps(result, indent=2, default=json_default) + "\n", encoding="utf-8"
    )
    if result.get("rows"):
        print(json.dumps(result["rows"], ensure_ascii=False, indent=2, default=json_default))
    print(f"Concluído no BigQuery. Evidência: {report_path}")
    return 0
