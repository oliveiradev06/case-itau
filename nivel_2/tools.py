# -*- coding: utf-8 -*-
"""Ferramentas que o agente pode chamar para consultar a base do Nível 2.

Princípio do case aplicado à risca: TODO número que sai daqui foi calculado
em pandas. O agente decide O QUE consultar e interpreta o resultado — nunca
calcula. Cada ferramenta devolve um dict serializável em JSON.
"""
from functools import lru_cache
from pathlib import Path

import pandas as pd

import regras

CAMINHO_BASE = Path(__file__).resolve().parent.parent / "dados" / "dados_nivel_2.json"


@lru_cache(maxsize=1)
def _base() -> pd.DataFrame:
    """Base do Nível 2 limpa e com as flags das regras (carregada uma única vez)."""
    return regras.preparar_base(CAMINHO_BASE)


def _fmt_data(ts) -> str | None:
    return None if pd.isna(ts) else ts.strftime("%Y-%m-%d")


def historico_cliente(cliente_id: str) -> dict:
    """Resumo agregado das operações do cliente: volumes, mediana, extremos,
    contrapartes e o resultado das regras determinísticas (dias de possível
    fracionamento e operações de valor atípico)."""
    ops = _base().query("cliente_id == @cliente_id")
    if ops.empty:
        return {"erro": f"cliente {cliente_id} não encontrado"}

    dias_fracionamento = sorted(
        _fmt_data(d) for d in ops.loc[ops["flag_fracionamento"], "data"].unique()
    )
    atipicas = ops.loc[
        ops["flag_valor_atipico"], ["id", "valor_brl", "tipo", "canal", "contraparte"]
    ]
    return {
        "cliente_id": cliente_id,
        "qtd_operacoes": int(len(ops)),
        "volume_total_brl": round(float(ops["valor_brl"].sum()), 2),
        "mediana_brl": round(float(ops["valor_brl"].median()), 2),
        "maior_operacao_brl": round(float(ops["valor_brl"].max()), 2),
        "periodo": [_fmt_data(ops["data"].min()), _fmt_data(ops["data"].max())],
        "operacoes_sem_data": int(ops["data"].isna().sum()),
        "operacoes_em_usd_convertidas": int((ops["moeda"] == "USD").sum()),
        "qtd_contrapartes_distintas": int(ops["contraparte"].nunique()),
        "tipos_de_operacao": ops["tipo"].value_counts().to_dict(),
        "regra_fracionamento_dias": dias_fracionamento,
        "regra_valor_atipico_operacoes": atipicas.round(2).to_dict(orient="records"),
    }


def operacoes_do_dia(cliente_id: str, data: str) -> dict:
    """Recorte detalhado de um dia específico do cliente (data em YYYY-MM-DD):
    lista de operações e totais do dia, já em BRL."""
    try:
        alvo = pd.Timestamp(data)
    except ValueError:
        return {"erro": f"data inválida: {data!r} (use YYYY-MM-DD)"}

    ops = _base().query("cliente_id == @cliente_id and data == @alvo")
    if ops.empty:
        return {"cliente_id": cliente_id, "data": data, "qtd_operacoes": 0, "operacoes": []}

    return {
        "cliente_id": cliente_id,
        "data": data,
        "qtd_operacoes": int(len(ops)),
        "soma_do_dia_brl": round(float(ops["valor_brl"].sum()), 2),
        "maior_operacao_brl": round(float(ops["valor_brl"].max()), 2),
        "operacoes": ops[["id", "valor_brl", "canal", "tipo", "contraparte"]]
        .round(2)
        .to_dict(orient="records"),
    }


def perfil_canal(cliente_id: str) -> dict:
    """Distribuição de uso por canal (pix, ted, boleto, cartão, espécie):
    quantidade de operações e volume em BRL por canal."""
    ops = _base().query("cliente_id == @cliente_id")
    if ops.empty:
        return {"erro": f"cliente {cliente_id} não encontrado"}

    por_canal = (
        ops.groupby("canal")
        .agg(qtd_operacoes=("id", "size"), volume_brl=("valor_brl", "sum"))
        .round(2)
    )
    volume_total = float(ops["valor_brl"].sum())
    perfil = {
        canal: {
            "qtd_operacoes": int(linha["qtd_operacoes"]),
            "volume_brl": float(linha["volume_brl"]),
            "pct_do_volume": round(100 * float(linha["volume_brl"]) / volume_total, 1),
        }
        for canal, linha in por_canal.iterrows()
    }
    especie = perfil.get("especie", {}).get("pct_do_volume", 0.0)
    return {"cliente_id": cliente_id, "por_canal": perfil, "pct_volume_em_especie": especie}


# Registro usado pelo agente: schema OpenAI de cada ferramenta
FERRAMENTAS = {
    "historico_cliente": historico_cliente,
    "operacoes_do_dia": operacoes_do_dia,
    "perfil_canal": perfil_canal,
}

SCHEMAS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "historico_cliente",
            "description": (
                "Resumo agregado das operações de um cliente: volumes, mediana, extremos, "
                "contrapartes e o que as regras determinísticas apontaram (dias de possível "
                "fracionamento e operações atípicas). Comece por aqui."
            ),
            "parameters": {
                "type": "object",
                "properties": {"cliente_id": {"type": "string", "description": "ex.: CLI-002"}},
                "required": ["cliente_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "operacoes_do_dia",
            "description": (
                "Detalhe das operações de um cliente em um dia específico. Útil para investigar "
                "um dia apontado como possível fracionamento."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_id": {"type": "string"},
                    "data": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["cliente_id", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "perfil_canal",
            "description": (
                "Distribuição de uso por canal (pix, ted, boleto, cartão, espécie) com percentual "
                "do volume. Útil para avaliar peso de espécie e padrão de movimentação."
            ),
            "parameters": {
                "type": "object",
                "properties": {"cliente_id": {"type": "string"}},
                "required": ["cliente_id"],
            },
        },
    },
]


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(historico_cliente("CLI-002"), ensure_ascii=False, indent=2))
    print(_json.dumps(operacoes_do_dia("CLI-002", "2026-05-01"), ensure_ascii=False, indent=2))
    print(_json.dumps(perfil_canal("CLI-023"), ensure_ascii=False, indent=2))
