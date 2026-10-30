-- Diagnóstico analítico: classificações são exclusivas; motivos podem se sobrepor.
SELECT 'CLASSIFICACAO_DIARIA' AS tipo, classificacao AS grupo,
  COUNT(*) AS linhas, COUNT(DISTINCT id_colaborador) AS colaboradores,
  SUM(horas_abonadas) AS horas_abonadas, SUM(horas_injustificadas) AS horas_injustificadas
FROM `{{dataset}}.fct_ausencias_diarias`
GROUP BY classificacao
UNION ALL
SELECT 'MOTIVO_PENDENCIA', motivo,
  COUNT(*), COUNT(DISTINCT id_colaborador), CAST(NULL AS NUMERIC), CAST(NULL AS NUMERIC)
FROM `{{dataset}}.qa_ausencias_diarias`
GROUP BY motivo
ORDER BY tipo, grupo;
