-- GoogleSQL. Fontes planas para o Looker Studio, sem misturar grãos nas medidas.
-- Não altera modelos de negócio nem a planilha de gestão.
CREATE OR REPLACE VIEW `{{dataset}}.vw_dashboard_diario`
OPTIONS(description='Dashboard: uma linha por ID/data; taxas devem ser razões entre somas. Valores financeiros são subtotais conhecidos.') AS
SELECT f.id_colaborador,
  IF(m.id_colaborador IS NOT NULL, f.id_colaborador, NULL) AS id_colaborador_no_periodo,
  COALESCE(f.nome, CONCAT(f.id_colaborador, ' (cadastro em revisão)')) AS colaborador,
  COALESCE(f.departamento, 'Não informado') AS departamento,
  COALESCE(g.nome, f.id_gestor, 'Não informado') AS gestor,
  f.id_gestor, f.id_escala,
  f.data_registro AS data, DATE_TRUNC(f.data_registro, MONTH) AS mes,
  CONCAT(CAST(MOD(EXTRACT(DAYOFWEEK FROM f.data_registro) + 5, 7) + 1 AS STRING), ' · ',
    ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'][OFFSET(MOD(EXTRACT(DAYOFWEEK FROM f.data_registro) + 5, 7))])
    AS dia_semana,
  MOD(EXTRACT(DAYOFWEEK FROM f.data_registro) + 5, 7) + 1 AS dia_semana_ordem,
  f.classificacao, f.elegivel_indicadores, f.salario_pendente,
  1 AS linhas_observadas, IF(f.elegivel_indicadores, 1, 0) AS linhas_elegiveis,
  IF(f.elegivel_indicadores, 0, 1) AS dias_pendentes,
  IF(f.elegivel_indicadores, IF(f.jornada_esperada_horas > 0, 1, 0), NULL) AS dias_trabalho_validos,
  IF(f.elegivel_indicadores, IF(f.falta_integral_injustificada, 1, 0), NULL) AS faltas_integrais,
  IF(f.elegivel_indicadores, IF(f.ausencia_parcial_injustificada, 1, 0), NULL) AS ausencias_parciais,
  f.horas_esperadas_indicadores AS horas_previstas,
  f.horas_trabalhadas_na_jornada AS horas_trabalhadas_na_jornada,
  f.horas_abonadas, f.horas_injustificadas,
  f.horas_abonadas + f.horas_injustificadas AS horas_ausencia_total,
  f.horas_excedentes,
  CASE WHEN i.dsr_perdido THEN 1 WHEN i.dsr_perdido = FALSE THEN 0 ELSE NULL END AS dsrs_perdidos,
  IF(i.dia_dsr_apurado, 1, 0) AS descansos_apurados,
  i.dsrs_indeterminados, i.dsrs_com_fronteira,
  IF(i.horas_sem_valoracao, 1, 0) AS dias_horas_sem_valoracao,
  IF(i.dsr_sem_valoracao, 1, 0) AS dsrs_sem_valoracao,
  i.valor_horas_nao_arredondado AS valor_horas_conhecido,
  i.valor_dsr_componente AS valor_dsr_conhecido,
  CASE
    WHEN NOT f.elegivel_indicadores AND COALESCE(i.valor_dsr_componente, NUMERIC '0') = 0 THEN NULL
    WHEN i.valor_horas_nao_arredondado IS NULL AND i.valor_dsr_componente IS NULL THEN NULL
    ELSE COALESCE(i.valor_horas_nao_arredondado, NUMERIC '0')
      + COALESCE(i.valor_dsr_componente, NUMERIC '0')
  END AS valor_conhecido_parcial
FROM `{{dataset}}.fct_ausencias_diarias` AS f
JOIN `{{dataset}}.fct_impacto_diario` AS i
  ON i.id_colaborador = f.id_colaborador AND i.data_registro = f.data_registro
LEFT JOIN `{{dataset}}.dim_colaboradores` AS g ON g.id_colaborador = f.id_gestor
LEFT JOIN `{{dataset}}.mart_gestao_colaboradores` AS m ON m.id_colaborador = f.id_colaborador;

CREATE OR REPLACE VIEW `{{dataset}}.vw_dashboard_gestao`
OPTIONS(description='Dashboard: uma linha por colaborador; recomendações de jun-ago/2025. Não aplicar filtro mensal a essa política trimestral.') AS
SELECT m.id_colaborador,
  COALESCE(m.nome, CONCAT(m.id_colaborador, ' (cadastro em revisão)')) AS colaborador,
  COALESCE(m.departamento, 'Não informado') AS departamento,
  COALESCE(g.nome, m.id_gestor, 'Não informado') AS gestor,
  m.id_gestor, m.id_escala,
  'Junho a agosto de 2025' AS periodo_analise,
  1 AS colaboradores,
  m.total_faltas_injustificadas_confirmadas AS faltas_confirmadas,
  m.total_ausencias_parciais_confirmadas AS ausencias_parciais_confirmadas,
  m.total_dsr_perdido_confirmado AS dsrs_perdidos_confirmados,
  m.maior_sequencia_ciclos_perdidos,
  m.dias_pendentes, m.dsrs_indeterminados, m.dsrs_com_fronteira,
  m.salario_pendente, m.apuracao_dsr_indisponivel, m.financeiro_incompleto,
  m.acao_disciplinar_recomendada,
  COALESCE(m.acao_disciplinar_recomendada, 'Pendente de validação') AS acao_visualizacao,
  m.status_recomendacao, m.escopo_recomendacao,
  CASE m.status_recomendacao
    WHEN 'COMPLETA_NO_ESCOPO' THEN 'Conclusiva no escopo'
    WHEN 'NIVEL_MAXIMO_COMPROVADO_COM_PENDENCIAS' THEN 'Suspensão comprovada; contagens pendentes'
    ELSE 'Aguardando validação'
  END AS situacao_recomendacao,
  IF(m.elegivel_reverse_etl, 'Apto à atualização', 'Retido para revisão') AS situacao_publicacao,
  IF(m.elegivel_reverse_etl, 1, 0) AS aptos_atualizacao,
  IF(m.elegivel_reverse_etl, 0, 1) AS retidos_revisao,
  IF(m.acao_disciplinar_recomendada IS NULL, 1, 0) AS recomendacoes_pendentes,
  IF(m.acao_disciplinar_recomendada = 'Suspensão Disciplinar (1 a 3 dias)', 1, 0)
    AS suspensoes_recomendadas,
  m.desconto_estimado_confirmado,
  IF(m.desconto_estimado_confirmado IS NOT NULL, m.subtotal_conhecido_nao_arredondado, NULL)
    AS valor_conhecido_parcial
FROM `{{dataset}}.mart_gestao_colaboradores` AS m
LEFT JOIN `{{dataset}}.dim_colaboradores` AS g ON g.id_colaborador = m.id_gestor;

CREATE OR REPLACE VIEW `{{dataset}}.vw_dashboard_qualidade`
OPTIONS(description='Dashboard: uma linha por ID/data/motivo. Ocorrências se sobrepõem; contar id_dia distinto para o total de dias pendentes.') AS
SELECT q.id_colaborador,
  CONCAT(q.id_colaborador, '|', CAST(q.data_registro AS STRING)) AS id_dia,
  q.data_registro AS data,
  COALESCE(f.nome, CONCAT(q.id_colaborador, ' (cadastro em revisão)')) AS colaborador,
  COALESCE(f.departamento, 'Não informado') AS departamento,
  COALESCE(g.nome, f.id_gestor, 'Não informado') AS gestor,
  q.classificacao, q.motivo AS motivo_codigo,
  CASE q.motivo
    WHEN 'CADASTRO_CONFLITANTE' THEN 'Cadastro com versões conflitantes'
    WHEN 'ESCALA_AUSENTE_OU_NAO_SUPORTADA' THEN 'Escala ausente ou não suportada'
    WHEN 'FORA_DO_VINCULO' THEN 'Ponto fora do vínculo'
    WHEN 'PONTO_CONFLITANTE' THEN 'Ponto conflitante no mesmo dia'
    WHEN 'PONTO_INVALIDO' THEN 'Horas ou valores inválidos'
    WHEN 'DSR_COM_JORNADA_POSITIVA' THEN 'DSR com jornada esperada positiva'
    WHEN 'DSR_DIVERGE_CALENDARIO' THEN 'DSR diverge do calendário'
    WHEN 'JORNADA_DIVERGE_CALENDARIO' THEN 'Jornada diverge do calendário'
    WHEN 'ABONO_SEM_DURACAO' THEN 'Abono sem duração informada'
    WHEN 'SEM_REGISTRO_PONTO' THEN 'Dia sem registro de ponto'
    ELSE q.motivo
  END AS motivo,
  1 AS ocorrencias,
  ARRAY_TO_STRING(ARRAY(SELECT CAST(linha AS STRING)
    FROM UNNEST(q.ponto_linhas_origem) AS linha ORDER BY linha), ', ') AS linhas_ponto_origem,
  ARRAY_TO_STRING(ARRAY(SELECT CAST(linha AS STRING)
    FROM UNNEST(q.cadastro_linhas_origem) AS linha ORDER BY linha), ', ') AS linhas_cadastro_origem
FROM `{{dataset}}.qa_ausencias_diarias` AS q
JOIN `{{dataset}}.fct_ausencias_diarias` AS f
  ON f.id_colaborador = q.id_colaborador AND f.data_registro = q.data_registro
LEFT JOIN `{{dataset}}.dim_colaboradores` AS g ON g.id_colaborador = f.id_gestor;
