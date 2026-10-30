"""Gera fórmulas e links de criação a partir do contrato do dashboard, sem criar relatórios."""

import argparse
from pathlib import Path

from demarco.config import cloud_config
from demarco.dashboard import create_report_url, load_report_spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--spec", type=Path, default=Path("dashboard/report_spec.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/dashboard"))
    args = parser.parse_args()
    config = cloud_config(args.env_file)
    spec = load_report_spec(args.spec)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Fórmulas do dashboard",
        "",
        "Gerado por `scripts/build_looker_guide.py` a partir de `dashboard/report_spec.json`.",
        "As mesmas fórmulas são verificadas no BigQuery antes da montagem visual.",
        "",
        "Criar os campos na fonte indicada e manter a agregação automática nas fórmulas agregadas.",
        "Percentuais são razões de 0 a 1: formatar como porcentagem, sem multiplicar por 100.",
        "Valores monetários são parciais; formatar como BRL com duas casas.",
        "",
    ]
    for alias, view in spec["sources"].items():
        lines += [f"## Fonte `{view}`", ""]
        for metric in spec["metrics"]:
            if metric["source"] == alias:
                lines += [
                    f"### {metric['label']}",
                    "",
                    f"ID de referência: `{metric['id']}`. Tipo: `{metric['type']}`.",
                    "",
                    "```text",
                    metric["formula"],
                    "```",
                    "",
                ]
    (args.output_dir / "formulas.md").write_text("\n".join(lines), encoding="utf-8")
    links = [
        "# Links de criação",
        "",
        "Estes links iniciam a criação com uma fonte pré-configurada. "
        "Não são relatórios publicados.",
        "Exigem navegador, login, acesso aos dados e salvamento na conta Google do usuário.",
        "Não montam automaticamente o layout personalizado de quatro páginas.",
        "",
        "Use o primeiro link para iniciar o relatório; adicione as outras duas fontes pelo editor.",
        "",
    ]
    for alias, view in spec["sources"].items():
        links.append(f"- [{view}]({create_report_url(config, spec, alias)})")
    links += [
        "",
        "[Referência da Linking API](https://developers.google.com/data-studio/integrate/linking-api).",
        "",
    ]
    (args.output_dir / "links.md").write_text("\n".join(links), encoding="utf-8")
    print(
        f"Fórmulas e links de criação gerados em {args.output_dir}. Nenhum relatório foi publicado."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
