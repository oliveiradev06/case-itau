# -*- coding: utf-8 -*-
"""Confronto regra determinística × agente (Nível 2, Parte D).

Critério de correspondência (justificativa em docs/DECISOES.md):
- fracionamento detectado         -> risco esperado ALTO  (tipologia clássica de PLD)
- 2+ operações de valor atípico   -> risco esperado ALTO  (desvio recorrente do padrão)
- 1 operação de valor atípico     -> risco esperado MEDIO (desvio pontual)
- nenhuma sinalização             -> risco esperado BAIXO

Compara com o nivel_risco emitido pelo agente para os clientes do lote,
reporta a taxa de concordância e lista as divergências com a justificativa
do agente — matéria-prima da análise qualitativa (quem estava certo?).
"""
from pathlib import Path
import json

import pandas as pd

import regras

RAIZ = Path(__file__).resolve().parent.parent
ARQ_PARECERES = RAIZ / "outputs" / "nivel2_pareceres.jsonl"
ORDEM_RISCO = {"baixo": 0, "medio": 1, "alto": 2}


def risco_esperado_pelas_regras(linha: pd.Series) -> str:
    if linha["ops_fracionamento"] > 0 or linha["ops_valor_atipico"] >= 2:
        return "alto"
    if linha["ops_valor_atipico"] == 1:
        return "medio"
    return "baixo"


def montar_confronto() -> pd.DataFrame:
    if not ARQ_PARECERES.exists():
        raise SystemExit("outputs/nivel2_pareceres.jsonl não existe — rode antes: python nivel_2/agente.py")

    with open(ARQ_PARECERES, encoding="utf-8") as f:
        registros = [json.loads(linha) for linha in f if linha.strip()]

    base = regras.preparar_base(RAIZ / "dados" / "dados_nivel_2.json")
    resumo_regras = regras.resumo_por_cliente(base)

    linhas = []
    for r in registros:
        parecer = r["parecer"] or {}
        regras_cliente = resumo_regras.loc[r["cliente_id"]]
        esperado = risco_esperado_pelas_regras(regras_cliente)
        agente = parecer.get("nivel_risco")
        linhas.append({
            "cliente_id": r["cliente_id"],
            "risco_regras": esperado,
            "risco_agente": agente,
            "concorda": agente == esperado,
            "distancia": abs(ORDEM_RISCO[agente] - ORDEM_RISCO[esperado]) if agente else None,
            "ops_fracionamento": int(regras_cliente["ops_fracionamento"]),
            "ops_valor_atipico": int(regras_cliente["ops_valor_atipico"]),
            "tipologia_agente": parecer.get("tipologia_suspeita"),
            "justificativa_agente": parecer.get("justificativa"),
        })
    return pd.DataFrame(linhas)


def main() -> None:
    confronto = montar_confronto()
    saida = RAIZ / "outputs"
    confronto.to_csv(saida / "nivel2_confronto.csv", index=False)

    avaliados = confronto[confronto["risco_agente"].notna()]
    taxa = 100 * avaliados["concorda"].mean() if len(avaliados) else float("nan")

    print(f"Clientes confrontados: {len(confronto)}")
    print(f"Taxa de concordância exata: {taxa:.0f}%")
    print(f"Distância média entre níveis (0=igual, 2=oposto): {avaliados['distancia'].mean():.2f}\n")
    print(confronto[["cliente_id", "risco_regras", "risco_agente", "concorda",
                     "ops_fracionamento", "ops_valor_atipico"]].to_string(index=False))

    divergencias = avaliados[~avaliados["concorda"]]
    if len(divergencias):
        print("\nDivergências (justificativa do agente):")
        for _, d in divergencias.iterrows():
            print(f"\n- {d['cliente_id']}: regras={d['risco_regras']} × agente={d['risco_agente']}")
            print(f"  {d['justificativa_agente']}")
    else:
        print("\nNenhuma divergência — agente e regras concordaram em todos os casos.")

    print(f"\nSalvo em: {saida / 'nivel2_confronto.csv'}")


if __name__ == "__main__":
    main()
