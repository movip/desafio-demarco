# Resultados e validação

Os resultados abaixo foram obtidos com as quatro planilhas sintéticas versionadas. Os modelos e as verificações foram executados no BigQuery real; a atualização foi executada na API do Google Sheets. Os arquivos de evidência, com IDs dos jobs, consultas renderizadas e backups, permanecem locais em `artifacts/`.

## Fontes e tratamento

| Fonte | Linhas recebidas | Chaves distintas | Duplicatas exatas excedentes | Chaves conflitantes |
| --- | ---: | ---: | ---: | ---: |
| Cadastro | 46 | 45 | 0 | 1 |
| Escalas | 4 | 4 | 0 | 0 |
| Ponto | 3.779 | 3.687 | 82 | 10 |
| Gestão | 40 | 40 | 0 | 0 |

O staging do ponto tem **3.697 linhas** após remover somente as 82 repetições exatas. A consolidação diária mantém uma linha por ID/data, com conflitos sinalizados. A correção de codificação alterou 41 células no staging; os originais e `raw_*` foram preservados.

## Indicadores conferidos

| Indicador | Resultado |
| --- | ---: |
| Colaboradores no escopo da gestão | 40 |
| Linhas diárias | 3.687 |
| Linhas elegíveis / pendentes | 3.399 / 288 |
| Cobertura das linhas | 92,19% |
| Faltas integrais / ausências parciais injustificadas | 25 / 105 |
| Ausências integrais abonadas | 6 |
| Horas previstas validadas | 20.220,4 |
| Horas injustificadas / abonadas | 247,7 / 42 |
| Taxa de horas injustificadas | 1,23% |
| Taxa de horas ausentes, incluindo abonos | 1,43% |
| Taxa de dias de falta integral | 0,98% |
| DSRs perdidos confirmados | 27 |
| Descansos sem conclusão | 75 |
| Descansos de fronteira com maio, incluídos nos 75 | 45 |
| Desconto de horas conhecido | R$ 4.247,95 |
| Desconto de DSR conhecido | R$ 2.839,95 |
| Subtotal conhecido, parcial | R$ 7.087,90 |
| Dias com déficit positivo sem preço / DSRs perdidos sem preço | 25 / 8 |
| Motivos de qualidade / dias distintos | 301 / 288 |

As horas injustificadas incluem 202,4h de faltas integrais e 45,3h de ausências parciais. As 288 datas pendentes incluem 92 por cadastro conflitante, 184 por escala ausente, sete fora do vínculo, uma por horas inválidas, três por DSR com jornada positiva e uma declaração sem duração. Há motivos sobrepostos, incluindo os dez conflitos de ponto.

Dos 75 descansos inconclusivos, 48 estão indeterminados e 27 têm pendência cadastral. Os dois cadastros sem escala têm DSR indisponível, sem inventar uma quantidade de descansos. Os totais financeiros integrais dos 40 colaboradores continuam nulos; o subtotal conhecido tem o escopo definido em [regras de negócio](regras-de-negocio.md).

## Gestão e preservação do histórico

Distribuição das ações: **26 sem ação, zero alinhamentos, uma advertência, seis suspensões e sete pendentes**. Um caso de suspensão comprovada tem contagens incompletas; por isso há **32 elegíveis e oito retidos**.

A execução real atualizou **128 células em 32 colaboradores** e preservou os oito retidos. A comparação antes/depois confirmou os campos protegidos, incluindo **sete datas de conversa, nove registros de advertência e dez observações**. A reexecução retornou `NO_CHANGES`, sem novo lote nem alteração de datas de processamento.

Os registros originais dessa execução estão em `artifacts/reverse-etl/20261029T223129-e726d840e6ed/`; os da reexecução em `artifacts/reverse-etl/20261029T223201-316646dfb04c/`. Esses diretórios não são distribuídos com o repositório. Os [comandos de reprodução](execucao.md) geram novas evidências em cada ambiente.

## Verificações automatizadas

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

Os testes locais não dependem de rede ou credenciais. Cobrem leitura e preservação das entradas, datas e salários, nulos, duplicatas e conflitos, preparação dos SQL, contrato do dashboard e integração Sheets simulada. Esta última inclui reordenação, fórmulas, formatos, falhas de acesso, concorrência, backups privados e reexecução.

Na revisão final, **89 testes passaram**, assim como lint e formatação. Uma cópia contendo apenas os arquivos públicos instalou o projeto com `uv.lock`, executou o diagnóstico, preparou os nove comandos de carga/SQL e gerou o guia de fórmulas sem credenciais Google. A seleção pública foi verificada quanto a links locais quebrados, padrões de segredos e exclusões; os hashes dos XLSX e dos SQL foram preservados. A conferência pública de leitura da planilha real também passou para os 40 colaboradores, comparando os campos protegidos com o template original.

| SQL | Verificação no serviço |
| --- | --- |
| `02_staging_checks.sql` | Contagens, deduplicação, preservação da referência e 14 casos da correção de texto |
| `05_daily_checks.sql` | 23 casos da função diária; unicidade, vínculo, nulos, origem e conciliação das horas |
| `09_finance_checks.sql` | 35 casos das funções financeiras/disciplinares; ciclos, sequência, cobertura e valores |
| `13_dashboard_checks.sql` | Fórmulas do mesmo contrato, grãos separados, taxas ponderadas, denominador zero e valor sem preço |

Exemplos financeiros conferidos: salário 2.200/divisor 220/jornada 44h, falta de 8,8h e um DSR perdido resultam em **R$ 161,33**; salário 1.800/divisor 180/jornada 36h, falta de 7,2h e dois descansos do mesmo ciclo resultam em **R$ 192,00**. Domingo e segunda do ciclo noturno continuam uma única semana para a política.

As contagens de regressão são específicas das entradas fornecidas. A análise sintática local dos SQL não substitui sua execução no BigQuery; as duas verificações foram realizadas durante o desenvolvimento.

### Repetibilidade

Os modelos diário e financeiro foram reexecutados sem alteração dos resultados. Para repetir a comparação diária:

```bash
uv run demarco bq-daily-check --execute --output-dir artifacts/reexecucao/antes
uv run demarco bq-daily --execute
uv run demarco bq-daily-check --execute --output-dir artifacts/reexecucao/depois
uv run python scripts/compare_daily_runs.py artifacts/reexecucao/antes/bq-daily-check-result.json artifacts/reexecucao/depois/bq-daily-check-result.json
```

A comparação usa contagens, medidas e assinatura do conteúdo independente da ordem das linhas; IDs de jobs ficam fora dela. O mesmo utilitário aceita os relatórios de verificação financeira.

## Dashboard e acesso da banca

[Relatório salvo no Looker Studio](https://datastudio.google.com/reporting/7bdfde4c-c915-4549-ad2d-d13e40f32b2f).

Em **30/10/2026**, o usuário confirmou que o teste de acesso em janela anônima funcionou após a montagem das quatro páginas. Os indicadores das três primeiras páginas foram confirmados durante a montagem, incluindo os totais da tabela de ausências e os 40 colaboradores da gestão. O fechamento da página Qualidade foi orientado com 288 dias distintos e 301 ocorrências.

A checagem HTTP sem autenticação também retornou status 200 e o título do relatório. Ela é reproduzível com `uv run python scripts/check_report_access.py`, mas **não renderiza os gráficos**. Seu campo `visual_access_verified` permanece falso por essa limitação; a confirmação visual de acesso foi fornecida pelo usuário, não pelo script.

O relatório está conectado às três views do BigQuery. [Configuração de páginas, filtros e fórmulas](dashboard.md). O link público e a conta de origem precisam permanecer disponíveis durante a avaliação.
