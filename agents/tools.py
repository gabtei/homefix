"""Módulo de ferramentas analíticas do HomeFix para consumo por MCP e agentes de IA.

Encapsula consultas SQL avançadas (CTEs, Window Functions, métricas de resolução
e análise de churn) sobre a base de dados DuckDB, retornando estruturas Python limpas.
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

QUERIES_DIR = ROOT_DIR / "data" / "queries"


def _read_query(filename: str) -> str:
    """Lê o conteúdo textual de um arquivo SQL do diretório data/queries.

    Remove ponto e vírgula final para permitir composição em subqueries/CTEs.

    Args:
        filename: Nome do arquivo (ex: 'kpi_gmv_by_specialty.sql').

    Returns:
        String contendo a declaração SQL sem o delimitador final.
    """
    path = QUERIES_DIR / filename
    return path.read_text(encoding="utf-8").strip().rstrip(";")


def get_gmv_by_specialty(
    min_orders: int = 0,
    db_path: str | Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[dict[str, Any]]:
    """Consulta volume financeiro bruto (GMV) e representatividade por especialidade.

    Args:
        min_orders: Filtro para considerar apenas especialidades com no mínimo X ordens.
        db_path: Caminho opcional do arquivo DuckDB.
        conn: Conexão ativa opcional.

    Returns:
        Lista de dicionários contendo indicadores consolidados por especialidade.
    """
    raw_sql = _read_query("kpi_gmv_by_specialty.sql")
    query = f"""
    WITH base_result AS (
        {raw_sql}
    )
    SELECT * FROM base_result
    WHERE total_orders >= {int(min_orders)}
    ORDER BY total_gmv DESC;
    """
    df = fetch_df(query, conn=conn, db_path=db_path)
    return df.to_dict(orient="records")


def get_contractor_scorecard(
    specialty: str | None = None,
    min_rating: float = 0.0,
    db_path: str | Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[dict[str, Any]]:
    """Consulta o scorecard e ranking de prestadores com Window Functions.

    Args:
        specialty: Filtro opcional por especialidade (ex: 'Elétrica').
        min_rating: Nota média mínima de avaliação para filtragem.
        db_path: Caminho opcional do arquivo DuckDB.
        conn: Conexão ativa opcional.

    Returns:
        Lista de dicionários com métricas e rankings dos prestadores.
    """
    raw_sql = _read_query("kpi_contractor_scorecard.sql")
    where_clauses = [f"avg_rating >= {float(min_rating)}"]

    if specialty:
        clean_spec = specialty.replace("'", "''")
        where_clauses.append(f"LOWER(specialty) = LOWER('{clean_spec}')")

    where_stmt = " AND ".join(where_clauses)
    query = f"""
    WITH base_result AS (
        {raw_sql}
    )
    SELECT * FROM base_result
    WHERE {where_stmt}
    ORDER BY specialty, rank_in_specialty;
    """
    df = fetch_df(query, conn=conn, db_path=db_path)
    return df.to_dict(orient="records")


def get_resolution_rate(
    min_cancellation_pct: float = 0.0,
    db_path: str | Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[dict[str, Any]]:
    """Consulta a taxa de conversão e tempos de ciclo de atendimento por categoria.

    Args:
        min_cancellation_pct: Filtro para retornar categorias com taxa de cancelamento >= %.
        db_path: Caminho opcional do arquivo DuckDB.
        conn: Conexão ativa opcional.

    Returns:
        Lista de dicionários com taxas de resolução e ciclo operacional.
    """
    raw_sql = _read_query("kpi_resolution_rate.sql")
    query = f"""
    WITH base_result AS (
        {raw_sql}
    )
    SELECT * FROM base_result
    WHERE cancellation_rate_pct >= {float(min_cancellation_pct)}
    ORDER BY resolution_rate_pct DESC;
    """
    df = fetch_df(query, conn=conn, db_path=db_path)
    return df.to_dict(orient="records")


def get_incidents_churn(
    churn_status: str | None = None,
    db_path: str | Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[dict[str, Any]]:
    """Consulta incidentes reportados em chamados e correlaciona com risco de churn.

    Args:
        churn_status: Filtro opcional por status ('ALTO_RISCO_CHURN' ou 'RETIDO').
        db_path: Caminho opcional do arquivo DuckDB.
        conn: Conexão ativa opcional.

    Returns:
        Lista de dicionários contendo incidentes e status de retenção do cliente.
    """
    raw_sql = _read_query("joins_incidents_churn.sql")
    where_stmt = ""
    if churn_status:
        clean_status = churn_status.replace("'", "''").upper()
        where_stmt = f"WHERE churn_risk_status = '{clean_status}'"

    query = f"""
    WITH base_result AS (
        {raw_sql}
    )
    SELECT * FROM base_result
    {where_stmt}
    ORDER BY order_date DESC;
    """
    df = fetch_df(query, conn=conn, db_path=db_path)
    return df.to_dict(orient="records")


def diagnose_marketplace_health(
    db_path: str | Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """Gera um diagnóstico analítico consolidado sobre a operação do marketplace.

    Avalia volume transacionado, especialidades com cancelamentos anômalos,
    prestadores críticos e clientes sob risco de evasão.

    Args:
        db_path: Caminho opcional do arquivo DuckDB.
        conn: Conexão ativa opcional.

    Returns:
        Dicionário com KPIs globais e listas de alertas operacionais.
    """
    active_conn = (
        conn if conn is not None else get_connection(db_path=db_path, read_only=True)
    )

    try:
        # 1. Indicadores globais
        gmv_data = get_gmv_by_specialty(conn=active_conn)
        total_gmv = round(sum(item["total_gmv"] for item in gmv_data), 2)
        total_orders = sum(item["total_orders"] for item in gmv_data)
        completed_orders = sum(item["completed_orders"] for item in gmv_data)
        global_resolution_pct = (
            round((completed_orders / total_orders) * 100.0, 2)
            if total_orders > 0
            else 0.0
        )

        # 2. Resoluções e categorias em alerta (> 15% cancelamento)
        resolutions = get_resolution_rate(conn=active_conn)
        critical_categories = [
            cat for cat in resolutions if cat["cancellation_rate_pct"] > 15.0
        ]

        # 3. Prestadores com nota baixa (< 3.5) ou com incidentes (> 2)
        scorecard = get_contractor_scorecard(conn=active_conn)
        underperforming_contractors = [
            k
            for k in scorecard
            if (0.0 < k["avg_rating"] < 3.5) or (k["total_incidents"] >= 2)
        ]

        # 4. Incidentes e clientes sob risco de churn
        churn_records = get_incidents_churn(
            churn_status="ALTO_RISCO_CHURN", conn=active_conn
        )
        churn_risk_count = len(churn_records)

        return {
            "summary": {
                "total_gmv": total_gmv,
                "total_orders": total_orders,
                "completed_orders": completed_orders,
                "global_resolution_pct": global_resolution_pct,
                "total_specialties": len(gmv_data),
            },
            "alerts": {
                "critical_categories_count": len(critical_categories),
                "critical_categories": critical_categories,
                "underperforming_contractors_count": len(underperforming_contractors),
                "underperforming_contractors": underperforming_contractors,
                "churn_risk_clients_count": churn_risk_count,
            },
            "top_specialties_by_gmv": gmv_data[:3],
        }
    finally:
        if conn is None:
            active_conn.close()
