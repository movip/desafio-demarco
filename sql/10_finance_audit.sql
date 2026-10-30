-- Auditoria de recomendações e apuração de DSR, com grãos explicitados em tipo.
SELECT 'RECOMENDACAO_POR_COLABORADOR' AS tipo,
  COALESCE(acao_disciplinar_recomendada, 'PENDENTE_VALIDACAO') AS grupo,
  COUNT(*) AS ocorrencias,
  SUM(total_faltas_injustificadas_confirmadas) AS faltas_confirmadas,
  SUM(total_dsr_perdido_confirmado) AS descansos_perdidos_confirmados,
  ROUND(SUM(IF(desconto_estimado_confirmado IS NOT NULL,
    subtotal_conhecido_nao_arredondado, NULL)), 2)
    AS valor_conhecido
FROM `{{dataset}}.mart_gestao_colaboradores`
GROUP BY acao_disciplinar_recomendada
UNION ALL
SELECT 'STATUS_POR_DESCANSO', status_dsr, COUNT(*), CAST(NULL AS INT64),
  COUNTIF(dsr_perdido), ROUND(SUM(valor_dsr_nao_arredondado), 2)
FROM `{{dataset}}.fct_dsr_diario`
GROUP BY status_dsr
UNION ALL
SELECT 'CICLOS_NA_FRONTEIRA', status_dsr, COUNT(*), SUM(faltas_integrais_confirmadas),
  SUM(IF(status_dsr = 'PERDIDO', descansos_no_periodo, 0)), CAST(NULL AS NUMERIC)
FROM `{{dataset}}.fct_dsr_ciclos`
WHERE ciclo_com_fronteira
GROUP BY status_dsr
ORDER BY tipo, grupo;
