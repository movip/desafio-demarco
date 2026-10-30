-- GoogleSQL. Período fixado no escopo recebido; chaves e origem preservadas.
{{attendance_udf}}

CREATE OR REPLACE TABLE `{{dataset}}.dim_colaboradores` AS
WITH grouped AS (
  SELECT id_colaborador,
    COUNT(*) AS linhas_cadastrais,
    ARRAY_AGG(_source_row ORDER BY _source_row) AS linhas_origem,
    ANY_VALUE(_source_file) AS arquivo_origem,
    ANY_VALUE(_source_sha256) AS hash_origem,
    COUNT(DISTINCT TO_JSON_STRING(STRUCT(nome))) AS versoes_nome,
    COUNT(DISTINCT TO_JSON_STRING(STRUCT(cargo))) AS versoes_cargo,
    COUNT(DISTINCT TO_JSON_STRING(STRUCT(departamento))) AS versoes_departamento,
    COUNT(DISTINCT TO_JSON_STRING(STRUCT(salario_mensal))) AS versoes_salario,
    COUNT(DISTINCT TO_JSON_STRING(STRUCT(id_escala))) AS versoes_escala,
    COUNT(DISTINCT TO_JSON_STRING(STRUCT(data_admissao))) AS versoes_admissao,
    COUNT(DISTINCT TO_JSON_STRING(STRUCT(data_desligamento))) AS versoes_desligamento,
    COUNT(DISTINCT TO_JSON_STRING(STRUCT(id_gestor))) AS versoes_gestor,
    ANY_VALUE(nome) AS nome,
    ANY_VALUE(cargo) AS cargo,
    ANY_VALUE(departamento) AS departamento,
    ANY_VALUE(salario_mensal) AS salario_mensal,
    ANY_VALUE(id_escala) AS id_escala,
    ANY_VALUE(data_admissao) AS data_admissao,
    ANY_VALUE(data_desligamento) AS data_desligamento,
    ANY_VALUE(id_gestor) AS id_gestor,
    LOGICAL_OR(admissao_invalida OR desligamento_invalido) AS datas_invalidas
  FROM `{{dataset}}.stg_colaboradores`
  WHERE id_colaborador IS NOT NULL
  GROUP BY id_colaborador
)
SELECT id_colaborador, linhas_cadastrais, linhas_origem, arquivo_origem, hash_origem,
  IF(versoes_nome = 1, nome, NULL) AS nome,
  IF(versoes_cargo = 1, cargo, NULL) AS cargo,
  IF(versoes_departamento = 1, departamento, NULL) AS departamento,
  IF(versoes_salario = 1 AND salario_mensal > 0, salario_mensal, NULL) AS salario_mensal,
  IF(versoes_escala = 1, id_escala, NULL) AS id_escala,
  IF(versoes_admissao = 1, data_admissao, NULL) AS data_admissao,
  IF(versoes_desligamento = 1, data_desligamento, NULL) AS data_desligamento,
  IF(versoes_gestor = 1, id_gestor, NULL) AS id_gestor,
  versoes_nome > 1 OR versoes_escala > 1 OR versoes_admissao > 1 OR versoes_desligamento > 1
    AS cadastro_critico_conflitante,
  versoes_cargo > 1 OR versoes_departamento > 1 OR versoes_gestor > 1 AS atributos_conflitantes,
  versoes_salario != 1 OR salario_mensal IS NULL OR salario_mensal <= 0 AS salario_pendente,
  NOT datas_invalidas AND versoes_admissao = 1 AND data_admissao IS NOT NULL
    AND versoes_desligamento = 1
    AND (data_desligamento IS NULL OR data_desligamento >= data_admissao) AS vinculo_confiavel
FROM grouped;

CREATE OR REPLACE TABLE `{{dataset}}.dim_escalas` AS
WITH declared AS (
  SELECT *,
    CASE id_escala
      WHEN 'ESC_44H' THEN NUMERIC '44'
      WHEN 'ESC_40H' THEN NUMERIC '40'
      WHEN 'ESC_36H_NOT' THEN NUMERIC '36'
      ELSE NULL
    END AS jornada_semanal_contratual,
    (SELECT SUM(IF(TRIM(dia) = 'SAB', horas_sabado, horas_diarias))
     FROM UNNEST(SPLIT(dias_trabalho, ',')) AS dia) AS soma_horas_escala,
    versoes_id = 1 AND dias_trabalho != 'ALTERNADO' AND dia_dsr != 'VARIAVEL'
      AND horas_diarias BETWEEN 0 AND 24 AND horas_sabado BETWEEN 0 AND 24
      AND NOT EXISTS (
        SELECT 1 FROM UNNEST(SPLIT(CONCAT(dias_trabalho, ',', dia_dsr), ',')) AS dia
        WHERE TRIM(dia) NOT IN ('DOM', 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB')
      ) AS calendario_suportado
  FROM `{{dataset}}.stg_escalas`
)
-- Escalas duplicadas não podem multiplicar linhas do calendário.
SELECT *,
  jornada_semanal_contratual IS NOT NULL
    AND ABS(soma_horas_escala - jornada_semanal_contratual) > NUMERIC '0.000001'
    AS jornada_semanal_divergente
FROM declared
WHERE versoes_id = 1 AND id_escala IS NOT NULL;

CREATE OR REPLACE TABLE `{{dataset}}.int_calendario_colaborador` AS
WITH dates AS (
  SELECT c.id_colaborador, dia AS data_registro,
    ['DOM','SEG','TER','QUA','QUI','SEX','SAB'][OFFSET(EXTRACT(DAYOFWEEK FROM dia) - 1)]
      AS dia_semana,
    e.* EXCEPT(id_escala)
  FROM `{{dataset}}.dim_colaboradores` AS c
  LEFT JOIN `{{dataset}}.dim_escalas` AS e USING (id_escala)
  CROSS JOIN UNNEST(GENERATE_DATE_ARRAY(DATE '2025-06-01', DATE '2025-08-31')) AS dia
  WHERE c.vinculo_confiavel
    AND dia >= c.data_admissao
    AND (c.data_desligamento IS NULL OR dia <= c.data_desligamento)
), scheduled AS (
  SELECT id_colaborador, data_registro, dia_semana, calendario_suportado,
    IF(calendario_suportado,
       EXISTS(SELECT 1 FROM UNNEST(SPLIT(dias_trabalho, ',')) AS d WHERE TRIM(d) = dia_semana),
       NULL) AS dia_trabalho_contratual,
    IF(calendario_suportado,
       EXISTS(SELECT 1 FROM UNNEST(SPLIT(dia_dsr, ',')) AS d WHERE TRIM(d) = dia_semana),
       NULL) AS descanso_contratual,
    horas_diarias, horas_sabado
  FROM dates
)
SELECT id_colaborador, data_registro, dia_semana, calendario_suportado,
  dia_trabalho_contratual, descanso_contratual,
  CASE WHEN NOT COALESCE(calendario_suportado, FALSE) THEN NULL
       WHEN NOT dia_trabalho_contratual THEN NUMERIC '0'
       WHEN dia_semana = 'SAB' THEN horas_sabado ELSE horas_diarias END AS jornada_calendario
FROM scheduled;

-- Linhas sem chave diária válida permanecem consultáveis, sem virar faltas.
CREATE OR REPLACE TABLE `{{dataset}}.qa_ponto_sem_chave_periodo` AS
SELECT * FROM `{{dataset}}.stg_ponto`
WHERE id_colaborador IS NULL OR data_registro IS NULL
  OR data_registro NOT BETWEEN DATE '2025-06-01' AND DATE '2025-08-31';

CREATE OR REPLACE TABLE `{{dataset}}.int_ponto_dia` AS
SELECT id_colaborador, data_registro,
  COUNT(*) AS versoes_ponto,
  ARRAY_AGG(_source_row ORDER BY _source_row) AS linhas_origem,
  ANY_VALUE(_source_file) AS arquivo_origem,
  ANY_VALUE(_source_sha256) AS hash_origem,
  SUM(duplicatas_exatas_removidas) AS duplicatas_exatas_removidas,
  IF(COUNT(DISTINCT TO_JSON_STRING(STRUCT(jornada_esperada_horas))) = 1,
     ANY_VALUE(jornada_esperada_horas), NULL) AS jornada_esperada_horas,
  IF(COUNT(DISTINCT TO_JSON_STRING(STRUCT(horas_trabalhadas))) = 1,
     ANY_VALUE(horas_trabalhadas), NULL) AS horas_trabalhadas,
  IF(COUNT(DISTINCT TO_JSON_STRING(STRUCT(flag_dsr))) = 1,
     ANY_VALUE(flag_dsr), NULL) AS flag_dsr,
  IF(COUNT(DISTINCT TO_JSON_STRING(STRUCT(codigo_abono))) = 1,
     ANY_VALUE(codigo_abono), NULL) AS codigo_abono,
  LOGICAL_OR(registro_invalido) AS registro_invalido,
  LOGICAL_OR(dsr_com_jornada_positiva) AS dsr_com_jornada_positiva
FROM `{{dataset}}.stg_ponto`
WHERE id_colaborador IS NOT NULL AND data_registro BETWEEN DATE '2025-06-01' AND DATE '2025-08-31'
GROUP BY id_colaborador, data_registro;

CREATE OR REPLACE TABLE `{{dataset}}.fct_ausencias_diarias` AS
WITH joined AS (
  SELECT COALESCE(k.id_colaborador, p.id_colaborador) AS id_colaborador,
    COALESCE(k.data_registro, p.data_registro) AS data_registro,
    p.id_colaborador IS NOT NULL AS possui_registro_ponto,
    c.id_colaborador IS NOT NULL AS possui_cadastro,
    c.nome, c.cargo, c.departamento, c.id_gestor, c.id_escala, c.salario_mensal,
    c.salario_pendente, c.cadastro_critico_conflitante, c.vinculo_confiavel,
    c.data_admissao, c.data_desligamento,
    COALESCE(e.calendario_suportado, FALSE) AS escala_suportada,
    e.jornada_semanal_divergente,
    k.dia_trabalho_contratual, k.descanso_contratual, k.jornada_calendario,
    p.jornada_esperada_horas, p.horas_trabalhadas, p.flag_dsr, p.codigo_abono,
    p.versoes_ponto, p.registro_invalido, p.dsr_com_jornada_positiva,
    p.linhas_origem AS ponto_linhas_origem,
    p.arquivo_origem AS ponto_arquivo_origem, p.hash_origem AS ponto_hash_origem,
    c.linhas_origem AS cadastro_linhas_origem,
    p.duplicatas_exatas_removidas
  FROM `{{dataset}}.int_calendario_colaborador` AS k
  FULL OUTER JOIN `{{dataset}}.int_ponto_dia` AS p USING (id_colaborador, data_registro)
  LEFT JOIN `{{dataset}}.dim_colaboradores` AS c
    ON c.id_colaborador = COALESCE(k.id_colaborador, p.id_colaborador)
  LEFT JOIN `{{dataset}}.dim_escalas` AS e ON e.id_escala = c.id_escala
), reasons AS (
  SELECT *,
    COALESCE(jornada_calendario IS NOT NULL AND jornada_esperada_horas IS NOT NULL
      AND ABS(jornada_calendario - jornada_esperada_horas) > NUMERIC '0.000001', FALSE)
      AS jornada_diverge_calendario,
    COALESCE(jornada_calendario > 0 AND jornada_esperada_horas = 0 AND flag_dsr = 0, FALSE)
      AS dispensa_jornada_informada,
    ARRAY(SELECT reason FROM UNNEST([
      IF(NOT possui_cadastro, 'CADASTRO_AUSENTE', NULL),
      IF(COALESCE(cadastro_critico_conflitante, FALSE), 'CADASTRO_CONFLITANTE', NULL),
      IF(possui_cadastro AND NOT COALESCE(vinculo_confiavel, FALSE), 'VINCULO_NAO_VALIDADO', NULL),
      IF(possui_cadastro AND vinculo_confiavel AND (
        data_registro < data_admissao OR (data_desligamento IS NOT NULL AND data_registro > data_desligamento)
      ), 'FORA_DO_VINCULO', NULL),
      IF(NOT escala_suportada, 'ESCALA_AUSENTE_OU_NAO_SUPORTADA', NULL),
      IF(NOT possui_registro_ponto, 'SEM_REGISTRO_PONTO', NULL),
      IF(versoes_ponto > 1, 'PONTO_CONFLITANTE', NULL),
      IF(registro_invalido, 'PONTO_INVALIDO', NULL),
      IF(dsr_com_jornada_positiva, 'DSR_COM_JORNADA_POSITIVA', NULL),
      IF(jornada_calendario IS NOT NULL AND jornada_esperada_horas IS NOT NULL
        AND ABS(jornada_calendario - jornada_esperada_horas) > NUMERIC '0.000001'
        AND NOT (jornada_calendario > 0 AND jornada_esperada_horas = 0 AND flag_dsr = 0),
        'JORNADA_DIVERGE_CALENDARIO', NULL),
      IF(flag_dsr = 1 AND descanso_contratual = FALSE, 'DSR_DIVERGE_CALENDARIO', NULL)
    ]) AS reason WHERE reason IS NOT NULL) AS bloqueios
  FROM joined
), classified AS (
  SELECT *, classificar_ausencia(
    jornada_esperada_horas, horas_trabalhadas, codigo_abono, descanso_contratual, bloqueios
  ) AS classificacao,
    descanso_contratual IS NOT NULL AND flag_dsr IS NOT NULL
      AND descanso_contratual != (flag_dsr = 1) AS divergencia_flag_dsr
  FROM reasons
), eligibility AS (
  SELECT *, NOT STARTS_WITH(classificacao, 'PENDENTE_') AS elegivel_indicadores,
    ARRAY_CONCAT(bloqueios,
      IF(classificacao = 'PENDENTE_DURACAO_ABONO', ['ABONO_SEM_DURACAO'], ARRAY<STRING>[]),
      IF(classificacao = 'PENDENTE_ABONO_DESCONHECIDO', ['ABONO_DESCONHECIDO'], ARRAY<STRING>[]),
      IF(classificacao = 'PENDENTE_HORAS_INVALIDAS', ['HORAS_INVALIDAS'], ARRAY<STRING>[])
    ) AS motivos_pendencia
  FROM classified
)
SELECT * EXCEPT(bloqueios),
  EXTRACT(MONTH FROM data_registro) AS mes,
  EXTRACT(DAYOFWEEK FROM data_registro) AS dia_semana_numero,
  IF(elegivel_indicadores, jornada_esperada_horas, NULL) AS horas_esperadas_indicadores,
  IF(elegivel_indicadores, horas_trabalhadas, NULL) AS horas_trabalhadas_indicadores,
  IF(elegivel_indicadores, LEAST(jornada_esperada_horas, horas_trabalhadas), NULL)
    AS horas_trabalhadas_na_jornada,
  IF(elegivel_indicadores,
    IF(classificacao IN ('AUSENCIA_INTEGRAL_ABONADA', 'AUSENCIA_PARCIAL_ABONADA'),
      jornada_esperada_horas - horas_trabalhadas, NUMERIC '0'), NULL) AS horas_abonadas,
  IF(elegivel_indicadores,
    IF(classificacao IN ('FALTA_INTEGRAL_INJUSTIFICADA', 'AUSENCIA_PARCIAL_INJUSTIFICADA'),
      jornada_esperada_horas - horas_trabalhadas, NUMERIC '0'), NULL) AS horas_injustificadas,
  IF(elegivel_indicadores, GREATEST(horas_trabalhadas - jornada_esperada_horas, NUMERIC '0'), NULL)
    AS horas_excedentes,
  IF(elegivel_indicadores, classificacao = 'FALTA_INTEGRAL_INJUSTIFICADA', NULL)
    AS falta_integral_injustificada,
  IF(elegivel_indicadores, classificacao = 'AUSENCIA_PARCIAL_INJUSTIFICADA', NULL)
    AS ausencia_parcial_injustificada,
  IF(NOT elegivel_indicadores AND jornada_esperada_horas BETWEEN 0 AND 24
    AND horas_trabalhadas BETWEEN 0 AND 24,
    GREATEST(jornada_esperada_horas - horas_trabalhadas, NUMERIC '0'), NULL) AS deficit_horas_pendente
FROM eligibility;

CREATE OR REPLACE TABLE `{{dataset}}.qa_ausencias_diarias` AS
SELECT id_colaborador, data_registro, classificacao, motivo,
  ponto_linhas_origem, cadastro_linhas_origem
FROM `{{dataset}}.fct_ausencias_diarias`
CROSS JOIN UNNEST(motivos_pendencia) AS motivo;
