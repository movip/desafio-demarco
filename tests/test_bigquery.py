import json
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
import sqlglot
from google.api_core.exceptions import NotFound
from sqlglot import exp

from demarco.bigquery import (
    create_client,
    load_plan,
    load_raw,
    preflight,
    raw_rows,
    run_staging,
    staging_sql,
)
from demarco.config import CloudConfig, cloud_config
from demarco.ingestion import InputError, read_source
from demarco.sources import SOURCES

ROOT = Path(__file__).resolve().parents[1]
CONFIG = CloudConfig("example-project", "demarco_absenteismo", "US", 1073741824)


@pytest.fixture
def tables():
    return {source.name: read_source(ROOT / "data/raw", source) for source in SOURCES}


def test_cloud_settings_validate_before_forming_sql_identifiers(tmp_path, monkeypatch):
    for key in (
        "GOOGLE_CLOUD_PROJECT",
        "BIGQUERY_DATASET",
        "BIGQUERY_LOCATION",
        "BIGQUERY_MAX_BYTES_BILLED",
    ):
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_CLOUD_PROJECT=example-project\nBIGQUERY_DATASET=example\n")
    assert cloud_config(env_file).dataset_id == "example-project.example"
    monkeypatch.setenv("BIGQUERY_DATASET", "other_dataset")
    assert cloud_config(env_file).dataset == "other_dataset"
    monkeypatch.setenv("BIGQUERY_DATASET", "unsafe`; DROP TABLE a; --")
    with pytest.raises(InputError, match="BIGQUERY_DATASET"):
        cloud_config(env_file)


def test_raw_payload_preserves_null_text_and_source_types(tables):
    table = tables["colaboradores"]
    table.records[0].values["salario_mensal"] = " NULL "
    table.records[0].values["data_admissao"] = datetime(2020, 1, 1)
    payload = raw_rows(table)[0]
    assert payload["salario_mensal"] == " NULL "
    assert payload["data_admissao"] == "2020-01-01T00:00:00"
    assert payload["_source_row"] == 2
    assert payload["_source_sha256"] == table.sha256
    assert json.loads(payload["_raw_json"])["value_types"]["data_admissao"] == "datetime"


def test_batch_load_replaces_only_raw_tables_and_checks_row_counts(tables):
    client = Mock()
    client.get_dataset.return_value.location = "US"
    client.get_table.side_effect = [Mock(num_rows=len(table.records)) for table in tables.values()]
    client.load_table_from_json.return_value.job_id = "test-job"
    result = load_raw(client, CONFIG, tables)
    assert result["completed"]
    assert len(result["tables"]) == 4
    for call in client.load_table_from_json.call_args_list:
        assert call.args[1].startswith(CONFIG.dataset_id + ".raw_")
        assert call.kwargs["job_config"].write_disposition == "WRITE_TRUNCATE"
        assert call.kwargs["job_config"].max_bad_records == 0
        assert not call.kwargs["job_config"].autodetect
        assert call.kwargs["location"] == "US"
    assert client.load_table_from_json.return_value.result.call_count == 4
    assert load_plan(tables, CONFIG)["tables"][2]["rows"] == 3779


def test_row_count_mismatch_stops_load_before_next_table(tables):
    client = Mock()
    client.get_dataset.return_value.location = "US"
    client.get_table.return_value.num_rows = 0
    with pytest.raises(InputError, match="Contagem divergente"):
        load_raw(client, CONFIG, tables)
    assert client.load_table_from_json.call_count == 1


def test_existing_dataset_in_another_location_stops_before_loading(tables):
    client = Mock()
    client.get_dataset.return_value.location = "southamerica-east1"
    with pytest.raises(InputError, match="ajuste BIGQUERY_LOCATION"):
        load_raw(client, CONFIG, tables)
    client.load_table_from_json.assert_not_called()


def test_preflight_handles_absent_dataset_without_creating_one():
    client = Mock()
    client.query.return_value.result.return_value = []
    client.query.return_value.job_id = "test-job"
    client.get_dataset.side_effect = NotFound("Not found")
    report = preflight(client, CONFIG)
    assert report == {"query_ok": True, "dataset_exists": False, "job_id": "test-job"}
    client.create_dataset.assert_not_called()
    assert client.query.call_args.kwargs["job_config"].maximum_bytes_billed == 1073741824


def test_google_sql_parses_and_only_writes_staging_tables():
    sql = staging_sql(ROOT / "sql/01_staging.sql", CONFIG)
    assert "{{dataset}}" not in sql
    statements = sqlglot.parse(sql, read="bigquery")
    assert len(statements) == 8
    assert all(isinstance(statement, exp.Create) for statement in statements)
    destinations = [s.this.name for s in statements if s.args["kind"] == "TABLE"]
    assert len(destinations) == 4
    assert all(name.startswith("stg_") for name in destinations)
    # BigQuery não permite misturar funções temporárias e persistentes no mesmo job.
    functions = [statement for statement in statements if statement.args["kind"] == "FUNCTION"]
    assert len(functions) == 4
    assert all(
        any(
            isinstance(prop, exp.TemporaryProperty)
            for prop in statement.args["properties"].expressions
        )
        for statement in functions
    )


def test_text_repair_checks_and_audit_parse_without_writing_tables():
    for name in ("02_staging_checks.sql", "03_encoding_audit.sql"):
        sql = staging_sql(ROOT / "sql" / name, CONFIG)
        statements = sqlglot.parse(sql, read="bigquery")
        assert statements
        assert not any(
            isinstance(statement, (exp.Delete, exp.Update, exp.Insert))
            or (isinstance(statement, exp.Create) and statement.args["kind"] != "FUNCTION")
            for statement in statements
        )


def test_staging_execution_sets_cost_limit_and_waits_for_completion():
    client = Mock()
    client.query.return_value.result.return_value = []
    client.query.return_value.job_id = "test-job"
    client.query.return_value.total_bytes_processed = 123
    assert run_staging(client, CONFIG, "SELECT 1")["bytes_processed"] == 123
    assert client.query.call_args.kwargs["job_config"].maximum_bytes_billed == 1073741824
    client.query.return_value.result.assert_called_once()


def test_credentials_in_env_file_are_resolved_without_exposing_content(tmp_path, monkeypatch):
    for key in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS"):
        monkeypatch.delenv(key, raising=False)
    credential = tmp_path / "credential.json"
    credential.write_text("{}")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GOOGLE_CLOUD_PROJECT=example-project\nGOOGLE_APPLICATION_CREDENTIALS=credential.json\n"
    )
    config = cloud_config(env_file)
    assert config.credentials_file == credential
    fake_credentials = object()
    loader = Mock(return_value=(fake_credentials, "example-project"))
    constructor = Mock()
    monkeypatch.setattr("demarco.bigquery.load_credentials_from_file", loader)
    monkeypatch.setattr("demarco.bigquery.bigquery.Client", constructor)
    create_client(config)
    assert constructor.call_args.kwargs["credentials"] is fake_credentials
    assert loader.call_args.args == (str(credential),)


def test_missing_credentials_file_stops_before_cloud_access(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "example-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "absent.json"))
    with pytest.raises(InputError, match="GOOGLE_APPLICATION_CREDENTIALS não encontrado"):
        cloud_config(tmp_path / ".env")
