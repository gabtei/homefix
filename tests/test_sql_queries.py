"""Suíte de testes para a Camada Gold e repositório de consultas analíticas SQL.

Valida a criação e consistência das tabelas dimensionais e fatos (dim_clients,
dim_contractors, fct_orders, kpi_monthly_summary) e a integridade de execução
das consultas analíticas (CTEs, Window Functions, taxas de resolução e churn).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from scripts.bronze_ingestion import run_bronze_ingestion
from scripts.connection import get_connection
from scripts.gold_processing import (
    process_gold_dim_clients,
    process_gold_dim_contractors,
    process_gold_fct_orders,
    process_gold_kpi_monthly_summary,
    run_gold_processing,
)
from scripts.silver_processing import run_silver_processing

QUERIES_DIR = Path("data/queries")


@pytest.fixture
def populated_conn() -> duckdb.DuckDBPyConnection:
    """Fixture que fornece banco em memória com Bronze, Silver e Gold carregadas."""
    conn = get_connection(db_path=":memory:")
    run_bronze_ingestion(raw_dir="data/raw", conn=conn)
    run_silver_processing(conn=conn)
    run_gold_processing(conn=conn)
    yield conn
    conn.close()


def test_gold_tables_integrity(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida a integridade volumétrica e de schemas da Camada Gold."""
    # dim_clients
    df_clients = populated_conn.execute("SELECT * FROM gold.dim_clients").df()
    assert len(df_clients) == 100
    assert (df_clients["total_orders_placed"] >= 0).all()
    assert (df_clients["total_spend"] >= 0.00).all()

    # dim_contractors
    df_contractors = populated_conn.execute("SELECT * FROM gold.dim_contractors").df()
    assert len(df_contractors) == 30
    assert (df_contractors["completion_rate_pct"].between(0.0, 100.0)).all()
    assert (df_contractors["avg_rating"].between(0.0, 5.0)).all()

    # fct_orders
    df_orders = populated_conn.execute("SELECT * FROM gold.fct_orders").df()
    assert len(df_orders) == 500
    assert (df_orders["lead_time_days"] >= 0).all()

    # kpi_monthly_summary
    df_monthly = populated_conn.execute("SELECT * FROM gold.kpi_monthly_summary").df()
    assert len(df_monthly) > 0
    assert (df_monthly["total_gmv"] >= 0.00).all()
    assert (df_monthly["completion_rate_pct"].between(0.0, 100.0)).all()


def test_individual_gold_functions(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Testa a execução individual de cada gerador da Camada Gold."""
    assert process_gold_dim_clients(populated_conn) == 100
    assert process_gold_dim_contractors(populated_conn) == 30
    assert process_gold_fct_orders(populated_conn) == 500
    assert process_gold_kpi_monthly_summary(populated_conn) > 0


def test_gold_processing_disk_without_conn(tmp_path: Path) -> None:
    """Testa orquestração Gold em disco com abertura e fechamento automático de conexão."""
    db_file = tmp_path / "gold_disk.duckdb"
    run_bronze_ingestion(raw_dir="data/raw", db_path=db_file)
    run_silver_processing(db_path=db_file)
    gold_counts = run_gold_processing(db_path=db_file)

    assert len(gold_counts) == 4
    for count in gold_counts.values():
        assert count > 0


def test_query_kpi_gmv_by_specialty(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida a consulta analítica de GMV por especialidade com CTEs."""
    sql_path = QUERIES_DIR / "kpi_gmv_by_specialty.sql"
    assert sql_path.exists()

    query = sql_path.read_text(encoding="utf-8")
    df = populated_conn.execute(query).df()

    assert len(df) > 0
    required_cols = {
        "specialty",
        "total_orders",
        "completed_orders",
        "canceled_orders",
        "total_gmv",
        "avg_ticket",
        "share_of_total_gmv_pct",
    }
    assert required_cols.issubset(set(df.columns))

    # GMV deve ser estritamente decrescente
    gmvs = df["total_gmv"].tolist()
    assert gmvs == sorted(gmvs, reverse=True)

    # A soma das participações relativas deve se aproximar de 100%
    assert 99.0 <= df["share_of_total_gmv_pct"].sum() <= 101.0


def test_query_kpi_contractor_scorecard(
    populated_conn: duckdb.DuckDBPyConnection,
) -> None:
    """Valida o scorecard de prestadores com Window Functions."""
    sql_path = QUERIES_DIR / "kpi_contractor_scorecard.sql"
    assert sql_path.exists()

    query = sql_path.read_text(encoding="utf-8")
    df = populated_conn.execute(query).df()

    assert len(df) == 30
    required_cols = {
        "contractor_id",
        "contractor_name",
        "specialty",
        "total_gmv",
        "avg_rating",
        "specialty_avg_rating",
        "specialty_avg_gmv",
        "rank_in_specialty",
        "overall_gmv_rank",
    }
    assert required_cols.issubset(set(df.columns))

    # Cada especialidade deve ter o rank 1 presente
    for specialty in df["specialty"].unique():
        sub = df[df["specialty"] == specialty]
        assert 1 in sub["rank_in_specialty"].values


def test_query_kpi_resolution_rate(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida a taxa de resolução e ciclo operacional por categoria."""
    sql_path = QUERIES_DIR / "kpi_resolution_rate.sql"
    assert sql_path.exists()

    query = sql_path.read_text(encoding="utf-8")
    df = populated_conn.execute(query).df()

    assert len(df) > 0
    required_cols = {
        "service_category",
        "total_orders",
        "completed_orders",
        "canceled_orders",
        "resolution_rate_pct",
        "cancellation_rate_pct",
        "avg_cycle_time_days",
    }
    assert required_cols.issubset(set(df.columns))
    assert (df["resolution_rate_pct"].between(0.0, 100.0)).all()
    assert (df["cancellation_rate_pct"].between(0.0, 100.0)).all()


def test_query_joins_incidents_churn(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida a consulta com múltiplos JOINs mapeando incidentes e risco de churn."""
    sql_path = QUERIES_DIR / "joins_incidents_churn.sql"
    assert sql_path.exists()

    query = sql_path.read_text(encoding="utf-8")
    df = populated_conn.execute(query).df()

    assert len(df) > 0
    required_cols = {
        "order_id",
        "client_id",
        "client_name",
        "contractor_name",
        "contractor_specialty",
        "rating",
        "incident_type",
        "churn_risk_status",
    }
    assert required_cols.issubset(set(df.columns))
    assert set(df["churn_risk_status"].unique()).issubset(
        {"ALTO_RISCO_CHURN", "RETIDO"}
    )
