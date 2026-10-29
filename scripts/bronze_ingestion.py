"""Módulo de ingestão da camada Bronze no DuckDB.

Carrega os 5 arquivos CSV brutos gerados na Fase 1 para o esquema 'bronze'
do DuckDB, adicionando metadados de auditoria (_ingested_at) sem alterar
os dados de origem.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import duckdb

from scripts.connection import get_connection

BRONZE_TABLE_MAP = {
    "clients.csv": "bronze.raw_clients",
    "contractors.csv": "bronze.raw_contractors",
    "service_orders.csv": "bronze.raw_service_orders",
    "service_items.csv": "bronze.raw_service_items",
    "reviews.csv": "bronze.raw_reviews",
}


def ingest_bronze_table(
    csv_path: Path,
    table_name: str,
    conn: duckdb.DuckDBPyConnection,
) -> int:
    """Ingere um arquivo CSV bruto em uma tabela no esquema bronze do DuckDB.

    Args:
        csv_path: Caminho do arquivo CSV de origem.
        table_name: Nome qualificado da tabela de destino (ex: bronze.raw_clients).
        conn: Conexão ativa com o DuckDB.

    Returns:
        Total de registros inseridos na tabela.

    Raises:
        FileNotFoundError: Se o arquivo CSV de origem não existir.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {csv_path}")

    # Normaliza caminho para sintaxe SQL (forward slashes)
    clean_csv_path = str(csv_path.resolve()).replace("\\", "/")

    query = f"""
    CREATE OR REPLACE TABLE {table_name} AS
    SELECT
        *,
        CURRENT_TIMESTAMP AS _ingested_at
    FROM read_csv('{clean_csv_path}', all_varchar=True, header=True);
    """
    conn.execute(query)

    count_result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    count = count_result[0] if count_result else 0
    return count


def run_bronze_ingestion(
    raw_dir: Path | str = "data/raw",
    db_path: Path | str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, int]:
    """Executa a ingestão completa dos 5 arquivos brutos para a camada Bronze.

    Args:
        raw_dir: Diretório raiz contendo os arquivos CSV.
        db_path: Caminho opcional do arquivo DuckDB.
        conn: Conexão opcional com o DuckDB. Se None, cria ou utiliza o padrão.

    Returns:
        Dicionário mapeando cada tabela para o total de linhas ingeridas.
    """
    active_conn = conn if conn is not None else get_connection(db_path=db_path)
    base_raw = Path(raw_dir)
    results: dict[str, int] = {}

    try:
        for csv_filename, table_name in BRONZE_TABLE_MAP.items():
            csv_path = base_raw / csv_filename
            count = ingest_bronze_table(csv_path, table_name, active_conn)
            results[table_name] = count
    finally:
        if conn is None:
            active_conn.close()

    return results


if __name__ == "__main__":
    counts = run_bronze_ingestion()
    print("[OK] Ingestao Bronze finalizada com sucesso:")
    for tbl, count in counts.items():
        print(f"  - {tbl}: {count} registros")
