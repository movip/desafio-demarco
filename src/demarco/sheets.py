"""Cliente restrito a leitura da planilha e escrita de valores de células selecionadas."""

from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession

from demarco.config import CloudConfig, ManagementConfig
from demarco.ingestion import InputError

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


class SheetsError(InputError):
    def __init__(self, status: int, reason: str, message: str):
        self.status = status
        self.reason = reason
        super().__init__(f"Google Sheets HTTP {status} ({reason}): {message}")


class SheetsClient:
    def __init__(self, session: AuthorizedSession, config: ManagementConfig):
        self.session = session
        self.config = config
        self.url = f"https://sheets.googleapis.com/v4/spreadsheets/{config.spreadsheet_id}"

    def _request(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        response = self.session.request(method, url, timeout=45, **kwargs)
        if not response.ok:
            try:
                error = response.json().get("error", {})
            except ValueError:
                error = {}
            reason = error.get("status", "REQUEST_FAILED")
            for detail in error.get("details", []):
                if detail.get("reason"):
                    reason = detail["reason"]
                    break
            raise SheetsError(
                response.status_code, reason, error.get("message", "Falha de acesso.")
            )
        return response.json()

    def metadata(self) -> dict[str, Any]:
        return self._request(
            "GET",
            self.url,
            params={
                "fields": "spreadsheetId,properties(title),sheets(properties)",
            },
        )

    def snapshot(self) -> dict[str, Any]:
        title = self.config.worksheet.replace("'", "''")
        return self._request(
            "GET",
            self.url,
            params={
                "ranges": f"'{title}'",
                "includeGridData": "true",
                "fields": (
                    "spreadsheetId,properties(title),sheets(properties,"
                    "data(startRow,startColumn,rowData(values(userEnteredValue,effectiveValue,"
                    "userEnteredFormat,note,dataValidation,textFormatRuns))))"
                ),
            },
        )

    def write_cells(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request("POST", self.url + ":batchUpdate", json={"requests": requests})

    def close(self) -> None:
        self.session.close()


def create_sheets_client(cloud: CloudConfig, management: ManagementConfig) -> SheetsClient:
    if cloud.credentials_file is not None:
        credentials, _ = google.auth.load_credentials_from_file(
            str(cloud.credentials_file), scopes=[SHEETS_SCOPE]
        )
    else:
        credentials, _ = google.auth.default(scopes=[SHEETS_SCOPE])
    return SheetsClient(AuthorizedSession(credentials), management)
