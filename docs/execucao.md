# Como reproduzir

Execute todos os comandos na raiz do repositório. Requer Python 3.12 ou superior e [uv](https://docs.astral.sh/uv/getting-started/installation/).

## Instalação e diagnóstico local

```bash
uv sync --locked
uv run demarco diagnose
uv run pytest -q
```

O diagnóstico lê os quatro XLSX sintéticos em `data/raw/`, sem alterar os originais, e grava JSONL e relatórios de qualidade em `artifacts/diagnostico/`. Não precisa de credenciais ou acesso ao Google. Fórmulas, erros Excel e estrutura incompatível interrompem a leitura. Valores inválidos são identificados no relatório; saída zero confirma a geração do diagnóstico, não ausência de problemas nas fontes.

## Configuração Google

Copie `.env.example` para `.env` e preencha as variáveis:

```dotenv
GOOGLE_APPLICATION_CREDENTIALS=credentials/google-service-account.json
GOOGLE_CLOUD_PROJECT=SEU_PROJETO
BIGQUERY_DATASET=demarco_absenteismo
BIGQUERY_LOCATION=US
BIGQUERY_MAX_BYTES_BILLED=1073741824
MANAGEMENT_SPREADSHEET_ID=ID_DA_PLANILHA_NATIVA
MANAGEMENT_WORKSHEET=Ações Disciplinares
```

Use uma credencial própria, guardada em `credentials/`; o `.env` contém apenas o caminho do JSON. Ambos são ignorados pelo Git. Variáveis exportadas no ambiente prevalecem sobre o `.env`. Caminhos relativos de credenciais são resolvidos em relação à pasta do `.env`.

No ambiente entregue, o projeto é `desafio-demarco-513123`, o dataset é `demarco_absenteismo` e a localização é `US`. Para reproduzir em outra conta, configure um projeto próprio. A identidade precisa poder criar jobs, ler e escrever as tabelas do dataset e, caso ainda não exista, criar o dataset. Habilite a BigQuery API. O conector do Looker Studio requer projeto associado a faturamento; consulte os [requisitos](https://docs.cloud.google.com/data-studio/connect-to-google-bigquery) e os [preços do BigQuery](https://cloud.google.com/bigquery/pricing).

Sem caminho de chave, o cliente usa Application Default Credentials. Para BigQuery, uma alternativa é instalar a [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk) e executar:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project SEU_PROJETO
```

O login no Console pelo navegador não autentica o Python local. [Referência de ADC](https://docs.cloud.google.com/docs/authentication/set-up-adc-local-dev-environment). Para usar ADC também no Sheets, o OAuth precisa autorizar o escopo de planilhas; a integração entregue foi validada com conta de serviço.

## Preparar a planilha de gestão

1. Envie `data/raw/template_acoes_disciplinares.xlsx` ao Drive e converta-o em uma planilha nativa: **Arquivo → Salvar como Planilhas Google**.
2. Habilite a **Google Sheets API** no projeto.
3. Compartilhe essa planilha como **Editor** com o `client_email` da conta de serviço.
4. Preencha `MANAGEMENT_SPREADSHEET_ID` com o trecho entre `/d/` e `/edit` da URL e `MANAGEMENT_WORKSHEET` com o título exato da aba.

Acesso público de leitura não concede edição. A conta usada no ambiente entregue não possui permissão para habilitar serviços; essa configuração foi realizada por uma identidade autorizada. Detalhes de escrita e preservação estão em [Reverse ETL](reverse-etl.md).

Quando a planilha estiver acessível por link, a conferência pública abaixo compara os IDs e campos protegidos com o template, sem escrever:

```bash
uv run demarco check-template --spreadsheet-id ID_DA_PLANILHA
```

Saída `0`: comparação passou; `1`: erro de leitura/estrutura; `2`: divergências. O comando não verifica permissão de edição nem formatação; as quatro colunas calculadas ficam fora dessa comparação.

## Executar o pipeline no BigQuery

```bash
uv run demarco bq-status
uv run demarco bq-load --execute
uv run demarco bq-stage --execute
uv run demarco bq-check --execute
uv run demarco bq-daily --execute
uv run demarco bq-daily-check --execute
uv run demarco bq-finance --execute
uv run demarco bq-finance-check --execute
uv run demarco bq-dashboard --execute
uv run demarco bq-dashboard-check --execute
```

`bq-status` somente consulta a conexão e a localização do dataset. Nos demais comandos `bq-*`, omitir `--execute` gera planos ou SQL locais, sem chamadas ao Google; ainda é necessário configurar um projeto válido no `.env`. Por exemplo:

```bash
uv run demarco bq-load
uv run demarco bq-dashboard-check
```

A carga usa schema explícito, tolerância zero para registros rejeitados e `WRITE_TRUNCATE` apenas nas quatro tabelas `raw_*`. As transformações recriam suas tabelas e views derivadas. Isso evita acumular registros em reexecuções. As etapas são jobs sucessivos, não uma transação única: em caso de falha, interrompa as etapas seguintes e reexecute a etapa afetada antes de prosseguir. Não misture cargas parciais com o resultado final.

O código recusa localização de dataset divergente. `BIGQUERY_MAX_BYTES_BILLED` limita cada consulta submetida pelo Python; não limita automaticamente consultas do Looker Studio, armazenamento ou consumo mensal.

Os SQL efetivamente submetidos, IDs dos jobs e resultados ficam em `artifacts/bigquery/`. Os valores `NUMERIC` são serializados como strings decimais para preservar precisão. Gerar SQL sem `--execute` não constitui evidência de execução no serviço.

## Atualizar a gestão e conectar o dashboard

```bash
uv run demarco sheets-sync
uv run demarco sheets-sync --execute
```

O primeiro comando gera uma prévia consultando BigQuery e Sheets; exige rede e credenciais, mas não escreve. O segundo reconstrói o plano atual, aplica somente as células permitidas e verifica os valores e campos protegidos. Veja [Reverse ETL](reverse-etl.md).

As três views finais são conectadas no editor do Looker Studio conforme [a configuração do dashboard](dashboard.md). A criação das páginas e a configuração visual são realizadas no editor; os scripts não publicam um relatório personalizado automaticamente.

## Auditorias opcionais

As verificações principais já estão na sequência do pipeline. Para detalhar achados:

```bash
uv run demarco bq-check --sql-file sql/03_encoding_audit.sql --output-dir artifacts/codificacao --execute
uv run demarco bq-daily-check --sql-file sql/06_daily_audit.sql --output-dir artifacts/diario --execute
uv run demarco bq-daily-check --sql-file sql/07_calendar_divergences.sql --output-dir artifacts/calendario --execute
uv run demarco bq-finance-check --sql-file sql/10_finance_audit.sql --output-dir artifacts/financeiro --execute
```

## Utilitários mantidos na entrega

Todos os scripts utilizados permanecem disponíveis, inclusive os de preparação e apoio. Seus resultados gerados ficam fora do Git.

| Script em `scripts/` | Uso |
| --- | --- |
| `install-gcloud.sh` | Instala a versão fixada da CLI em Linux x86_64 quando ausente, conferindo SHA-256 |
| `enable_sheets_api.py` | Habilita somente a Sheets API; exige permissão administrativa correspondente |
| `check_sheets_access.py` | Lê metadados da planilha; não comprova permissão de escrita |
| `compare_daily_runs.py` | Compara resumos e assinatura de duas execuções |
| `build_looker_guide.py` | Gera fórmulas e links de criação em `artifacts/dashboard/` |
| `render_dashboard_layout.py` | Gera referência SVG; `--refresh-charts` consulta as séries reais com `sql/14_dashboard_charts.sql` |
| `check_report_access.py` | Verifica resposta HTTP do relatório; não renderiza os gráficos |

Use `uv run python scripts/NOME.py --help` para as opções. O instalador da CLI é executado com `bash scripts/install-gcloud.sh` e usa os [arquivos versionados do Google](https://docs.cloud.google.com/sdk/docs/downloads-versioned-archives).
