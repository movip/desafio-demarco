-- GoogleSQL: evidência por valor original e tratado, sem escrever nas fontes.
-- A junção usa a origem da linha, não o ID cadastral que pode estar duplicado.
WITH changes AS (
  SELECT 'colaboradores' AS fonte, field.campo, field.original, field.tratado
  FROM `{{dataset}}.raw_colaboradores` AS r
  JOIN `{{dataset}}.stg_colaboradores` AS s
    USING (_source_file, _source_sheet, _source_row, _source_sha256)
  CROSS JOIN UNNEST([
    STRUCT('nome' AS campo, r.nome AS original, s.nome AS tratado,
           s.nome_codificacao_corrigida AS corrigido),
    ('cargo', r.cargo, s.cargo, s.cargo_codificacao_corrigida),
    ('departamento', r.departamento, s.departamento, s.departamento_codificacao_corrigida)
  ]) AS field
  WHERE field.corrigido
  UNION ALL
  SELECT 'escalas', 'descricao', r.descricao, s.descricao
  FROM `{{dataset}}.raw_escalas` AS r
  JOIN `{{dataset}}.stg_escalas` AS s
    USING (_source_file, _source_sheet, _source_row, _source_sha256)
  WHERE s.descricao_codificacao_corrigida
)
SELECT fonte, campo, original, tratado, COUNT(*) AS ocorrencias
FROM changes
GROUP BY fonte, campo, original, tratado
ORDER BY fonte, campo, original;
