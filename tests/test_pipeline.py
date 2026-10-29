"""Suíte de testes automatizados para o pipeline de dados DuckDB (Bronze & Silver).

Valida a conexão, ingestão integral de arquivos brutos, sanitização de moedas,
padronização de datas para tipo DATE, conversão booleana e normalização categórica.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from scripts.bronze_ingestion import (
    ingest_bronze_table,
    run_bronze_ingestion,
)
from scripts.connection import execute_query, fetch_df, get_connection, init_schemas
from scripts.silver_processing import (
    run_silver_processing,
)


@pytest.fixture
def mem_conn() -> duckdb.DuckDBPyConnection:
    """Fixture que fornece uma conexão limpa em memória com schemas criados."""
    conn = get_connection(db_path=":memory:")
    yield conn
    conn.close()


def test_connection_and_schemas(mem_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida se a conexão em memória inicializa os 3 esquemas medalhão."""
    init_schemas(mem_conn)
    schemas = [
        row[0]
        for row in mem_conn.execute(
            "SELECT schema_name FROM information_schema.schemata;"
        ).fetchall()
    ]
    assert "bronze" in schemas
    assert "silver" in schemas
    assert "gold" in schemas


def test_connection_disk(tmp_path: Path) -> None:
    """Valida conexão persistente em disco e execução de query e fetch_df."""
    db_file = tmp_path / "test_homefix.duckdb"
    conn = get_connection(db_path=db_file)
    execute_query("CREATE TABLE bronze.teste (id INT);", conn=conn)
    execute_query("INSERT INTO bronze.teste VALUES (42);", conn=conn)

    df = fetch_df("SELECT * FROM bronze.teste;", conn=conn)
    assert len(df) == 1
    assert df["id"].iloc[0] == 42
    conn.close()

    # Testa fetch_df sem conexão explícita (abrindo internamente)
    df_disk = fetch_df("SELECT * FROM bronze.teste;", db_path=db_file)
    assert len(df_disk) == 1


def test_execute_query_without_conn(tmp_path: Path) -> None:
    """Testa execute_query abrindo e fechando conexão automaticamente."""
    db_file = tmp_path / "auto_exec.duckdb"
    execute_query("CREATE SCHEMA IF NOT EXISTS bronze;", db_path=db_file)
    execute_query("CREATE TABLE bronze.t (val VARCHAR);", db_path=db_file)
    execute_query("INSERT INTO bronze.t VALUES ('ok');", db_path=db_file)

    df = fetch_df("SELECT * FROM bronze.t;", db_path=db_file)
    assert len(df) == 1
    assert df["val"].iloc[0] == "ok"


def test_bronze_ingestion_file_not_found(mem_conn: duckdb.DuckDBPyConnection) -> None:
    """Garante que tentar ingerir arquivo inexistente levanta FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        ingest_bronze_table(
            Path("data/raw/nao_existe.csv"), "bronze.raw_fake", mem_conn
        )


def test_bronze_ingestion_e2e(mem_conn: duckdb.DuckDBPyConnection) -> None:
    """Testa a ingestão dos 5 CSVs reais para a camada Bronze em memória."""
    results = run_bronze_ingestion(raw_dir="data/raw", conn=mem_conn)

    assert len(results) == 5
    for table_name, count in results.items():
        assert count > 0
        db_count = mem_conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        assert db_count == count

        # Valida que _ingested_at foi gerado
        cols = [c[0] for c in mem_conn.execute(f"DESCRIBE {table_name}").fetchall()]
        assert "_ingested_at" in cols


def test_silver_processing_pipeline(mem_conn: duckdb.DuckDBPyConnection) -> None:
    """Executa o pipeline Bronze -> Silver completo e valida os tipos e consistência."""
    # 1. Ingestão Bronze
    run_bronze_ingestion(raw_dir="data/raw", conn=mem_conn)

    # 2. Processamento Silver
    silver_counts = run_silver_processing(conn=mem_conn)
    assert len(silver_counts) == 5

    # 3. Validações silver.clients
    clients_df = mem_conn.execute("SELECT * FROM silver.clients").df()
    assert len(clients_df) == 100
    assert clients_df["signup_date"].isna().sum() == 0  # 100% das datas convertidas
    assert clients_df["client_phone"].str.contains(r"\D").sum() == 0  # Somente dígitos

    # 4. Validações silver.contractors
    contractors_df = mem_conn.execute("SELECT * FROM silver.contractors").df()
    assert len(contractors_df) == 30
    assert (contractors_df["hourly_rate"] > 0).all()  # Todas as moedas decimais > 0
    assert set(contractors_df["is_active"].unique()).issubset({True, False})

    # Especialidades normalizadas
    valid_specialties = {
        "Elétrica",
        "Hidráulica",
        "Pintura",
        "Climatização",
        "Marcenaria",
        "Alvenaria",
        "Limpeza",
    }
    assert set(contractors_df["specialty"].unique()).issubset(valid_specialties)

    # 5. Validações silver.service_orders
    orders_df = mem_conn.execute("SELECT * FROM silver.service_orders").df()
    assert len(orders_df) == 500
    assert orders_df["order_date"].isna().sum() == 0
    assert set(orders_df["order_status"].unique()) == {
        "CONCLUIDO",
        "CANCELADO",
        "EM_ANDAMENTO",
        "ABERTO",
    }
    # Ordens canceladas devem ter valor final 0.00 e motivo preenchido
    canceled = orders_df[orders_df["order_status"] == "CANCELADO"]
    assert (canceled["total_final_amount"] == 0.00).all()
    assert canceled["cancellation_reason"].notna().all()

    # 6. Validações silver.service_items
    items_df = mem_conn.execute("SELECT * FROM silver.service_items").df()
    assert len(items_df) > 500
    assert set(items_df["item_type"].unique()).issubset({"LABOR", "PARTS"})
    assert (items_df["unit_price"] > 0).all()
    assert (items_df["total_price"] > 0).all()

    # 7. Validações silver.reviews
    reviews_df = mem_conn.execute("SELECT * FROM silver.reviews").df()
    assert len(reviews_df) > 0
    assert reviews_df["rating"].between(1, 5).all()
    assert set(reviews_df["incident_reported"].unique()).issubset({True, False})
    assert reviews_df["review_date"].isna().sum() == 0


def test_run_pipeline_disk_without_conn(tmp_path: Path) -> None:
    """Testa a execução de bronze e silver com criação e fechamento de conexões em disco."""
    db_file = tmp_path / "pipeline_disk.duckdb"

    # Executa bronze sem conn
    bronze_counts = run_bronze_ingestion(raw_dir="data/raw", db_path=db_file)
    assert len(bronze_counts) == 5

    # Executa silver sem conn
    silver_counts = run_silver_processing(db_path=db_file)
    assert len(silver_counts) == 5

    # Conecta para conferir
    conn = get_connection(db_path=db_file, read_only=True)
    assert conn.execute("SELECT COUNT(*) FROM silver.service_orders;").fetchone()[0] == 500
    conn.close()

