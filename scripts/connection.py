"""Gerenciador centralizado de conexões com o banco de dados DuckDB.

Fornece conexões persistentes ou em memória para o pipeline Medalhão HomeFix,
assegurando a inicialização automática dos esquemas bronze, silver e gold.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_DB_PATH = Path("data/warehouse/homefix.duckdb")


def init_schemas(conn: duckdb.DuckDBPyConnection) -> None:
    """Cria os esquemas bronze, silver e gold caso não existam.

    Args:
        conn: Conexão ativa com o DuckDB.
    """
    conn.execute("CREATE SCHEMA IF NOT EXISTS bronze;")
    conn.execute("CREATE SCHEMA IF NOT EXISTS silver;")
    conn.execute("CREATE SCHEMA IF NOT EXISTS gold;")


def get_connection(
    db_path: str | Path | None = None,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """Abre e retorna uma conexão com o banco DuckDB.

    Se o caminho for None, utiliza a variável de ambiente HOMEFIX_DB_PATH
    ou o caminho padrão 'data/warehouse/homefix.duckdb'.
    Se for especificado ':memory:', abre um banco volátil em memória.

    Args:
        db_path: Caminho opcional do arquivo de banco ou ':memory:'.
        read_only: Se True, abre em modo somente leitura.

    Returns:
        Instância de DuckDBPyConnection configurada com os esquemas base.
    """
    if db_path is None:
        env_path = os.getenv("HOMEFIX_DB_PATH")
        db_target = Path(env_path) if env_path else DEFAULT_DB_PATH
    elif str(db_path) == ":memory:":
        db_target = ":memory:"
    else:
        db_target = Path(db_path)

    if isinstance(db_target, Path) and str(db_target) != ":memory:":
        db_target.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(db_target), read_only=read_only)
    else:
        conn = duckdb.connect(":memory:", read_only=read_only)

    if not read_only:
        init_schemas(conn)

    return conn


def execute_query(
    query: str,
    conn: duckdb.DuckDBPyConnection | None = None,
    db_path: str | Path | None = None,
) -> duckdb.DuckDBPyConnection:
    """Executa comando SQL DDL ou DML no DuckDB.

    Args:
        query: Declaração SQL a ser executada.
        conn: Conexão opcional existente. Se None, cria uma temporária.
        db_path: Caminho opcional caso conn seja None.

    Returns:
        O cursor ou conexão após a execução.
    """
    if conn is not None:
        return conn.execute(query)

    with get_connection(db_path=db_path) as local_conn:
        return local_conn.execute(query)


def fetch_df(
    query: str,
    conn: duckdb.DuckDBPyConnection | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Executa uma consulta SQL e retorna o resultado como DataFrame do Pandas.

    Args:
        query: Consulta SQL analítica.
        conn: Conexão opcional ativa.
        db_path: Caminho opcional do banco se conn for None.

    Returns:
        DataFrame contendo o resultado da consulta.
    """
    if conn is not None:
        return conn.execute(query).df()

    with get_connection(db_path=db_path, read_only=True) as local_conn:
        return local_conn.execute(query).df()
