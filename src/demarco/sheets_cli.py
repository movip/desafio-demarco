"""Orquestração do Reverse ETL: prévia por padrão, lote atômico e conferência."""

import argparse
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from demarco.bigquery import create_client, run_staging, staging_sql
from demarco.config import cloud_config, management_config
from demarco.ingestion import InputError
from demarco.reverse_etl import (
    fingerprint,
    make_plan,
    parse_snapshot,
    protected_state,
    save_private_json,
    update_requests,
    verify_after,
)
from demarco.sheets import create_sheets_client


def add_sheets_command(commands) -> None:
    command = commands.add_parser("sheets-sync", help="Prévia da gestão; --execute aplica valores")
    command.add_argument("--env-file", type=Path, default=Path(".env"))
    command.add_argument("--output-dir", type=Path, default=Path("artifacts/reverse-etl"))
    command.add_argument("--execute", action="store_true")


def run_sheets_sync(args: argparse.Namespace) -> int:
    cloud = cloud_config(args.env_file)
    management = management_config(args.env_file)
    now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    run_dir = args.output_dir / (now.strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:12])
    run_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    client = create_sheets_client(cloud, management)
    report = {
        "status": "READING",
        "execution_requested": args.execute,
        "run_directory": str(run_dir),
    }
    try:
        before = parse_snapshot(client.snapshot(), management.worksheet)
        save_private_json(run_dir / "snapshot-before.json", before.raw)
        sql = staging_sql(Path("sql/11_reverse_etl_source.sql"), cloud)
        (run_dir / "source.sql").write_text(sql, encoding="utf-8")
        with create_client(cloud) as warehouse:
            source = run_staging(warehouse, cloud, sql)
        save_private_json(run_dir / "source-result.json", source)
        plan = make_plan(before, source["rows"], now.isoformat(timespec="seconds"))
        requests = update_requests(before, plan)
        save_private_json(run_dir / "plan.json", plan)
        save_private_json(run_dir / "requests.json", {"requests": requests})
        report.update(
            {
                "status": "PREVIEW",
                "source_job_id": source["job_id"],
                "spreadsheet_id": management.spreadsheet_id,
                "rows_to_update": len(plan["updated_ids"]),
                "cells_to_update": len(requests),
                "skipped_rows": len(plan["skipped"]),
                "unchanged_rows": len(plan["unchanged_ids"]),
            }
        )
        if args.execute:
            if requests:
                latest = parse_snapshot(client.snapshot(), management.worksheet)
                save_private_json(run_dir / "snapshot-preflight.json", latest.raw)
                if fingerprint(protected_state(latest, set())) != plan["baseline_sha256"]:
                    report["status"] = "ABORTED_CONCURRENT_CHANGE"
                    raise InputError(
                        "A planilha mudou após a prévia. Nenhuma escrita foi enviada; reexecute."
                    )
                # Único POST, sem retries de escrita. Campos e endereços foram validados.
                report["status"] = "WRITE_NOT_CONFIRMED"
                response = client.write_cells(requests)
                report["status"] = "WRITTEN_AWAITING_VERIFICATION"
                save_private_json(run_dir / "batch-response.json", response)
                after = parse_snapshot(client.snapshot(), management.worksheet)
                save_private_json(run_dir / "snapshot-after.json", after.raw)
                report.update(verify_after(before, after, plan))
                report["status"] = "UPDATED_AND_VERIFIED"
            else:
                report.update(verify_after(before, before, plan))
                report["status"] = "NO_CHANGES"
        print(f"Status: {report['status']}.")
        print(
            f"Linhas: {len(plan['updated_ids'])} com alterações, "
            f"{len(plan['skipped'])} preservadas por pendência/ausência de resultado, "
            f"{len(plan['unchanged_ids'])} já atualizadas."
        )
        print(f"Células calculadas no lote: {len(requests)}. Evidências: {run_dir}")
        if not args.execute:
            print("Prévia somente de leitura. Nenhuma célula foi escrita.")
        return 0
    except Exception as exc:
        if report["status"] in {"READING", "PREVIEW"}:
            report["status"] = "FAILED_BEFORE_WRITE"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
        raise
    finally:
        try:
            save_private_json(run_dir / "report.json", report)
        finally:
            client.close()
