import sys
from pathlib import Path
from unittest.mock import Mock

import sqlglot
from sqlglot import exp

from demarco.bigquery import staging_sql
from demarco.cli import main
from demarco.config import CloudConfig

ROOT = Path(__file__).resolve().parents[1]
CONFIG = CloudConfig("example-project", "example", "US", 1073741824)


def test_finance_model_only_recreates_its_derived_tables_and_temporary_functions():
    sql = staging_sql(ROOT / "sql/08_dsr_finance_policy.sql", CONFIG)
    statements = sqlglot.parse(sql, read="bigquery")
    assert len(statements) == 10
    assert all(isinstance(s, exp.Create) for s in statements)
    tables = {s.this.name for s in statements if s.args["kind"] == "TABLE"}
    assert tables == {
        "int_descansos_contratuais",
        "fct_dsr_ciclos",
        "fct_dsr_diario",
        "fct_impacto_diario",
        "mart_impacto_mensal",
        "mart_gestao_colaboradores",
    }
    for statement in statements:
        if statement.args["kind"] == "FUNCTION":
            assert any(
                isinstance(p, exp.TemporaryProperty)
                for p in statement.args["properties"].expressions
            )


def test_financial_checks_share_production_functions_and_do_not_change_tables():
    model = staging_sql(ROOT / "sql/08_dsr_finance_policy.sql", CONFIG)
    checks = staging_sql(ROOT / "sql/09_finance_checks.sql", CONFIG)
    helper = (ROOT / "sql/functions/financeiro_disciplina.sql").read_text()
    assert helper in model and helper in checks
    assert "{{" not in model and "{{" not in checks
    statements = sqlglot.parse(checks, read="bigquery")
    assert len(statements) == 24
    assert not any(isinstance(s, (exp.Insert, exp.Update, exp.Delete)) for s in statements)
    assert not any(isinstance(s, exp.Create) and s.args["kind"] != "FUNCTION" for s in statements)


def test_finance_plan_requires_no_google_access(tmp_path, monkeypatch):
    for key in (
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "BIGQUERY_DATASET",
        "BIGQUERY_LOCATION",
        "BIGQUERY_MAX_BYTES_BILLED",
    ):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text("GOOGLE_CLOUD_PROJECT=example-project\n")
    factory = Mock()
    monkeypatch.setattr("demarco.cloud_cli.create_client", factory)
    for command, filename in (
        ("bq-finance", "08_dsr_finance_policy.sql"),
        ("bq-finance-check", "09_finance_checks.sql"),
    ):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "demarco",
                command,
                "--env-file",
                str(env),
                "--output-dir",
                str(tmp_path / "output"),
            ],
        )
        assert main() == 0
        sql = (tmp_path / "output" / filename).read_text()
        assert "CREATE TEMP FUNCTION recomendar_acao" in sql
        assert "example-project.demarco_absenteismo" in sql
    factory.assert_not_called()


def test_finance_distribution_audit_is_read_only():
    sql = staging_sql(ROOT / "sql/10_finance_audit.sql", CONFIG)
    statements = sqlglot.parse(sql, read="bigquery")
    assert len(statements) == 1
    assert isinstance(statements[0], exp.Union)
