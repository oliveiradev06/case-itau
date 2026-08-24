# Case PLD — Estágio em Engenharia de IA

Mini-sistema de triagem para Prevenção à Lavagem de Dinheiro (PLD): **regras determinísticas em pandas** detectam padrões suspeitos nas operações, e um **LLM** redige o parecer de risco dos clientes sinalizados — cada um no seu papel (cálculo é pandas; interpretação e redação são do modelo).

> Dados 100% fictícios, fornecidos pelo desafio.

## Como rodar

```bash
pip install -r requirements.txt
copy .env.example .env   # e preencha LLM_API_KEY com a sua chave (Gemini ou Groq)
```

A chave de API vive **apenas** no `.env` local (ignorado pelo git). O provedor é intercambiável: Gemini (padrão) ou Groq, trocando três variáveis no `.env` — o código usa o endpoint compatível com OpenAI de ambos.

- **Nível 1:** abrir `nivel_1/nivel_1.ipynb` (já commitado com as saídas executadas).
- **Nível 2:** instruções serão adicionadas junto com os módulos.

## Estrutura

```
├── dados/          # arquivos originais do desafio
├── nivel_1/        # notebook: limpeza, regras e primeira análise com LLM
├── nivel_2/        # regras em escala, ferramentas, agente e confronto
├── outputs/        # resultados salvos das execuções
├── docs/           # DECISOES.md e USO_DE_IA.md
└── ENTREGA.yaml    # autodeclaração honesta do que foi feito
```

## Conclusões

*(preenchido ao final do desenvolvimento)*
