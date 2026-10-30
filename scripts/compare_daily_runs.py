"""Compara resumos e assinatura das linhas antes/depois de uma reexecução."""

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    valid = (
        before.get("completed") is True
        and after.get("completed") is True
        and before.get("rows") == after.get("rows")
        and len(before.get("rows", [])) == 1
        and "assinatura_resultado" in before["rows"][0]
    )
    print("Reexecução consistente." if valid else "Resultados ausentes ou divergentes.")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
