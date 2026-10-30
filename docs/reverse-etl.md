# Atualização da gestão no Google Sheets

## Estado da integração

O comando `demarco sheets-sync` está implementado e foi executado na planilha real, com prévia, backups, escrita de células específicas e verificação após a atualização. Os testes locais também simulam a API e cobrem preservação de histórico e reexecução. O acesso atual está configurado com Sheets API habilitada e a conta de serviço como Editor.

A prévia identificou 32 colaboradores e 128 células para alteração. A execução retornou `UPDATED_AND_VERIFIED`: os valores escritos conferiram e os campos protegidos ficaram iguais. A reexecução retornou `NO_CHANGES`, com zero células para alterar e sem novo lote de escrita. Os oito registros com pendências permaneceram intactos.

A conta de serviço não possui `serviceusage.services.enable`: em outra instalação, a Sheets API deve ser habilitada por uma identidade autorizada no projeto, antes de executar o pipeline.

## Configurar o acesso

1. Habilitar a **Google Sheets API** no projeto Google Cloud.
2. Compartilhar a planilha nativa com o `client_email` da service account, como **Editor**. Essa identidade consta no JSON local de credenciais; somente o endereço precisa ser usado no compartilhamento, nunca a chave privada.
3. Conferir no `.env` o ID da planilha, o título exato da aba e o caminho da credencial.

```dotenv
GOOGLE_CLOUD_PROJECT=SEU_PROJETO
GOOGLE_APPLICATION_CREDENTIALS=credentials/google-service-account.json
MANAGEMENT_SPREADSHEET_ID=ID_DA_PLANILHA_NATIVA
MANAGEMENT_WORKSHEET=Ações Disciplinares
```

O cliente usa o escopo `https://www.googleapis.com/auth/spreadsheets`; a permissão de BigQuery e o acesso público para visualização não concedem, por si só, direito de edição. ADC pode ser usado como alternativa, desde que o OAuth tenha os escopos necessários ao Sheets. A execução local atual usa o arquivo de service account fornecido pelo autor.

O repositório inclui dois utilitários:

```bash
uv run python scripts/check_sheets_access.py
uv run python scripts/enable_sheets_api.py
```

O primeiro somente lê metadados. O segundo habilita exclusivamente a Sheets API se a conta tiver a permissão necessária; não altera planilhas. Sem essa permissão, habilitar pelo Console com uma conta autorizada. O utilitário de leitura não comprova a permissão de escrita.

Referências: [escopos da API](https://developers.google.com/workspace/sheets/api/scopes) e [habilitação de serviços](https://docs.cloud.google.com/service-usage/docs/reference/rest/v1/services/enable).

## Fluxo

1. Ler a aba existente pela API, incluindo valores digitados, fórmulas, formatos, notas e validações.
2. Salvar uma cópia local antes de qualquer escrita.
3. Consultar `mart_gestao_colaboradores` com o SQL versionado `sql/11_reverse_etl_source.sql`.
4. Encontrar cada pessoa pelo `ID_Colaborador` normalizado e localizar colunas pelos cabeçalhos, aceitando reordenação.
5. Montar a prévia somente para registros com `elegivel_reverse_etl = TRUE`, contagens válidas e recomendação reconhecida.
6. Antes da escrita, reler a aba e comparar com a referência da prévia. Mudanças detectadas interrompem a execução sem enviar o lote.
7. Enviar um único `spreadsheets.batchUpdate` com uma requisição `updateCells` por célula alterada, usando `fields = userEnteredValue` e endereço inicial de uma única célula.
8. Reler e conferir todos os valores escritos e o estado protegido da aba.

O endpoint aplica as requisições do lote em conjunto. Não são enviados comandos de limpeza, substituição de aba, inserção de linhas ou alteração de formatação. A máscara de campos limita a escrita ao valor das células selecionadas. [Documentação de lotes e máscaras](https://developers.google.com/workspace/sheets/api/guides/batchupdate).

## Colunas sob responsabilidade do pipeline

Somente estas quatro colunas são atualizadas:

- `Total_Faltas_Injustificadas`
- `Total_DSR_Perdido`
- `Acao_Disciplinar_Recomendada`
- `Data_Ultimo_Processamento`

As três colunas manuais, os campos de nome/departamento/gestor e quaisquer colunas extras ficam fora das requisições. Valores calculados existentes nas linhas retidas também são protegidos. Não se busca a pessoa pelo nome nem pela posição fixa da linha.

Cabeçalhos ausentes/duplicados, IDs vazios/duplicados, ID derivado de fórmula, contagens inválidas ou ação fora do contrato interrompem a preparação. IDs novos não criam linhas: aparecem no relatório como `SEM_LINHA_NA_GESTAO`. Pessoas na aba sem resultado analítico permanecem intactas e são sinalizadas.

Uma célula calculada com formatação em trechos de texto exige revisão antes da escrita, pois alterar seu valor pode apagar esses trechos. Fórmulas dos campos manuais são preservadas pela expressão original; uma eventual atualização de seu resultado calculado é permitida, sem reescrever a fórmula.

## Pendências e escopo dos valores

Nas entradas atuais, 32 registros têm recomendação e contagens conclusivas para essa publicação; oito ficam retidos. Retidos não recebem zeros, não têm cálculos antigos apagados e não recebem novo carimbo de processamento.

Os valores de DSR e as recomendações usam o escopo descrito nas [regras de negócio](regras-de-negocio.md): faltas de junho a agosto e sequências de ciclos com trabalho na janela. Os descansos iniciais que dependem de maio continuam sinalizados na camada analítica. A conclusão da recomendação nesse escopo não torna o desconto financeiro integral calculável.

Os oito casos retidos devem ser tratados na revisão de qualidade. O relatório da execução lista seus IDs e motivos. Se uma linha já tiver resultado antigo, a data anterior continua indicando que ela não foi atualizada nesta rodada; a automação não inventa uma recomendação para substituir dados inconclusivos.

## Executar

Prévia, com leitura de BigQuery e Sheets, **sem escrever**:

```bash
uv run demarco sheets-sync
```

Aplicar e conferir:

```bash
uv run demarco sheets-sync --execute
```

A execução com `--execute` reconstrói o plano com os dados atuais; não aplica um arquivo de prévia antigo. Os comandos exigem conexão e credenciais, inclusive a prévia. Para outro ambiente ou pasta de relatórios, usar `--env-file` e `--output-dir`.

## Reexecução e data de processamento

Se os três valores de negócio já coincidirem e houver data de processamento, a linha é considerada atualizada: não há escrita nem mudança da data. Na primeira carga, ou quando houver mudança de negócio, o carimbo é gerado em ISO 8601 no fuso `America/Sao_Paulo`.

Uma reexecução sem mudanças retorna `NO_CHANGES` e não envia um segundo lote. Ela ainda lê as fontes e registra a conferência em uma nova pasta de execução.

## Backups e evidências

Cada rodada usa um diretório exclusivo em `artifacts/reverse-etl/`, com acesso local restrito. Arquivos JSON são criados com permissão `0600`, sem sobrescrever backups anteriores. A pasta é ignorada pelo Git.

| Arquivo | Conteúdo |
| --- | --- |
| `snapshot-before.json` | Aba antes da execução, com conteúdo digitado e metadados protegidos |
| `source.sql` | SQL efetivamente enviado ao BigQuery |
| `source-result.json` | Job do BigQuery e registros que alimentam a gestão |
| `plan.json` | Diferenças por ID/célula, registros retidos e assinatura da referência |
| `requests.json` | Lote restrito às células calculadas |
| `snapshot-preflight.json` | Nova leitura imediatamente antes da escrita |
| `batch-response.json` | Resposta da escrita, quando houver |
| `snapshot-after.json` | Aba após a escrita, quando houver |
| `report.json` | Estado final, contagens, verificação e eventual erro |

O estado protegido inclui valores digitados, fórmulas, formatos, notas, validações, trechos de texto e posições dos IDs. Apenas os valores das células explicitamente previstas para mudança são excluídos dessa comparação. Resultados derivados de fórmulas não entram na assinatura, pois podem recalcular legitimamente.

## Falhas e concorrência

`UPDATED_AND_VERIFIED` só é informado quando a API respondeu e a comparação posterior passou. Falhas de acesso ou estrutura anteriores ao lote não escrevem células. Se a chamada de escrita sofrer um timeout ou outro erro sem confirmação, a execução não assume que nada foi aplicado: grava `WRITE_NOT_CONFIRMED` e mantém as evidências. Se a conferência posterior falhar, o estado indica que a escrita aguardava validação.

Não há restauração automática de notas ou da aba inteira, pois isso poderia sobrescrever uma edição recente do gestor. Uma alteração detectada antes da escrita retorna `ABORTED_CONCURRENT_CHANGE` e exige regenerar o plano.

A API não fornece nesta implementação um bloqueio de edição estrutural entre a última leitura e o lote. Evitar ordenar/inserir/remover linhas nesse curto intervalo; a conferência posterior detecta divergências, mas não constitui uma trava de concorrência. A máscara de campos mantém as anotações manuais fora de todas as requisições de escrita.

## Código e testes

- `src/demarco/sheets.py`: autenticação e acesso à API.
- `src/demarco/reverse_etl.py`: leitura, validação, plano, lista de escrita e comparação.
- `src/demarco/sheets_cli.py`: execução, backups e relatório.
- `sql/11_reverse_etl_source.sql`: contrato da consulta de origem.
- `tests/test_reverse_etl.py`: preservação de campos e linhas retidas, reordenação, fórmulas, validações, falhas, backups privados, prévia e reexecução.

Testes locais não dependem de rede. Na verificação real foram preservadas sete datas de conversa, nove registros preenchidos de advertência e dez observações, além dos demais campos protegidos. A comprovação usa comparação de conteúdo e metadados, não apenas contagem de células.

As evidências locais da escrita estão em `artifacts/reverse-etl/20261029T223129-e726d840e6ed/`; a reexecução sem mudanças está em `artifacts/reverse-etl/20261029T223201-316646dfb04c/`. Os backups e relatórios permanecem ignorados pelo Git. O arquivo `report.json` de cada rodada registra seu estado final, a consulta de origem e as verificações.
