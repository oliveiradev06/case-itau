# -*- coding: utf-8 -*-
"""Agente de parecer PLD (Nível 2, Partes B e C).

Feito "na mão" com o SDK openai (endpoint compatível: Gemini ou Groq via .env):
o modelo DECIDE quais ferramentas de tools.py chamar para cada cliente — o
loop apenas executa o que ele pedir e devolve o resultado. Executar como
script roda o lote dos 10 clientes da Parte A e salva tudo em outputs/.

Separação regra × LLM: todo número vem das ferramentas (pandas). O modelo
interpreta e redige o parecer estruturado; ele é instruído a não calcular.
"""
from pathlib import Path
import json
import os
import time

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

import regras
import tools

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "outputs"
ARQ_PARECERES = SAIDA / "nivel2_pareceres.jsonl"

MAX_RODADAS_FERRAMENTA = 6   # limite de idas e vindas de tool calls por cliente
MAX_TENTATIVAS_JSON = 2      # re-tentativas se o parecer vier malformado
PAUSA_ENTRE_CLIENTES_S = 8   # respeita o rate limit da camada gratuita (~10 req/min)

# Preços de referência do tier PAGO do modelo default (USD por 1M tokens), só para
# estimar custo; na camada gratuita o custo real é zero.
PRECO_ENTRADA_USD_1M = 0.30
PRECO_SAIDA_USD_1M = 2.50

NIVEIS_VALIDOS = {"baixo", "medio", "alto"}

PROMPT_SISTEMA = """Você é um analista sênior de Prevenção à Lavagem de Dinheiro (PLD) de um banco.
Sua tarefa: emitir um parecer de risco sobre UM cliente, baseado APENAS em dados
consultados pelas ferramentas disponíveis.

Regras de trabalho:
1. Você NÃO faz cálculos. Todos os números (somas, medianas, percentuais) já vêm
   prontos das ferramentas. Seu papel é interpretar e redigir.
2. Decida quais ferramentas usar conforme o caso — nem toda ferramenta é útil para
   todo cliente. Comece pelo histórico; aprofunde só no que os dados indicarem
   (ex.: um dia de possível fracionamento merece o detalhe daquele dia; um outlier
   pode pedir o perfil de canal). Não chame ferramentas de que não precisa.
3. As regras determinísticas do banco são propositalmente simples e podem gerar
   falsos positivos. Você pode discordar delas — desde que justifique com os dados.
4. Ao final, responda SOMENTE com um JSON válido, sem markdown, neste formato:
{"nivel_risco": "baixo|medio|alto",
 "tipologia_suspeita": "descrição curta da tipologia (ou 'nenhuma identificada')",
 "red_flags": ["lista", "de", "indícios"],
 "justificativa": "parágrafo objetivo citando os números consultados",
 "ferramentas_relevantes": ["quais consultas embasaram o parecer"]}"""


def _cliente() -> OpenAI:
    load_dotenv(RAIZ / ".env")
    chave = os.environ.get("LLM_API_KEY", "").strip()
    if not chave:
        raise SystemExit(
            "LLM_API_KEY vazia no .env — crie a chave (Gemini ou Groq) e preencha o arquivo."
        )
    return OpenAI(api_key=chave, base_url=os.environ["LLM_BASE_URL"])


def _modelo() -> str:
    return os.environ.get("LLM_MODEL", "gemini-2.5-flash")


def _chamar_com_retry(client: OpenAI, **kwargs):
    """Chamada com backoff simples para o rate limit da camada gratuita (HTTP 429)."""
    for tentativa in range(4):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:  # 429 / 5xx transitórios
            transitorio = "429" in str(exc) or "rate" in str(exc).lower() or "503" in str(exc)
            if not transitorio or tentativa == 3:
                raise
            espera = 20 * (tentativa + 1)
            print(f"    rate limit/erro transitório; aguardando {espera}s…")
            time.sleep(espera)


def _validar_parecer(texto: str) -> tuple[dict | None, str | None]:
    """Valida o JSON do parecer. Devolve (parecer, None) ou (None, motivo do erro)."""
    texto = texto.strip()
    if texto.startswith("```"):  # modelo insistiu em cercar com markdown
        texto = texto.strip("`")
        texto = texto[texto.find("{"): texto.rfind("}") + 1]
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as exc:
        return None, f"JSON inválido: {exc}"
    obrigatorios = {"nivel_risco", "tipologia_suspeita", "red_flags", "justificativa"}
    faltando = obrigatorios - dados.keys()
    if faltando:
        return None, f"campos ausentes: {sorted(faltando)}"
    if dados["nivel_risco"] not in NIVEIS_VALIDOS:
        return None, f"nivel_risco inválido: {dados['nivel_risco']!r} (use baixo/medio/alto)"
    if not isinstance(dados["red_flags"], list):
        return None, "red_flags deve ser uma lista"
    return dados, None


def analisar_cliente(client: OpenAI, cliente_id: str) -> dict:
    """Roda o loop agêntico para um cliente e devolve o registro completo
    (parecer + ferramentas usadas + tokens + latência + custo estimado)."""
    mensagens = [
        {"role": "system", "content": PROMPT_SISTEMA},
        {"role": "user", "content": f"Emita o parecer de risco do cliente {cliente_id}."},
    ]
    ferramentas_usadas: list[dict] = []
    tokens_entrada = tokens_saida = chamadas_llm = 0
    inicio = time.perf_counter()

    for _ in range(MAX_RODADAS_FERRAMENTA):
        resposta = _chamar_com_retry(
            client, model=_modelo(), messages=mensagens,
            tools=tools.SCHEMAS_OPENAI, tool_choice="auto",
        )
        chamadas_llm += 1
        uso = resposta.usage
        tokens_entrada += uso.prompt_tokens
        tokens_saida += uso.completion_tokens
        escolha = resposta.choices[0].message

        if not escolha.tool_calls:  # o modelo decidiu concluir
            mensagens.append({"role": "assistant", "content": escolha.content})
            break

        mensagens.append(escolha.model_dump(exclude_none=True))
        for chamada in escolha.tool_calls:
            nome = chamada.function.name
            args = json.loads(chamada.function.arguments or "{}")
            funcao = tools.FERRAMENTAS.get(nome)
            resultado = funcao(**args) if funcao else {"erro": f"ferramenta desconhecida: {nome}"}
            ferramentas_usadas.append({"ferramenta": nome, "argumentos": args})
            mensagens.append({
                "role": "tool", "tool_call_id": chamada.id,
                "content": json.dumps(resultado, ensure_ascii=False),
            })

    # validação do parecer, com re-tentativa corretiva se vier malformado
    parecer, erro = _validar_parecer(escolha.content or "")
    tentativas_validacao = 1
    while parecer is None and tentativas_validacao <= MAX_TENTATIVAS_JSON:
        mensagens.append({
            "role": "user",
            "content": f"Sua resposta anterior falhou na validação ({erro}). "
                       "Reenvie SOMENTE o JSON do parecer, corrigido, sem nenhum outro texto.",
        })
        resposta = _chamar_com_retry(client, model=_modelo(), messages=mensagens)
        chamadas_llm += 1
        tokens_entrada += resposta.usage.prompt_tokens
        tokens_saida += resposta.usage.completion_tokens
        parecer, erro = _validar_parecer(resposta.choices[0].message.content or "")
        tentativas_validacao += 1

    latencia = round(time.perf_counter() - inicio, 2)
    custo = tokens_entrada / 1e6 * PRECO_ENTRADA_USD_1M + tokens_saida / 1e6 * PRECO_SAIDA_USD_1M
    return {
        "cliente_id": cliente_id,
        "parecer": parecer,                       # None = falhou mesmo após re-tentativas
        "erro_validacao": None if parecer else erro,
        "ferramentas_usadas": ferramentas_usadas,
        "chamadas_llm": chamadas_llm,
        "tokens_entrada": tokens_entrada,
        "tokens_saida": tokens_saida,
        "custo_estimado_usd": round(custo, 6),    # tier pago de referência; free tier = $0
        "latencia_s": latencia,
        "modelo": _modelo(),
    }


def _ja_analisados() -> set[str]:
    """Cache simples e retomável: clientes já presentes no JSONL não são re-analisados
    (protege contra estouro de cota da camada gratuita no meio do lote)."""
    if not ARQ_PARECERES.exists():
        return set()
    with open(ARQ_PARECERES, encoding="utf-8") as f:
        return {json.loads(linha)["cliente_id"] for linha in f if linha.strip()}


def rodar_lote() -> None:
    base = regras.preparar_base(RAIZ / "dados" / "dados_nivel_2.json")
    top10 = regras.top_sinalizados(regras.resumo_por_cliente(base), 10)
    client = _cliente()
    SAIDA.mkdir(exist_ok=True)

    prontos = _ja_analisados()
    print(f"Lote: {len(top10)} clientes | já analisados (cache): {len(prontos)}")

    for cliente_id in top10.index:
        if cliente_id in prontos:
            print(f"  {cliente_id}: cache — pulando")
            continue
        print(f"  {cliente_id}: analisando…")
        registro = analisar_cliente(client, cliente_id)
        with open(ARQ_PARECERES, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        situacao = registro["parecer"]["nivel_risco"] if registro["parecer"] else "FALHA DE VALIDAÇÃO"
        print(f"    risco={situacao} | ferramentas={len(registro['ferramentas_usadas'])} "
              f"| {registro['tokens_entrada']}+{registro['tokens_saida']} tokens "
              f"| {registro['latencia_s']}s")
        time.sleep(PAUSA_ENTRE_CLIENTES_S)

    # análise dos totais com pandas (custo e latência), salva em outputs/
    registros = [json.loads(l) for l in open(ARQ_PARECERES, encoding="utf-8") if l.strip()]
    resumo = pd.DataFrame([{
        "cliente_id": r["cliente_id"],
        "nivel_risco_agente": (r["parecer"] or {}).get("nivel_risco"),
        "ferramentas_chamadas": len(r["ferramentas_usadas"]),
        "chamadas_llm": r["chamadas_llm"],
        "tokens_entrada": r["tokens_entrada"],
        "tokens_saida": r["tokens_saida"],
        "custo_estimado_usd": r["custo_estimado_usd"],
        "latencia_s": r["latencia_s"],
    } for r in registros])
    resumo.to_csv(SAIDA / "nivel2_lote_resumo.csv", index=False)

    print("\nTotais do lote (pandas):")
    print(resumo[["tokens_entrada", "tokens_saida", "custo_estimado_usd", "latencia_s"]]
          .agg(["sum", "mean"]).round(4).to_string())
    print(f"\nPareceres: {ARQ_PARECERES}")
    print(f"Resumo:    {SAIDA / 'nivel2_lote_resumo.csv'}")


if __name__ == "__main__":
    rodar_lote()
