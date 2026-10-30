-- Leitura das mesmas séries da página Visão geral para a referência de layout.
-- A fórmula monetária é compartilhada com o contrato e as verificações do painel.
SELECT TO_JSON_STRING(STRUCT(
  ARRAY(
    SELECT AS STRUCT mes,
      SUM(horas_injustificadas) AS horas_injustificadas,
      SUM(horas_abonadas) AS horas_abonadas
    FROM `{{dataset}}.vw_dashboard_diario`
    GROUP BY mes ORDER BY mes
  ) AS meses,
  ARRAY(
    SELECT AS STRUCT departamento,
      {{metric:desconto_conhecido}} AS valor
    FROM `{{dataset}}.vw_dashboard_diario`
    GROUP BY departamento ORDER BY valor DESC, departamento
  ) AS departamentos
)) AS chart_data;
