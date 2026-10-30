"""Leitura de metadados da planilha configurada, sem escrever em células."""

import argparse
import json
from pathlib import Path

from demarco.config import cloud_config, management_config
from demarco.ingestion import InputError
from demarco.sheets import create_sheets_client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    client = create_sheets_client(cloud_config(args.env_file), management_config(args.env_file))
    try:
        print(json.dumps(client.metadata(), ensure_ascii=False, indent=2))
    except InputError as exc:
        print(str(exc))
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
