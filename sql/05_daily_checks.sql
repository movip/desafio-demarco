-- Casos de regra executados contra a mesma função que materializa a fato diária.
{{attendance_udf}}

ASSERT (
  -- presenca
  classificar_ausencia(NUMERIC '8', NUMERIC '8', CAST(NULL AS STRING), FALSE, ARRAY<STRING>[]) = 'PRESENCA'
  -- falta total
  AND classificar_ausencia(NUMERIC '8', NUMERIC '0', CAST(NULL AS STRING), FALSE, ARRAY<STRING>[]) = 'FALTA_INTEGRAL_INJUSTIFICADA'
  -- deficit parcial
  AND classificar_ausencia(NUMERIC '8', NUMERIC '7.75', CAST(NULL AS STRING), FALSE, ARRAY<STRING>[]) = 'AUSENCIA_PARCIAL_INJUSTIFICADA'
  -- deficit minimo sem tolerancia inventada
  AND classificar_ausencia(NUMERIC '8', NUMERIC '7.99', CAST(NULL AS STRING), FALSE, ARRAY<STRING>[]) = 'AUSENCIA_PARCIAL_INJUSTIFICADA'
  -- atestado integral
  AND classificar_ausencia(NUMERIC '8', NUMERIC '0', 'ATESTADO MEDICO', FALSE, ARRAY<STRING>[]) = 'AUSENCIA_INTEGRAL_ABONADA'
  -- atestado parcial
  AND classificar_ausencia(NUMERIC '8', NUMERIC '5', 'ATESTADO MEDICO', FALSE, ARRAY<STRING>[]) = 'AUSENCIA_PARCIAL_ABONADA'
  -- folga compensatoria
  AND classificar_ausencia(NUMERIC '8.8', NUMERIC '0', 'FOLGA_COMPENSATORIA', FALSE, ARRAY<STRING>[]) = 'AUSENCIA_INTEGRAL_ABONADA'
  -- declaracao sem duracao
  AND classificar_ausencia(NUMERIC '8.8', NUMERIC '0', 'DECLARACAO_HORAS', FALSE, ARRAY<STRING>[]) = 'PENDENTE_DURACAO_ABONO'
  -- declaracao sem deficit
  AND classificar_ausencia(NUMERIC '8', NUMERIC '8', 'DECLARACAO_HORAS', FALSE, ARRAY<STRING>[]) = 'PRESENCA'
  -- abono desconhecido
  AND classificar_ausencia(NUMERIC '8', NUMERIC '0', 'OUTRO', FALSE, ARRAY<STRING>[]) = 'PENDENTE_ABONO_DESCONHECIDO'
  -- dsr
  AND classificar_ausencia(NUMERIC '0', NUMERIC '0', CAST(NULL AS STRING), TRUE, ARRAY<STRING>[]) = 'DESCANSO_SEMANAL'
  -- folga
  AND classificar_ausencia(NUMERIC '0', NUMERIC '0', CAST(NULL AS STRING), FALSE, ARRAY<STRING>[]) = 'FOLGA'
  -- trabalho no descanso
  AND classificar_ausencia(NUMERIC '0', NUMERIC '8', CAST(NULL AS STRING), TRUE, ARRAY<STRING>[]) = 'TRABALHO_EM_DESCANSO'
  -- excedente nao compensa outro dia
  AND classificar_ausencia(NUMERIC '8', NUMERIC '9', CAST(NULL AS STRING), FALSE, ARRAY<STRING>[]) = 'PRESENCA'
  -- horas negativas
  AND classificar_ausencia(NUMERIC '8', NUMERIC '-0.5', CAST(NULL AS STRING), FALSE, ARRAY<STRING>[]) = 'PENDENTE_HORAS_INVALIDAS'
  -- mais de 24 horas
  AND classificar_ausencia(NUMERIC '8', NUMERIC '25', CAST(NULL AS STRING), FALSE, ARRAY<STRING>[]) = 'PENDENTE_HORAS_INVALIDAS'
  -- jornada nula
  AND classificar_ausencia(CAST(NULL AS NUMERIC), NUMERIC '0', CAST(NULL AS STRING), FALSE, ARRAY<STRING>[]) = 'PENDENTE_HORAS_INVALIDAS'
  -- horas nulas
  AND classificar_ausencia(NUMERIC '8', CAST(NULL AS NUMERIC), CAST(NULL AS STRING), FALSE, ARRAY<STRING>[]) = 'PENDENTE_HORAS_INVALIDAS'
  -- cadastro conflitante
  AND classificar_ausencia(NUMERIC '8', NUMERIC '0', CAST(NULL AS STRING), FALSE, ARRAY<STRING>['CADASTRO_CONFLITANTE']) = 'PENDENTE_VALIDACAO'
  -- ponto conflitante
  AND classificar_ausencia(NUMERIC '8', NUMERIC '0', CAST(NULL AS STRING), FALSE, ARRAY<STRING>['PONTO_CONFLITANTE']) = 'PENDENTE_VALIDACAO'
  -- sem ponto nao comprova falta
  AND classificar_ausencia(NUMERIC '8', NUMERIC '0', CAST(NULL AS STRING), FALSE, ARRAY<STRING>['SEM_REGISTRO_PONTO']) = 'PENDENTE_VALIDACAO'
  -- fora do vinculo
  AND classificar_ausencia(NUMERIC '8', NUMERIC '0', CAST(NULL AS STRING), FALSE, ARRAY<STRING>['FORA_DO_VINCULO']) = 'PENDENTE_VALIDACAO'
  -- dsr conflitante
  AND classificar_ausencia(NUMERIC '8', NUMERIC '0', CAST(NULL AS STRING), TRUE, ARRAY<STRING>['DSR_COM_JORNADA_POSITIVA']) = 'PENDENTE_VALIDACAO'
) AS 'As classificações diárias devem coincidir com os casos de negócio';

ASSERT (
  (SELECT COUNT(*) FROM `{{dataset}}.dim_colaboradores`) =
  (SELECT COUNT(DISTINCT id_colaborador) FROM `{{dataset}}.stg_colaboradores`)
) AS 'Uma dimensão por ID cadastral';

ASSERT (NOT EXISTS (
  SELECT id_colaborador FROM `{{dataset}}.dim_colaboradores`
  GROUP BY id_colaborador HAVING COUNT(*) > 1
)) AS 'A dimensão não pode multiplicar colaboradores';

ASSERT (NOT EXISTS (
  SELECT id_colaborador, data_registro FROM `{{dataset}}.fct_ausencias_diarias`
  GROUP BY id_colaborador, data_registro HAVING COUNT(*) != 1
)) AS 'A fato deve ter uma única linha por colaborador e data';

ASSERT (
  (SELECT COUNT(*) FROM `{{dataset}}.fct_ausencias_diarias`) =
  (SELECT COUNT(*) FROM (
    SELECT id_colaborador, data_registro FROM `{{dataset}}.int_calendario_colaborador`
    UNION DISTINCT
    SELECT id_colaborador, data_registro FROM `{{dataset}}.int_ponto_dia`
  ))
) AS 'Nenhuma chave diária pode desaparecer ou ser criada sem origem';

ASSERT (
  (SELECT COUNT(*) FROM `{{dataset}}.stg_ponto`) =
  COALESCE((SELECT SUM(versoes_ponto) FROM `{{dataset}}.int_ponto_dia`), 0) +
  (SELECT COUNT(*) FROM `{{dataset}}.qa_ponto_sem_chave_periodo`)
) AS 'Todas as linhas de staging devem estar representadas na agregação ou na qualidade';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.fct_ausencias_diarias`
  WHERE id_colaborador IS NULL OR data_registro IS NULL
    OR data_registro NOT BETWEEN DATE '2025-06-01' AND DATE '2025-08-31'
)) AS 'Chaves e janela da análise devem ser válidas';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.fct_ausencias_diarias`
  WHERE NOT elegivel_indicadores AND (
    horas_esperadas_indicadores IS NOT NULL OR horas_trabalhadas_indicadores IS NOT NULL
    OR horas_abonadas IS NOT NULL OR horas_injustificadas IS NOT NULL
    OR falta_integral_injustificada IS NOT NULL OR ausencia_parcial_injustificada IS NOT NULL
    OR ARRAY_LENGTH(motivos_pendencia) = 0
  )
)) AS 'Dados pendentes não podem virar números confirmados nem zeros artificiais';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.fct_ausencias_diarias`
  WHERE elegivel_indicadores AND (
    horas_esperadas_indicadores != horas_trabalhadas_na_jornada + horas_abonadas + horas_injustificadas
    OR horas_abonadas < 0 OR horas_injustificadas < 0 OR horas_excedentes < 0
    OR (horas_abonadas > 0 AND horas_injustificadas > 0)
    OR (falta_integral_injustificada AND ausencia_parcial_injustificada)
    OR (horas_esperadas_indicadores = 0 AND horas_injustificadas != 0)
  )
)) AS 'Horas esperadas devem fechar entre trabalho, abono e ausência injustificada';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.fct_ausencias_diarias`
  WHERE elegivel_indicadores AND (
    cadastro_critico_conflitante OR NOT possui_registro_ponto OR versoes_ponto > 1
    OR registro_invalido OR dsr_com_jornada_positiva OR NOT vinculo_confiavel
    OR data_registro < data_admissao
    OR (data_desligamento IS NOT NULL AND data_registro > data_desligamento)
    OR NOT escala_suportada
  )
)) AS 'Problemas críticos não podem produzir faltas confirmadas';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.dim_colaboradores`
  WHERE salario_pendente AND salario_mensal IS NOT NULL
)) AS 'Salários incertos devem permanecer nulos';

ASSERT (NOT EXISTS (
  SELECT 1 FROM `{{dataset}}.fct_ausencias_diarias`
  WHERE elegivel_indicadores AND dispensa_jornada_informada
    AND (horas_esperadas_indicadores != 0 OR horas_injustificadas != 0 OR falta_integral_injustificada)
)) AS 'Jornada zero informada como dispensa não pode virar falta';

SELECT
  COUNT(*) AS linhas_diarias,
  COUNT(DISTINCT id_colaborador) AS ids_com_observacoes_ou_calendario,
  COUNTIF(elegivel_indicadores) AS linhas_elegiveis,
  COUNTIF(NOT elegivel_indicadores) AS linhas_pendentes,
  COUNTIF(falta_integral_injustificada) AS faltas_integrais_confirmadas,
  COUNTIF(ausencia_parcial_injustificada) AS ausencias_parciais_confirmadas,
  SUM(horas_esperadas_indicadores) AS horas_esperadas_validas,
  SUM(horas_abonadas) AS horas_abonadas_confirmadas,
  SUM(horas_injustificadas) AS horas_injustificadas_confirmadas,
  COUNTIF(divergencia_flag_dsr) AS divergencias_flag_dsr,
  COUNTIF(jornada_diverge_calendario) AS divergencias_jornada_calendario,
  COUNTIF(elegivel_indicadores AND dispensa_jornada_informada) AS dispensas_jornada_confirmadas,
  COUNTIF(elegivel_indicadores AND salario_pendente) AS linhas_sem_salario_para_valoracao,
  BIT_XOR(FARM_FINGERPRINT(TO_JSON_STRING(f))) AS assinatura_resultado
FROM `{{dataset}}.fct_ausencias_diarias` AS f;
