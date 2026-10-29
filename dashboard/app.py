"""Painel Analítico Executivo em Streamlit para o Marketplace HomeFix.

Apresenta visualizações consolidadas de faturamento (GMV), ticket médio,
performance de prestadores, eficiência operacional e análise de churn
a partir da Camada Gold do DuckDB.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import duckdb
import pandas as pd
import streamlit as st

from scripts.connection import fetch_df


def load_kpi_summary(
    conn: duckdb.DuckDBPyConnection | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Carrega a série histórica mensal de KPIs consolidados da Camada Gold."""
    query = """
    SELECT
        order_month,
        total_orders,
        completed_orders,
        canceled_orders,
        completion_rate_pct,
        total_gmv,
        avg_ticket,
        avg_rating,
        total_incidents
    FROM gold.kpi_monthly_summary
    ORDER BY order_month ASC;
    """
    return fetch_df(query, conn=conn, db_path=db_path)


def load_gmv_by_specialty(
    conn: duckdb.DuckDBPyConnection | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Carrega o faturamento consolidado e representatividade por especialidade."""
    query = """
    SELECT
        service_category AS specialty,
        COUNT(order_id) AS total_orders,
        COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END) AS completed_orders,
        COUNT(CASE WHEN order_status = 'CANCELADO' THEN 1 END) AS canceled_orders,
        ROUND(COALESCE(SUM(CASE WHEN order_status = 'CONCLUIDO' THEN total_final_amount ELSE 0 END), 0), 2) AS total_gmv,
        ROUND(COALESCE(AVG(CASE WHEN order_status = 'CONCLUIDO' THEN total_final_amount END), 0), 2) AS avg_ticket,
        ROUND(
            (COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END)::DOUBLE / NULLIF(COUNT(order_id), 0)) * 100,
            2
        ) AS resolution_rate_pct
    FROM silver.service_orders
    GROUP BY service_category
    ORDER BY total_gmv DESC;
    """
    return fetch_df(query, conn=conn, db_path=db_path)


def load_contractors_scorecard(
    specialty_filter: str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Carrega o scorecard de prestadores com métricas de GMV e avaliação."""
    where_stmt = ""
    if specialty_filter and specialty_filter != "Todas":
        clean_spec = specialty_filter.replace("'", "''")
        where_stmt = f"WHERE specialty = '{clean_spec}'"

    query = f"""
    SELECT
        contractor_id,
        contractor_name,
        specialty,
        city,
        experience_years,
        total_orders_assigned,
        completed_orders,
        completion_rate_pct,
        total_gmv_generated,
        avg_rating,
        incidents_count,
        is_active
    FROM gold.dim_contractors
    {where_stmt}
    ORDER BY total_gmv_generated DESC, avg_rating DESC;
    """
    return fetch_df(query, conn=conn, db_path=db_path)


def load_operational_efficiency(
    conn: duckdb.DuckDBPyConnection | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Carrega tempos médios de ciclo e taxas de conversão de chamados."""
    query = """
    SELECT
        service_category,
        COUNT(*) AS total_orders,
        COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END) AS completed_orders,
        COUNT(CASE WHEN order_status = 'CANCELADO' THEN 1 END) AS canceled_orders,
        ROUND((COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END)::DOUBLE / NULLIF(COUNT(*), 0)) * 100, 2) AS resolution_rate_pct,
        ROUND((COUNT(CASE WHEN order_status = 'CANCELADO' THEN 1 END)::DOUBLE / NULLIF(COUNT(*), 0)) * 100, 2) AS cancellation_rate_pct,
        ROUND(COALESCE(AVG(cycle_time_days), 0), 1) AS avg_cycle_time_days
    FROM gold.fct_orders
    GROUP BY service_category
    ORDER BY resolution_rate_pct DESC;
    """
    return fetch_df(query, conn=conn, db_path=db_path)


def load_churn_risk_data(
    conn: duckdb.DuckDBPyConnection | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Carrega clientes impactados por incidentes com classificação de risco de churn."""
    query = """
    WITH client_orders AS (
        SELECT
            client_id,
            COUNT(order_id) AS total_orders,
            MAX(order_date) AS last_order_date
        FROM silver.service_orders
        GROUP BY client_id
    )
    SELECT
        so.order_id,
        so.client_id,
        cl.client_name,
        cl.client_city,
        co.contractor_name,
        so.service_category,
        so.order_date,
        so.total_final_amount,
        r.rating,
        r.incident_type,
        r.review_comment,
        CASE
            WHEN co_orders.total_orders = 1 OR co_orders.last_order_date = so.order_date
            THEN 'ALTO_RISCO_CHURN'
            ELSE 'RETIDO'
        END AS churn_risk_status
    FROM silver.service_orders so
    JOIN silver.clients cl ON so.client_id = cl.client_id
    JOIN silver.contractors co ON so.contractor_id = co.contractor_id
    JOIN silver.reviews r ON so.order_id = r.order_id
    JOIN client_orders co_orders ON so.client_id = co_orders.client_id
    WHERE r.incident_reported = TRUE
    ORDER BY so.order_date DESC;
    """
    return fetch_df(query, conn=conn, db_path=db_path)


def render_dashboard() -> None:
    """Monta a interface interativa do Streamlit com filtros e visualizações."""
    st.set_page_config(
        page_title="HomeFix | Dashboard Analítico",
        page_icon="🛠️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("🛠️ HomeFix — Inteligência Operacional & Analytics")
    st.markdown(
        "> *Monitoramento estratégico de GMV, eficiência operacional de serviços residenciais "
        "e qualidade dos prestadores em tempo real.*"
    )
    st.write("---")

    # Barra lateral de filtros
    st.sidebar.header("🔍 Filtros de Análise")
    df_spec = load_gmv_by_specialty()
    specialties_list = ["Todas"] + sorted(df_spec["specialty"].unique().tolist())
    selected_specialty = st.sidebar.selectbox(
        "Especialidade de Serviço:", specialties_list
    )

    st.sidebar.markdown("---")
    st.sidebar.info(
        "💡 **Motor Analítico:** DuckDB in-process\n\n"
        "🏛️ **Arquitetura:** Medalhão (Bronze $\\rightarrow$ Silver $\\rightarrow$ Gold)\n\n"
        "⚡ **Processamento:** 100% colunar e otimizado"
    )

    # 1. Cartões de Métricas Globais (Header Cards)
    df_monthly = load_kpi_summary()
    total_gmv = df_spec["total_gmv"].sum()
    total_orders = df_spec["total_orders"].sum()
    completed_orders = df_spec["completed_orders"].sum()
    global_resolution = (
        round((completed_orders / total_orders) * 100, 1) if total_orders > 0 else 0.0
    )
    avg_ticket = round(total_gmv / completed_orders, 2) if completed_orders > 0 else 0.0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("💰 GMV Total", f"R$ {total_gmv:,.2f}")
    col2.metric("📋 Ordens Totais", f"{total_orders:,}")
    col3.metric("✅ Taxa de Conclusão", f"{global_resolution}%")
    col4.metric("🏷️ Ticket Médio", f"R$ {avg_ticket:,.2f}")
    total_incidents = df_monthly["total_incidents"].sum() if not df_monthly.empty else 0
    col5.metric("🚨 Total de Incidentes", f"{total_incidents}")

    st.write("")

    # 2. Abas Analíticas
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📈 Tendências Mensais",
            "💼 Performance por Especialidade",
            "🏆 Scorecard de Prestadores",
            "⚠️ Eficiência & Churn",
        ]
    )

    with tab1:
        st.subheader("📈 Evolução Temporal de GMV e Volume de Ordens")
        if not df_monthly.empty:
            chart_gmv = df_monthly.set_index("order_month")[["total_gmv"]]
            chart_gmv.columns = ["GMV Mensal (R$)"]
            st.line_chart(chart_gmv, use_container_width=True)

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 📊 Conclusões vs Cancelamentos")
                chart_orders = df_monthly.set_index("order_month")[
                    ["completed_orders", "canceled_orders"]
                ]
                chart_orders.columns = ["Concluídos", "Cancelados"]
                st.bar_chart(chart_orders, use_container_width=True)

            with c2:
                st.markdown("#### ⭐ Evolução da Nota Média (CSAT)")
                chart_rating = df_monthly.set_index("order_month")[["avg_rating"]]
                chart_rating.columns = ["CSAT Médio"]
                st.line_chart(chart_rating, use_container_width=True)

            st.dataframe(df_monthly, use_container_width=True)
        else:
            st.warning("Nenhum dado mensal encontrado.")

    with tab2:
        st.subheader("💼 Desempenho e Faturamento por Especialidade")
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown("#### 💰 Faturamento Bruto (GMV) por Categoria")
            chart_bar = df_spec.set_index("specialty")[["total_gmv"]]
            chart_bar.columns = ["GMV Total (R$)"]
            st.bar_chart(chart_bar, use_container_width=True)

        with c2:
            st.markdown("#### 🏷️ Ticket Médio por Categoria")
            chart_ticket = df_spec.set_index("specialty")[["avg_ticket"]]
            chart_ticket.columns = ["Ticket Médio (R$)"]
            st.bar_chart(chart_ticket, use_container_width=True)

        st.dataframe(df_spec, use_container_width=True)

    with tab3:
        st.subheader("🏆 Scorecard e Classificação de Prestadores")
        df_contractors = load_contractors_scorecard(specialty_filter=selected_specialty)
        st.markdown(f"Exibindo **{len(df_contractors)} prestadores** cadastrados:")
        st.dataframe(
            df_contractors.style.format(
                {
                    "total_gmv_generated": "R$ {:,.2f}",
                    "completion_rate_pct": "{:.1f}%",
                    "avg_rating": "{:.2f}",
                }
            ),
            use_container_width=True,
        )

    with tab4:
        st.subheader("⚠️ Eficiência Operacional, Cancelamentos e Risco de Churn")
        df_eff = load_operational_efficiency()
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### ⏱️ Tempo Médio de Ciclo (Dias até Conclusão)")
            chart_cycle = df_eff.set_index("service_category")[["avg_cycle_time_days"]]
            chart_cycle.columns = ["Dias Médios"]
            st.bar_chart(chart_cycle, use_container_width=True)

        with c2:
            st.markdown("#### ❌ Taxa de Cancelamento por Categoria (%)")
            chart_canc = df_eff.set_index("service_category")[["cancellation_rate_pct"]]
            chart_canc.columns = ["Cancelamento (%)"]
            st.bar_chart(chart_canc, use_container_width=True)

        st.markdown("---")
        st.subheader("🚨 Incidentes Críticos & Clientes sob Risco de Churn")
        df_churn = load_churn_risk_data()
        churn_high = df_churn[df_churn["churn_risk_status"] == "ALTO_RISCO_CHURN"]
        st.warning(
            f"Identificados **{len(churn_high)} chamados** com incidentes operacionais cujos clientes "
            f"encontram-se em **ALTO RISCO DE CHURN** (compra única ou sem nova contratação após o problema)."
        )
        st.dataframe(df_churn, use_container_width=True)


if __name__ == "__main__":
    render_dashboard()
