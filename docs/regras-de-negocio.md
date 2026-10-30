# Regras de negócio e modelo de dados

As regras abaixo implementam o cenário sintético de junho a agosto de 2025. As decisões para dados ambíguos são explícitas; totais confirmados e componentes inconclusivos permanecem separados.

## Camadas e rastreabilidade

| Camada | Grão e responsabilidade |
| --- | --- |
| `raw_colaboradores`, `raw_escalas`, `raw_ponto`, `raw_gestao` | Linhas recebidas, com arquivo, aba, linha, hash e `_raw_json` |
| `stg_*` | Tipos normalizados, correções sinalizadas e duplicatas exatas de ponto removidas |
| `dim_colaboradores`, `dim_escalas` | Uma linha por ID/escala; atributos consensuais e calendário suportado |
| `int_calendario_colaborador`, `int_ponto_dia` | Calendário no vínculo e observações consolidadas por ID/data |
| `fct_ausencias_diarias` | ID/data; ausências, abonos, excedentes e pendências |
| `qa_ausencias_diarias` | ID/data/motivo; motivos podem se sobrepor |
| `qa_ponto_sem_chave_periodo` | Linhas sem chave/data válida ou fora da janela |
| `int_descansos_contratuais`, `fct_dsr_ciclos`, `fct_dsr_diario` | Calendário de descansos, ciclos semanais e perdas por descanso |
| `fct_impacto_diario`, `mart_impacto_mensal` | Componentes monetários por ID/data e ID/mês |
| `mart_gestao_colaboradores` | Uma linha por colaborador com vínculo no trimestre; recomendação e elegibilidade de atualização |
| `vw_dashboard_*` | Fontes planas para diário, gestão e qualidade, mantendo seus grãos separados |

A ingestão preserva os valores e tipos originais no JSON de origem; as colunas brutas do BigQuery são textuais. Os XLSX e `raw_*` não são corrigidos em lugar. As funções SQL compartilhadas estão em [`sql/functions/`](../sql/functions/).

## Saneamento, identidade e salário

- IDs são normalizados por espaços e caixa; nomes não são chaves.
- Datas ISO, brasileiras e seriais Excel são convertidas explicitamente. Nulos textuais e números decimais são tratados sem preencher valores inválidos com zero.
- Repetições exatas do ponto são removidas, mantendo contagem e origem. Versões conflitantes na mesma chave não são somadas nem resolvidas por ordem de chegada.
- Na dimensão cadastral, um atributo só é conservado quando as versões concordam, inclusive quanto a nulo versus preenchido. Nome, escala ou vínculo conflitante impedem confirmar ausências. Um problema exclusivamente salarial impede a valorização financeira, preservando frequência confiável.
- Salário ausente, não positivo, conflitante ou escrito como `A combinar` permanece nulo; não é estimado por cargo ou média. O salário é considerado constante no trimestre, pois não há histórico de alterações.

`EMP_019` tem dois nomes e salários distintos e concentra as dez chaves conflitantes de ponto. Suas datas ficam pendentes, sem escolher uma identidade arbitrariamente.

### Codificação

As fontes já continham textos como `Auxiliar de ProduÃ§Ã£o`. A função `repair_text` reconstrói a sequência UTF-8 interpretada como Latin-1 somente quando a reconversão estrita é válida. As 41 células afetadas foram corrigidas no staging: quatro nomes, 17 cargos, 18 departamentos e duas descrições de escala.

Texto com acento correto permanece intacto. Misturas incompatíveis e caracteres já substituídos por `�` não são reconstruídos. Campos `_codificacao_corrigida` sinalizam alterações; arquivo, linha e hash permitem compará-las com o bruto. `stg_gestao_referencia` preserva integralmente a referência de gestão, sem modificar os textos manuais.

## Período, vínculo e calendário

A janela é **01/06/2025 a 31/08/2025**, inclusive. Admissão e desligamento são inclusivos. O calendário é gerado apenas dentro do vínculo confiável. Observações fora dele continuam auditáveis e pendentes.

Quatro IDs sem ponto estavam desligados antes de junho e não recebem faltas fictícias. `EMP_051`, fora da gestão, possui sete registros de ponto fora do vínculo, já encerrado antes de junho; eles permanecem para auditoria, sem aumentar o quadro de 40 colaboradores do trimestre.

As escalas fixas 40h, 44h e 36h noturnas são suportadas. A 12x36 não tem data-base de alternância e não possui colaborador associado nas entradas atuais; não é inferido um calendário. Dois cadastros sem escala ficam pendentes.

| Exceção | Decisão implementada |
| --- | --- |
| Escala 44h soma 48,4h nos horários diários | Déficit calculado com a jornada diária válida; fórmula financeira usa 44h contratuais. A divergência permanece sinalizada. |
| Noturna descansa domingo e segunda, mas o ponto marca DSR só no domingo | Prevalece o descanso contratual. A divergência do flag é auditável. |
| DSR com jornada positiva ou flag de descanso em dia contratual de trabalho | Pendência bloqueante, sem correção automática. |
| Jornada zero e flag DSR zero em dia contratual de trabalho | Dispensa diária informada pela fonte; não aumenta jornada esperada, faltas ou descontos. |
| Dia previsto sem observação | Pendência de registro, inclusive em descansos; não comprova ausência nem trabalho. |

A dispensa aparece em 09/07 para 38 IDs com escala conhecida: 37 datas elegíveis e uma ainda bloqueada pelo cadastro conflitante. Não se presume feriado ou localidade. Outras divergências de jornada permanecem pendentes.

## Apuração diária

Para datas elegíveis:

```text
déficit = máximo(horas esperadas − horas trabalhadas, 0)
trabalho na jornada = mínimo(horas esperadas, horas trabalhadas)
excedente = máximo(horas trabalhadas − horas esperadas, 0)
horas esperadas = trabalho na jornada + horas abonadas + horas injustificadas
```

Excedentes não compensam ausências de outro dia. A fonte contém horas agregadas, sem batidas: um déficit parcial não distingue atraso de saída antecipada e não recebe tolerância inventada.

- **Falta integral injustificada:** jornada positiva, nenhum trabalho, sem abono aplicável e sem bloqueios.
- **Ausência parcial injustificada:** trabalho positivo abaixo da jornada, sem abono aplicável e sem bloqueios.
- **Presença:** jornada cumprida, com eventual excedente separado.
- **Folga/descanso:** jornada zero e nenhum trabalho; trabalho positivo é classificado como trabalho em descanso, sem estimar pagamento extra.

| Abono | Tratamento |
| --- | --- |
| `ATESTADO MEDICO` | Abona o déficit da data, por premissa; não é trabalho realizado nem se estende para outros dias. |
| `FOLGA_COMPENSATORIA` | Autoriza o déficit da data sem registrar trabalho fictício. |
| `DECLARACAO_HORAS` | Se há déficit, falta duração para decidir: a data fica pendente. Jornada cumprida não tem déficit a abonar. |
| Código desconhecido | Pendência para mapeamento. |

Horas ausentes, negativas ou acima de 24 ficam pendentes. Nas datas inconclusivas, medidas e flags confirmados são nulos. `deficit_horas_pendente` pode mostrar uma diferença observável, mas não comprova falta injustificada. Nulo significa desconhecido; zero significa valor validado sem déficit.

## DSR perdido e ciclos consecutivos

O gatilho é uma **falta integral injustificada confirmada**, não uma ausência parcial. O ciclo considera o trabalho contratual anterior ao descanso, com âncora no domingo:

| Escala | Trabalho antecedente | Descansos do ciclo |
| --- | --- | --- |
| 44h | Segunda a sábado | Domingo |
| 40h | Segunda a sexta | Domingo |
| 36h noturna | Terça a sábado | Domingo e segunda |

Uma falta integral comprovada basta para classificar o ciclo como perdido mesmo havendo outra data desconhecida. Sem falta comprovada e com lacuna, o ciclo é indeterminado. Identidade conflitante gera pendência cadastral. Uma base confiável sem faltas/lacunas preserva o descanso.

Cada descanso é contado uma vez. Várias faltas na semana não multiplicam o mesmo DSR. Na escala noturna, um ciclo perdido pode retirar dois descansos, mas representa **um único ciclo semanal**.

Consecutividade exige âncoras separadas por sete dias. Ciclo preservado, indeterminado ou fora do escopo quebra a sequência comprovada; domingo e segunda do mesmo ciclo não formam duas semanas consecutivas.

### Fronteiras e escopo disciplinar

Os descansos de 01/06 e, na noturna, 02/06 dependem de trabalho em maio, ausente nas fontes. São inconclusivos, sem presumir preservação ou perda. O domingo de 31/08 pode ser apurado com agosto; a segunda de 01/09 fica fora da cobrança do período.

A recomendação usa faltas de junho–agosto e sequências cujo trabalho antecedente está na janela. Assim, uma possível conduta de maio não gera medida disciplinar. Incertezas internas à janela tornam a recomendação incompleta. Essa convenção está em `escopo_recomendacao`; ela não elimina a incompletude financeira dos descansos iniciais.

## Valorização financeira

```text
Valor Hora = Salário Mensal / Divisor Contratual
Diária de DSR = Valor Hora × (Jornada Semanal Contratual / 6)
Desconto = Horas Injustificadas × Valor Hora + DSRs Perdidos × Diária de DSR
```

O cálculo usa `NUMERIC`, sem arredondar componentes diários/mensais antecipadamente. Formate a soma em moeda com duas casas. Rótulos de grupos arredondados separadamente podem diferir um centavo da soma calculada antes do arredondamento.

Salário/divisor inválido e componentes inconclusivos não recebem preço artificial. Um componente comprovadamente zero pode ser zero mesmo sem salário. Frequência totalmente pendente ou perdas positivas sem preço e sem parcela positiva conhecida não recebem estimativa zero no resumo.

| Campo | Interpretação |
| --- | --- |
| `desconto_estimado_confirmado` | Subtotal conhecido com os dados disponíveis |
| `desconto_total_periodo` | Total apenas quando todos os componentes forem calculáveis |
| `financeiro_incompleto` | Há lacunas de frequência, salário, calendário ou DSR |
| `dsrs_indeterminados`, `dsrs_com_fronteira` | Descansos enumeráveis sem conclusão e subconjunto dependente da fronteira |
| `apuracao_dsr_indisponivel` | Nem o calendário permite enumerar descansos, como na falta de escala |

O subtotal de **R$ 7.087,90** é parcial. Os 40 totais financeiros integrais permanecem nulos por fronteiras e/ou outras insuficiências. O valor não equivale ao custo total do absenteísmo: as fontes não demonstram substituições, encargos ou extras pagos. As fórmulas e recomendações reproduzem a especificação do cenário.

## Política disciplinar e atualização

Aplica-se primeiro a condição de maior gravidade:

| Evidência no escopo | Recomendação exata |
| --- | --- |
| 4+ faltas integrais **ou** 2+ ciclos perdidos consecutivos | `Suspensão Disciplinar (1 a 3 dias)` |
| 2–3 faltas integrais | `Advertência Escrita` |
| 1 falta integral | `Alinhamento em 1-on-1` |
| Nenhuma falta integral, com base conclusiva | `Sem ação requerida` |

Ausências parciais não aumentam a contagem de faltas integrais. Dados incompletos mantêm a recomendação nula, salvo quando o nível máximo já está comprovado. Esse último caso é sinalizado como suspensão comprovada com pendências.

`COMPLETA_NO_ESCOPO` qualifica o escopo disciplinar, não a completude financeira de todo o trimestre. `elegivel_reverse_etl` exige ação e contagens conclusivas para publicar conjuntamente os campos de gestão. Assim, a suspensão comprovada com contagens pendentes continua retida.

Há 32 colaboradores elegíveis e oito retidos. Sete ações estão pendentes; o oitavo retido tem suspensão já comprovada, mas contagens incompletas. A [atualização da planilha](reverse-etl.md) preserva esses casos e o histórico manual.

## Indicadores do dashboard

- Taxas são razões entre **somas de numeradores e denominadores válidos**, nunca médias simples de taxas.
- Taxa injustificada: horas injustificadas / horas previstas validadas. Taxa total de horas ausentes inclui abonadas + injustificadas no numerador.
- Taxa de dias de falta: faltas integrais / dias de trabalho válidos; descansos não entram como oportunidade de falta.
- Cobertura: linhas elegíveis / linhas observadas; não é percentual de pessoas sem problemas.
- Qualidade: contar `id_dia` distinto para os 288 dias; somar ocorrências para os 301 motivos sobrepostos.
- Denominador zero permanece nulo. Recomendações trimestrais não recebem filtro mensal.

Os [resultados e verificações](validacao.md) são reconciliados com o código e com as fórmulas do contrato em [`dashboard/report_spec.json`](../dashboard/report_spec.json).
