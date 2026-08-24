# -*- coding: utf-8 -*-
"""Nível 3 — Trilha B: servidor MCP local (stdio) expondo as ferramentas do Nível 2.

As três funções de nivel_2/tools.py viram ferramentas MCP — mesma lógica, mesmo
princípio (todo número nasce em pandas). Nenhuma linha das ferramentas muda:
este arquivo é só a casca de protocolo.

Executar direto (o cliente MCP normalmente faz isso por você):
    python nivel_3/servidor_mcp.py
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "nivel_2"))

from mcp.server import MCPServer

import tools

mcp = MCPServer("pld-tools")

# Reexporta cada ferramenta com a mesma assinatura e docstring do Nível 2
mcp.tool()(tools.historico_cliente)
mcp.tool()(tools.operacoes_do_dia)
mcp.tool()(tools.perfil_canal)

if __name__ == "__main__":
    mcp.run()  # transporte stdio por padrão
