"""Configuração sem segredos; variáveis do ambiente prevalecem sobre o .env local."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from demarco.ingestion import InputError


@dataclass(frozen=True)
class CloudConfig:
    project: str
    dataset: str
    location: str
    max_bytes_billed: int
    credentials_file: Path | None = None

    @property
    def dataset_id(self) -> str:
        return f"{self.project}.{self.dataset}"


@dataclass(frozen=True)
class ManagementConfig:
    spreadsheet_id: str
    worksheet: str


def management_config(env_file: Path = Path(".env")) -> ManagementConfig:
    values = {**dotenv_values(env_file), **os.environ}
    spreadsheet_id = values.get("MANAGEMENT_SPREADSHEET_ID", "")
    worksheet = values.get("MANAGEMENT_WORKSHEET", "")
    if not spreadsheet_id or not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", spreadsheet_id):
        raise InputError("Defina um MANAGEMENT_SPREADSHEET_ID válido no .env.")
    if not worksheet or not worksheet.strip():
        raise InputError("Defina MANAGEMENT_WORKSHEET com o nome exato da aba.")
    return ManagementConfig(spreadsheet_id, worksheet)


def cloud_config(env_file: Path = Path(".env")) -> CloudConfig:
    values = {**dotenv_values(env_file), **os.environ}
    project = values.get("GOOGLE_CLOUD_PROJECT", "")
    dataset = values.get("BIGQUERY_DATASET", "demarco_absenteismo")
    location = values.get("BIGQUERY_LOCATION", "US")
    if not project or not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
        raise InputError("Defina um GOOGLE_CLOUD_PROJECT válido no .env ou no ambiente.")
    if not dataset or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,1023}", dataset):
        raise InputError("BIGQUERY_DATASET inválido.")
    if not location or not re.fullmatch(r"[A-Za-z0-9-]+", location):
        raise InputError("BIGQUERY_LOCATION inválido.")
    try:
        limit = int(values.get("BIGQUERY_MAX_BYTES_BILLED", "1073741824"))
    except (TypeError, ValueError) as exc:
        raise InputError("BIGQUERY_MAX_BYTES_BILLED deve ser um inteiro positivo.") from exc
    if limit <= 0:
        raise InputError("BIGQUERY_MAX_BYTES_BILLED deve ser um inteiro positivo.")
    credential_path = values.get("GOOGLE_APPLICATION_CREDENTIALS")
    credentials_file = None
    if credential_path:
        credentials_file = Path(credential_path).expanduser()
        if not credentials_file.is_absolute():
            credentials_file = env_file.resolve().parent / credentials_file
        if not credentials_file.is_file():
            raise InputError("Arquivo GOOGLE_APPLICATION_CREDENTIALS não encontrado.")
    return CloudConfig(project, dataset, location, limit, credentials_file)
