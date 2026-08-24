# -*- coding: utf-8 -*-
"""Tratamento e regras determinísticas de PLD, reutilizáveis em qualquer base do case.

As funções nasceram no notebook do Nível 1 e migraram para cá sem mudança de
lógica — apenas parametrizadas pelo caminho do arquivo. Executar como script
aplica tudo à base do Nível 2 e salva os resultados em outputs/.
"""
from pathlib import Path
import json

import pandas as pd

# Limiares das regras (ver enunciado, seção 5)
LIMIAR_SOMA_DIA = 50_000       # soma diária que caracteriza fracionamento
LIMIAR_OP_ISOLADA = 20_000     # nenhuma operação isolada atinge este valor
MIN_OPS_DIA = 3                # mínimo de operações no mesmo dia
FATOR_ATIPICO = 5              # múltiplo da mediana do cliente
MIN_OPS_CLIENTE = 4            # mínimo de operações para a Regra 2

RAIZ = Path(__file__).resolve().parent.parent


def carregar_operacoes(caminho: str | Path) -> tuple[pd.DataFrame, float]:
    """Lê um arquivo de operações do case e devolve (DataFrame bruto, taxa USD→BRL)."""
    with open(caminho, encoding="utf-8") as f:
        raw = json.load(f)
    return pd.DataFrame(raw["operacoes"]), raw["taxa_cambio_usd_brl"]


def limpar(df: pd.DataFrame, taxa_usd_brl: float) -> pd.DataFrame:
    """Limpeza padrão do case (decisões justificadas em docs/DECISOES.md):

    - remove registros duplicados exatos (reprocessamento do sistema legado);
    - normaliza tudo para BRL em `valor_brl`, preservando valor/moeda originais;
    - converte `data` para datetime; datas nulas viram NaT e ficam de fora
      apenas das regras que dependem de data.
    """
    limpo = df.drop_duplicates().copy()
    limpo["valor_brl"] = limpo["valor"].where(limpo["moeda"] == "BRL", limpo["valor"] * taxa_usd_brl)
    limpo["data"] = pd.to_datetime(limpo["data"], errors="coerce")
    return limpo


def aplicar_regra_fracionamento(ops: pd.DataFrame) -> pd.DataFrame:
    """Regra 1: marca operações de grupos (cliente, dia) com 3+ ops, soma > 50k e todas < 20k."""
    grupos = (
        ops.dropna(subset=["data"])
        .groupby(["cliente_id", "data"])["valor_brl"]
        .agg(["size", "sum", "max"])
    )
    dias_suspeitos = grupos[
        (grupos["size"] >= MIN_OPS_DIA)
        & (grupos["sum"] > LIMIAR_SOMA_DIA)
        & (grupos["max"] < LIMIAR_OP_ISOLADA)
    ].index
    flag = ops.set_index(["cliente_id", "data"]).index.isin(dias_suspeitos)
    return ops.assign(flag_fracionamento=flag)


def aplicar_regra_valor_atipico(ops: pd.DataFrame) -> pd.DataFrame:
    """Regra 2: marca a operação acima de 5x a mediana do cliente (clientes com 4+ ops)."""
    qtd_ops_cliente = ops.groupby("cliente_id")["id"].transform("size")
    mediana_cliente = ops.groupby("cliente_id")["valor_brl"].transform("median")
    flag = (qtd_ops_cliente >= MIN_OPS_CLIENTE) & (ops["valor_brl"] > FATOR_ATIPICO * mediana_cliente)
    return ops.assign(mediana_cliente=mediana_cliente, flag_valor_atipico=flag)


def preparar_base(caminho: str | Path) -> pd.DataFrame:
    """Pipeline completo: carga → limpeza → duas regras."""
    df, taxa = carregar_operacoes(caminho)
    return aplicar_regra_valor_atipico(aplicar_regra_fracionamento(limpar(df, taxa)))


def resumo_por_cliente(ops: pd.DataFrame) -> pd.DataFrame:
    """Consolida sinalizações por cliente.

    Critério (justificativa completa em DECISOES.md): as flags são atribuídas a
    OPERAÇÕES, então `sinalizacoes` conta operações sinalizadas por qualquer
    regra. Cada operação de um dia de fracionamento conta — o padrão orquestrado
    (3-4 ops coordenadas) pesa mais que um outlier isolado, como deve ser em PLD.
    """
    resumo = ops.groupby("cliente_id").agg(
        operacoes=("id", "size"),
        volume_brl=("valor_brl", "sum"),
        ops_fracionamento=("flag_fracionamento", "sum"),
        ops_valor_atipico=("flag_valor_atipico", "sum"),
    )
    dias = ops[ops["flag_fracionamento"]].groupby("cliente_id")["data"].nunique()
    resumo["dias_fracionamento"] = dias.reindex(resumo.index, fill_value=0).astype(int)
    resumo["sinalizacoes"] = resumo["ops_fracionamento"] + resumo["ops_valor_atipico"]
    return resumo.sort_values(["sinalizacoes", "volume_brl"], ascending=False)


def top_sinalizados(resumo: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Top-n clientes por nº de sinalizações, volume total como desempate."""
    return resumo[resumo["sinalizacoes"] > 0].head(n)


if __name__ == "__main__":
    base = preparar_base(RAIZ / "dados" / "dados_nivel_2.json")
    resumo = resumo_por_cliente(base)
    top10 = top_sinalizados(resumo, 10)

    saida = RAIZ / "outputs"
    saida.mkdir(exist_ok=True)
    flagadas = base[base["flag_fracionamento"] | base["flag_valor_atipico"]]
    flagadas.to_csv(saida / "nivel2_operacoes_sinalizadas.csv", index=False)
    top10.to_csv(saida / "nivel2_top10_clientes.csv")

    print(f"Base nível 2: {len(base)} operações limpas, {base['cliente_id'].nunique()} clientes")
    print(f"Regra 1 (fracionamento): {base['flag_fracionamento'].sum()} operações em "
          f"{base[base['flag_fracionamento']].groupby(['cliente_id', 'data']).ngroups} dias suspeitos")
    print(f"Regra 2 (valor atípico): {base['flag_valor_atipico'].sum()} operações\n")
    print("Top-10 clientes mais sinalizados (desempate por volume):")
    print(top10.to_string())
