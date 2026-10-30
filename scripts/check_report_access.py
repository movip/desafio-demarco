"""Confere a resposta HTTP do relatório; não valida gráficos ou acesso visual."""

import argparse
import json
import re
from datetime import UTC, datetime
from html import unescape
from pathlib import Path

import requests

REPORT_URL = "https://datastudio.google.com/reporting/7bdfde4c-c915-4549-ad2d-d13e40f32b2f"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-url", default=REPORT_URL)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/dashboard/report-access-check.json")
    )
    args = parser.parse_args()
    report = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "report_url": args.report_url,
        "method": "HTTP GET sem autenticação; não executa JavaScript",
        "visual_access_verified": False,
        "limitation": "Uma resposta HTTP não confirma a renderização dos gráficos "
        "nem as permissões das fontes.",
    }
    success = False
    try:
        with requests.get(args.report_url, timeout=25) as response:
            title = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.I | re.S)
            report.update(
                status_code=response.status_code,
                final_url=response.url,
                content_type=response.headers.get("Content-Type"),
                html_title=unescape(title.group(1).strip())[:200] if title else None,
                response_bytes=len(response.content),
            )
            success = 200 <= response.status_code < 300
    except requests.RequestException as exc:
        report["request_error"] = type(exc).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
