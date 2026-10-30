-- As fórmulas são lidas do mesmo contrato que o guia manda copiar no Looker.
{{dashboard_metrics}}

ASSERT (NOT EXISTS (
  SELECT id_colaborador, data FROM `{{dataset}}.vw_dashboard_diario`
  GROUP BY id_colaborador, data HAVING COUNT(*) != 1
)) AS 'A fonte diária deve manter uma linha por ID e data';

ASSERT (
  (SELECT COUNT(*) FROM `{{dataset}}.vw_dashboard_diario`) =
  (SELECT COUNT(*) FROM `{{dataset}}.fct_ausencias_diarias`)
) AS 'Os joins de apresentação não podem multiplicar ou excluir observações';

ASSERT (NOT EXISTS (
  SELECT id_colaborador FROM `{{dataset}}.vw_dashboard_gestao`
  GROUP BY id_colaborador HAVING COUNT(*) != 1
)) AS 'Recomendações não podem ser repetidas por dia';

ASSERT (
  (SELECT SUM(faltas_integrais) FROM `{{dataset}}.vw_dashboard_diario`) =
  (SELECT COUNTIF(falta_integral_injustificada) FROM `{{dataset}}.fct_ausencias_diarias`)
  AND (SELECT SUM(dias_pendentes) FROM `{{dataset}}.vw_dashboard_diario`) =
  (SELECT COUNTIF(NOT elegivel_indicadores) FROM `{{dataset}}.fct_ausencias_diarias`)
  AND (SELECT SUM(horas_previstas) FROM `{{dataset}}.vw_dashboard_diario`) =
  (SELECT SUM(horas_esperadas_indicadores) FROM `{{dataset}}.fct_ausencias_diarias`)
) AS 'As medidas de frequência e qualidade devem conciliar com a fato';

ASSERT (
  (SELECT SUM(dsrs_perdidos) FROM `{{dataset}}.vw_dashboard_diario`) =
  (SELECT COUNTIF(dsr_perdido) FROM `{{dataset}}.fct_dsr_diario`)
  AND ABS((SELECT SUM(valor_conhecido_parcial) FROM `{{dataset}}.vw_dashboard_diario`) -
      (SELECT SUM(IF(dias_elegiveis > 0, subtotal_conhecido_nao_arredondado, NULL))
       FROM `{{dataset}}.mart_gestao_colaboradores`)) < NUMERIC '0.00001'
) AS 'Valores e DSRs devem manter a apuração financeira, sem duplicação';

ASSERT (
  (SELECT COUNT(*) FROM `{{dataset}}.vw_dashboard_qualidade`) =
  (SELECT COUNT(*) FROM `{{dataset}}.qa_ausencias_diarias`)
  AND (SELECT COUNT(DISTINCT id_dia) FROM `{{dataset}}.vw_dashboard_qualidade`) =
  (SELECT COUNTIF(NOT elegivel_indicadores) FROM `{{dataset}}.fct_ausencias_diarias`)
) AS 'Motivos podem se sobrepor, mas dias distintos devem conciliar';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.INFORMATION_SCHEMA.COLUMNS`
  WHERE table_name IN ('vw_dashboard_diario','vw_dashboard_gestao','vw_dashboard_qualidade')
    AND STARTS_WITH(data_type, 'ARRAY')
)) AS 'Fontes do Looker devem ter campos planos';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.INFORMATION_SCHEMA.COLUMNS`
  WHERE table_name = 'vw_dashboard_gestao' AND data_type IN ('DATE','DATETIME','TIMESTAMP')
)) AS 'A recomendação trimestral não deve aparentar um cálculo diário ou mensal';

-- Teste das fórmulas reais do contrato: taxa agregada deve ser 1/9, não a média 1/2.
ASSERT (
  (SELECT {{metric:taxa_injustificada}} FROM (
    SELECT NUMERIC '8' AS horas_previstas, NUMERIC '0' AS horas_injustificadas
    UNION ALL SELECT NUMERIC '1', NUMERIC '1'
  )) = SAFE_DIVIDE(NUMERIC '1', NUMERIC '9')
) AS 'Taxas devem dividir somas, não fazer média das taxas diárias';

ASSERT (
  (SELECT {{metric:taxa_injustificada}} FROM (
    SELECT NUMERIC '0' AS horas_previstas, NUMERIC '0' AS horas_injustificadas
  )) IS NULL
) AS 'Uma seleção sem jornada não pode produzir uma taxa falsa';

ASSERT (
  (SELECT {{metric:desconto_conhecido}} FROM (
    SELECT NUMERIC '0' AS valor_conhecido_parcial, 1 AS dias_horas_sem_valoracao,
      0 AS dsrs_sem_valoracao, 1 AS linhas_elegiveis
  )) IS NULL
  AND (SELECT {{metric:desconto_conhecido}} FROM (
    SELECT NUMERIC '0' AS valor_conhecido_parcial, 0 AS dias_horas_sem_valoracao,
      0 AS dsrs_sem_valoracao, 1 AS linhas_elegiveis
  )) = NUMERIC '0'
) AS 'Déficit sem preço não é custo zero, mas ausência comprovada de desconto pode ser zero';

ASSERT (
  (SELECT colaboradores_periodo FROM dashboard_metrics) =
  (SELECT COUNT(*) FROM `{{dataset}}.mart_gestao_colaboradores`)
  AND (SELECT registros_gestao FROM dashboard_metrics) =
  (SELECT COUNT(*) FROM `{{dataset}}.mart_gestao_colaboradores`)
) AS 'Headcount da apresentação deve respeitar o escopo de vínculo';

SELECT *,
  (SELECT BIT_XOR(FARM_FINGERPRINT(TO_JSON_STRING(d))) FROM `{{dataset}}.vw_dashboard_diario` AS d)
    AS assinatura_resultado
FROM dashboard_metrics;
