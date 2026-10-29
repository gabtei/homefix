"""Módulo de processamento da camada Gold no DuckDB.

Transforma os dados higienizados da camada Silver em modelagem dimensional
e tabelas agregadas de negócio prontas para consumo por dashboards e IA:
- gold.dim_clients: Dimensão de clientes com LTV e métricas de engajamento
- gold.dim_contractors: Dimensão de prestadores com scorecard e ratings
- gold.fct_orders: Tabela fato de ordens de serviço com lead time e tempos de ciclo
- gold.kpi_monthly_summary: Tabela consolidada de evolução mensal de GMV e taxas
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import duckdb

from scripts.connection import get_connection


def process_gold_dim_clients(conn: duckdb.DuckDBPyConnection) -> int:
    """Cria ou substitui a dimensão analítica de clientes na camada Gold.

    Args:
        conn: Conexão ativa com o DuckDB.

    Returns:
        Total de clientes na dimensão.
    """
    query = """
    CREATE OR REPLACE TABLE gold.dim_clients AS
    WITH client_orders AS (
        SELECT
            client_id,
            COUNT(order_id) AS total_orders_placed,
            COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END) AS completed_orders,
            COUNT(CASE WHEN order_status = 'CANCELADO' THEN 1 END) AS canceled_orders,
            ROUND(COALESCE(SUM(CASE WHEN order_status = 'CONCLUIDO' THEN total_final_amount ELSE 0.00 END), 0.00), 2) AS total_spend,
            MIN(order_date) AS first_order_date,
            MAX(order_date) AS last_order_date
        FROM silver.service_orders
        GROUP BY client_id
    )
    SELECT
        c.client_id,
        c.client_name,
        c.client_email,
        c.client_phone,
        c.client_city,
        c.client_state,
        c.signup_date,
        COALESCE(co.total_orders_placed, 0) AS total_orders_placed,
        COALESCE(co.completed_orders, 0) AS completed_orders,
        COALESCE(co.canceled_orders, 0) AS canceled_orders,
        COALESCE(co.total_spend, 0.00) AS total_spend,
        ROUND(
            CASE
                WHEN COALESCE(co.completed_orders, 0) > 0 THEN co.total_spend / co.completed_orders
                ELSE 0.00
            END,
            2
        ) AS avg_order_value,
        co.first_order_date,
        co.last_order_date,
        CURRENT_TIMESTAMP AS _processed_at
    FROM silver.clients c
    LEFT JOIN client_orders co ON c.client_id = co.client_id;
    """
    conn.execute(query)
    res = conn.execute("SELECT COUNT(*) FROM gold.dim_clients").fetchone()
    return res[0] if res else 0


def process_gold_dim_contractors(conn: duckdb.DuckDBPyConnection) -> int:
    """Cria ou substitui a dimensão analítica de prestadores na camada Gold.

    Args:
        conn: Conexão ativa com o DuckDB.

    Returns:
        Total de prestadores na dimensão.
    """
    query = """
    CREATE OR REPLACE TABLE gold.dim_contractors AS
    WITH contractor_metrics AS (
        SELECT
            so.contractor_id,
            COUNT(so.order_id) AS total_orders_assigned,
            COUNT(CASE WHEN so.order_status = 'CONCLUIDO' THEN 1 END) AS completed_orders,
            COUNT(CASE WHEN so.order_status = 'CANCELADO' THEN 1 END) AS canceled_orders,
            ROUND(COALESCE(SUM(CASE WHEN so.order_status = 'CONCLUIDO' THEN so.total_final_amount ELSE 0.00 END), 0.00), 2) AS total_gmv_generated,
            ROUND(COALESCE(AVG(r.rating), 0.0), 2) AS avg_rating,
            COUNT(CASE WHEN r.incident_reported THEN 1 END) AS incidents_count
        FROM silver.service_orders so
        LEFT JOIN silver.reviews r ON so.order_id = r.order_id
        GROUP BY so.contractor_id
    )
    SELECT
        c.contractor_id,
        c.contractor_name,
        c.specialty,
        c.hourly_rate,
        c.experience_years,
        c.city,
        c.state,
        c.is_active,
        COALESCE(cm.total_orders_assigned, 0) AS total_orders_assigned,
        COALESCE(cm.completed_orders, 0) AS completed_orders,
        COALESCE(cm.canceled_orders, 0) AS canceled_orders,
        ROUND(
            CASE
                WHEN COALESCE(cm.total_orders_assigned, 0) > 0 THEN
                    (cm.completed_orders::DOUBLE / cm.total_orders_assigned) * 100.0
                ELSE 0.0
            END,
            2
        ) AS completion_rate_pct,
        COALESCE(cm.total_gmv_generated, 0.00) AS total_gmv_generated,
        COALESCE(cm.avg_rating, 0.0) AS avg_rating,
        COALESCE(cm.incidents_count, 0) AS incidents_count,
        CURRENT_TIMESTAMP AS _processed_at
    FROM silver.contractors c
    LEFT JOIN contractor_metrics cm ON c.contractor_id = cm.contractor_id;
    """
    conn.execute(query)
    res = conn.execute("SELECT COUNT(*) FROM gold.dim_contractors").fetchone()
    return res[0] if res else 0


def process_gold_fct_orders(conn: duckdb.DuckDBPyConnection) -> int:
    """Cria ou substitui a tabela fato analítica de ordens na camada Gold.

    Args:
        conn: Conexão ativa com o DuckDB.

    Returns:
        Total de registros na tabela fato.
    """
    query = """
    CREATE OR REPLACE TABLE gold.fct_orders AS
    SELECT
        so.order_id,
        so.client_id,
        so.contractor_id,
        so.order_date,
        so.scheduled_date,
        so.completion_date,
        so.order_status,
        so.service_category,
        so.total_quoted_amount,
        so.total_final_amount,
        DATEDIFF('day', so.order_date, so.scheduled_date) AS lead_time_days,
        CASE
            WHEN so.completion_date IS NOT NULL THEN DATEDIFF('day', so.order_date, so.completion_date)
            ELSE NULL
        END AS cycle_time_days,
        r.rating,
        COALESCE(r.incident_reported, FALSE) AS has_incident,
        COALESCE(r.incident_type, 'Nenhum') AS incident_type,
        CURRENT_TIMESTAMP AS _processed_at
    FROM silver.service_orders so
    LEFT JOIN silver.reviews r ON so.order_id = r.order_id;
    """
    conn.execute(query)
    res = conn.execute("SELECT COUNT(*) FROM gold.fct_orders").fetchone()
    return res[0] if res else 0


def process_gold_kpi_monthly_summary(conn: duckdb.DuckDBPyConnection) -> int:
    """Cria a tabela consolidada de métricas mensais da plataforma.

    Args:
        conn: Conexão ativa com o DuckDB.

    Returns:
        Total de meses consolidados.
    """
    query = """
    CREATE OR REPLACE TABLE gold.kpi_monthly_summary AS
    SELECT
        STRFTIME(order_date, '%Y-%m') AS order_month,
        COUNT(order_id) AS total_orders,
        COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END) AS completed_orders,
        COUNT(CASE WHEN order_status = 'CANCELADO' THEN 1 END) AS canceled_orders,
        ROUND(
            (COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END)::DOUBLE / NULLIF(COUNT(order_id), 0)) * 100.0,
            2
        ) AS completion_rate_pct,
        ROUND(COALESCE(SUM(CASE WHEN order_status = 'CONCLUIDO' THEN total_final_amount ELSE 0.00 END), 0.00), 2) AS total_gmv,
        ROUND(COALESCE(AVG(CASE WHEN order_status = 'CONCLUIDO' THEN total_final_amount END), 0.00), 2) AS avg_ticket,
        ROUND(COALESCE(AVG(rating), 0.0), 2) AS avg_rating,
        COUNT(CASE WHEN has_incident THEN 1 END) AS total_incidents,
        CURRENT_TIMESTAMP AS _processed_at
    FROM gold.fct_orders
    GROUP BY STRFTIME(order_date, '%Y-%m')
    ORDER BY order_month ASC;
    """
    conn.execute(query)
    res = conn.execute("SELECT COUNT(*) FROM gold.kpi_monthly_summary").fetchone()
    return res[0] if res else 0


def run_gold_processing(
    db_path: Path | str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, int]:
    """Executa o processamento completo das dimensões e fatos da camada Gold.

    Args:
        db_path: Caminho opcional do arquivo DuckDB.
        conn: Conexão opcional ativa.

    Returns:
        Dicionário com a contagem de registros gerados por tabela Gold.
    """
    active_conn = conn if conn is not None else get_connection(db_path=db_path)
    results: dict[str, int] = {}

    try:
        results["gold.dim_clients"] = process_gold_dim_clients(active_conn)
        results["gold.dim_contractors"] = process_gold_dim_contractors(active_conn)
        results["gold.fct_orders"] = process_gold_fct_orders(active_conn)
        results["gold.kpi_monthly_summary"] = process_gold_kpi_monthly_summary(
            active_conn
        )
    finally:
        if conn is None:
            active_conn.close()

    return results


if __name__ == "__main__":
    counts = run_gold_processing()
    print("[OK] Processamento Gold finalizado com sucesso:")
    for tbl, count in counts.items():
        print(f"  - {tbl}: {count} registros")
