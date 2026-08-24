# Decisões de projeto

Documento vivo — registra trade-offs, interpretações do enunciado e limitações, na ordem em que as decisões foram tomadas.

## Limpeza de dados (Nível 1)

Diagnóstico antes de qualquer tratamento revelou três problemas plantados. Para cada um, a decisão e o porquê:

**1. Registro duplicado (OP-0007 aparece 2×, idêntico em todos os campos).**
Removi a cópia (`drop_duplicates`). Mesmo `id` e mesmo conteúdo indicam reprocessamento do sistema legado, não duas operações reais. Essa decisão **muda o resultado da Regra 1**: com a duplicata, o CLI-A-3 somaria R$ 65.700 no dia 05/03 e seria sinalizado por fracionamento; sem ela, soma R$ 48.500 e fica (corretamente) fora. A validação no notebook demonstra os dois cenários.
*Alternativa considerada:* tratar como duas operações legítimas com id repetido — rejeitada porque todos os nove campos são idênticos; a chance de duas operações reais idênticas no mesmo dia com mesmo id é desprezível frente à hipótese de duplicação técnica.

**2. Data nula (OP-0017, observação "data nao capturada pelo sistema").**
Mantive a operação nas agregações de volume e canal, e a excluí **apenas** das regras que dependem de data (Regra 1). A operação aconteceu — o valor é real e deve contar no volume do cliente; só a data é desconhecida.
*Alternativa considerada:* descartar a linha — rejeitada porque jogaria fora R$ 4.300 de volume real e mascararia um depósito em espécie, justamente o tipo de operação que PLD mais observa.

**3. Moeda estrangeira (OP-0013, US$ 12.000).**
Converti para BRL com a taxa fixa fornecida no próprio arquivo (5.4), em coluna nova `valor_brl`, preservando `valor` e `moeda` originais para auditoria. Sem a conversão, a operação (R$ 64.800) passaria despercebida pela Regra 2 — convertida, ela é 11,9× a mediana do CLI-A-4.

## Interpretações do enunciado

- **Regra 2 — mediana:** calculada sobre **todas** as operações do cliente em BRL, incluindo a própria operação avaliada. Testei a alternativa (excluir a operação da mediana): no dataset do Nível 1 o resultado é o mesmo; mantive a forma mais simples e documentei aqui.
- **Regras dependentes de data ignoram operações com data nula** (não há como agrupá-las por dia). Elas seguem contando para volume, canal e mediana.
- **Flags no DataFrame:** `flag_fracionamento` marca cada operação que participa de um grupo (cliente, dia) enquadrado na Regra 1; `flag_valor_atipico` marca a operação individual que dispara a Regra 2.

## Nível 2 — critério de "clientes mais sinalizados"

O enunciado pede o top-10 "ordenados pelo número de sinalizações, com o volume total como critério de desempate", mas não define o que conta como uma sinalização. Testei dois critérios:

- **Dias de fracionamento + operações atípicas:** cada dia enquadrado na Regra 1 vale 1. Resultado ruim na prática: os quatro clientes com fracionamento (CLI-002, CLI-003, CLI-017, CLI-029) empatam com quem teve **um único** outlier, e CLI-002 e CLI-003 **caem para fora do top-10** no desempate por volume — os dois casos mais graves da base ficariam sem parecer.
- **Operações sinalizadas (critério adotado):** as flags são atribuídas a operações (como pede o Nível 1), então conto operações sinalizadas por qualquer regra. Um dia de fracionamento com 4 operações coordenadas vale 4 — o padrão orquestrado pesa mais que um outlier isolado, que é como uma mesa de PLD priorizaria.

Com o critério adotado, o top-10 abre com os 4 fracionamentos (CLI-029, CLI-017, CLI-002, CLI-003), seguidos de CLI-014 (3 outliers) e dos clientes com 2 outliers. **Limitação honesta:** o corte em 10 deixa de fora o CLI-001 (11º), que tem um outlier de 15,6× a mediana — numa operação real, o tamanho do lote seria dimensionado pela capacidade da mesa, não por um número fixo.

## Reuso do Nível 1 no Nível 2

As regras nasceram como funções puras no notebook e migraram para `nivel_2/regras.py` sem mudança de lógica — só parametrizei o caminho do arquivo. O que eu faria diferente desde o começo: criar o módulo primeiro e fazer o notebook importar dele (uma única fonte de verdade); mantive a duplicação porque o enunciado pede o notebook autocontido com saídas, e sincronizar os dois manualmente por 24h é risco menor que reestruturar no meio.

## Stack e arquitetura

- **Cliente LLM via endpoint compatível com OpenAI** (SDK `openai` + `base_url` no `.env`): Gemini e Groq expõem o mesmo contrato, então trocar de provedor é editar três variáveis — nenhuma linha de código muda. Escolhido para não acoplar o case a um fornecedor e respeitar a restrição de camada gratuita.
- **Segurança da chave:** `.env` no `.gitignore` desde o primeiro commit; `.env.example` documenta as variáveis sem valores.

## Limitações conhecidas

*(preenchido conforme o desenvolvimento avança)*

## O que faria com mais tempo

*(preenchido ao final)*
