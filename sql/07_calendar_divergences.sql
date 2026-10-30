-- Auditoria das jornadas observadas que divergem do calendário contratual.
SELECT data_registro, id_escala, jornada_calendario, jornada_esperada_horas, flag_dsr,
  COUNT(*) AS linhas,
  STRING_AGG(id_colaborador, ', ' ORDER BY id_colaborador) AS ids
FROM `{{dataset}}.fct_ausencias_diarias`
WHERE jornada_diverge_calendario
GROUP BY data_registro, id_escala, jornada_calendario, jornada_esperada_horas, flag_dsr
ORDER BY data_registro, id_escala;
