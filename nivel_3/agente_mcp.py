# -*- coding: utf-8 -*-
"""Nível 3 — Trilha B: o agente consumindo as ferramentas VIA MCP (não por import).

Diferença estrutural em relação ao nivel_2/agente.py:
- lá, as ferramentas são funções Python importadas;
- aqui, o agente abre uma sessão MCP com o servidor (nivel_3/servidor_mcp.py,
  spawnado via stdio), DESCOBRE as ferramentas com list_tools() e as executa
  com call_tool() — o mesmo mecanismo que um cliente MCP genérico usaria.

O loop de decisão, o prompt e a validação do parecer são REUTILIZADOS do
Nível 2 (import), provando que só o transporte das ferramentas mudou.

Uso (demonstração com um cliente do lote):
    python nivel_3/agente_mcp.py [CLI-002]
"""
import asyncio
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "nivel_2"))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import agente as agente_nivel2  # reuso: prompt, validação, cliente LLM

SERVIDOR = StdioServerParameters(
    command=sys.executable,
    args=[str(RAIZ / "nivel_3" / "servidor_mcp.py")],
)


def _schema_openai(tool) -> dict:
    """Converte a ferramenta descoberta via MCP para o formato de tools da OpenAI."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema,
        },
    }


def _texto_do_resultado(resultado) -> str:
    """Extrai o conteúdo devolvido pelo call_tool (estruturado ou texto)."""
    if getattr(resultado, "structuredContent", None):
        return json.dumps(resultado.structuredContent, ensure_ascii=False)
    partes = [c.text for c in resultado.content if getattr(c, "text", None)]
    return "\n".join(partes) if partes else "{}"


async def analisar_via_mcp(cliente_id: str) -> dict:
    llm = agente_nivel2._cliente()
    modelo = agente_nivel2._modelo()

    async with stdio_client(SERVIDOR) as (leitura, escrita):
        async with ClientSession(leitura, escrita) as sessao:
            await sessao.initialize()
            descobertas = (await sessao.list_tools()).tools
            schemas = [_schema_openai(t) for t in descobertas]
            print(f"ferramentas descobertas via MCP: {[t.name for t in descobertas]}")

            mensagens = [
                {"role": "system", "content": agente_nivel2.PROMPT_SISTEMA},
                {"role": "user", "content": f"Emita o parecer de risco do cliente {cliente_id}."},
            ]
            usadas, tokens_in, tokens_out = [], 0, 0
            inicio = time.perf_counter()

            for _ in range(agente_nivel2.MAX_RODADAS_FERRAMENTA):
                resposta = agente_nivel2._chamar_com_retry(
                    llm, model=modelo, messages=mensagens,
                    tools=schemas, tool_choice="auto",
                )
                tokens_in += resposta.usage.prompt_tokens
                tokens_out += resposta.usage.completion_tokens
                escolha = resposta.choices[0].message

                if not escolha.tool_calls:
                    mensagens.append({"role": "assistant", "content": escolha.content})
                    break

                mensagens.append(escolha.model_dump(exclude_none=True))
                for chamada in escolha.tool_calls:
                    args = json.loads(chamada.function.arguments or "{}")
                    resultado = await sessao.call_tool(chamada.function.name, args)
                    usadas.append({"ferramenta": chamada.function.name, "argumentos": args})
                    mensagens.append({
                        "role": "tool", "tool_call_id": chamada.id,
                        "content": _texto_do_resultado(resultado),
                    })

            parecer, erro = agente_nivel2._validar_parecer(escolha.content or "")
            return {
                "cliente_id": cliente_id,
                "transporte": "mcp/stdio",
                "parecer": parecer,
                "erro_validacao": erro,
                "ferramentas_usadas": usadas,
                "tokens_entrada": tokens_in,
                "tokens_saida": tokens_out,
                "latencia_s": round(time.perf_counter() - inicio, 2),
                "modelo": modelo,
            }


def main() -> None:
    cliente_id = sys.argv[1] if len(sys.argv) > 1 else "CLI-002"
    registro = asyncio.run(analisar_via_mcp(cliente_id))

    saida = RAIZ / "outputs" / "nivel3_parecer_mcp.json"
    # comparação com o parecer do mesmo cliente obtido por import direto (Nível 2)
    arq_n2 = RAIZ / "outputs" / "nivel2_pareceres.jsonl"
    if arq_n2.exists():
        for linha in open(arq_n2, encoding="utf-8"):
            r = json.loads(linha)
            if r["cliente_id"] == cliente_id:
                registro["comparacao_com_import_direto"] = {
                    "nivel_risco_nivel2": (r["parecer"] or {}).get("nivel_risco"),
                    "nivel_risco_mcp": (registro["parecer"] or {}).get("nivel_risco"),
                    "ferramentas_nivel2": [f["ferramenta"] for f in r["ferramentas_usadas"]],
                    "ferramentas_mcp": [f["ferramenta"] for f in registro["ferramentas_usadas"]],
                }
                break

    saida.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(registro.get("comparacao_com_import_direto", {}), ensure_ascii=False, indent=2))
    print(f"risco={registro['parecer']['nivel_risco'] if registro['parecer'] else 'FALHA'}")
    print(f"salvo em {saida}")


if __name__ == "__main__":
    main()
