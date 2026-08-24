# Case PLD — Estágio em Engenharia de IA

Mini-sistema de triagem para Prevenção à Lavagem de Dinheiro (PLD): **regras determinísticas em pandas** detectam padrões suspeitos nas operações, e um **LLM** redige o parecer de risco dos clientes sinalizados — cada um no seu papel (**cálculo é pandas; interpretação e redação são do modelo**).

> Dados 100% fictícios, fornecidos pelo desafio.

## Como rodar

```bash
pip install -r requirements.txt
copy .env.example .env   # e preencha LLM_API_KEY com a sua chave
```

A chave de API vive **apenas** no `.env` local (ignorado pelo git). O provedor é intercambiável trocando três variáveis no `.env` — o código fala com o endpoint compatível com OpenAI de qualquer um deles. Usado na entrega: **Groq** com `openai/gpt-oss-120b` (camada gratuita).

| O quê | Comando |
|---|---|
| **Nível 1** (limpeza, regras, parecer LLM) | abrir `nivel_1/nivel_1.ipynb` — já commitado **com as saídas executadas**; para reproduzir: `jupyter lab` → Run All |
| **Nível 2A** — regras em escala + top-10 | `python nivel_2/regras.py` |
| **Nível 2B/C** — agente + lote dos 10 clientes | `python nivel_2/agente.py` (retomável: clientes já analisados não são re-processados) |
| **Nível 2D** — confronto regra × agente | `python nivel_2/confronto.py` |
| **Nível 3** — agente consumindo ferramentas via MCP | `python nivel_3/agente_mcp.py CLI-002` |

Os resultados de todas as execuções estão commitados em `outputs/`.

### Nível 3 — como conectar ao servidor MCP

O servidor (`nivel_3/servidor_mcp.py`) fala MCP por **stdio**: quem consome é que o inicia. O
`agente_mcp.py` já faz isso sozinho; para conectar qualquer outro cliente MCP (Claude Desktop,
IDEs, inspetores), configure:

```json
{
  "mcpServers": {
    "pld-tools": {
      "command": "python",
      "args": ["<caminho-do-repo>/nivel_3/servidor_mcp.py"]
    }
  }
}
```

As três ferramentas (`historico_cliente`, `operacoes_do_dia`, `perfil_canal`) são descobertas
automaticamente via `list_tools` — mesmas funções do Nível 2, sem nenhuma alteração.

## Estrutura

```
├── dados/          # arquivos originais do desafio
├── nivel_1/        # notebook: limpeza, regras, validação e Parte B com LLM
├── nivel_2/        # regras.py (escala), tools.py, agente.py, confronto.py
├── outputs/        # pareceres, top-10, confronto e métricas de custo/latência
├── docs/           # DECISOES.md (trade-offs) e USO_DE_IA.md
└── ENTREGA.yaml    # autodeclaração honesta do que foi feito
```

## O que concluí

1. **A limpeza muda o veredito.** Os dados trazem duplicatas exatas, datas nulas e valores em USD plantados. Sem deduplicar, o CLI-A-3 seria acusado de fracionamento por uma operação contada duas vezes (R$ 65,7 mil "somados" vs R$ 48,5 mil reais); sem converter moeda, a remessa de US$ 12 mil do CLI-A-4 (11,9× a mediana dele) passaria despercebida. O notebook demonstra os dois cenários.

2. **Na base maior, as regras pegam 4 fracionamentos e 21 valores atípicos** (317 operações limpas, 30 clientes) — e nenhum cliente cai nas duas regras ao mesmo tempo, o que já antecipa que elas medem coisas diferentes.

3. **O agente decide de verdade:** nos 4 clientes com fracionamento ele consultou o detalhe do dia suspeito; nos 6 com outliers, pulou essa ferramenta e foi ao perfil de canal. Lote completo: ~42 mil tokens, custo estimado de US$ 0,011 no tier pago de referência (real: R$ 0, camada gratuita), latência média de 15,4s/cliente.

4. **Confronto: 30% de concordância exata — e isso é informação, não defeito.** O agente moderou 7 dos 10 "altos" das regras; em 3 divergências a leitura dele é melhor que a da regra (que ignora, por exemplo, a direção das operações), e em 1 (CLI-029, "baixo" para 4 operações coladas no limite de R$ 20 mil) a regra tinha razão. Detalhe decisivo: **dois pareceres citam números errados** — reforçando a tese do case de que LLM interpreta e redige, mas todo número precisa nascer (e ser conferido) em código. Análise completa em [`docs/DECISOES.md`](docs/DECISOES.md).
