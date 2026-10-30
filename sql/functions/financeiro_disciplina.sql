-- Funções compartilhadas entre os modelos e os testes de negócio.
CREATE TEMP FUNCTION classificar_dsr(
  faltas INT64, dias_pendentes INT64, dias_sem_base INT64, cadastro_confiavel BOOL
)
RETURNS STRING AS (
  CASE
    WHEN cadastro_confiavel IS NOT TRUE THEN 'PENDENTE_CADASTRO'
    WHEN faltas IS NULL OR dias_pendentes IS NULL OR dias_sem_base IS NULL
      OR faltas < 0 OR dias_pendentes < 0 OR dias_sem_base < 0 THEN 'PENDENTE_DADOS'
    -- Uma falta integral confirmada já comprova perda, mesmo havendo outra data pendente.
    WHEN faltas > 0 THEN 'PERDIDO'
    WHEN dias_pendentes > 0 OR dias_sem_base > 0 THEN 'INDETERMINADO'
    ELSE 'PRESERVADO'
  END
);

CREATE TEMP FUNCTION valorizar_horas(horas NUMERIC, salario NUMERIC, divisor NUMERIC)
RETURNS NUMERIC AS (
  CASE
    WHEN horas IS NULL OR horas < 0 THEN NULL
    WHEN horas = 0 THEN NUMERIC '0'
    WHEN salario > 0 AND divisor > 0 THEN horas * SAFE_DIVIDE(salario, divisor)
    ELSE NULL
  END
);

CREATE TEMP FUNCTION valorizar_dsr(
  status STRING, salario NUMERIC, divisor NUMERIC, jornada_semanal NUMERIC
)
RETURNS NUMERIC AS (
  CASE
    WHEN status = 'PRESERVADO' THEN NUMERIC '0'
    WHEN status = 'PERDIDO' AND jornada_semanal > 0
      THEN valorizar_horas(SAFE_DIVIDE(jornada_semanal, NUMERIC '6'), salario, divisor)
    ELSE NULL
  END
);

CREATE TEMP FUNCTION recomendar_acao(faltas INT64, sequencia_ciclos INT64, base_completa BOOL)
RETURNS STRING AS (
  CASE
    WHEN faltas < 0 OR sequencia_ciclos < 0 THEN NULL
    WHEN faltas >= 4 OR sequencia_ciclos >= 2 THEN 'Suspensão Disciplinar (1 a 3 dias)'
    WHEN faltas IS NULL OR sequencia_ciclos IS NULL THEN NULL
    WHEN base_completa IS NOT TRUE THEN NULL
    WHEN faltas BETWEEN 2 AND 3 THEN 'Advertência Escrita'
    WHEN faltas = 1 THEN 'Alinhamento em 1-on-1'
    ELSE 'Sem ação requerida'
  END
);
