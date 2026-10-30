-- GoogleSQL. Complementa a fato diária sem alterar as fontes ou o Google Sheets.
{{finance_udf}}

CREATE OR REPLACE TABLE `{{dataset}}.int_descansos_contratuais` AS
SELECT k.id_colaborador, k.data_registro AS data_descanso, c.id_escala,
  -- Todos os contratos fixos recebidos iniciam o grupo de descansos no domingo.
  -- A segunda da escala noturna pertence ao domingo imediatamente anterior.
  IF(EXTRACT(DAYOFWEEK FROM k.data_registro) = 2,
     DATE_SUB(k.data_registro, INTERVAL 1 DAY), k.data_registro) AS ancora_ciclo,
  c.vinculo_confiavel AND NOT c.cadastro_critico_conflitante AS cadastro_confiavel
FROM `{{dataset}}.int_calendario_colaborador` AS k
JOIN `{{dataset}}.dim_colaboradores` AS c USING (id_colaborador)
WHERE k.descanso_contratual AND k.calendario_suportado
  AND c.id_escala IN ('ESC_40H', 'ESC_44H', 'ESC_36H_NOT');

CREATE OR REPLACE TABLE `{{dataset}}.fct_dsr_ciclos` AS
WITH cycles AS (
  SELECT id_colaborador, id_escala, ancora_ciclo,
    COUNT(*) AS descansos_no_periodo,
    ARRAY_AGG(data_descanso ORDER BY data_descanso) AS datas_descanso,
    LOGICAL_AND(cadastro_confiavel) AS cadastro_confiavel
  FROM `{{dataset}}.int_descansos_contratuais`
  GROUP BY id_colaborador, id_escala, ancora_ciclo
), bounds AS (
  SELECT *, DATE_SUB(ancora_ciclo, INTERVAL 6 DAY) AS inicio_ciclo,
    DATE_SUB(ancora_ciclo, INTERVAL 1 DAY) AS fim_ciclo
  FROM cycles
), expected AS (
  SELECT b.id_colaborador, b.ancora_ciclo, dia AS data_trabalho
  FROM bounds AS b
  JOIN `{{dataset}}.dim_colaboradores` AS c USING (id_colaborador)
  JOIN `{{dataset}}.dim_escalas` AS e ON e.id_escala = b.id_escala
  CROSS JOIN UNNEST(GENERATE_DATE_ARRAY(b.inicio_ciclo, b.fim_ciclo)) AS dia
  WHERE dia >= c.data_admissao AND (c.data_desligamento IS NULL OR dia <= c.data_desligamento)
    AND EXISTS (
      SELECT 1 FROM UNNEST(SPLIT(e.dias_trabalho, ',')) AS token
      WHERE TRIM(token) = ['DOM','SEG','TER','QUA','QUI','SEX','SAB'][OFFSET(EXTRACT(DAYOFWEEK FROM dia) - 1)]
    )
), observed AS (
  SELECT e.id_colaborador, e.ancora_ciclo,
    COUNT(*) AS dias_trabalho_previstos,
    COUNTIF(e.data_trabalho NOT BETWEEN DATE '2025-06-01' AND DATE '2025-08-31') AS dias_sem_base,
    COUNTIF(e.data_trabalho BETWEEN DATE '2025-06-01' AND DATE '2025-08-31'
      AND NOT COALESCE(f.elegivel_indicadores, FALSE)) AS dias_pendentes,
    COUNTIF(f.falta_integral_injustificada) AS faltas_integrais_confirmadas
  FROM expected AS e
  LEFT JOIN `{{dataset}}.fct_ausencias_diarias` AS f
    ON f.id_colaborador = e.id_colaborador AND f.data_registro = e.data_trabalho
  GROUP BY e.id_colaborador, e.ancora_ciclo
), classified AS (
  SELECT b.*, COALESCE(o.dias_trabalho_previstos, 0) AS dias_trabalho_previstos,
    COALESCE(o.dias_sem_base, 0) AS dias_sem_base,
    COALESCE(o.dias_pendentes, 0) AS dias_pendentes,
    COALESCE(o.faltas_integrais_confirmadas, 0) AS faltas_integrais_confirmadas,
    classificar_dsr(COALESCE(o.faltas_integrais_confirmadas, 0),
      COALESCE(o.dias_pendentes, 0), COALESCE(o.dias_sem_base, 0), b.cadastro_confiavel) AS status_dsr
  FROM bounds AS b
  LEFT JOIN observed AS o USING (id_colaborador, ancora_ciclo)
), tagged AS (
  SELECT *, dias_sem_base > 0 AS ciclo_com_fronteira,
    dias_sem_base = 0 AND status_dsr = 'PERDIDO' AS perdido_no_escopo_disciplinar,
    -- Domingo e segunda do mesmo ciclo nunca constituem semanas consecutivas.
    LAG(status_dsr) OVER (PARTITION BY id_colaborador ORDER BY ancora_ciclo) AS status_anterior,
    LAG(ancora_ciclo) OVER (PARTITION BY id_colaborador ORDER BY ancora_ciclo) AS ancora_anterior,
    LAG(dias_sem_base) OVER (PARTITION BY id_colaborador ORDER BY ancora_ciclo) AS fronteira_anterior
  FROM classified
), islands AS (
  SELECT *, SUM(IF(perdido_no_escopo_disciplinar
    AND status_anterior = 'PERDIDO' AND fronteira_anterior = 0
    AND DATE_DIFF(ancora_ciclo, ancora_anterior, DAY) = 7, 0, 1))
      OVER (PARTITION BY id_colaborador ORDER BY ancora_ciclo ROWS UNBOUNDED PRECEDING) AS grupo_sequencia
  FROM tagged
)
SELECT * EXCEPT(status_anterior, ancora_anterior, fronteira_anterior),
  IF(perdido_no_escopo_disciplinar,
    COUNTIF(perdido_no_escopo_disciplinar) OVER (
      PARTITION BY id_colaborador, grupo_sequencia ORDER BY ancora_ciclo ROWS UNBOUNDED PRECEDING
    ), 0) AS sequencia_ciclos_perdidos
FROM islands;

CREATE OR REPLACE TABLE `{{dataset}}.fct_dsr_diario` AS
SELECT d.id_colaborador, d.data_descanso, d.ancora_ciclo, d.id_escala,
  c.status_dsr, c.ciclo_com_fronteira, c.dias_sem_base, c.dias_pendentes,
  c.faltas_integrais_confirmadas, c.sequencia_ciclos_perdidos,
  CASE WHEN c.status_dsr = 'PERDIDO' THEN TRUE
       WHEN c.status_dsr = 'PRESERVADO' THEN FALSE ELSE NULL END AS dsr_perdido,
  e.jornada_semanal_contratual, e.divisor_folha, p.salario_mensal,
  valorizar_dsr(c.status_dsr, p.salario_mensal, e.divisor_folha, e.jornada_semanal_contratual)
    AS valor_dsr_nao_arredondado
FROM `{{dataset}}.int_descansos_contratuais` AS d
JOIN `{{dataset}}.fct_dsr_ciclos` AS c USING (id_colaborador, ancora_ciclo)
JOIN `{{dataset}}.dim_colaboradores` AS p USING (id_colaborador)
JOIN `{{dataset}}.dim_escalas` AS e ON e.id_escala = d.id_escala;

CREATE OR REPLACE TABLE `{{dataset}}.fct_impacto_diario` AS
SELECT f.id_colaborador, f.data_registro, DATE_TRUNC(f.data_registro, MONTH) AS mes,
  f.nome, f.departamento, f.id_gestor, f.id_escala, f.elegivel_indicadores,
  f.classificacao, f.motivos_pendencia, f.salario_mensal, f.salario_pendente,
  f.horas_esperadas_indicadores, f.horas_abonadas, f.horas_injustificadas,
  f.falta_integral_injustificada, f.ausencia_parcial_injustificada,
  e.divisor_folha, e.jornada_semanal_contratual,
  SAFE_DIVIDE(f.salario_mensal, NULLIF(e.divisor_folha, NUMERIC '0')) AS valor_hora,
  valorizar_horas(f.horas_injustificadas, f.salario_mensal, e.divisor_folha)
    AS valor_horas_nao_arredondado,
  d.ancora_ciclo, d.status_dsr, d.dsr_perdido, d.ciclo_com_fronteira,
  d.valor_dsr_nao_arredondado,
  CASE WHEN d.data_descanso IS NOT NULL THEN d.valor_dsr_nao_arredondado
       WHEN f.descanso_contratual IS FALSE THEN NUMERIC '0' ELSE NULL END AS valor_dsr_componente,
  d.data_descanso IS NOT NULL AS dia_dsr_apurado,
  IF(d.data_descanso IS NOT NULL AND d.status_dsr NOT IN ('PERDIDO', 'PRESERVADO'), 1, 0)
    AS dsrs_indeterminados,
  IF(d.data_descanso IS NOT NULL AND d.ciclo_com_fronteira, 1, 0) AS dsrs_com_fronteira,
  f.horas_injustificadas > 0 AND
    valorizar_horas(f.horas_injustificadas, f.salario_mensal, e.divisor_folha) IS NULL
    AS horas_sem_valoracao,
  d.dsr_perdido IS TRUE AND d.valor_dsr_nao_arredondado IS NULL AS dsr_sem_valoracao
FROM `{{dataset}}.fct_ausencias_diarias` AS f
LEFT JOIN `{{dataset}}.dim_escalas` AS e ON e.id_escala = f.id_escala
LEFT JOIN `{{dataset}}.fct_dsr_diario` AS d
  ON d.id_colaborador = f.id_colaborador AND d.data_descanso = f.data_registro;

CREATE OR REPLACE TABLE `{{dataset}}.mart_impacto_mensal` AS
SELECT id_colaborador, mes, ANY_VALUE(nome) AS nome,
  ANY_VALUE(departamento) AS departamento, ANY_VALUE(id_gestor) AS id_gestor,
  COUNT(*) AS dias_observados, COUNTIF(elegivel_indicadores) AS dias_elegiveis,
  COUNTIF(NOT elegivel_indicadores) AS dias_pendentes,
  COUNTIF(falta_integral_injustificada) AS faltas_integrais_confirmadas,
  COUNTIF(ausencia_parcial_injustificada) AS ausencias_parciais_confirmadas,
  SUM(horas_esperadas_indicadores) AS horas_esperadas_confirmadas,
  SUM(horas_abonadas) AS horas_abonadas_confirmadas,
  SUM(horas_injustificadas) AS horas_injustificadas_confirmadas,
  COUNTIF(dsr_perdido) AS dsrs_perdidos_confirmados,
  SUM(dsrs_indeterminados) AS dsrs_indeterminados,
  SUM(dsrs_com_fronteira) AS dsrs_com_fronteira,
  COUNTIF(horas_sem_valoracao) AS dias_horas_sem_valoracao,
  COUNTIF(dsr_sem_valoracao) AS dsrs_sem_valoracao,
  SUM(valor_horas_nao_arredondado) AS valor_horas_confirmado_nao_arredondado,
  SUM(valor_dsr_componente) AS valor_dsr_confirmado_nao_arredondado,
  SUM(IF(valor_horas_nao_arredondado IS NOT NULL OR valor_dsr_componente IS NOT NULL,
    COALESCE(valor_horas_nao_arredondado, NUMERIC '0')
    + COALESCE(valor_dsr_componente, NUMERIC '0'), NULL)) AS subtotal_conhecido_nao_arredondado,
  COUNTIF(valor_horas_nao_arredondado IS NOT NULL OR valor_dsr_componente IS NOT NULL)
    AS componentes_monetarios_conhecidos
FROM `{{dataset}}.fct_impacto_diario`
GROUP BY id_colaborador, mes;

CREATE OR REPLACE TABLE `{{dataset}}.mart_gestao_colaboradores` AS
WITH totais_pessoa AS (
  SELECT id_colaborador,
    SUM(dias_observados) AS dias_observados, SUM(dias_elegiveis) AS dias_elegiveis,
    SUM(dias_pendentes) AS dias_pendentes,
    SUM(faltas_integrais_confirmadas) AS total_faltas_injustificadas_confirmadas,
    SUM(ausencias_parciais_confirmadas) AS total_ausencias_parciais_confirmadas,
    SUM(horas_esperadas_confirmadas) AS horas_esperadas_confirmadas,
    SUM(horas_abonadas_confirmadas) AS horas_abonadas_confirmadas,
    SUM(horas_injustificadas_confirmadas) AS horas_injustificadas_confirmadas,
    SUM(dsrs_perdidos_confirmados) AS total_dsr_perdido_confirmado,
    SUM(dsrs_indeterminados) AS dsrs_indeterminados,
    SUM(dsrs_com_fronteira) AS dsrs_com_fronteira,
    SUM(dias_horas_sem_valoracao) AS dias_horas_sem_valoracao,
    SUM(dsrs_sem_valoracao) AS dsrs_sem_valoracao,
    SUM(valor_horas_confirmado_nao_arredondado) AS valor_horas_confirmado_nao_arredondado,
    SUM(valor_dsr_confirmado_nao_arredondado) AS valor_dsr_confirmado_nao_arredondado,
    SUM(subtotal_conhecido_nao_arredondado) AS subtotal_conhecido_nao_arredondado,
    SUM(componentes_monetarios_conhecidos) AS componentes_monetarios_conhecidos
  FROM `{{dataset}}.mart_impacto_mensal`
  GROUP BY id_colaborador
), cycles AS (
  SELECT id_colaborador, MAX(sequencia_ciclos_perdidos) AS maior_sequencia_ciclos_perdidos,
    COUNTIF(NOT ciclo_com_fronteira AND status_dsr NOT IN ('PERDIDO', 'PRESERVADO'))
      AS ciclos_internos_pendentes
  FROM `{{dataset}}.fct_dsr_ciclos`
  GROUP BY id_colaborador
), candidates AS (
  SELECT c.id_colaborador, c.nome, c.departamento, c.id_gestor, c.id_escala,
    c.salario_mensal, c.salario_pendente, c.cadastro_critico_conflitante,
    NOT COALESCE(e.calendario_suportado, FALSE) AS apuracao_dsr_indisponivel,
    e.jornada_semanal_divergente, r.* EXCEPT(id_colaborador),
    COALESCE(y.maior_sequencia_ciclos_perdidos, 0) AS maior_sequencia_ciclos_perdidos,
    COALESCE(y.ciclos_internos_pendentes, 0) AS ciclos_internos_pendentes,
    r.dias_pendentes = 0 AND c.vinculo_confiavel AND NOT c.cadastro_critico_conflitante
      AND COALESCE(e.calendario_suportado, FALSE)
      AND COALESCE(y.ciclos_internos_pendentes, 0) = 0 AS base_recomendacao_completa
  FROM `{{dataset}}.dim_colaboradores` AS c
  JOIN totais_pessoa AS r USING (id_colaborador)
  LEFT JOIN cycles AS y USING (id_colaborador)
  LEFT JOIN `{{dataset}}.dim_escalas` AS e ON e.id_escala = c.id_escala
  WHERE c.vinculo_confiavel AND c.data_admissao <= DATE '2025-08-31'
    AND (c.data_desligamento IS NULL OR c.data_desligamento >= DATE '2025-06-01')
), recommended AS (
  SELECT *, recomendar_acao(total_faltas_injustificadas_confirmadas,
    maior_sequencia_ciclos_perdidos, base_recomendacao_completa) AS acao_disciplinar_recomendada
  FROM candidates
)
SELECT *,
  IF(dias_pendentes = 0, total_faltas_injustificadas_confirmadas, NULL)
    AS total_faltas_injustificadas,
  IF(base_recomendacao_completa, total_dsr_perdido_confirmado, NULL) AS total_dsr_perdido,
  IF(dias_elegiveis > 0 AND
    (valor_horas_confirmado_nao_arredondado > 0 OR dias_horas_sem_valoracao = 0),
    ROUND(valor_horas_confirmado_nao_arredondado, 2), NULL)
    AS desconto_horas_confirmado,
  IF(dias_elegiveis > 0 AND
    (valor_dsr_confirmado_nao_arredondado > 0 OR dsrs_sem_valoracao = 0),
    ROUND(valor_dsr_confirmado_nao_arredondado, 2), NULL)
    AS desconto_dsr_confirmado,
  IF(dias_elegiveis > 0 AND componentes_monetarios_conhecidos > 0
    AND (subtotal_conhecido_nao_arredondado > 0 OR
      (dias_horas_sem_valoracao = 0 AND dsrs_sem_valoracao = 0)),
    ROUND(subtotal_conhecido_nao_arredondado, 2), NULL)
    AS desconto_estimado_confirmado,
  IF(dias_pendentes = 0 AND dias_horas_sem_valoracao = 0 AND dsrs_sem_valoracao = 0
    AND dsrs_indeterminados = 0 AND NOT salario_pendente AND NOT apuracao_dsr_indisponivel,
    ROUND(subtotal_conhecido_nao_arredondado, 2), NULL) AS desconto_total_periodo,
  dias_pendentes > 0 OR dias_horas_sem_valoracao > 0 OR dsrs_sem_valoracao > 0
    OR dsrs_indeterminados > 0 OR salario_pendente OR apuracao_dsr_indisponivel AS financeiro_incompleto,
  CASE WHEN acao_disciplinar_recomendada IS NULL THEN 'PENDENTE_VALIDACAO'
       WHEN base_recomendacao_completa THEN 'COMPLETA_NO_ESCOPO'
       ELSE 'NIVEL_MAXIMO_COMPROVADO_COM_PENDENCIAS' END AS status_recomendacao,
  base_recomendacao_completa AND acao_disciplinar_recomendada IS NOT NULL AS elegivel_reverse_etl,
  'Faltas de jun-ago/2025; sequências de DSR com trabalho na janela' AS escopo_recomendacao
FROM recommended;
