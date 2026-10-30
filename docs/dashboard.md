# Dashboard no Looker Studio

**Relatório:** [Demarco | Absenteísmo e impacto em folha](https://datastudio.google.com/reporting/7bdfde4c-c915-4549-ad2d-d13e40f32b2f).

As quatro páginas foram montadas com as views do BigQuery. Em **30/10/2026**, o usuário confirmou que o teste em janela anônima funcionou. Essa é a evidência de acesso visual; o leitor HTTP do projeto não executa JavaScript nem valida o carregamento dos gráficos.

## Fontes e filtros

No conector BigQuery, selecione o projeto `desafio-demarco-513123`, dataset `demarco_absenteismo` e as views abaixo. Para reproduzir em outra conta, use as views criadas pelo pipeline no projeto configurado no seu `.env`.

| Fonte | Uma linha representa | Páginas / filtros |
| --- | --- | --- |
| `vw_dashboard_diario` | ID/data | Visão geral e Padrões; período, departamento e gestor |
| `vw_dashboard_gestao` | Colaborador no trimestre | Gestão; departamento, gestor e `acao_visualizacao` |
| `vw_dashboard_qualidade` | ID/data/motivo | Qualidade; período, departamento, gestor e `motivo` |

Cada gráfico e controle deve usar a fonte da sua página. Os controles são de página. Use `data` como dimensão de período e intervalo automático nos gráficos diários/de qualidade; o seletor tem padrão fixo **01/06/2025–31/08/2025**. Gestão usa o trimestre completo, indicado no subtítulo, sem filtro mensal.

As fontes permanecem separadas, evitando multiplicar valores e pessoas pelas linhas de motivos. As medidas confirmadas já respeitam elegibilidade; um filtro geral de linhas elegíveis esconderia as pendências.

## Fórmulas e apresentação

O contrato [`dashboard/report_spec.json`](../dashboard/report_spec.json) contém as fontes, páginas e todas as fórmulas. As mesmas expressões, com adaptação de `COUNT_DISTINCT` para GoogleSQL, são avaliadas em `sql/13_dashboard_checks.sql`.

Para gerar a lista copiável de fórmulas e os links de criação:

```bash
uv run python scripts/build_looker_guide.py
```

Saídas: `artifacts/dashboard/formulas.md` e `links.md`. Os links preenchem a conexão para iniciar um relatório no navegador; não publicam páginas ou gráficos personalizados. Na fonte correspondente, crie os campos calculados necessários. Fórmulas agregadas mantêm agregação **Automática**.

- Percentuais são razões de 0 a 1, formatadas como porcentagem; não multiplicar por 100.
- Horas são decimais. Moeda: BRL, duas casas; rótulo **Desconto parcial**.
- Nulos aparecem como traço. Zero significa ausência de déficit já validada.
- `mes`: granularidade Ano e mês, em ordem crescente.
- As taxas dividem somas, conforme [as regras de negócio](regras-de-negocio.md).

## 1. Visão geral

Fonte diária. Cartões: **25 faltas integrais**, **247,7 horas injustificadas**, **27 DSRs perdidos**, **R$ 7.087,90 de desconto parcial**, **1,23% de taxa injustificada** e **288 dias pendentes**.

| Visual | Dimensão | Métricas |
| --- | --- | --- |
| Colunas mensais agrupadas | `mes` | Soma de `horas_injustificadas` e `horas_abonadas` |
| Barras horizontais | `departamento` | Campo calculado “Desconto conhecido (parcial)”, ordem decrescente |
| Cartões de cobertura | — | Cobertura 92,19%; ausências parciais 105; horas abonadas 42; DSRs sem conclusão 75 |

No gráfico mensal, ambas as séries medem horas e usam a mesma escala. Para as entradas atuais, mantenha mínimo 0 e máximo 150 nos dois eixos, se separados; o direito pode ficar sem rótulos. Somente alinhar o zero não iguala escalas. Revise o limite se mudar as entradas ou a granularidade.

Aviso abaixo dos gráficos:

> Valores financeiros parciais: há parcelas sem salário confiável e descansos iniciais que dependem de maio. Datas pendentes ficam fora dos totais confirmados.

A taxa de horas ausentes incluindo abonos é 1,43%; nomeie-a por extenso se exibida, distinguindo-a da taxa injustificada.

## 2. Padrões de ausência

Fonte diária e mesmos três filtros. A tabela dinâmica usa linhas `departamento`, colunas `dia_semana` em ordem crescente e métrica **Taxa de dias de falta integral**:

```text
CASE WHEN SUM(dias_trabalho_validos) > 0
THEN SUM(faltas_integrais) / SUM(dias_trabalho_validos) END
```

Mantenha a métrica como Número e aplique regras de formatação condicional de cor única em todas as colunas:

| Taxa | Fundo | Texto |
| --- | --- | --- |
| 0 | `#FFFFFF` | `#0F172A` |
| > 0 e ≤ 0,01 | `#FEF3C7` | `#0F172A` |
| > 0,01 e ≤ 0,03 | `#FCD34D` | `#0F172A` |
| > 0,03 | `#B91C1C` | `#FFFFFF` |

As faixas usam proporções e servem à apresentação, não à política disciplinar. O mapa de calor nativo normaliza a intensidade por coluna; as faixas fixas permitem comparar dias pela mesma cor. [Referência da tabela dinâmica](https://docs.cloud.google.com/data-studio/pivot-table-reference). Ausência de base fica como traço. Concentração visual não comprova intenção de “emenda”.

Adicione colunas de faltas integrais por `dia_semana` e barras horizontais empilhadas por `departamento`, com horas injustificadas e abonadas por soma. Use cores consistentes e legenda.

A tabela **Detalhamento das ausências** contém dimensões `data`, `id_colaborador`, `colaborador`, `departamento` e `gestor`; métricas por soma: `faltas_integrais`, `ausencias_parciais`, `horas_injustificadas`, `horas_abonadas`. Filtro exclusivo da tabela: **Incluir `horas_ausencia_total` > 0**. Paginação de dez linhas, data decrescente e resumo acompanhando os filtros. Totais no trimestre: **25 / 105 / 247,70 / 42,00**.

## 3. Gestão de pessoas

Fonte de gestão. Subtítulo: **Recomendações referentes a junho–agosto de 2025**. Cartões por soma: `colaboradores` **40**, `aptos_atualizacao` **32**, `retidos_revisao` **8**, `suspensoes_recomendadas` **6**.

As barras horizontais usam `acao_visualizacao` e soma de `colaboradores`, em ordem decrescente:

| Ação | Pessoas |
| --- | ---: |
| Sem ação requerida | 26 |
| Pendente de validação | 7 |
| Suspensão Disciplinar (1 a 3 dias) | 6 |
| Advertência Escrita | 1 |

Não há casos de alinhamento em 1-on-1 nestas entradas. A tabela usa dimensões `id_colaborador`, `colaborador`, `departamento`, `gestor`, `acao_visualizacao`, `situacao_publicacao`; métricas `faltas_confirmadas` e `dsrs_perdidos_confirmados` por soma, `maior_sequencia_ciclos_perdidos` por máximo. Sequências não são aditivas. Ordene por faltas decrescentes e use paginação de dez linhas.

Use rótulos legíveis: “Ação recomendada”, “Situação da atualização”, “Faltas confirmadas”, “DSRs perdidos” e “Ciclos seguidos”. `situacao_recomendacao` está disponível para detalhar pendências. Há oito retidos e sete ações pendentes porque uma suspensão já está comprovada, mas suas contagens seguem incompletas. “Apto à atualização” indica elegibilidade, não recibo de escrita.

Para abrir a [planilha de gestão](https://docs.google.com/spreadsheets/d/1L4JSPWAaKSKgAFMyALhtBc5jEEzK32q0Vwna4B-hlYs/edit), pode-se usar um botão de navegação com link estático ou texto com hiperlink. [Configuração de botões](https://docs.cloud.google.com/data-studio/add-buttons).

## 4. Qualidade dos dados

Fonte de qualidade. Cartões: `id_dia` com **Contagem distinta = 288**, `ocorrencias` com **Soma = 301**. Barras horizontais: `motivo`, soma de ocorrências, ordem decrescente; título **Ocorrências por motivo**.

A tabela **Pendências para revisão** contém dimensões `data`, `id_colaborador`, `colaborador`, `departamento`, `gestor`, `motivo`, `linhas_ponto_origem`, `linhas_cadastro_origem`; métrica `ocorrencias` por soma. Renomeie as duas últimas dimensões para “Linhas no ponto de origem” e “Linhas no cadastro de origem”. Use paginação de dez linhas, data decrescente e resumo acompanhando filtros. No trimestre, a tabela tem **301 linhas de motivos**, não 288.

> Um colaborador pode ter mais de um motivo na mesma data. As 301 ocorrências correspondem a 288 combinações distintas de pessoa e dia. Esses casos não viram faltas ou descontos automaticamente.

Essa fonte mostra `qa_ausencias_diarias`. Rejeições anteriores de chave/período ficam em `qa_ponto_sem_chave_periodo`, sem linhas nas entradas atuais.

## Layout e acesso

Tela da Visão geral: **1440 × 1000 px**. Demais páginas: **1440 × 1300 px**, usando a configuração individual da página. Margens de 40 px, intervalos de 20–24 px, fonte Arial/Roboto, título 30 px, rótulos 13 px e valores principais 32–34 px (moeda 26 px).

Fundo `#F8FAFC`, cartões brancos, texto `#0F172A`, borda fina `#E2E8F0`, abonos/destaques `#0D9488`, faltas `#B91C1C` e pendências `#B45309`. Cartões do mesmo grupo têm tamanhos iguais; gráficos aproveitam a largura; tabelas mantêm paginação e fontes legíveis.

O código de referência visual continua disponível, gerando apenas artefatos locais:

```bash
uv run python scripts/render_dashboard_layout.py --refresh-charts
```

Ele exige o resultado real de `bq-dashboard-check`; a opção consulta séries com `sql/14_dashboard_charts.sql` e concilia seus totais. Sem a opção, usa séries locais ou espaços reservados. O SVG é referência estática, não o dashboard publicado.

Para visualização pela banca, configure compartilhamento para **qualquer pessoa com o link visualizar** e use **Credenciais do proprietário** nas fontes, quando disponíveis. Referências: [compartilhamento](https://docs.cloud.google.com/data-studio/invite-others-to-your-reports) e [credenciais](https://docs.cloud.google.com/data-studio/data-credentials-article). O teste anônimo aprovado pelo usuário está registrado em [validação](validacao.md).
