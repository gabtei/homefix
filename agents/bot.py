"""Agente inteligente de diagnóstico operacional para o marketplace HomeFix.

Interpreta métricas analíticas provenientes das ferramentas MCP e gera
relatórios de saúde operacional, triagem de incidentes e planos de ação
para contenção de churn e otimização de GMV.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import duckdb

from agents.tools import (
    diagnose_marketplace_health,
    get_contractor_scorecard,
    get_gmv_by_specialty,
    get_incidents_churn,
    get_resolution_rate,
)


class OperationalDiagnosticBot:
    """Agente especialista em diagnóstico de performance e operações do HomeFix."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Inicializa o agente com o caminho opcional do banco de dados.

        Args:
            db_path: Caminho do arquivo DuckDB ou None para usar o padrão.
        """
        self.db_path = db_path

    def run_health_check(
        self,
        conn: duckdb.DuckDBPyConnection | None = None,
    ) -> dict[str, Any]:
        """Executa a checagem consolidada de saúde da operação.

        Args:
            conn: Conexão opcional com DuckDB.

        Returns:
            Dicionário com diagnóstico estruturado.
        """
        return diagnose_marketplace_health(db_path=self.db_path, conn=conn)

    def generate_executive_diagnosis(
        self,
        conn: duckdb.DuckDBPyConnection | None = None,
    ) -> str:
        """Elabora um relatório executivo formal em Markdown para a diretoria.

        Args:
            conn: Conexão opcional com DuckDB.

        Returns:
            String contendo o relatório executivo formatado em Markdown.
        """
        data = self.run_health_check(conn=conn)
        summary = data["summary"]
        alerts = data["alerts"]
        top_spec = data["top_specialties_by_gmv"]

        # Formata destaques das especialidades líderes
        top_spec_lines = [
            f"- **{s['specialty']}:** R$ {s['total_gmv']:,.2f} ({s['share_of_total_gmv_pct']}% do GMV) | Ticket Médio: R$ {s['avg_ticket']:,.2f}"
            for s in top_spec
        ]
        top_spec_str = "\n".join(top_spec_lines)

        # Formata alertas de categorias críticas
        if alerts["critical_categories"]:
            crit_lines = [
                f"- **{c['service_category']}:** Taxa de cancelamento de **{c['cancellation_rate_pct']}%** (Conclusão: {c['resolution_rate_pct']}%)"
                for c in alerts["critical_categories"]
            ]
            crit_str = "\n".join(crit_lines)
        else:
            crit_str = "- Nenhuma categoria com taxa de cancelamento superior a 15%."

        # Formata prestadores em atenção
        if alerts["underperforming_contractors"]:
            cont_lines = [
                f"- **{p['contractor_name']}** ({p['specialty']}): Nota média **{p['avg_rating']}** | Incidentes: {p['total_incidents']}"
                for p in alerts["underperforming_contractors"][:5]
            ]
            cont_str = "\n".join(cont_lines)
        else:
            cont_str = "- Nenhum prestador crítico identificado."

        report = f"""# 📋 Relatório de Diagnóstico Operacional — HomeFix

## 1. Visão Geral da Operação
- **Volume Transacionado (GMV):** R$ {summary["total_gmv"]:,.2f}
- **Total de Chamados Abertos:** {summary["total_orders"]}
- **Chamados Concluídos com Sucesso:** {summary["completed_orders"]}
- **Taxa Global de Resolução:** **{summary["global_resolution_pct"]}%**

### 🏆 Especialidades com Maior Participação no GMV
{top_spec_str}

---

## 2. Indicadores em Alerta & Gargalos
### ⚠️ Categorias com Alta Taxa de Cancelamento (> 15%)
{crit_str}

### 👤 Prestadores em Ponto de Atenção (Baixo CSAT / Múltiplos Incidentes)
{cont_str}

### 🚨 Risco de Churn Pós-Incidente
- **{alerts["churn_risk_clients_count"]} clientes** sofreram incidentes operacionais e estão classificados como **ALTO RISCO DE CHURN** (não voltaram a comprar no marketplace após a ocorrência).

---

## 3. Recomendações Estratégicas
1. **Contenção Imediata de Churn:** O time de Customer Success deve contatar proativamente os {alerts["churn_risk_clients_count"]} clientes afetados por incidentes, oferecendo bonificação ou resolução assistida.
2. **Capacitação e Credenciamento:** Revisar a alocação de profissionais em categorias com cancelamento elevado e oferecer treinamento para prestadores com CSAT abaixo de 3.5.
3. **Expansão de Oferta:** Intensificar campanhas de aquisição nas 3 principais especialidades em GMV para maximizar o ticket médio do marketplace.
"""
        return report

    def answer_query(
        self,
        prompt: str,
        conn: duckdb.DuckDBPyConnection | None = None,
    ) -> str:
        """Processa perguntas dos operadores e retorna análises personalizadas.

        Args:
            prompt: Pergunta ou comando do usuário em linguagem natural.
            conn: Conexão opcional com DuckDB.

        Returns:
            Resposta analítica estruturada.
        """
        p_lower = prompt.lower()

        if any(
            w in p_lower
            for w in ["diagnostico", "saude", "relatorio", "geral", "visao"]
        ):
            return self.generate_executive_diagnosis(conn=conn)

        if any(
            w in p_lower for w in ["gmv", "faturamento", "receita", "especialidade"]
        ):
            data = get_gmv_by_specialty(db_path=self.db_path, conn=conn)
            total = sum(d["total_gmv"] for d in data)
            lines = [
                f"- **{d['specialty']}:** R$ {d['total_gmv']:,.2f} ({d['share_of_total_gmv_pct']}%) | Ordens: {d['completed_orders']}"
                for d in data
            ]
            return (
                f"### 💰 Análise de GMV por Especialidade\n\n"
                f"**GMV Total Acumulado:** R$ {total:,.2f}\n\n" + "\n".join(lines)
            )

        if any(
            w in p_lower
            for w in ["prestador", "ranking", "scorecard", "avaliacao", "nota"]
        ):
            scorecard = get_contractor_scorecard(db_path=self.db_path, conn=conn)
            top_5 = scorecard[:5]
            lines = [
                f"{i + 1}. **{p['contractor_name']}** ({p['specialty']}): Nota {p['avg_rating']} | GMV: R$ {p['total_gmv']:,.2f} | Rank na especialidade: #{p['rank_in_specialty']}"
                for i, p in enumerate(top_5)
            ]
            return "### ⭐ Ranking dos Principais Prestadores\n\n" + "\n".join(lines)

        if any(
            w in p_lower for w in ["cancelamento", "resolucao", "taxa", "eficiencia"]
        ):
            rates = get_resolution_rate(db_path=self.db_path, conn=conn)
            lines = [
                f"- **{r['service_category']}:** Conclusão: {r['resolution_rate_pct']}% | Cancelamento: {r['cancellation_rate_pct']}% | Tempo médio: {r['avg_cycle_time_days']} dias"
                for r in rates
            ]
            return (
                "### ⏱️ Taxa de Resolução e Cancelamentos por Categoria\n\n"
                + "\n".join(lines)
            )

        if any(w in p_lower for w in ["churn", "incidente", "reclamacao", "problema"]):
            churns = get_incidents_churn(
                churn_status="ALTO_RISCO_CHURN", db_path=self.db_path, conn=conn
            )
            return (
                f"### 🚨 Alerta de Incidentes e Evasão (Churn)\n\n"
                f"Foram identificados **{len(churns)} chamados** com incidentes graves cujos clientes encontram-se em **alto risco de abandono**. "
                f"Recomenda-se acionamento preventivo imediato."
            )

        # Resposta padrão caso a intenção não seja específica
        return self.generate_executive_diagnosis(conn=conn)
