"""Servidor Model Context Protocol (MCP) do DuckDB para o HomeFix.

Disponibiliza ferramentas diretas de exploração e execução SQL sobre o banco
de dados DuckDB local, permitindo que LLMs e agentes de IA consultem dados
e traduzam perguntas em consultas SQL.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import duckdb
from mcp.server.mcpserver import MCPServer

from agents.tools import (
    describe_table,
    execute_query,
    get_schema_context,
    list_tables,
)

server = MCPServer(
    name="duckdb-homefix",
    instructions=(
        "Servidor MCP do DuckDB para a plataforma HomeFix. "
        "Permite listar esquemas e tabelas (bronze, silver, gold), descrever colunas "
        "e executar consultas SQL dinâmicas (SELECT) para responder a dúvidas de negócio."
    ),
)


@server.tool()
def tool_execute_query(query: str) -> str:
    """Executa uma consulta SQL arbitrária no banco de dados DuckDB e retorna os dados em JSON.

    Args:
        query: Consulta SQL a ser executada (ex: 'SELECT * FROM gold.fct_orders LIMIT 5;').
    """
    try:
        data = execute_query(query=query)
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except (duckdb.Error, ValueError, RuntimeError) as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2)


@server.tool()
def tool_list_tables() -> str:
    """Lista todos os esquemas e tabelas existentes no banco de dados DuckDB."""
    try:
        data = list_tables()
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except (duckdb.Error, ValueError, RuntimeError) as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2)


@server.tool()
def tool_describe_table(table_name: str) -> str:
    """Retorna os metadados de colunas e tipos de dados de uma tabela específica no DuckDB.

    Args:
        table_name: Nome qualificado da tabela (ex: 'gold.dim_clients' ou 'silver.service_orders').
    """
    try:
        data = describe_table(table_name=table_name)
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except (duckdb.Error, ValueError, RuntimeError) as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2)


@server.tool()
def tool_get_schema_context() -> str:
    """Retorna a documentação consolidada do catálogo de esquemas e tabelas do banco DuckDB."""
    try:
        return get_schema_context()
    except (duckdb.Error, ValueError, RuntimeError) as exc:
        return f"Erro ao obter catálogo: {exc}"


if __name__ == "__main__":
    print(
        "[OK] Servidor DuckDB MCP HomeFix iniciado (transporte stdio)...",
        file=sys.stderr,
    )
    server.run()
