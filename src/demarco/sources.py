"""Contratos das entradas recebidas; nomes originais mantidos para rastreabilidade."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    filename: str
    columns: tuple[str, ...]
    key: tuple[str, ...]


SOURCES = (
    Source(
        "colaboradores",
        "base_colaboradores.xlsx",
        (
            "id_colaborador",
            "nome",
            "cargo",
            "departamento",
            "salario_mensal",
            "id_escala",
            "data_admissao",
            "data_desligamento",
            "id_gestor",
        ),
        ("id_colaborador",),
    ),
    Source(
        "escalas",
        "escalas.xlsx",
        (
            "id_escala",
            "descricao",
            "dias_trabalho",
            "dia_dsr",
            "horas_diarias",
            "horas_sabado",
            "divisor_folha",
        ),
        ("id_escala",),
    ),
    Source(
        "ponto",
        "espelho_ponto_marcaoes.xlsx",
        (
            "data_registro",
            "id_colaborador",
            "jornada_esperada_horas",
            "horas_trabalhadas",
            "flag_dsr",
            "codigo_abono",
        ),
        ("id_colaborador", "data_registro"),
    ),
    Source(
        "gestao",
        "template_acoes_disciplinares.xlsx",
        (
            "ID_Colaborador",
            "Nome",
            "Departamento",
            "Gestor",
            "Total_Faltas_Injustificadas",
            "Total_DSR_Perdido",
            "Acao_Disciplinar_Recomendada",
            "Data_Ultimo_Processamento",
            "Data_Conversa_1on1",
            "Advertencia_Aplicada_SN",
            "Observacoes_Gestor",
        ),
        ("ID_Colaborador",),
    ),
)

MANUAL_COLUMNS = ("Data_Conversa_1on1", "Advertencia_Aplicada_SN", "Observacoes_Gestor")
CALCULATED_COLUMNS = (
    "Total_Faltas_Injustificadas",
    "Total_DSR_Perdido",
    "Acao_Disciplinar_Recomendada",
    "Data_Ultimo_Processamento",
)
