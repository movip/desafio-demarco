"""Gera referência vetorial da página inicial com dados conferidos no BigQuery."""

import argparse
import json
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from demarco.bigquery import create_client, run_staging, staging_sql
from demarco.config import cloud_config
from demarco.dashboard import load_report_spec


def br(value, places=0):
    return (
        f"{Decimal(str(value)):,.{places}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    )


def decimal(value):
    return Decimal(str(value)) if value is not None else Decimal(0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics", type=Path, default=Path("artifacts/bigquery/bq-dashboard-check-result.json")
    )
    parser.add_argument(
        "--charts", type=Path, default=Path("artifacts/bigquery/dashboard-charts-result.json")
    )
    parser.add_argument(
        "--refresh-charts", action="store_true", help="Consulta as séries reais no BigQuery."
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--spec", type=Path, default=Path("dashboard/report_spec.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/dashboard/layout.svg"))
    args = parser.parse_args()
    evidence = json.loads(args.metrics.read_text(encoding="utf-8"))
    if evidence.get("completed") is not True or len(evidence.get("rows", [])) != 1:
        raise ValueError("A referência visual exige uma conferência real concluída.")
    metrics = evidence["rows"][0]
    theme = load_report_spec(args.spec)["theme"]
    if args.refresh_charts:
        config = cloud_config(args.env_file)
        sql = staging_sql(Path("sql/14_dashboard_charts.sql"), config)
        with create_client(config) as client:
            report = run_staging(client, config, sql)
        args.charts.parent.mkdir(parents=True, exist_ok=True)
        args.charts.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    charts = None
    if args.charts.exists():
        report = json.loads(args.charts.read_text(encoding="utf-8"))
        if report.get("completed") is not True or len(report.get("rows", [])) != 1:
            raise ValueError("A consulta das séries precisa estar concluída.")
        charts = json.loads(report["rows"][0]["chart_data"], parse_float=Decimal)
        for field in ["horas_injustificadas", "horas_abonadas"]:
            total = sum(decimal(row[field]) for row in charts["meses"])
            if abs(total - decimal(metrics[field])) > Decimal("0.000001"):
                raise ValueError(f"Séries e cartões divergem em {field}; atualize a conferência.")
        total = sum(decimal(row["valor"]) for row in charts["departamentos"])
        if abs(total - decimal(metrics["desconto_conhecido"])) > Decimal("0.01"):
            raise ValueError("Série de descontos diverge dos cartões; atualize a conferência.")

    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="1000" '
        'viewBox="0 0 1440 1000">',
        "<title>Demarco — referência visual da Visão geral</title>",
        "<desc>Referência para montagem no Looker Studio. Os filtros desenhados não são "
        "interativos. Totais conferidos; gráficos reais quando a consulta de séries é fornecida. "
        "Este arquivo não é um relatório publicado.</desc>",
        '<g font-family="Arial, sans-serif">',
    ]

    def rect(x, y, w, h, fill, border="none", radius=10):
        svg.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
            f'fill="{fill}" stroke="{border}"/>'
        )

    def text(x, y, value, size=14, color=None, bold=False, anchor="start"):
        svg.append(
            f'<text x="{x}" y="{y}" font-size="{size}" fill="{color or theme["text"]}" '
            f'font-weight="{700 if bold else 400}" text-anchor="{anchor}">'
            f"{escape(str(value))}</text>"
        )

    def line(x1, y1, x2, y2):
        svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{theme["border"]}"/>')

    muted = "#64748B"
    rect(0, 0, 1440, 1000, theme["background"], radius=0)
    rect(40, 28, 4, 70, theme["accent"], radius=2)
    text(60, 42, "DEMARCO / GESTÃO DE PESSOAS", 11, theme["accent"], True)
    text(60, 76, "Absenteísmo e impacto em folha", 30, bold=True)
    text(60, 100, "Visão geral · Junho a agosto de 2025 · Dados sintéticos", 14, muted)
    rect(1220, 42, 180, 34, "#E6F4F1")
    text(1310, 64, "VISÃO GERAL", 12, theme["accent"], True, "middle")

    for x, label, value in [
        (40, "DEPARTAMENTO", "Todos os departamentos"),
        (500, "GESTOR", "Todos os gestores"),
        (960, "PERÍODO DE ANÁLISE", "01/06/2025 a 31/08/2025"),
    ]:
        rect(x, 124, 440, 64, theme["surface"], theme["border"])
        text(x + 16, 146, label, 10, muted, True)
        text(x + 16, 172, value, 14)
        text(x + 414, 168, "⌄", 18, muted, anchor="middle")

    cards = [
        ("Faltas integrais", br(metrics["faltas_integrais"]), "Confirmadas", theme["loss"]),
        (
            "Horas injustificadas",
            br(metrics["horas_injustificadas"], 1),
            "Horas decimais confirmadas",
            theme["loss"],
        ),
        ("DSRs perdidos", br(metrics["dsrs_perdidos"]), "Descansos confirmados", theme["text"]),
        (
            "Desconto parcial",
            "R$ " + br(metrics["desconto_conhecido"], 2),
            "Subtotal conhecido",
            theme["accent"],
        ),
        (
            "Taxa injustificada",
            br(decimal(metrics["taxa_injustificada"]) * 100, 2) + "%",
            "Sobre horas validadas",
            theme["text"],
        ),
        ("Dias pendentes", br(metrics["dias_pendentes"]), "Aguardam validação", theme["warning"]),
    ]
    for index, (label, value, caption, color) in enumerate(cards):
        x = 40 + index * 230
        rect(
            x,
            212,
            210,
            128,
            "#EAF7F3" if index == 3 else theme["surface"],
            "#BFE3D7" if index == 3 else theme["border"],
        )
        text(x + 16, 240, label, 13, muted)
        text(x + 16, 289, value, 26 if index == 3 else 34, color, True)
        text(x + 16, 319, caption, 11, muted)

    rect(40, 364, 810, 344, theme["surface"], theme["border"])
    rect(870, 364, 530, 344, theme["surface"], theme["border"])
    text(64, 398, "Evolução mensal das ausências", 18, bold=True)
    text(64, 422, "Horas decimais · Mesma escala nas duas séries", 12, muted)
    text(894, 398, "Desconto por departamento", 18, bold=True)
    text(894, 422, "Subtotal conhecido · Valores em reais", 12, muted)

    if charts:
        rect(64, 442, 10, 10, theme["loss"], radius=2)
        text(82, 451, "Injustificadas", 12, muted)
        rect(200, 442, 10, 10, theme["accent"], radius=2)
        text(218, 451, "Abonadas", 12, muted)
        months = charts["meses"]
        highest = max(
            decimal(row[field])
            for row in months
            for field in ["horas_injustificadas", "horas_abonadas"]
        )
        step = max(Decimal(50), (highest / 3 / 50).to_integral_value(ROUND_CEILING) * 50)
        maximum = step * 3
        for tick in range(4):
            y = 654 - tick * 58
            line(104, y, 822, y)
            text(88, y + 4, br(step * tick), 11, muted, anchor="end")
        month_names = [
            "Jan",
            "Fev",
            "Mar",
            "Abr",
            "Mai",
            "Jun",
            "Jul",
            "Ago",
            "Set",
            "Out",
            "Nov",
            "Dez",
        ]
        for index, row in enumerate(months):
            center = 104 + (index + 0.5) * 718 / len(months)
            for field, offset, color in [
                ("horas_injustificadas", -48, theme["loss"]),
                ("horas_abonadas", 8, theme["accent"]),
            ]:
                value = decimal(row[field])
                height = float(value / maximum) * 174
                if height > 0:
                    rect(center + offset, 654 - height, 40, height, color, radius=0)
                label = br(value, 2).rstrip("0").rstrip(",") if value else "0"
                text(center + offset + 20, 646 - height, label, 12, color, True, "middle")
            month = int(row["mes"][5:7])
            text(
                center,
                682,
                month_names[month - 1] + "/" + row["mes"][:4],
                12,
                muted,
                anchor="middle",
            )

        departments = charts["departamentos"]
        highest = max(decimal(row["valor"]) for row in departments)
        maximum = max(Decimal(1000), (highest / 1000).to_integral_value(ROUND_CEILING) * 1000)
        spacing = min(42, 208 / max(1, len(departments)))
        for index, row in enumerate(departments):
            y = 462 + index * spacing
            text(894, y + 17, row["departamento"], 12)
            rect(984, y, 264, 24, "#F1F5F9", radius=0)
            if row["valor"] is not None:
                width = float(decimal(row["valor"]) / maximum) * 264
                rect(984, y, width, 24, theme["accent"], radius=0)
            text(
                1376,
                y + 17,
                br(row["valor"], 2) if row["valor"] is not None else "—",
                12,
                bold=True,
                anchor="end",
            )
        text(984, 692, "0", 11, muted)
        text(1248, 692, br(maximum), 11, muted, anchor="end")
    else:
        text(445, 560, "Espaço para o gráfico mensal", 17, muted, anchor="middle")
        text(1135, 560, "Espaço para as barras", 17, muted, anchor="middle")

    text(40, 741, "Cobertura e qualidade", 16, bold=True)
    details = [
        (
            "Cobertura das linhas",
            br(decimal(metrics["cobertura_linhas"]) * 100, 2) + "%",
            "Linhas elegíveis / observadas",
        ),
        ("Ausências parciais", br(metrics["ausencias_parciais"]), "Ocorrências confirmadas"),
        ("Horas abonadas", br(metrics["horas_abonadas"], 1), "Justificadas por abono"),
        ("DSRs sem conclusão", br(metrics["dsrs_indeterminados"]), "Descansos em revisão"),
    ]
    for index, (label, value, caption) in enumerate(details):
        x = 40 + index * 345
        rect(x, 754, 325, 112, theme["surface"], theme["border"])
        text(x + 16, 781, label, 13, muted)
        text(x + 16, 824, value, 30, bold=True)
        text(x + 16, 848, caption, 11, muted)

    rect(40, 890, 1360, 64, "#FFFBEB", "#FDE68A")
    rect(56, 906, 28, 28, "#FEF3C7", radius=14)
    text(70, 926, "i", 18, theme["warning"], True, "middle")
    text(
        98,
        916,
        "Valores financeiros parciais: há parcelas sem salário confiável "
        "e descansos iniciais que dependem de maio.",
        13,
        theme["warning"],
    )
    text(
        98,
        939,
        "Datas pendentes ficam fora dos totais confirmados. "
        "Consulte a página de qualidade para revisar os casos.",
        13,
        theme["warning"],
    )
    text(
        40,
        983,
        "Referência visual para montagem no Looker Studio · "
        "Filtros ilustrados, sem interação · Não é um dashboard publicado",
        11,
        muted,
    )
    svg += ["</g>", "</svg>"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(svg) + "\n", encoding="utf-8")
    print(f"Referência visual salva em {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
