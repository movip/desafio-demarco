{{finance_udf}}

-- Regressões das regras, executadas com as mesmas funções utilizadas no modelo.
ASSERT (
  classificar_dsr(0, 0, 0, TRUE) = 'PRESERVADO'
  AND classificar_dsr(1, 0, 0, TRUE) = 'PERDIDO'
  AND classificar_dsr(3, 0, 0, TRUE) = 'PERDIDO'
  AND classificar_dsr(1, 2, 5, TRUE) = 'PERDIDO'
  AND classificar_dsr(0, 1, 0, TRUE) = 'INDETERMINADO'
  AND classificar_dsr(0, 0, 5, TRUE) = 'INDETERMINADO'
  AND classificar_dsr(1, 0, 0, FALSE) = 'PENDENTE_CADASTRO'
  AND classificar_dsr(-1, 0, 0, TRUE) = 'PENDENTE_DADOS'
) AS 'Uma falta integral confirma a perda; ausência parcial sozinha não a dispara';

ASSERT (
  valorizar_horas(NUMERIC '8.8', NUMERIC '2200', NUMERIC '220') = NUMERIC '88'
  AND valorizar_horas(NUMERIC '0', NULL, NULL) = NUMERIC '0'
  AND valorizar_horas(NUMERIC '8', NULL, NUMERIC '220') IS NULL
  AND valorizar_horas(NUMERIC '8', NUMERIC '2200', NUMERIC '0') IS NULL
  AND valorizar_horas(NULL, NUMERIC '2200', NUMERIC '220') IS NULL
  AND valorizar_horas(NUMERIC '-1', NUMERIC '2200', NUMERIC '220') IS NULL
  AND ROUND(valorizar_dsr('PERDIDO', NUMERIC '2200', NUMERIC '220', NUMERIC '44'), 2) = NUMERIC '73.33'
  AND ROUND(valorizar_dsr('PERDIDO', NUMERIC '2000', NUMERIC '200', NUMERIC '40'), 2) = NUMERIC '66.67'
  AND valorizar_dsr('PERDIDO', NUMERIC '1800', NUMERIC '180', NUMERIC '36') = NUMERIC '60'
  AND valorizar_dsr('PRESERVADO', NULL, NULL, NULL) = NUMERIC '0'
  AND valorizar_dsr('PERDIDO', NULL, NUMERIC '180', NUMERIC '36') IS NULL
  AND valorizar_dsr('INDETERMINADO', NUMERIC '1800', NUMERIC '180', NUMERIC '36') IS NULL
  AND ROUND(valorizar_horas(NUMERIC '8.8', NUMERIC '2200', NUMERIC '220')
    + valorizar_dsr('PERDIDO', NUMERIC '2200', NUMERIC '220', NUMERIC '44'), 2) = NUMERIC '161.33'
  AND ROUND(valorizar_horas(NUMERIC '7.2', NUMERIC '1800', NUMERIC '180')
    + NUMERIC '2' * valorizar_dsr('PERDIDO', NUMERIC '1800', NUMERIC '180', NUMERIC '36'), 2) = NUMERIC '192'
) AS 'As fórmulas financeiras devem preservar precisão e não inventar salário';

ASSERT (
  recomendar_acao(0, 0, TRUE) = 'Sem ação requerida'
  AND recomendar_acao(1, 0, TRUE) = 'Alinhamento em 1-on-1'
  AND recomendar_acao(2, 0, TRUE) = 'Advertência Escrita'
  AND recomendar_acao(3, 1, TRUE) = 'Advertência Escrita'
  AND recomendar_acao(4, 0, TRUE) = 'Suspensão Disciplinar (1 a 3 dias)'
  AND recomendar_acao(2, 2, TRUE) = 'Suspensão Disciplinar (1 a 3 dias)'
  AND recomendar_acao(2, 1, TRUE) = 'Advertência Escrita'
  AND recomendar_acao(0, 0, FALSE) IS NULL
  AND recomendar_acao(1, 0, FALSE) IS NULL
  AND recomendar_acao(4, 0, FALSE) = 'Suspensão Disciplinar (1 a 3 dias)'
  AND recomendar_acao(4, NULL, FALSE) = 'Suspensão Disciplinar (1 a 3 dias)'
  AND recomendar_acao(NULL, 2, FALSE) = 'Suspensão Disciplinar (1 a 3 dias)'
  AND recomendar_acao(-1, 0, TRUE) IS NULL
) AS 'A régua deve manter textos exatos, precedência e pendências explícitas';

ASSERT (NOT EXISTS (
  SELECT id_colaborador, ancora_ciclo FROM `{{dataset}}.fct_dsr_ciclos`
  GROUP BY id_colaborador, ancora_ciclo HAVING COUNT(*) != 1
)) AS 'Um registro por ciclo e colaborador';

ASSERT (NOT EXISTS (
  SELECT id_colaborador, data_descanso FROM `{{dataset}}.fct_dsr_diario`
  GROUP BY id_colaborador, data_descanso HAVING COUNT(*) != 1
)) AS 'Cada descanso só pode ser contado uma vez';

ASSERT (
  (SELECT COUNT(*) FROM `{{dataset}}.fct_dsr_diario`) =
  (SELECT SUM(descansos_no_periodo) FROM `{{dataset}}.fct_dsr_ciclos`)
) AS 'Os descansos físicos devem conciliar com os grupos semanais';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.fct_dsr_ciclos`
  WHERE status_dsr = 'PERDIDO' AND (faltas_integrais_confirmadas = 0 OR NOT cadastro_confiavel)
)) AS 'Nenhum DSR pode ser perdido sem uma falta integral confirmada e identidade confiável';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.fct_dsr_ciclos`
  WHERE status_dsr = 'PRESERVADO' AND
    (faltas_integrais_confirmadas > 0 OR dias_sem_base > 0 OR dias_pendentes > 0)
)) AS 'Ciclos inconclusivos não podem virar preservados por ausência de evidência';

ASSERT (NOT EXISTS (
  SELECT 1 FROM (
    SELECT *,
      LAG(perdido_no_escopo_disciplinar) OVER (PARTITION BY id_colaborador ORDER BY ancora_ciclo) AS anterior_perdido,
      LAG(ancora_ciclo) OVER (PARTITION BY id_colaborador ORDER BY ancora_ciclo) AS anterior_ancora,
      LAG(sequencia_ciclos_perdidos) OVER (PARTITION BY id_colaborador ORDER BY ancora_ciclo) AS anterior_sequencia
    FROM `{{dataset}}.fct_dsr_ciclos`
  )
  WHERE sequencia_ciclos_perdidos != CASE
    WHEN NOT perdido_no_escopo_disciplinar THEN 0
    WHEN anterior_perdido AND DATE_DIFF(ancora_ciclo, anterior_ancora, DAY) = 7 THEN anterior_sequencia + 1
    ELSE 1 END
)) AS 'Sequências devem avançar por semanas e reiniciar em ciclos não perdidos';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.fct_dsr_diario`
  WHERE data_descanso NOT BETWEEN DATE '2025-06-01' AND DATE '2025-08-31'
    OR data_descanso < ancora_ciclo OR DATE_DIFF(data_descanso, ancora_ciclo, DAY) > 1
)) AS 'Descansos devem respeitar o ciclo e a janela, sem cobrar setembro';

ASSERT (
  (SELECT COUNT(*) FROM `{{dataset}}.fct_impacto_diario`) =
  (SELECT COUNT(*) FROM `{{dataset}}.fct_ausencias_diarias`)
) AS 'A junção financeira não pode multiplicar as linhas diárias';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.fct_impacto_diario`
  WHERE horas_injustificadas > 0 AND salario_pendente AND valor_horas_nao_arredondado IS NOT NULL
)) AS 'Horas sem salário confiável não podem ganhar um preço artificial';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.fct_impacto_diario`
  WHERE valor_horas_nao_arredondado < 0 OR valor_dsr_componente < 0
    OR (NOT elegivel_indicadores AND valor_horas_nao_arredondado IS NOT NULL)
)) AS 'Componentes financeiros devem ser não negativos e respeitar a elegibilidade';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.mart_gestao_colaboradores`
  WHERE (financeiro_incompleto AND desconto_total_periodo IS NOT NULL)
    OR (dias_elegiveis = 0 AND desconto_estimado_confirmado IS NOT NULL)
    OR (elegivel_reverse_etl AND (acao_disciplinar_recomendada IS NULL
        OR total_faltas_injustificadas IS NULL OR total_dsr_perdido IS NULL))
)) AS 'O resumo deve distinguir subtotais, totais inconclusivos e dados publicáveis';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.mart_gestao_colaboradores`
  WHERE (dias_horas_sem_valoracao > 0 OR dsrs_sem_valoracao > 0)
    AND desconto_estimado_confirmado = 0
)) AS 'Componentes positivos sem preço não podem produzir uma estimativa de custo zero';

ASSERT (NOT EXISTS (
  SELECT id_colaborador FROM `{{dataset}}.mart_gestao_colaboradores`
  GROUP BY id_colaborador HAVING COUNT(*) != 1
)) AS 'Uma recomendação por colaborador';

ASSERT (
  (SELECT SUM(total_faltas_injustificadas_confirmadas) FROM `{{dataset}}.mart_gestao_colaboradores`) =
  (SELECT COUNTIF(falta_integral_injustificada) FROM `{{dataset}}.fct_ausencias_diarias`)
) AS 'Faltas da gestão devem conciliar com a fato diária';

ASSERT (
  ABS((SELECT SUM(subtotal_conhecido_nao_arredondado) FROM `{{dataset}}.mart_gestao_colaboradores`) -
      (SELECT SUM(subtotal_conhecido_nao_arredondado) FROM `{{dataset}}.mart_impacto_mensal`)) < NUMERIC '0.00001'
) AS 'Os valores não arredondados devem conciliar entre os meses e o período';

ASSERT (NOT EXISTS (
  SELECT id_colaborador FROM `{{dataset}}.mart_gestao_colaboradores`
  EXCEPT DISTINCT
  SELECT UPPER(TRIM(ID_Colaborador)) FROM `{{dataset}}.stg_gestao_referencia`
)) AS 'Os colaboradores ativos devem ter correspondência no template recebido';

SELECT COUNT(*) AS colaboradores_no_periodo,
  SUM(total_faltas_injustificadas_confirmadas) AS faltas_integrais_confirmadas,
  SUM(total_dsr_perdido_confirmado) AS dsrs_perdidos_confirmados,
  SUM(dsrs_indeterminados) AS dsrs_indeterminados,
  SUM(dsrs_com_fronteira) AS dsrs_com_fronteira,
  ROUND(SUM(valor_horas_confirmado_nao_arredondado), 2) AS desconto_horas_conhecido,
  ROUND(SUM(valor_dsr_confirmado_nao_arredondado), 2) AS desconto_dsr_conhecido,
  ROUND(SUM(IF(dias_elegiveis > 0, subtotal_conhecido_nao_arredondado, NULL)), 2)
    AS desconto_confirmado_conhecido,
  COUNTIF(financeiro_incompleto) AS colaboradores_com_financeiro_incompleto,
  SUM(dias_horas_sem_valoracao) AS dias_com_horas_sem_valoracao,
  SUM(dsrs_sem_valoracao) AS dsrs_perdidos_sem_valoracao,
  COUNTIF(elegivel_reverse_etl) AS colaboradores_elegiveis_reverse_etl,
  COUNTIF(acao_disciplinar_recomendada IS NULL) AS recomendacoes_pendentes,
  COUNTIF(acao_disciplinar_recomendada = 'Suspensão Disciplinar (1 a 3 dias)') AS recomendacoes_suspensao,
  BIT_XOR(FARM_FINGERPRINT(TO_JSON_STRING(m))) AS assinatura_resultado
FROM `{{dataset}}.mart_gestao_colaboradores` AS m;
