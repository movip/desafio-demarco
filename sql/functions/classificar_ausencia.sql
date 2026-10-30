-- Uma única implementação para o modelo diário e seus casos de teste no BigQuery.
-- Sem tolerância inventada: a fonte fornece horas decimais agregadas por dia.
CREATE TEMP FUNCTION classificar_ausencia(
  jornada NUMERIC, trabalhadas NUMERIC, abono STRING, descanso BOOL, bloqueios ARRAY<STRING>
)
RETURNS STRING AS (
  CASE
    WHEN ARRAY_LENGTH(bloqueios) > 0 THEN 'PENDENTE_VALIDACAO'
    WHEN jornada IS NULL OR trabalhadas IS NULL
      OR jornada NOT BETWEEN 0 AND 24 OR trabalhadas NOT BETWEEN 0 AND 24
      THEN 'PENDENTE_HORAS_INVALIDAS'
    WHEN abono IS NOT NULL AND abono NOT IN (
      'ATESTADO MEDICO', 'FOLGA_COMPENSATORIA', 'DECLARACAO_HORAS'
    ) THEN 'PENDENTE_ABONO_DESCONHECIDO'
    WHEN trabalhadas < jornada AND abono = 'DECLARACAO_HORAS'
      THEN 'PENDENTE_DURACAO_ABONO'
    WHEN trabalhadas < jornada AND abono IN ('ATESTADO MEDICO', 'FOLGA_COMPENSATORIA')
      THEN IF(trabalhadas = 0, 'AUSENCIA_INTEGRAL_ABONADA', 'AUSENCIA_PARCIAL_ABONADA')
    WHEN trabalhadas = 0 AND jornada > 0 THEN 'FALTA_INTEGRAL_INJUSTIFICADA'
    WHEN trabalhadas < jornada THEN 'AUSENCIA_PARCIAL_INJUSTIFICADA'
    WHEN jornada = 0 AND trabalhadas > 0 THEN 'TRABALHO_EM_DESCANSO'
    WHEN jornada = 0 AND descanso THEN 'DESCANSO_SEMANAL'
    WHEN jornada = 0 THEN 'FOLGA'
    ELSE 'PRESENCA'
  END
);
