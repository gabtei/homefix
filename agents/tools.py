"""Módulo de ferramentas do DuckDB para consumo pelo servidor MCP e agentes de IA.

Permite listar tabelas, inspecionar metadados de schemas e executar consultas
SQL dinâmicas sobre o banco de dados analítico local do HomeFix.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import duckdb

from scripts.connection import fetch_df, get_connection


def execute_query(
    query: str,
    db_path: str | Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[dict[str, Any]]:
    """Executa uma consulta SQL arbitrária no banco de dados DuckDB.

    Args:
        query: Declaração SQL (tipicamente SELECT).
        db_path: Caminho opcional do arquivo DuckDB.
        conn: Conexão ativa opcional.

    Returns:
        Lista de dicionários representando as linhas do resultado.

    Raises:
        ValueError: Se a query for vazia ou contiver comandos perigosos não autorizados.
    """
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("A consulta SQL não pode ser vazia.")

    # Proteção simples contra DDL destrutivo em ferramentas de consulta
    normalized = clean_query.upper()
    destructive_keywords = ["DROP DATABASE", "TRUNCATE DATABASE"]
    for keyword in destructive_keywords:
        if keyword in normalized:
            raise ValueError(f"Comando bloqueado por segurança: {keyword}")

    df = fetch_df(clean_query, conn=conn, db_path=db_path)
    return df.to_dict(orient="records")


def list_tables(
    db_path: str | Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[dict[str, Any]]:
    """Lista todos os esquemas e tabelas de dados existentes no DuckDB.

    Args:
        db_path: Caminho opcional do arquivo DuckDB.
        conn: Conexão ativa opcional.

    Returns:
        Lista de tabelas com seus respectivos esquemas e contagens de linhas.
    """
    sql = """
    SELECT
        table_schema,
        table_name,
        table_type
    FROM information_schema.tables
    WHERE table_schema IN ('bronze', 'silver', 'gold')
    ORDER BY table_schema, table_name;
    """
    df = fetch_df(sql, conn=conn, db_path=db_path)
    records = df.to_dict(orient="records")

    active_conn = (
        conn if conn is not None else get_connection(db_path=db_path, read_only=True)
    )
    try:
        for r in records:
            full_tbl = f"{r['table_schema']}.{r['table_name']}"
            try:
                cnt = active_conn.execute(
                    f"SELECT COUNT(*) FROM {full_tbl}"
                ).fetchone()[0]
                r["row_count"] = cnt
            except (duckdb.Error, RuntimeError):
                r["row_count"] = None
    finally:
        if conn is None:
            active_conn.close()

    return records


def describe_table(
    table_name: str,
    db_path: str | Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[dict[str, Any]]:
    """Retorna as colunas, tipos e características de uma tabela específica.

    Args:
        table_name: Nome qualificado da tabela (ex: 'gold.fct_orders').
        db_path: Caminho opcional do arquivo DuckDB.
        conn: Conexão ativa opcional.

    Returns:
        Lista de dicionários descrevendo cada coluna da tabela.

    Raises:
        ValueError: Se o nome da tabela contiver caracteres inválidos.
    """
    clean_table = table_name.strip()
    if not clean_table:
        raise ValueError("O nome da tabela não pode ser vazio.")

    # Permite apenas formato schema.tabela ou tabela
    if any(ch in clean_table for ch in [";", " ", "--", "/*"]):
        raise ValueError(f"Nome de tabela inválido: {clean_table}")

    sql = f"DESCRIBE {clean_table};"
    df = fetch_df(sql, conn=conn, db_path=db_path)
    return df.to_dict(orient="records")


def get_schema_context(
    db_path: str | Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> str:
    """Gera uma documentação textual completa do esquema do banco de dados.

    Utilizado para fornecer contexto ao LLM para tradução precisa de perguntas
    em linguagem natural em comandos SQL DuckDB.

    Args:
        db_path: Caminho opcional do arquivo DuckDB.
        conn: Conexão ativa opcional.

    Returns:
        String em formato Markdown descrevendo os esquemas e tabelas disponíveis.
    """
    tables = list_tables(db_path=db_path, conn=conn)
    lines: list[str] = [
        "# Catálogo de Esquemas e Tabelas do DuckDB (HomeFix)\n",
        "Utilize este catálogo para gerar queries SQL precisas sobre os dados do marketplace:\n",
    ]

    for tbl in tables:
        full_name = f"{tbl['table_schema']}.{tbl['table_name']}"
        row_info = f"({tbl.get('row_count', 'N/A')} linhas)"
        lines.append(f"### Tabela: `{full_name}` {row_info}")

        cols = describe_table(full_name, db_path=db_path, conn=conn)
        col_desc = [
            f"- `{c.get('column_name', c.get('Field', ''))}`: {c.get('column_type', c.get('Type', ''))}"
            for c in cols
        ]
        lines.extend(col_desc)
        lines.append("")

    return "\n".join(lines)
