"""Agente analítico de linguagem natural para o DuckDB no ecossistema HomeFix.

Interpreta perguntas de negócio dos usuários, traduz em consultas SQL
otimizadas para o DuckDB e retorna respostas ricas e explicativas em Markdown.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import duckdb

from agents.tools import describe_table, execute_query, list_tables


class DuckDBAnalystBot:
    """Agente especialista em interpretar perguntas em linguagem natural e consultar o DuckDB."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Inicializa o bot com o caminho opcional do banco DuckDB.

        Args:
            db_path: Caminho do arquivo de banco ou ':memory:'.
        """
        self.db_path = db_path

    def translate_to_sql(self, question: str) -> str:
        """Traduz uma pergunta em linguagem natural para uma query SQL DuckDB.

        Se o prompt já for uma query SQL válida (iniciando com SELECT, WITH, DESCRIBE ou SHOW),
        retorna a query diretamente. Caso contrário, aplica heurísticas sobre o catálogo.

        Args:
            question: Pergunta em português ou comando SQL.

        Returns:
            Declaração SQL compatível com o DuckDB.
        """
        q = question.strip()
        q_upper = q.upper()

        # Caso seja uma query SQL direta digitada pelo operador
        if q_upper.startswith(("SELECT", "WITH", "DESCRIBE", "SHOW", "EXPLAIN")):
            return q

        q_lower = q.lower()

        # Mapeamento semântico de perguntas comuns para SQL no DuckDB
        if any(w in q_lower for w in ["tabela", "quais tabelas", "esquema"]):
            return (
                "SELECT table_schema, table_name, table_type "
                "FROM information_schema.tables "
                "WHERE table_schema IN ('bronze', 'silver', 'gold') "
                "ORDER BY table_schema, table_name;"
            )

        if any(
            w in q_lower
            for w in [
                "top clientes",
                "maiores clientes",
                "melhores clientes",
                "gasto por cliente",
            ]
        ):
            return (
                "SELECT client_id, client_name, client_city, "
                "total_orders_placed, completed_orders, total_spend, avg_order_value "
                "FROM gold.dim_clients "
                "ORDER BY total_spend DESC "
                "LIMIT 10;"
            )

        if any(
            w in q_lower for w in ["gmv", "faturamento", "receita", "especialidade"]
        ):
            return (
                "SELECT service_category AS specialty, "
                "COUNT(order_id) AS total_orders, "
                "COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END) AS completed_orders, "
                "ROUND(COALESCE(SUM(CASE WHEN order_status = 'CONCLUIDO' THEN total_final_amount ELSE 0 END), 0), 2) AS total_gmv, "
                "ROUND(COALESCE(AVG(CASE WHEN order_status = 'CONCLUIDO' THEN total_final_amount END), 0), 2) AS avg_ticket "
                "FROM silver.service_orders "
                "GROUP BY service_category "
                "ORDER BY total_gmv DESC;"
            )

        if any(
            w in q_lower
            for w in [
                "prestador",
                "ranking",
                "scorecard",
                "melhor",
                "nota",
                "avaliacao",
            ]
        ):
            return (
                "SELECT contractor_id, contractor_name, specialty, city, "
                "total_orders_assigned, completed_orders, completion_rate_pct, "
                "total_gmv_generated, avg_rating, incidents_count "
                "FROM gold.dim_contractors "
                "ORDER BY total_gmv_generated DESC, avg_rating DESC "
                "LIMIT 10;"
            )

        if any(
            w in q_lower for w in ["cancelamento", "resolucao", "taxa", "eficiencia"]
        ):
            return (
                "SELECT service_category, "
                "COUNT(*) AS total_orders, "
                "COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END) AS completed_orders, "
                "COUNT(CASE WHEN order_status = 'CANCELADO' THEN 1 END) AS canceled_orders, "
                "ROUND((COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END)::DOUBLE / COUNT(*)) * 100, 2) AS resolution_rate_pct, "
                "ROUND((COUNT(CASE WHEN order_status = 'CANCELADO' THEN 1 END)::DOUBLE / COUNT(*)) * 100, 2) AS cancellation_rate_pct "
                "FROM silver.service_orders "
                "GROUP BY service_category "
                "ORDER BY resolution_rate_pct DESC;"
            )

        if any(w in q_lower for w in ["churn", "incidente", "reclamacao", "risco"]):
            return (
                "SELECT so.order_id, cl.client_name, cl.client_city, co.contractor_name, "
                "so.service_category, r.rating, r.incident_type, r.review_comment "
                "FROM silver.service_orders so "
                "JOIN silver.clients cl ON so.client_id = cl.client_id "
                "JOIN silver.contractors co ON so.contractor_id = co.contractor_id "
                "JOIN silver.reviews r ON so.order_id = r.order_id "
                "WHERE r.incident_reported = TRUE "
                "ORDER BY so.order_date DESC "
                "LIMIT 10;"
            )

        # Fallback padrão: sumário mensal do marketplace
        return (
            "SELECT * FROM gold.kpi_monthly_summary ORDER BY order_month DESC LIMIT 6;"
        )

    def ask(
        self,
        question: str,
        conn: duckdb.DuckDBPyConnection | None = None,
    ) -> dict[str, Any]:
        """Processa a pergunta do usuário, gera SQL, executa no DuckDB e formata a resposta.

        Args:
            question: Pergunta em linguagem natural ou consulta SQL.
            conn: Conexão ativa opcional.

        Returns:
            Dicionário com a query gerada, dados brutos e texto de resposta em Markdown.
        """
        sql = self.translate_to_sql(question)
        try:
            results = execute_query(sql, conn=conn, db_path=self.db_path)
            error = None
        except (duckdb.Error, ValueError, RuntimeError) as exc:
            results = []
            error = str(exc)

        if error:
            answer = f"⚠️ **Erro na execução da consulta SQL:**\n```sql\n{sql}\n```\n**Detalhe:** {error}"
        elif not results:
            answer = f"ℹ️ A consulta foi executada com sucesso, mas nenhum registro foi retornado.\n```sql\n{sql}\n```"
        else:
            total_rows = len(results)
            answer = (
                f"✅ **Consulta executada com sucesso no DuckDB** ({total_rows} registros retornados):\n\n"
                f"```sql\n{sql}\n```\n\n"
            )

        return {
            "question": question,
            "sql": sql,
            "results": results,
            "error": error,
            "answer": answer,
        }

    def get_available_tables(
        self,
        conn: duckdb.DuckDBPyConnection | None = None,
    ) -> list[dict[str, Any]]:
        """Retorna a lista de tabelas disponíveis nos esquemas analíticos."""
        return list_tables(db_path=self.db_path, conn=conn)

    def inspect_table(
        self,
        table_name: str,
        conn: duckdb.DuckDBPyConnection | None = None,
    ) -> list[dict[str, Any]]:
        """Inspeciona colunas e tipos de dados de uma tabela."""
        return describe_table(table_name, db_path=self.db_path, conn=conn)
