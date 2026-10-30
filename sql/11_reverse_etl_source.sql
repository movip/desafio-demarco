-- Contrato da atualização da gestão. Retém também os casos não publicáveis
-- para que a prévia explique por que cada linha foi preservada.
SELECT id_colaborador AS ID_Colaborador,
  total_faltas_injustificadas AS Total_Faltas_Injustificadas,
  total_dsr_perdido AS Total_DSR_Perdido,
  acao_disciplinar_recomendada AS Acao_Disciplinar_Recomendada,
  elegivel_reverse_etl, status_recomendacao, escopo_recomendacao
FROM `{{dataset}}.mart_gestao_colaboradores`
ORDER BY id_colaborador;
