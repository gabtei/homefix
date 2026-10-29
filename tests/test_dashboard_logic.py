"""Suíte de testes automatizados para a lógica do dashboard Streamlit e orquestrador.

Valida as funções de carregamento de métricas executivas, agregação de GMV,
scorecard de prestadores com filtros, análise de churn e a execução ponta a ponta
do orquestrador run_pipeline.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest

from dashboard.app import (
    load_churn_risk_data,
    load_contractors_scorecard,
    load_gmv_by_specialty,
    load_kpi_summary,
    load_operational_efficiency,
    render_dashboard,
)
from scripts.bronze_ingestion import run_bronze_ingestion
from scripts.connection import get_connection
from scripts.gold_processing import run_gold_processing
from scripts.run_pipeline import run_pipeline
from scripts.silver_processing import run_silver_processing


@pytest.fixture
def populated_conn() -> duckdb.DuckDBPyConnection:
    """Fixture com banco DuckDB em memória populado com Bronze, Silver e Gold."""
    conn = get_connection(db_path=":memory:")
    run_bronze_ingestion(raw_dir="data/raw", conn=conn)
    run_silver_processing(conn=conn)
    run_gold_processing(conn=conn)
    yield conn
    conn.close()


def test_run_pipeline_orchestrator(tmp_path: Path) -> None:
    """Testa a execução sequencial do orquestrador de pipeline em disco."""
    db_file = tmp_path / "orchestrator_test.duckdb"
    res = run_pipeline(raw_dir="data/raw", db_path=db_file)

    assert res["status"] == "SUCCESS"
    assert res["elapsed_seconds"] >= 0.0
    assert len(res["bronze"]) == 5
    assert len(res["silver"]) == 5
    assert len(res["gold"]) == 4

    conn = get_connection(db_path=db_file, read_only=True)
    assert conn.execute("SELECT COUNT(*) FROM gold.fct_orders;").fetchone()[0] == 500
    conn.close()


def test_load_kpi_summary(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida carregamento da série histórica mensal para os gráficos de tendência."""
    df = load_kpi_summary(conn=populated_conn)
    assert not df.empty
    expected_cols = {
        "order_month",
        "total_orders",
        "completed_orders",
        "canceled_orders",
        "total_gmv",
        "avg_rating",
    }
    assert expected_cols.issubset(set(df.columns))
    assert (df["total_gmv"] >= 0.0).all()


def test_load_gmv_by_specialty(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida carregamento de faturamento por especialidade."""
    df = load_gmv_by_specialty(conn=populated_conn)
    assert len(df) > 0
    assert "specialty" in df.columns
    assert "total_gmv" in df.columns
    assert "resolution_rate_pct" in df.columns


def test_load_contractors_scorecard(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida o scorecard de prestadores com e sem filtros."""
    # Sem filtro
    df_all = load_contractors_scorecard(conn=populated_conn)
    assert len(df_all) == 30

    # Filtro 'Todas'
    df_todas = load_contractors_scorecard(specialty_filter="Todas", conn=populated_conn)
    assert len(df_todas) == 30

    # Filtro por especialidade
    first_spec = df_all["specialty"].iloc[0]
    df_filtered = load_contractors_scorecard(
        specialty_filter=first_spec, conn=populated_conn
    )
    assert len(df_filtered) > 0
    assert (df_filtered["specialty"] == first_spec).all()


def test_load_operational_efficiency(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida tempos médios de ciclo e taxas operacionais."""
    df = load_operational_efficiency(conn=populated_conn)
    assert not df.empty
    assert "avg_cycle_time_days" in df.columns
    assert "cancellation_rate_pct" in df.columns
    assert (df["resolution_rate_pct"].between(0.0, 100.0)).all()


def test_load_churn_risk_data(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida dados de incidentes e detecção de risco de abandono."""
    df = load_churn_risk_data(conn=populated_conn)
    assert not df.empty
    assert "churn_risk_status" in df.columns
    assert "incident_type" in df.columns
    assert set(df["churn_risk_status"].unique()).issubset(
        {"ALTO_RISCO_CHURN", "RETIDO"}
    )


def test_render_dashboard_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Testa o fluxo de montagem do Streamlit simulando chamadas visuais."""
    import streamlit as st

    # Mock das funções do Streamlit para testar a renderização sem abrir servidor web
    monkeypatch.setattr(st, "set_page_config", MagicMock())
    monkeypatch.setattr(st, "title", MagicMock())
    monkeypatch.setattr(st, "markdown", MagicMock())
    monkeypatch.setattr(st, "write", MagicMock())
    monkeypatch.setattr(st, "metric", MagicMock())
    monkeypatch.setattr(
        st,
        "columns",
        lambda n: [MagicMock() for _ in range(n if isinstance(n, int) else len(n))],
    )
    monkeypatch.setattr(st, "tabs", lambda names: [MagicMock() for _ in names])
    monkeypatch.setattr(st, "subheader", MagicMock())
    monkeypatch.setattr(st, "dataframe", MagicMock())
    monkeypatch.setattr(st, "line_chart", MagicMock())
    monkeypatch.setattr(st, "bar_chart", MagicMock())
    monkeypatch.setattr(st, "warning", MagicMock())
    monkeypatch.setattr(st, "info", MagicMock())

    # Mock do sidebar
    sidebar_mock = MagicMock()
    sidebar_mock.selectbox = MagicMock(return_value="Todas")
    monkeypatch.setattr(st, "sidebar", sidebar_mock)

    # Executa a renderização completa
    render_dashboard()
    assert st.set_page_config.called
    assert st.title.called
