"""Módulo de processamento e higienização da camada Silver no DuckDB.

Transforma os dados brutos da camada Bronze em dados estruturados,
tipados e sanitizados na camada Silver:
- Conversão de moedas com ruído para DECIMAL(10,2)
- Padronização de datas mistas para DATE
- Normalização de booleanos, categorias, especialidades e status
- Adição da coluna _processed_at de auditoria
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import duckdb

from scripts.connection import get_connection

SQL_CLEAN_DATE = """
COALESCE(
    TRY_STRPTIME(NULLIF(TRIM({col}), ''), '%Y-%m-%d'),
    TRY_STRPTIME(NULLIF(TRIM({col}), ''), '%d/%m/%Y'),
    TRY_STRPTIME(NULLIF(TRIM({col}), ''), '%m-%d-%Y'),
    TRY_STRPTIME(NULLIF(TRIM({col}), ''), '%Y/%m/%d')
)::DATE
"""

SQL_CLEAN_CURRENCY = """
CASE
    WHEN {col} IS NULL OR TRIM({col}) = '' THEN 0.00
    WHEN INSTR({col}, ',') > 0 THEN
        COALESCE(TRY_CAST(REPLACE(REPLACE(REGEXP_REPLACE({col}, '[^0-9,]', '', 'g'), '.', ''), ',', '.') AS DECIMAL(10,2)), 0.00)
    ELSE
        COALESCE(TRY_CAST(REGEXP_REPLACE({col}, '[^0-9.]', '', 'g') AS DECIMAL(10,2)), 0.00)
END
"""

SQL_CLEAN_BOOL = """
CASE
    WHEN LOWER(TRIM({col})) IN ('true', '1', 'sim') THEN TRUE
    WHEN LOWER(TRIM({col})) IN ('false', '0', 'não', 'nao') THEN FALSE
    ELSE FALSE
END
"""

SQL_NORM_SPECIALTY = """
CASE
    WHEN LOWER({col}) LIKE '%el%trica%' THEN 'Elétrica'
    WHEN LOWER({col}) LIKE '%hidr%ulica%' THEN 'Hidráulica'
    WHEN LOWER({col}) LIKE '%pintura%' THEN 'Pintura'
    WHEN LOWER({col}) LIKE '%climatiza%' THEN 'Climatização'
    WHEN LOWER({col}) LIKE '%marcenaria%' THEN 'Marcenaria'
    WHEN LOWER({col}) LIKE '%alvenaria%' THEN 'Alvenaria'
    WHEN LOWER({col}) LIKE '%limpeza%' THEN 'Limpeza'
    ELSE TRIM({col})
END
"""

SQL_NORM_STATUS = """
CASE
    WHEN LOWER({col}) LIKE '%conclu%' THEN 'CONCLUIDO'
    WHEN LOWER({col}) LIKE '%cancel%' THEN 'CANCELADO'
    WHEN LOWER({col}) LIKE '%andamento%' THEN 'EM_ANDAMENTO'
    WHEN LOWER({col}) LIKE '%aberto%' THEN 'ABERTO'
    ELSE UPPER(TRIM({col}))
END
"""


def process_silver_clients(conn: duckdb.DuckDBPyConnection) -> int:
    """Processa e higieniza a tabela de clientes da Bronze para a Silver.

    Args:
        conn: Conexão ativa com o DuckDB.

    Returns:
        Total de clientes na camada Silver.
    """
    date_expr = SQL_CLEAN_DATE.format(col="signup_date")
    query = f"""
    CREATE OR REPLACE TABLE silver.clients AS
    SELECT
        client_id::INTEGER AS client_id,
        TRIM(client_name) AS client_name,
        LOWER(TRIM(client_email)) AS client_email,
        REGEXP_REPLACE(client_phone, '[^0-9]', '', 'g') AS client_phone,
        TRIM(client_city) AS client_city,
        UPPER(TRIM(client_state)) AS client_state,
        {date_expr} AS signup_date,
        CURRENT_TIMESTAMP AS _processed_at
    FROM bronze.raw_clients;
    """
    conn.execute(query)
    res = conn.execute("SELECT COUNT(*) FROM silver.clients").fetchone()
    return res[0] if res else 0


def process_silver_contractors(conn: duckdb.DuckDBPyConnection) -> int:
    """Processa e higieniza a tabela de prestadores da Bronze para a Silver.

    Args:
        conn: Conexão ativa com o DuckDB.

    Returns:
        Total de prestadores na camada Silver.
    """
    rate_expr = SQL_CLEAN_CURRENCY.format(col="hourly_rate")
    active_expr = SQL_CLEAN_BOOL.format(col="is_active")
    spec_expr = SQL_NORM_SPECIALTY.format(col="specialty")

    query = f"""
    CREATE OR REPLACE TABLE silver.contractors AS
    SELECT
        contractor_id::INTEGER AS contractor_id,
        TRIM(contractor_name) AS contractor_name,
        {spec_expr} AS specialty,
        {rate_expr} AS hourly_rate,
        experience_years::INTEGER AS experience_years,
        TRIM(city) AS city,
        UPPER(TRIM(state)) AS state,
        {active_expr} AS is_active,
        CURRENT_TIMESTAMP AS _processed_at
    FROM bronze.raw_contractors;
    """
    conn.execute(query)
    res = conn.execute("SELECT COUNT(*) FROM silver.contractors").fetchone()
    return res[0] if res else 0


def process_silver_service_orders(conn: duckdb.DuckDBPyConnection) -> int:
    """Processa e higieniza as ordens de serviço da Bronze para a Silver.

    Args:
        conn: Conexão ativa com o DuckDB.

    Returns:
        Total de ordens de serviço na camada Silver.
    """
    dt_order = SQL_CLEAN_DATE.format(col="order_date")
    dt_sched = SQL_CLEAN_DATE.format(col="scheduled_date")
    dt_comp = SQL_CLEAN_DATE.format(col="completion_date")
    status_expr = SQL_NORM_STATUS.format(col="order_status")
    category_expr = SQL_NORM_SPECIALTY.format(col="service_category")
    quoted_expr = SQL_CLEAN_CURRENCY.format(col="total_quoted_amount")
    final_expr = SQL_CLEAN_CURRENCY.format(col="total_final_amount")

    query = f"""
    CREATE OR REPLACE TABLE silver.service_orders AS
    SELECT
        order_id::INTEGER AS order_id,
        client_id::INTEGER AS client_id,
        contractor_id::INTEGER AS contractor_id,
        {dt_order} AS order_date,
        {dt_sched} AS scheduled_date,
        {dt_comp} AS completion_date,
        {status_expr} AS order_status,
        {category_expr} AS service_category,
        {quoted_expr} AS total_quoted_amount,
        {final_expr} AS total_final_amount,
        NULLIF(TRIM(cancellation_reason), '') AS cancellation_reason,
        CURRENT_TIMESTAMP AS _processed_at
    FROM bronze.raw_service_orders;
    """
    conn.execute(query)
    res = conn.execute("SELECT COUNT(*) FROM silver.service_orders").fetchone()
    return res[0] if res else 0


def process_silver_service_items(conn: duckdb.DuckDBPyConnection) -> int:
    """Processa e higieniza os itens de serviço da Bronze para a Silver.

    Args:
        conn: Conexão ativa com o DuckDB.

    Returns:
        Total de itens na camada Silver.
    """
    unit_expr = SQL_CLEAN_CURRENCY.format(col="unit_price")
    tot_expr = SQL_CLEAN_CURRENCY.format(col="total_price")

    query = f"""
    CREATE OR REPLACE TABLE silver.service_items AS
    SELECT
        item_id::INTEGER AS item_id,
        order_id::INTEGER AS order_id,
        TRIM(item_description) AS item_description,
        CASE
            WHEN LOWER(item_type) LIKE '%labor%' OR LOWER(item_type) LIKE '%m_o de obra%' OR LOWER(item_type) LIKE '%servi_o%' THEN 'LABOR'
            ELSE 'PARTS'
        END AS item_type,
        quantity::INTEGER AS quantity,
        {unit_expr} AS unit_price,
        {tot_expr} AS total_price,
        CURRENT_TIMESTAMP AS _processed_at
    FROM bronze.raw_service_items;
    """
    conn.execute(query)
    res = conn.execute("SELECT COUNT(*) FROM silver.service_items").fetchone()
    return res[0] if res else 0


def process_silver_reviews(conn: duckdb.DuckDBPyConnection) -> int:
    """Processa e higieniza as avaliações da Bronze para a Silver.

    Args:
        conn: Conexão ativa com o DuckDB.

    Returns:
        Total de avaliações na camada Silver.
    """
    bool_expr = SQL_CLEAN_BOOL.format(col="incident_reported")
    date_expr = SQL_CLEAN_DATE.format(col="review_date")

    query = f"""
    CREATE OR REPLACE TABLE silver.reviews AS
    SELECT
        review_id::INTEGER AS review_id,
        order_id::INTEGER AS order_id,
        rating::INTEGER AS rating,
        TRIM(review_comment) AS review_comment,
        {bool_expr} AS incident_reported,
        CASE
            WHEN {bool_expr} THEN TRIM(incident_type)
            ELSE 'Nenhum'
        END AS incident_type,
        {date_expr} AS review_date,
        CURRENT_TIMESTAMP AS _processed_at
    FROM bronze.raw_reviews;
    """
    conn.execute(query)
    res = conn.execute("SELECT COUNT(*) FROM silver.reviews").fetchone()
    return res[0] if res else 0


def run_silver_processing(
    db_path: Path | str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, int]:
    """Executa a sanitização e carga completa de todas as entidades na Silver.

    Args:
        db_path: Caminho opcional do arquivo DuckDB.
        conn: Conexão opcional com o DuckDB.

    Returns:
        Dicionário com a contagem de registros processados por tabela Silver.
    """
    active_conn = conn if conn is not None else get_connection(db_path=db_path)
    results: dict[str, int] = {}

    try:
        results["silver.clients"] = process_silver_clients(active_conn)
        results["silver.contractors"] = process_silver_contractors(active_conn)
        results["silver.service_orders"] = process_silver_service_orders(active_conn)
        results["silver.service_items"] = process_silver_service_items(active_conn)
        results["silver.reviews"] = process_silver_reviews(active_conn)
    finally:
        if conn is None:
            active_conn.close()

    return results


if __name__ == "__main__":
    counts = run_silver_processing()
    print("[OK] Processamento Silver finalizado com sucesso:")
    for tbl, count in counts.items():
        print(f"  - {tbl}: {count} registros")
