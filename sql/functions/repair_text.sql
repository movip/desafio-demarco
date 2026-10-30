-- Os arquivos recebidos contêm UTF-8 interpretado como Latin-1 (ex.: ProduÃ§Ã£o).
-- Só reinterpreta sequências compatíveis e cuja conversão inteira seja UTF-8 válida.
-- SAFE_CAST evita substituir caracteres por U+FFFD; falhas preservam o original.
-- Não aplicar a observações manuais. As tabelas raw_* e _raw_json permanecem intactas.
CREATE TEMP FUNCTION repair_text(s STRING)
RETURNS STRING AS (
  CASE
    WHEN REGEXP_CONTAINS(s, r'[ÃÂ][\x80-\xBF]') THEN
      COALESCE(SAFE_CAST(SAFE.CODE_POINTS_TO_BYTES(TO_CODE_POINTS(s)) AS STRING), s)
    ELSE s
  END
);

