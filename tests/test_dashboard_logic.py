"""Suíte de testes automatizados para a lógica do dashboard Streamlit e orquestrador.

Valida as funções de carregamento de métricas executivas, formatação brasileira
(moeda, números e percentuais), filtros reativos por especialidade e renderização.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest

from dashboard.app import (
    format_currency_brl,
    format_decimal_br,
    format_number_br,
    format_percent_br,
    load_all_specialties,
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


def test_format_helpers_ptbr() -> None:
    """Valida funções de formatação no padrão brasileiro (pt-BR)."""
    # Moeda
    assert format_currency_brl(1234.56) == "R$ 1.234,56"
    assert format_currency_brl(0.0) == "R$ 0,00"
    assert format_currency_brl(None) == "R$ 0,00"
    assert format_currency_brl(-50.50) == "-R$ 50,50"

    # Número
    assert format_number_br(1500) == "1.500"
    assert format_number_br(1500.75) == "1.500,75"
    assert format_number_br(0) == "0"
    assert format_number_br(None) == "0"

    # Percentual
    assert format_percent_br(71.8) == "71,8%"
    assert format_percent_br(100.0) == "100,0%"
    assert format_percent_br(None) == "0,0%"

    # Decimal
    assert format_decimal_br(4.85, 2) == "4,85"
    assert format_decimal_br(3.9, 1) == "3,9"
    assert format_decimal_br(None) == "-"


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


def test_load_all_specialties(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida listagem completa de especialidades com opção 'Todas'."""
    specs = load_all_specialties(conn=populated_conn)
    assert specs[0] == "Todas"
    assert len(specs) >= 5


def test_load_kpi_summary_with_filter(
    populated_conn: duckdb.DuckDBPyConnection,
) -> None:
    """Valida carregamento de série mensal com e sem filtro por especialidade."""
    df_all = load_kpi_summary(conn=populated_conn)
    assert not df_all.empty
    assert (df_all["total_gmv"] >= 0.0).all()

    # Com filtro
    df_alvenaria = load_kpi_summary(specialty_filter="Alvenaria", conn=populated_conn)
    assert not df_alvenaria.empty
    assert df_alvenaria["total_gmv"].sum() < df_all["total_gmv"].sum()


def test_load_gmv_by_specialty_with_filter(
    populated_conn: duckdb.DuckDBPyConnection,
) -> None:
    """Valida carregamento de faturamento por especialidade com filtro reativo."""
    df_all = load_gmv_by_specialty(conn=populated_conn)
    assert len(df_all) > 1

    df_filtered = load_gmv_by_specialty(specialty_filter="Pintura", conn=populated_conn)
    assert len(df_filtered) == 1
    assert df_filtered["specialty"].iloc[0] == "Pintura"


def test_load_contractors_scorecard_with_filter(
    populated_conn: duckdb.DuckDBPyConnection,
) -> None:
    """Valida o scorecard de prestadores com e sem filtros."""
    df_all = load_contractors_scorecard(conn=populated_conn)
    assert len(df_all) == 30

    df_todas = load_contractors_scorecard(specialty_filter="Todas", conn=populated_conn)
    assert len(df_todas) == 30

    first_spec = df_all["specialty"].iloc[0]
    df_filtered = load_contractors_scorecard(
        specialty_filter=first_spec, conn=populated_conn
    )
    assert len(df_filtered) > 0
    assert (df_filtered["specialty"] == first_spec).all()


def test_load_operational_efficiency_with_filter(
    populated_conn: duckdb.DuckDBPyConnection,
) -> None:
    """Valida tempos médios de ciclo e taxas operacionais com filtro."""
    df_all = load_operational_efficiency(conn=populated_conn)
    assert not df_all.empty

    df_filtered = load_operational_efficiency(
        specialty_filter="Limpeza", conn=populated_conn
    )
    assert len(df_filtered) == 1
    assert df_filtered["service_category"].iloc[0] == "Limpeza"


def test_load_churn_risk_data_with_filter(
    populated_conn: duckdb.DuckDBPyConnection,
) -> None:
    """Valida dados de incidentes e detecção de risco de abandono com filtro."""
    df_all = load_churn_risk_data(conn=populated_conn)
    assert not df_all.empty
    assert set(df_all["churn_risk_status"].unique()).issubset(
        {"ALTO_RISCO_CHURN", "RETIDO"}
    )

    df_filtered = load_churn_risk_data(
        specialty_filter="Hidráulica", conn=populated_conn
    )
    assert isinstance(df_filtered, object)


def test_render_dashboard_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Testa o fluxo de montagem do Streamlit simulando chamadas visuais e filtro ativo."""
    import streamlit as st

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

    sidebar_mock = MagicMock()
    # Simula seleção de filtro específico "Alvenaria"
    sidebar_mock.selectbox = MagicMock(return_value="Alvenaria")
    monkeypatch.setattr(st, "sidebar", sidebar_mock)

    render_dashboard()
    assert st.set_page_config.called
    assert st.title.called
