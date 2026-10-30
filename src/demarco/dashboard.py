"""Contrato do dashboard: fórmulas copiáveis e a mesma avaliação em GoogleSQL."""

import json
import re
from pathlib import Path
from urllib.parse import urlencode

from demarco.config import CloudConfig
from demarco.ingestion import InputError


def load_report_spec(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    ids = [metric["id"] for metric in spec["metrics"]]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in ids):
        raise InputError("IDs das métricas do dashboard inválidos ou duplicados.")
    for metric in spec["metrics"]:
        if metric["source"] not in spec["sources"]:
            raise InputError("Métrica referencia uma fonte inexistente.")
    return spec


def google_sql_formula(formula: str) -> str:
    # SUM, CASE e razões usam sintaxe comum; COUNT_DISTINCT tem nome diferente.
    return re.sub(r"\bCOUNT_DISTINCT\s*\(", "COUNT(DISTINCT ", formula)


def render_metric_table(spec: dict, dataset_id: str) -> str:
    subqueries = []
    for alias, view in spec["sources"].items():
        fields = [
            f"{google_sql_formula(m['formula'])} AS {m['id']}"
            for m in spec["metrics"]
            if m["source"] == alias
        ]
        subqueries.append(f"(SELECT {', '.join(fields)} FROM `{dataset_id}.{view}`) AS {alias}")
    return (
        "CREATE TEMP TABLE dashboard_metrics AS SELECT "
        + ", ".join(f"{alias}.*" for alias in spec["sources"])
        + " FROM "
        + " CROSS JOIN ".join(subqueries)
        + ";"
    )


def render_dashboard_checks(sql: str, spec: dict, dataset_id: str) -> str:
    sql = sql.replace("{{dashboard_metrics}}", render_metric_table(spec, dataset_id))
    for metric in spec["metrics"]:
        sql = sql.replace("{{metric:" + metric["id"] + "}}", google_sql_formula(metric["formula"]))
    return sql


def create_report_url(config: CloudConfig, spec: dict, source: str = "diario") -> str:
    if source not in spec["sources"]:
        raise InputError("Fonte do dashboard não reconhecida.")
    parameters = {
        "c.mode": "edit",
        "r.reportName": spec["title"],
        "ds.connector": "bigQuery",
        "ds.type": "TABLE",
        "ds.projectId": config.project,
        "ds.billingProjectId": config.project,
        "ds.datasetId": config.dataset,
        "ds.tableId": spec["sources"][source],
        "ds.datasourceName": f"Demarco | {source}",
    }
    return "https://lookerstudio.google.com/reporting/create?" + urlencode(parameters)
