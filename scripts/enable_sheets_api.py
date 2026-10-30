"""Habilita somente a Google Sheets API no projeto configurado, sem modificar planilhas."""

import argparse
import time
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession

from demarco.config import cloud_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    config = cloud_config(args.env_file)
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    if config.credentials_file:
        credentials, _ = google.auth.load_credentials_from_file(
            str(config.credentials_file), scopes=scopes
        )
    else:
        credentials, _ = google.auth.default(scopes=scopes)
    with AuthorizedSession(credentials) as session:
        url = f"https://serviceusage.googleapis.com/v1/projects/{config.project}/services/sheets.googleapis.com"
        response = session.post(url + ":enable", json={}, timeout=45)
        if not response.ok:
            print(f"Falha ao habilitar Sheets API: HTTP {response.status_code}.")
            print(
                response.json()
                .get("error", {})
                .get("message", "Consulte as permissões do projeto.")
            )
            return 1
        operation = response.json()
        for _ in range(20):
            if operation.get("done"):
                if operation.get("error"):
                    print(operation["error"].get("message", "Operação falhou."))
                    return 1
                print("Google Sheets API habilitada.")
                return 0
            time.sleep(1)
            response = session.get(
                "https://serviceusage.googleapis.com/v1/" + operation["name"], timeout=30
            )
            response.raise_for_status()
            operation = response.json()
    print("Habilitação solicitada; a operação ainda não terminou.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
