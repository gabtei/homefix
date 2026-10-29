"""Orquestrador do Pipeline Medalhão da plataforma HomeFix.

Executa de forma sequencial e idempotente as três etapas de processamento:
1. Camada Bronze: Ingestão dos CSVs brutos para o DuckDB (bronze.raw_*)
2. Camada Silver: Sanitização de moedas, datas, booleanos e categorias (silver.*)
3. Camada Gold: Construção de dimensões analíticas e tabelas de fatos (gold.*)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import duckdb

from scripts.bronze_ingestion import run_bronze_ingestion
from scripts.connection import get_connection
from scripts.gold_processing import run_gold_processing
from scripts.silver_processing import run_silver_processing


def run_pipeline(
    raw_dir: Path | str = "data/raw",
    db_path: Path | str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """Executa o pipeline completo Bronze -> Silver -> Gold.

    Args:
        raw_dir: Diretório raiz contendo os 5 arquivos CSV brutos.
        db_path: Caminho opcional do arquivo DuckDB (default: data/warehouse/homefix.duckdb).
        conn: Conexão ativa opcional.

    Returns:
        Dicionário com estatísticas de processamento de cada camada e tempo total.
    """
    start_time = time.perf_counter()
    active_conn = conn if conn is not None else get_connection(db_path=db_path)

    try:
        # Etapa 1: Ingestão Bronze
        bronze_results = run_bronze_ingestion(
            raw_dir=raw_dir,
            conn=active_conn,
        )

        # Etapa 2: Processamento Silver
        silver_results = run_silver_processing(
            conn=active_conn,
        )

        # Etapa 3: Modelagem Gold
        gold_results = run_gold_processing(
            conn=active_conn,
        )

        elapsed = round(time.perf_counter() - start_time, 2)

        return {
            "status": "SUCCESS",
            "elapsed_seconds": elapsed,
            "bronze": bronze_results,
            "silver": silver_results,
            "gold": gold_results,
        }
    finally:
        if conn is None:
            active_conn.close()


if __name__ == "__main__":
    print("[*] Iniciando execucao completa do pipeline Medalhao HomeFix...")
    report = run_pipeline()
    print(f"[OK] Pipeline concluido com sucesso em {report['elapsed_seconds']}s:")
    print("  --- Camada Bronze ---")
    for tbl, count in report["bronze"].items():
        print(f"    * {tbl}: {count} linhas")
    print("  --- Camada Silver ---")
    for tbl, count in report["silver"].items():
        print(f"    * {tbl}: {count} linhas")
    print("  --- Camada Gold ---")
    for tbl, count in report["gold"].items():
        print(f"    * {tbl}: {count} linhas")

