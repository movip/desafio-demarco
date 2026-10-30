import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, Mock

import sqlglot
from sqlglot import exp

from demarco.bigquery import staging_sql
from demarco.cli import main
from demarco.config import CloudConfig

ROOT = Path(__file__).resolve().parents[1]
CONFIG = CloudConfig("example-project", "example", "US", 1073741824)


def test_daily_sql_defines_unique_layers_without_overwriting_sources():
    sql = staging_sql(ROOT / "sql/04_daily_attendance.sql", CONFIG)
    assert "{{" not in sql
    statements = sqlglot.parse(sql, read="bigquery")
    tables = {s.this.name for s in statements if s.args.get("kind") == "TABLE"}
    assert tables == {
        "dim_colaboradores",
        "dim_escalas",
        "int_calendario_colaborador",
        "int_ponto_dia",
        "fct_ausencias_diarias",
        "qa_ausencias_diarias",
        "qa_ponto_sem_chave_periodo",
    }
    assert all(isinstance(s, exp.Create) for s in statements)
    for statement in statements:
        if statement.args["kind"] == "FUNCTION":
            assert any(
                isinstance(p, exp.TemporaryProperty)
                for p in statement.args["properties"].expressions
            )


def test_rule_checks_parse_and_use_the_same_function_as_the_model():
    model = staging_sql(ROOT / "sql/04_daily_attendance.sql", CONFIG)
    checks = staging_sql(ROOT / "sql/05_daily_checks.sql", CONFIG)
    helper = (ROOT / "sql/functions/classificar_ausencia.sql").read_text()
    assert helper in model
    assert helper in checks
    statements = sqlglot.parse(checks, read="bigquery")
    assert len(statements) == 14
    assert not any(isinstance(s, (exp.Insert, exp.Update, exp.Delete)) for s in statements)
    assert not any(isinstance(s, exp.Create) and s.args["kind"] != "FUNCTION" for s in statements)


def environment(tmp_path, monkeypatch):
    for key in (
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "BIGQUERY_DATASET",
        "BIGQUERY_LOCATION",
        "BIGQUERY_MAX_BYTES_BILLED",
    ):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text("GOOGLE_CLOUD_PROJECT=example-project\n")
    return path


def test_daily_plan_does_not_access_google(tmp_path, monkeypatch):
    env = environment(tmp_path, monkeypatch)
    client = Mock()
    monkeypatch.setattr("demarco.cloud_cli.create_client", client)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "demarco",
            "bq-daily",
            "--env-file",
            str(env),
            "--output-dir",
            str(tmp_path / "output"),
        ],
    )
    assert main() == 0
    client.assert_not_called()
    rendered = (tmp_path / "output/04_daily_attendance.sql").read_text()
    assert "CREATE TEMP FUNCTION classificar_ausencia" in rendered
    assert "example-project.demarco_absenteismo.fct_ausencias_diarias" in rendered


def test_query_evidence_preserves_numeric_precision_and_dates(tmp_path, monkeypatch):
    env = environment(tmp_path, monkeypatch)
    monkeypatch.setattr("demarco.cloud_cli.create_client", MagicMock())
    monkeypatch.setattr(
        "demarco.cloud_cli.run_staging",
        Mock(
            return_value={
                "completed": True,
                "job_id": "example-job",
                "rows": [{"horas": Decimal("8.800000001"), "dia": date(2025, 6, 1)}],
            }
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "demarco",
            "bq-daily-check",
            "--execute",
            "--env-file",
            str(env),
            "--output-dir",
            str(tmp_path / "output"),
        ],
    )
    assert main() == 0
    result = json.loads((tmp_path / "output/bq-daily-check-result.json").read_text())
    assert result["rows"] == [{"horas": "8.800000001", "dia": "2025-06-01"}]
