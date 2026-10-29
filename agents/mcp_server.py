"""Servidor Model Context Protocol (MCP) da plataforma HomeFix.

Disponibiliza ferramentas de análise de negócio, scorecards e diagnóstico
operacional sobre o motor DuckDB para agentes de inteligência artificial.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from mcp.server.mcpserver import MCPServer

from agents.tools import (
    diagnose_marketplace_health,
    get_contractor_scorecard,
    get_gmv_by_specialty,
    get_incidents_churn,
    get_resolution_rate,
)

server = MCPServer(
    name="homefix-analytics",
    instructions=(
        "Servidor MCP para análise e diagnóstico da operação do marketplace HomeFix. "
        "Permite consultar indicadores de GMV, taxas de resolução, scorecard de prestadores "
        "e clientes sob risco de evasão (churn)."
    ),
)


@server.tool()
def tool_get_gmv_by_specialty(min_orders: int = 0) -> str:
    """Retorna métricas de volume bruto (GMV) e representatividade (%) por especialidade.

    Args:
        min_orders: Volume mínimo de ordens para filtragem.
    """
    data = get_gmv_by_specialty(min_orders=min_orders)
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


@server.tool()
def tool_get_contractor_scorecard(specialty: str = "", min_rating: float = 0.0) -> str:
    """Retorna scorecard e rankings de prestadores calculados com Window Functions.

    Args:
        specialty: Nome da especialidade para filtro opcional (ex: 'Elétrica').
        min_rating: Nota média mínima de avaliação para filtro.
    """
    filter_spec = specialty.strip() if specialty.strip() else None
    data = get_contractor_scorecard(specialty=filter_spec, min_rating=min_rating)
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


@server.tool()
def tool_get_resolution_rate(min_cancellation_pct: float = 0.0) -> str:
    """Retorna taxas de resolução, cancelamento e lead time por categoria de serviço.

    Args:
        min_cancellation_pct: Filtro para retornar categorias com taxa de cancelamento >= %.
    """
    data = get_resolution_rate(min_cancellation_pct=min_cancellation_pct)
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


@server.tool()
def tool_get_incidents_churn(churn_status: str = "") -> str:
    """Retorna incidentes operacionais correlacionados a clientes em risco de abandono (churn).

    Args:
        churn_status: Filtro opcional: 'ALTO_RISCO_CHURN' ou 'RETIDO'.
    """
    filter_status = churn_status.strip() if churn_status.strip() else None
    data = get_incidents_churn(churn_status=filter_status)
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


@server.tool()
def tool_diagnose_marketplace_health() -> str:
    """Gera diagnóstico analítico consolidado sobre a saúde operacional do marketplace HomeFix."""
    data = diagnose_marketplace_health()
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


if __name__ == "__main__":
    print(
        "[OK] Iniciando servidor MCP HomeFix (transporte padrão stdio)...",
        file=sys.stderr,
    )
    server.run()
