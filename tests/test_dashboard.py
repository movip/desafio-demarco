import json
import sys
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
import sqlglot
from sqlglot import exp

from demarco.bigquery import staging_sql
from demarco.cli import main
from demarco.config import CloudConfig
from demarco.dashboard import create_report_url, load_report_spec
from demarco.ingestion import InputError

ROOT = Path(__file__).resolve().parents[1]
CONFIG = CloudConfig("example-project", "example", "US", 1073741824)


def test_presentation_only_creates_the_three_views_declared_in_report_contract():
    sql = staging_sql(ROOT / "sql/12_dashboard_sources.sql", CONFIG)
    statements = sqlglot.parse(sql, read="bigquery")
    spec = load_report_spec(ROOT / "dashboard/report_spec.json")
    assert len(statements) == 3
    assert all(isinstance(s, exp.Create) and s.args["kind"] == "VIEW" for s in statements)
    assert {s.this.name for s in statements} == set(spec["sources"].values())


def test_dashboard_checks_evaluate_the_same_metric_formulas_as_the_guide():
    spec = load_report_spec(ROOT / "dashboard/report_spec.json")
    sql = staging_sql(ROOT / "sql/13_dashboard_checks.sql", CONFIG)
    assert "{{" not in sql
    statements = sqlglot.parse(sql, read="bigquery")
    assert len(statements) == 14
    assert not any(isinstance(s, (exp.Update, exp.Delete, exp.Insert)) for s in statements)
    for metric in spec["metrics"]:
        assert f"AS {metric['id']}" in sql
    assert "COUNT(DISTINCT id_colaborador_no_periodo)" in sql
    assert "SUM(horas_injustificadas) / SUM(horas_previstas)" in sql


def test_period_policy_page_has_no_month_filter():
    spec = load_report_spec(ROOT / "dashboard/report_spec.json")
    policy = [page for page in spec["pages"] if page["source"] == "gestao"]
    assert len(policy) == 1
    assert policy[0]["date_filter"] is False
    assert "data" not in policy[0]["filters"]


def test_link_only_contains_public_connection_parameters():
    spec = load_report_spec(ROOT / "dashboard/report_spec.json")
    config = CloudConfig(
        "example-project", "example", "US", 1073741824, ROOT / "credentials/do-not-expose.json"
    )
    url = create_report_url(config, spec)
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert parsed.netloc == "lookerstudio.google.com"
    assert parsed.path == "/reporting/create"
    assert params["ds.projectId"] == ["example-project"]
    assert params["ds.tableId"] == ["vw_dashboard_diario"]
    assert params["r.reportName"] == [spec["title"]]
    assert "credentials" not in url and "token" not in url
    assert "c.reportId" not in params  # Link de criação; nenhum relatório publicado é inventado.


def test_duplicate_metric_id_is_rejected(tmp_path):
    spec = load_report_spec(ROOT / "dashboard/report_spec.json")
    spec["metrics"].append(spec["metrics"][0])
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    with pytest.raises(InputError, match="duplicados"):
        load_report_spec(path)


def test_planning_dashboard_does_not_access_google(tmp_path, monkeypatch):
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
        ("bq-dashboard", "12_dashboard_sources.sql"),
        ("bq-dashboard-check", "13_dashboard_checks.sql"),
    ):
        monkeypatch.setattr(
            sys,
            "argv",
            ["demarco", command, "--env-file", str(env), "--output-dir", str(tmp_path / "output")],
        )
        assert main() == 0
        assert "{{" not in (tmp_path / "output" / filename).read_text()
    factory.assert_not_called()
