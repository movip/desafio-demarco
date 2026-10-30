-- GoogleSQL. {{dataset}} é substituído por um identificador validado na configuração.
-- Camada de preparação: sem descontos ou recomendações disciplinares nesta etapa.
CREATE TEMP FUNCTION clean_text(s STRING) AS (
  CASE WHEN UPPER(TRIM(s)) IN ('', 'NULL', 'NONE', 'NAN', 'N/A') THEN NULL ELSE TRIM(s) END
);

{{text_repair_udf}}

CREATE TEMP FUNCTION parse_number(s STRING) AS (
  CASE
    WHEN REGEXP_CONTAINS(TRIM(REPLACE(clean_text(s), 'R$', '')), r'^[+-]?[0-9]+(\.[0-9]+)?$')
      THEN SAFE_CAST(TRIM(REPLACE(clean_text(s), 'R$', '')) AS NUMERIC)
    WHEN REGEXP_CONTAINS(TRIM(REPLACE(clean_text(s), 'R$', '')), r'^[+-]?([0-9]+|[0-9]{1,3}(\.[0-9]{3})+),[0-9]+$')
      THEN SAFE_CAST(REPLACE(REPLACE(TRIM(REPLACE(clean_text(s), 'R$', '')), '.', ''), ',', '.') AS NUMERIC)
    ELSE NULL
  END
);

CREATE TEMP FUNCTION parse_source_date(s STRING) AS (
  COALESCE(
    SAFE_CAST(clean_text(s) AS DATE),
    DATE(SAFE_CAST(clean_text(s) AS DATETIME)),
    SAFE.PARSE_DATE('%d/%m/%Y', clean_text(s)),
    CASE
      WHEN REGEXP_CONTAINS(clean_text(s), r'^[0-9]{1,5}(\.0+)?$')
        THEN DATE_ADD(DATE '1899-12-30', INTERVAL SAFE_CAST(SAFE_CAST(clean_text(s) AS NUMERIC) AS INT64) DAY)
      ELSE NULL
    END
  )
);

CREATE OR REPLACE TABLE `{{dataset}}.stg_colaboradores` AS
SELECT
  UPPER(clean_text(id_colaborador)) AS id_colaborador,
  repair_text(clean_text(nome)) AS nome,
  repair_text(clean_text(cargo)) AS cargo,
  repair_text(clean_text(departamento)) AS departamento,
  repair_text(clean_text(nome)) IS DISTINCT FROM clean_text(nome) AS nome_codificacao_corrigida,
  repair_text(clean_text(cargo)) IS DISTINCT FROM clean_text(cargo) AS cargo_codificacao_corrigida,
  repair_text(clean_text(departamento)) IS DISTINCT FROM clean_text(departamento) AS departamento_codificacao_corrigida,
  parse_number(salario_mensal) AS salario_mensal,
  UPPER(clean_text(id_escala)) AS id_escala,
  parse_source_date(data_admissao) AS data_admissao,
  parse_source_date(data_desligamento) AS data_desligamento,
  UPPER(clean_text(id_gestor)) AS id_gestor,
  COUNT(*) OVER (PARTITION BY UPPER(clean_text(id_colaborador))) AS versoes_id,
  clean_text(salario_mensal) IS NOT NULL AND parse_number(salario_mensal) IS NULL AS salario_invalido,
  clean_text(data_admissao) IS NOT NULL AND parse_source_date(data_admissao) IS NULL AS admissao_invalida,
  clean_text(data_desligamento) IS NOT NULL AND parse_source_date(data_desligamento) IS NULL AS desligamento_invalido,
  _source_file, _source_sheet, _source_row, _source_sha256, _raw_json
FROM `{{dataset}}.raw_colaboradores`;

CREATE OR REPLACE TABLE `{{dataset}}.stg_escalas` AS
SELECT
  UPPER(clean_text(id_escala)) AS id_escala,
  repair_text(clean_text(descricao)) AS descricao,
  repair_text(clean_text(descricao)) IS DISTINCT FROM clean_text(descricao) AS descricao_codificacao_corrigida,
  UPPER(clean_text(dias_trabalho)) AS dias_trabalho,
  UPPER(clean_text(dia_dsr)) AS dia_dsr,
  parse_number(horas_diarias) AS horas_diarias,
  parse_number(horas_sabado) AS horas_sabado,
  parse_number(divisor_folha) AS divisor_folha,
  COUNT(*) OVER (PARTITION BY UPPER(clean_text(id_escala))) AS versoes_id,
  _source_file, _source_sheet, _source_row, _source_sha256, _raw_json
FROM `{{dataset}}.raw_escalas`;

CREATE OR REPLACE TABLE `{{dataset}}.stg_ponto` AS
WITH unique_raw AS (
  SELECT *, COUNT(*) OVER (PARTITION BY _raw_json) - 1 AS duplicatas_exatas_removidas
  FROM `{{dataset}}.raw_ponto`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY _raw_json ORDER BY _source_row) = 1
), parsed AS (
  SELECT
    parse_source_date(data_registro) AS data_registro,
    UPPER(clean_text(id_colaborador)) AS id_colaborador,
    parse_number(jornada_esperada_horas) AS jornada_esperada_horas,
    parse_number(horas_trabalhadas) AS horas_trabalhadas,
    parse_number(flag_dsr) AS flag_dsr,
    UPPER(clean_text(codigo_abono)) AS codigo_abono,
    duplicatas_exatas_removidas,
    _source_file, _source_sheet, _source_row, _source_sha256, _raw_json
  FROM unique_raw
)
SELECT *,
  COUNT(*) OVER (PARTITION BY id_colaborador, data_registro) AS versoes_chave,
  data_registro IS NULL OR id_colaborador IS NULL
    OR jornada_esperada_horas IS NULL OR jornada_esperada_horas NOT BETWEEN 0 AND 24
    OR horas_trabalhadas IS NULL OR horas_trabalhadas NOT BETWEEN 0 AND 24
    OR flag_dsr IS NULL OR flag_dsr NOT IN (0, 1) AS registro_invalido,
  flag_dsr = 1 AND jornada_esperada_horas > 0 AS dsr_com_jornada_positiva
FROM parsed;

-- Cópia de referência, sem transformação dos campos manuais.
-- Esta tabela não substitui nem atualiza a planilha real dos gestores.
CREATE OR REPLACE TABLE `{{dataset}}.stg_gestao_referencia` AS
SELECT * FROM `{{dataset}}.raw_gestao`;
