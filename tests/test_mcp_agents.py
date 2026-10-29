"""Suíte de testes para a camada de IA Agêntica e Servidor MCP HomeFix.

Valida a execução das ferramentas analíticas, conformidade do servidor MCP
com o catálogo de tools, e o comportamento do agente OperationalDiagnosticBot.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import duckdb
import pytest

from agents.bot import OperationalDiagnosticBot
from agents.mcp_server import (
    server,
    tool_diagnose_marketplace_health,
    tool_get_contractor_scorecard,
    tool_get_gmv_by_specialty,
    tool_get_incidents_churn,
    tool_get_resolution_rate,
)
from agents.tools import (
    diagnose_marketplace_health,
    get_contractor_scorecard,
    get_gmv_by_specialty,
    get_incidents_churn,
    get_resolution_rate,
)
from scripts.bronze_ingestion import run_bronze_ingestion
from scripts.connection import get_connection
from scripts.gold_processing import run_gold_processing
from scripts.silver_processing import run_silver_processing


@pytest.fixture
def populated_conn() -> duckdb.DuckDBPyConnection:
    """Fixture que retorna conexão em memória com o banco totalmente populado."""
    conn = get_connection(db_path=":memory:")
    run_bronze_ingestion(raw_dir="data/raw", conn=conn)
    run_silver_processing(conn=conn)
    run_gold_processing(conn=conn)
    yield conn
    conn.close()


def test_tools_gmv_by_specialty(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida a ferramenta de GMV por especialidade."""
    res_all = get_gmv_by_specialty(conn=populated_conn)
    assert len(res_all) > 0
    assert "total_gmv" in res_all[0]
    assert "share_of_total_gmv_pct" in res_all[0]

    # Filtro min_orders
    res_filtered = get_gmv_by_specialty(min_orders=1000, conn=populated_conn)
    assert len(res_filtered) == 0


def test_tools_contractor_scorecard(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida a ferramenta de scorecard de prestadores."""
    res_all = get_contractor_scorecard(conn=populated_conn)
    assert len(res_all) == 30

    # Filtro por especialidade existente
    first_spec = res_all[0]["specialty"]
    res_spec = get_contractor_scorecard(specialty=first_spec, conn=populated_conn)
    assert len(res_spec) > 0
    assert all(r["specialty"].lower() == first_spec.lower() for r in res_spec)

    # Filtro por nota mínima
    res_rating = get_contractor_scorecard(min_rating=4.5, conn=populated_conn)
    assert all(r["avg_rating"] >= 4.5 for r in res_rating)


def test_tools_resolution_rate(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida a ferramenta de taxa de resolução."""
    res = get_resolution_rate(conn=populated_conn)
    assert len(res) > 0
    assert "resolution_rate_pct" in res[0]
    assert "cancellation_rate_pct" in res[0]

    # Filtro por cancelamento mínimo alto
    res_high = get_resolution_rate(min_cancellation_pct=99.0, conn=populated_conn)
    assert len(res_high) == 0


def test_tools_incidents_churn(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida a ferramenta de incidentes e churn."""
    res = get_incidents_churn(conn=populated_conn)
    assert len(res) > 0

    # Filtro por ALTO_RISCO_CHURN
    res_churn = get_incidents_churn(
        churn_status="ALTO_RISCO_CHURN", conn=populated_conn
    )
    assert all(r["churn_risk_status"] == "ALTO_RISCO_CHURN" for r in res_churn)


def test_tools_diagnose_marketplace_health(
    populated_conn: duckdb.DuckDBPyConnection,
) -> None:
    """Valida o diagnóstico executivo integrado."""
    diag = diagnose_marketplace_health(conn=populated_conn)
    assert "summary" in diag
    assert "alerts" in diag
    assert "top_specialties_by_gmv" in diag
    assert diag["summary"]["total_gmv"] > 0
    assert diag["summary"]["total_orders"] == 500


def test_tools_disk_without_conn(tmp_path: Path) -> None:
    """Valida as ferramentas utilizando caminho de arquivo físico sem passar conexão."""
    db_file = tmp_path / "tools_disk.duckdb"
    run_bronze_ingestion(raw_dir="data/raw", db_path=db_file)
    run_silver_processing(db_path=db_file)
    run_gold_processing(db_path=db_file)

    diag = diagnose_marketplace_health(db_path=db_file)
    assert diag["summary"]["total_orders"] == 500


def test_mcp_server_tools_registration() -> None:
    """Garante que todas as 5 ferramentas MCP foram devidamente registradas."""
    tools = asyncio.run(server.list_tools())
    tool_names = {t.name for t in tools}
    expected_tools = {
        "tool_get_gmv_by_specialty",
        "tool_get_contractor_scorecard",
        "tool_get_resolution_rate",
        "tool_get_incidents_churn",
        "tool_diagnose_marketplace_health",
    }
    assert expected_tools.issubset(tool_names)


def test_mcp_server_tool_calls() -> None:
    """Testa a invocação direta das funções expostas pelo MCP Server."""
    # 1. GMV
    gmv_raw = tool_get_gmv_by_specialty(min_orders=0)
    gmv_json = json.loads(gmv_raw)
    assert isinstance(gmv_json, list)

    # 2. Scorecard
    score_raw = tool_get_contractor_scorecard(specialty="", min_rating=0.0)
    score_json = json.loads(score_raw)
    assert isinstance(score_json, list)

    # 3. Resolução
    res_raw = tool_get_resolution_rate(min_cancellation_pct=0.0)
    res_json = json.loads(res_raw)
    assert isinstance(res_json, list)

    # 4. Churn
    churn_raw = tool_get_incidents_churn(churn_status="ALTO_RISCO_CHURN")
    churn_json = json.loads(churn_raw)
    assert isinstance(churn_json, list)

    # 5. Diagnóstico
    diag_raw = tool_diagnose_marketplace_health()
    diag_json = json.loads(diag_raw)
    assert "summary" in diag_json


def test_operational_diagnostic_bot(populated_conn: duckdb.DuckDBPyConnection) -> None:
    """Valida a geração de relatórios e atendimento a perguntas pelo agente inteligente."""
    bot = OperationalDiagnosticBot()

    # Relatório executivo
    report = bot.generate_executive_diagnosis(conn=populated_conn)
    assert "# 📋 Relatório de Diagnóstico Operacional" in report
    assert "Recomendações Estratégicas" in report
    assert "GMV" in report

    # Teste de roteamento de consultas em linguagem natural
    resp_gmv = bot.answer_query("Qual o GMV por especialidade?", conn=populated_conn)
    assert "Análise de GMV" in resp_gmv

    resp_contractor = bot.answer_query(
        "Mostre o ranking de prestadores", conn=populated_conn
    )
    assert "Ranking dos Principais Prestadores" in resp_contractor

    resp_cancel = bot.answer_query(
        "Qual a taxa de cancelamento e resolução?", conn=populated_conn
    )
    assert "Taxa de Resolução" in resp_cancel

    resp_churn = bot.answer_query(
        "Temos problemas de churn ou incidentes?", conn=populated_conn
    )
    assert "Alerta de Incidentes e Evasão" in resp_churn

    resp_default = bot.answer_query(
        "Gere um diagnóstico geral do sistema", conn=populated_conn
    )
    assert "Relatório de Diagnóstico Operacional" in resp_default


def test_bot_with_mocked_clean_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida relatório do bot quando não há alertas operacionais críticos."""
    bot = OperationalDiagnosticBot()

    def mock_clean_health(**kwargs: object) -> dict:
        return {
            "summary": {
                "total_gmv": 50000.0,
                "total_orders": 100,
                "completed_orders": 95,
                "global_resolution_pct": 95.0,
                "total_specialties": 5,
            },
            "alerts": {
                "critical_categories_count": 0,
                "critical_categories": [],
                "underperforming_contractors_count": 0,
                "underperforming_contractors": [],
                "churn_risk_clients_count": 0,
            },
            "top_specialties_by_gmv": [
                {
                    "specialty": "Elétrica",
                    "total_gmv": 20000.0,
                    "share_of_total_gmv_pct": 40.0,
                    "avg_ticket": 400.0,
                }
            ],
        }

    monkeypatch.setattr("agents.bot.diagnose_marketplace_health", mock_clean_health)
    report = bot.generate_executive_diagnosis()
    assert "Nenhuma categoria com taxa de cancelamento superior a 15%" in report
    assert "Nenhum prestador crítico identificado" in report
