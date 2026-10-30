"""Carga batch rastreável e execução dos SQL entregues no repositório."""

from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from google.api_core.exceptions import NotFound
from google.auth import load_credentials_from_file
from google.cloud import bigquery

from demarco.config import CloudConfig
from demarco.dashboard import load_report_spec, render_dashboard_checks
from demarco.ingestion import InputError, Table, encode_json


def create_client(config: CloudConfig) -> bigquery.Client:
    credentials = None
    if config.credentials_file is not None:
        credentials, _ = load_credentials_from_file(
            str(config.credentials_file), scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    return bigquery.Client(
        project=config.project, location=config.location, credentials=credentials
    )


def raw_schema(table: Table) -> list[bigquery.SchemaField]:
    return [bigquery.SchemaField(column, "STRING") for column in table.source.columns] + [
        bigquery.SchemaField("_source_file", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("_source_sheet", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("_source_row", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("_source_sha256", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("_raw_json", "STRING", mode="REQUIRED"),
    ]


def raw_rows(table: Table) -> list[dict[str, Any]]:
    def text(value):
        if value is None:
            return None
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        return str(value)

    return [
        {
            **{key: text(value) for key, value in record.values.items()},
            "_source_file": table.source.filename,
            "_source_sheet": table.sheet,
            "_source_row": record.row,
            "_source_sha256": table.sha256,
            "_raw_json": encode_json(
                {
                    "values": record.values,
                    "value_types": {
                        key: type(value).__name__ for key, value in record.values.items()
                    },
                }
            ),
        }
        for record in table.records
    ]


def load_plan(tables: dict[str, Table], config: CloudConfig) -> dict[str, Any]:
    return {
        "project": config.project,
        "dataset": config.dataset,
        "location": config.location,
        "write_disposition": "WRITE_TRUNCATE",
        "tables": [
            {
                "table_id": f"{config.dataset_id}.raw_{name}",
                "rows": len(table.records),
                "source_sha256": table.sha256,
                "schema": [f.to_api_repr() for f in raw_schema(table)],
            }
            for name, table in tables.items()
        ],
    }


def preflight(client: bigquery.Client, config: CloudConfig) -> dict[str, Any]:
    # Consulta simples confirma autenticação e permissão de criar jobs.
    # Ela não comprova permissões de escrita nem a configuração de faturamento.
    job = client.query(
        "SELECT 1 AS connection_ok",
        location=config.location,
        job_config=bigquery.QueryJobConfig(maximum_bytes_billed=config.max_bytes_billed),
    )
    list(job.result())
    try:
        dataset = client.get_dataset(config.dataset_id)
    except NotFound:
        return {"query_ok": True, "dataset_exists": False, "job_id": job.job_id}
    if dataset.location.upper() != config.location.upper():
        raise InputError(f"Dataset está em {dataset.location}; ajuste BIGQUERY_LOCATION.")
    return {"query_ok": True, "dataset_exists": True, "job_id": job.job_id}


def load_raw(client: bigquery.Client, config: CloudConfig, tables: dict[str, Table]) -> dict:
    dataset = bigquery.Dataset(config.dataset_id)
    dataset.location = config.location
    client.create_dataset(dataset, exists_ok=True)
    actual = client.get_dataset(config.dataset_id)
    if actual.location.upper() != config.location.upper():
        raise InputError(f"Dataset está em {actual.location}; ajuste BIGQUERY_LOCATION.")
    results = []
    for name, table in tables.items():
        table_id = f"{config.dataset_id}.raw_{name}"
        job = client.load_table_from_json(
            raw_rows(table),
            table_id,
            location=config.location,
            job_config=bigquery.LoadJobConfig(
                schema=raw_schema(table),
                autodetect=False,
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                max_bad_records=0,
                ignore_unknown_values=False,
            ),
        )
        job.result()
        actual_rows = client.get_table(table_id).num_rows
        if actual_rows != len(table.records):
            raise InputError(f"Contagem divergente em {table_id}: {actual_rows} linhas.")
        results.append({"table_id": table_id, "rows": actual_rows, "job_id": job.job_id})
    return {"tables": results, "completed": True}


def staging_sql(path: Path, config: CloudConfig) -> str:
    # Config valida projeto/dataset antes de formar identificadores, sem interpolar dados.
    sql = path.read_text(encoding="utf-8")
    includes = {
        "{{text_repair_udf}}": "repair_text.sql",
        "{{attendance_udf}}": "classificar_ausencia.sql",
        "{{finance_udf}}": "financeiro_disciplina.sql",
    }
    for marker, filename in includes.items():
        if marker in sql:
            helper = (path.parent / "functions" / filename).read_text(encoding="utf-8")
            sql = sql.replace(marker, helper)
    if "{{dashboard_metrics}}" in sql or "{{metric:" in sql:
        spec = load_report_spec(path.parent.parent / "dashboard" / "report_spec.json")
        sql = render_dashboard_checks(sql, spec, config.dataset_id)
    return sql.replace("{{dataset}}", config.dataset_id)


def run_staging(client: bigquery.Client, config: CloudConfig, sql: str) -> dict:
    job = client.query(
        sql,
        location=config.location,
        job_config=bigquery.QueryJobConfig(
            use_legacy_sql=False,
            maximum_bytes_billed=config.max_bytes_billed,
        ),
    )
    rows = [dict(row) for row in job.result()]
    return {
        "job_id": job.job_id,
        "bytes_processed": job.total_bytes_processed,
        "completed": True,
        "rows": rows,
    }
