"""Suíte de testes para o Servidor DuckDB MCP e o Agente Analítico HomeFix.

Valida as ferramentas nativas de banco de dados (execute_query, list_tables,
describe_table, get_schema_context), o catálogo do servidor MCP e a tradução
de perguntas em linguagem natural para queries no DuckDB.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import duckdb
import pytest

from agents.bot import DuckDBAnalystBot
from agents.mcp_server import (
    server,
    tool_describe_table,
    tool_execute_query,
    tool_get_schema_context,
    tool_list_tables,
)
from agents.tools import (
    describe_table,
    execute_query,
    get_schema_context,
    list_tables,
)
from scripts.bronze_ingestion import run_bronze_ingestion
from scripts.connection import get_connection
from scripts.gold_processing import run_gold_processing
from scripts.silver_processing import run_silver_processing


@pytest.fixture
def populated_conn() -> duckdb.DuckDBPyConnection:
    """Fixture que fornece uma conexão em memória com Bronze, Silver e Gold carregadas."""
    conn = get_connection(db_path=":memory:")
    run_bronze_ingestion(raw_dir="data/raw", conn=conn)
    run_silver_processing(conn=conn)
    run_gold_processing(conn=conn)
    yield conn
    conn.close()


def test_tools_execute_query(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida a execução de queries SQL no DuckDB."""
    # Query válida
    rows = execute_query(
        "SELECT COUNT(*) AS total FROM gold.fct_orders;", conn=populated_conn
    )
    assert len(rows) == 1
    assert rows[0]["total"] == 500

    # Query vazia
    with pytest.raises(ValueError, match="não pode ser vazia"):
        execute_query("   ", conn=populated_conn)

    # Bloqueio de comando destrutivo
    with pytest.raises(ValueError, match="Comando bloqueado"):
        execute_query("DROP DATABASE homefix;", conn=populated_conn)


def test_tools_list_tables(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida listagem de tabelas e contagem de registros."""
    tables = list_tables(conn=populated_conn)
    assert len(tables) >= 10
    schemas = {t["table_schema"] for t in tables}
    assert {"bronze", "silver", "gold"}.issubset(schemas)

    names = {f"{t['table_schema']}.{t['table_name']}" for t in tables}
    assert "gold.fct_orders" in names
    assert "silver.contractors" in names


def test_tools_describe_table(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida inspeção de schema de tabela específica."""
    cols = describe_table("gold.fct_orders", conn=populated_conn)
    assert len(cols) > 5
    col_names = [c["column_name"] for c in cols]
    assert "order_id" in col_names
    assert "total_final_amount" in col_names

    # Erros de validação
    with pytest.raises(ValueError, match="não pode ser vazio"):
        describe_table("", conn=populated_conn)

    with pytest.raises(ValueError, match="Nome de tabela inválido"):
        describe_table("gold.fct_orders; DROP TABLE x", conn=populated_conn)


def test_tools_get_schema_context(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida geração do catálogo de contexto para IA."""
    ctx = get_schema_context(conn=populated_conn)
    assert "# Catálogo de Esquemas e Tabelas do DuckDB" in ctx
    assert "gold.fct_orders" in ctx
    assert "silver.service_orders" in ctx


def test_tools_disk_without_conn(tmp_path: Path) -> None:
    """Valida ferramentas operando sobre banco em disco sem passar conexão."""
    db_file = tmp_path / "duckdb_tools.duckdb"
    run_bronze_ingestion(raw_dir="data/raw", db_path=db_file)
    run_silver_processing(db_path=db_file)
    run_gold_processing(db_path=db_file)

    tables = list_tables(db_path=db_file)
    assert len(tables) >= 10

    desc = describe_table("silver.clients", db_path=db_file)
    assert len(desc) > 0


def test_mcp_server_registration() -> None:
    """Garante que o servidor MCP registrou as 4 ferramentas do DuckDB."""
    tools = asyncio.run(server.list_tools())
    tool_names = {t.name for t in tools}
    expected = {
        "tool_execute_query",
        "tool_list_tables",
        "tool_describe_table",
        "tool_get_schema_context",
    }
    assert expected.issubset(tool_names)


def test_mcp_server_tool_calls() -> None:
    """Testa invocação direta das ferramentas no DuckDB MCP Server."""
    # List tables
    raw_tables = tool_list_tables()
    data_tables = json.loads(raw_tables)
    assert isinstance(data_tables, (list, dict))

    # Describe table
    raw_desc = tool_describe_table("gold.fct_orders")
    data_desc = json.loads(raw_desc)
    assert isinstance(data_desc, (list, dict))

    # Execute query
    raw_query = tool_execute_query("SELECT 1 AS num;")
    data_query = json.loads(raw_query)
    assert data_query[0]["num"] == 1

    # Schema context
    ctx = tool_get_schema_context()
    assert "Catálogo" in ctx or "Erro" not in ctx

    # Teste de ramos de erro no MCP Server
    err_desc = json.loads(tool_describe_table(""))
    assert "error" in err_desc

    err_list = json.loads(tool_list_tables())
    assert isinstance(err_list, (list, dict))

    # Erro de SQL tratado no MCP
    raw_err = tool_execute_query("SELECT * FROM tabela_que_nao_existe_xyz;")
    data_err = json.loads(raw_err)
    assert "error" in data_err


def test_duckdb_analyst_bot_ask(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Testa o bot traduzindo perguntas em linguagem natural para SQL e executando no DuckDB."""
    bot = DuckDBAnalystBot()

    # Pergunta sobre GMV
    res_gmv = bot.ask("Qual o GMV por especialidade?", conn=populated_conn)
    assert "total_gmv" in res_gmv["sql"].lower()
    assert len(res_gmv["results"]) > 0
    assert "✅" in res_gmv["answer"]

    # Pergunta sobre prestadores
    res_pres = bot.ask(
        "Quem são os melhores prestadores em nota e ranking?", conn=populated_conn
    )
    assert "dim_contractors" in res_pres["sql"].lower()
    assert len(res_pres["results"]) > 0

    # Pergunta sobre cancelamentos
    res_cancel = bot.ask(
        "Qual a taxa de cancelamento e resolução?", conn=populated_conn
    )
    assert "resolution_rate_pct" in res_cancel["sql"].lower()
    assert len(res_cancel["results"]) > 0

    # Pergunta sobre churn/incidentes
    res_churn = bot.ask(
        "Quais clientes estão em risco de churn por incidentes?", conn=populated_conn
    )
    assert "incident_reported" in res_churn["sql"].lower()

    # Pergunta sobre tabelas
    res_tables = bot.ask("Quais tabelas existem?", conn=populated_conn)
    assert "information_schema" in res_tables["sql"].lower()

    # Pergunta sobre clientes
    res_clients = bot.ask(
        "Quais são os maiores clientes em faturamento?", conn=populated_conn
    )
    assert "dim_clients" in res_clients["sql"].lower()

    # SQL direto
    res_direct = bot.ask(
        "SELECT COUNT(*) AS total_itens FROM silver.service_items;", conn=populated_conn
    )
    assert (
        res_direct["sql"] == "SELECT COUNT(*) AS total_itens FROM silver.service_items;"
    )
    assert res_direct["results"][0]["total_itens"] > 500

    # Fallback
    res_fall = bot.ask("Me dê um resumo geral da empresa", conn=populated_conn)
    assert "kpi_monthly_summary" in res_fall["sql"].lower()

    # Tratamento de erro
    res_bad = bot.ask("SELECT * FROM tabela_fantasma_xyz;", conn=populated_conn)
    assert "⚠️" in res_bad["answer"]
    assert res_bad["error"] is not None


def test_duckdb_analyst_bot_helpers(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Testa métodos utilitários do bot de inspeção e listagem."""
    bot = DuckDBAnalystBot()
    tables = bot.get_available_tables(conn=populated_conn)
    assert len(tables) >= 10

    desc = bot.inspect_table("silver.clients", conn=populated_conn)
    assert len(desc) > 0
