-- GoogleSQL: reconciliação da camada de preparação, sem alterar as tabelas.
{{text_repair_udf}}

-- Regressões executadas na mesma função usada em produção: reparo de textos
-- observados e preservação de acentos corretos, Unicode, nulos e casos ambíguos.
ASSERT (NOT EXISTS (
  SELECT 1 FROM UNNEST([
    STRUCT('Auxiliar de ProduÃ§Ã£o' AS entrada, 'Auxiliar de Produção' AS esperado),
    ('Analista de LogÃ­stica', 'Analista de Logística'),
    ('Coordenador de LogÃ­stica', 'Coordenador de Logística'),
    ('LogÃ­stica', 'Logística'),
    ('SÃ´nia Ferreira', 'Sônia Ferreira'),
    ('OperaÃ§Ãµes', 'Operações'),
    ('Produção', 'Produção'),
    ('João', 'João'),
    ('Ãngela', 'Ãngela'),
    ('Ângela', 'Ângela'),
    ('東京 🙂', '東京 🙂'),
    ('Texto �', 'Texto �'),
    ('João e ProduÃ§Ã£o', 'João e ProduÃ§Ã£o'),
    (CAST(NULL AS STRING), CAST(NULL AS STRING))
  ])
  WHERE repair_text(entrada) IS DISTINCT FROM esperado
    OR repair_text(repair_text(entrada)) IS DISTINCT FROM esperado
)) AS 'A correção de codificação deve reparar casos conhecidos e preservar textos incompatíveis';

ASSERT (
  SELECT COUNT(*) FROM `{{dataset}}.raw_colaboradores`
) = (
  SELECT COUNT(*) FROM `{{dataset}}.stg_colaboradores`
) AS 'O staging deve preservar todas as versões do cadastro';

ASSERT (
  SELECT COUNT(*) FROM `{{dataset}}.raw_ponto`
) = (
  SELECT COUNT(*) + COALESCE(SUM(duplicatas_exatas_removidas), 0)
  FROM `{{dataset}}.stg_ponto`
) AS 'O staging deve remover somente as repetições exatas do ponto';

ASSERT (
  SELECT COUNT(*) FROM `{{dataset}}.raw_escalas`
) = (
  SELECT COUNT(*) FROM `{{dataset}}.stg_escalas`
) AS 'O staging deve preservar as escalas';

-- EXCEPT DISTINCT em ambas as direções e comparação de contagens confirmam
-- preservação integral desta cópia de referência, incluindo os campos manuais.
ASSERT (NOT EXISTS (
  SELECT * FROM `{{dataset}}.raw_gestao`
  EXCEPT DISTINCT
  SELECT * FROM `{{dataset}}.stg_gestao_referencia`
) AND NOT EXISTS (
  SELECT * FROM `{{dataset}}.stg_gestao_referencia`
  EXCEPT DISTINCT
  SELECT * FROM `{{dataset}}.raw_gestao`
) AND (
  SELECT COUNT(*) FROM `{{dataset}}.raw_gestao`
) = (
  SELECT COUNT(*) FROM `{{dataset}}.stg_gestao_referencia`
)) AS 'A referência de gestão deve manter o conteúdo bruto';

SELECT
  (SELECT COUNT(*) FROM `{{dataset}}.raw_colaboradores`) AS colaboradores_raw,
  (SELECT COUNT(*) FROM `{{dataset}}.raw_escalas`) AS escalas_raw,
  (SELECT COUNT(*) FROM `{{dataset}}.raw_ponto`) AS ponto_raw,
  (SELECT COUNT(*) FROM `{{dataset}}.stg_ponto`) AS ponto_staging,
  (SELECT SUM(duplicatas_exatas_removidas) FROM `{{dataset}}.stg_ponto`) AS duplicatas_removidas,
  (SELECT COUNT(*) FROM (
    SELECT id_colaborador, data_registro FROM `{{dataset}}.stg_ponto`
    WHERE versoes_chave > 1 GROUP BY id_colaborador, data_registro
  )) AS chaves_ponto_conflitantes,
  (SELECT COUNTIF(registro_invalido) FROM `{{dataset}}.stg_ponto`) AS registros_ponto_invalidos,
  (SELECT COUNTIF(nome_codificacao_corrigida) FROM `{{dataset}}.stg_colaboradores`) AS nomes_corrigidos,
  (SELECT COUNTIF(cargo_codificacao_corrigida) FROM `{{dataset}}.stg_colaboradores`) AS cargos_corrigidos,
  (SELECT COUNTIF(departamento_codificacao_corrigida) FROM `{{dataset}}.stg_colaboradores`) AS departamentos_corrigidos,
  (SELECT COUNTIF(descricao_codificacao_corrigida) FROM `{{dataset}}.stg_escalas`) AS descricoes_escala_corrigidas,
  (SELECT COUNT(*) FROM `{{dataset}}.stg_gestao_referencia`) AS colaboradores_gestao;
