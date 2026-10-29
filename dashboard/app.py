"""Painel Analítico Executivo em Streamlit para o Marketplace HomeFix.

Apresenta visualizações consolidadas de faturamento (GMV), ticket médio,
performance de prestadores, eficiência operacional e análise de churn
a partir da Camada Gold do DuckDB, formatados no padrão brasileiro (pt-BR).
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


def format_currency_brl(value: float | None) -> str:
    """Formata valor numérico no padrão monetário brasileiro R$ 1.234,56.

    Args:
        value: Valor numérico float ou int.

    Returns:
        String formatada em reais com separador de milhar por ponto e decimal por vírgula.
    """
    if value is None or pd.isna(value):
        return "R$ 0,00"
    numeric_val = float(value)
    sign = "-" if numeric_val < 0 else ""
    abs_val = abs(numeric_val)
    int_part = int(abs_val)
    dec_part = round((abs_val - int_part) * 100)
    formatted_int = f"{int_part:,}".replace(",", ".")
    return f"{sign}R$ {formatted_int},{dec_part:02d}"


def format_number_br(value: float | None) -> str:
    """Formata número com separador de milhar por ponto (ex: 1.500).

    Args:
        value: Número inteiro ou float.

    Returns:
        String formatada no padrão brasileiro.
    """
    if value is None or pd.isna(value):
        return "0"
    numeric_val = float(value)
    if numeric_val.is_integer():
        return f"{int(numeric_val):,}".replace(",", ".")
    int_part = int(numeric_val)
    dec_part = round((numeric_val - int_part) * 100)
    formatted_int = f"{int_part:,}".replace(",", ".")
    return f"{formatted_int},{dec_part:02d}"


def format_percent_br(value: float | None) -> str:
    """Formata percentual no padrão brasileiro (ex: 71,8%).

    Args:
        value: Valor percentual (0 a 100).

    Returns:
        String formatada com vírgula decimal e símbolo de %.
    """
    if value is None or pd.isna(value):
        return "0,0%"
    return f"{float(value):.1f}%".replace(".", ",")


def format_decimal_br(value: float | None, decimals: int = 2) -> str:
    """Formata valor float no padrão brasileiro com vírgula decimal (ex: 4,85).

    Args:
        value: Valor numérico a ser formatado.
        decimals: Quantidade de casas decimais.

    Returns:
        String com casas decimais separadas por vírgula.
    """
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.{decimals}f}".replace(".", ",")


def load_kpi_summary(
    specialty_filter: str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Carrega a série histórica mensal de KPIs filtrando opcionalmente por especialidade."""
    where_stmt = ""
    if specialty_filter and specialty_filter != "Todas":
        clean_spec = specialty_filter.replace("'", "''")
        where_stmt = f"WHERE service_category = '{clean_spec}'"

    query = f"""
    SELECT
        STRFTIME(order_date, '%Y-%m') AS order_month,
        COUNT(order_id) AS total_orders,
        COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END) AS completed_orders,
        COUNT(CASE WHEN order_status = 'CANCELADO' THEN 1 END) AS canceled_orders,
        ROUND(
            (COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END)::DOUBLE / NULLIF(COUNT(order_id), 0)) * 100,
            2
        ) AS completion_rate_pct,
        ROUND(COALESCE(SUM(CASE WHEN order_status = 'CONCLUIDO' THEN total_final_amount ELSE 0 END), 0), 2) AS total_gmv,
        ROUND(COALESCE(AVG(CASE WHEN order_status = 'CONCLUIDO' THEN total_final_amount END), 0), 2) AS avg_ticket,
        ROUND(COALESCE(AVG(rating), 0.0), 2) AS avg_rating,
        COUNT(CASE WHEN has_incident THEN 1 END) AS total_incidents
    FROM gold.fct_orders
    {where_stmt}
    GROUP BY STRFTIME(order_date, '%Y-%m')
    ORDER BY order_month ASC;
    """
    return fetch_df(query, conn=conn, db_path=db_path)


def load_gmv_by_specialty(
    specialty_filter: str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Carrega o faturamento consolidado e representatividade por especialidade."""
    where_stmt = ""
    if specialty_filter and specialty_filter != "Todas":
        clean_spec = specialty_filter.replace("'", "''")
        where_stmt = f"WHERE service_category = '{clean_spec}'"

    query = f"""
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
    {where_stmt}
    GROUP BY service_category
    ORDER BY total_gmv DESC;
    """
    return fetch_df(query, conn=conn, db_path=db_path)


def load_all_specialties(
    conn: duckdb.DuckDBPyConnection | None = None,
    db_path: str | Path | None = None,
) -> list[str]:
    """Retorna a lista completa de todas as especialidades cadastradas."""
    query = "SELECT DISTINCT specialty FROM gold.dim_contractors ORDER BY specialty;"
    df = fetch_df(query, conn=conn, db_path=db_path)
    return ["Todas"] + df["specialty"].tolist()


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
    specialty_filter: str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Carrega tempos médios de ciclo e taxas de conversão de chamados."""
    where_stmt = ""
    if specialty_filter and specialty_filter != "Todas":
        clean_spec = specialty_filter.replace("'", "''")
        where_stmt = f"WHERE service_category = '{clean_spec}'"

    query = f"""
    SELECT
        service_category,
        COUNT(*) AS total_orders,
        COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END) AS completed_orders,
        COUNT(CASE WHEN order_status = 'CANCELADO' THEN 1 END) AS canceled_orders,
        ROUND((COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END)::DOUBLE / NULLIF(COUNT(*), 0)) * 100, 2) AS resolution_rate_pct,
        ROUND((COUNT(CASE WHEN order_status = 'CANCELADO' THEN 1 END)::DOUBLE / NULLIF(COUNT(*), 0)) * 100, 2) AS cancellation_rate_pct,
        ROUND(COALESCE(AVG(cycle_time_days), 0), 1) AS avg_cycle_time_days
    FROM gold.fct_orders
    {where_stmt}
    GROUP BY service_category
    ORDER BY resolution_rate_pct DESC;
    """
    return fetch_df(query, conn=conn, db_path=db_path)


def load_churn_risk_data(
    specialty_filter: str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Carrega clientes impactados por incidentes com classificação de risco de churn."""
    where_spec = ""
    if specialty_filter and specialty_filter != "Todas":
        clean_spec = specialty_filter.replace("'", "''")
        where_spec = f"AND so.service_category = '{clean_spec}'"

    query = f"""
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
    WHERE r.incident_reported = TRUE {where_spec}
    ORDER BY so.order_date DESC;
    """
    return fetch_df(query, conn=conn, db_path=db_path)


def render_dashboard() -> None:
    """Monta a interface interativa do Streamlit com filtros e visualizações em português."""
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
    st.markdown(
        """
        <style>
        /* Ajuste do tamanho e quebra das métricas para evitar reticências (...) */
        div[data-testid="stMetricValue"] {
            font-size: 1.55rem !important;
            white-space: nowrap !important;
            overflow: visible !important;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 0.90rem !important;
            font-weight: 600 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.write("---")

    # Barra lateral de filtros interativos
    st.sidebar.header("🔍 Filtros de Análise")
    all_specialties = load_all_specialties()
    selected_specialty = st.sidebar.selectbox(
        "Especialidade de Serviço:", all_specialties
    )

    st.sidebar.markdown("---")
    st.sidebar.info(
        "💡 **Motor Analítico:** DuckDB in-process\n\n"
        "🏛️ **Arquitetura:** Medalhão (Bronze $\\rightarrow$ Silver $\\rightarrow$ Gold)\n\n"
        "🇧🇷 **Padrão Numérico:** Moeda e números pt-BR"
    )

    # 1. Carregamento dos dados reativos ao filtro
    df_spec = load_gmv_by_specialty(specialty_filter=selected_specialty)
    df_monthly = load_kpi_summary(specialty_filter=selected_specialty)
    df_contractors = load_contractors_scorecard(specialty_filter=selected_specialty)
    df_eff = load_operational_efficiency(specialty_filter=selected_specialty)
    df_churn = load_churn_risk_data(specialty_filter=selected_specialty)

    # 2. Cartões de Métricas Globais (Header Cards) - Reativos ao filtro
    total_gmv = df_spec["total_gmv"].sum() if not df_spec.empty else 0.0
    total_orders = df_spec["total_orders"].sum() if not df_spec.empty else 0
    completed_orders = df_spec["completed_orders"].sum() if not df_spec.empty else 0
    global_resolution = (
        round((completed_orders / total_orders) * 100, 1) if total_orders > 0 else 0.0
    )
    avg_ticket = round(total_gmv / completed_orders, 2) if completed_orders > 0 else 0.0
    total_incidents = df_monthly["total_incidents"].sum() if not df_monthly.empty else 0

    filtro_label = (
        f" ({selected_specialty})" if selected_specialty != "Todas" else " (Geral)"
    )

    col1, col2, col3, col4, col5 = st.columns([1.35, 0.9, 1.0, 1.15, 0.9])
    col1.metric(f"💰 GMV Total{filtro_label}", format_currency_brl(total_gmv))
    col2.metric(f"📋 Ordens Totais{filtro_label}", format_number_br(total_orders))
    col3.metric(
        f"✅ Taxa de Conclusão{filtro_label}", format_percent_br(global_resolution)
    )
    col4.metric(f"🏷️ Ticket Médio{filtro_label}", format_currency_brl(avg_ticket))
    col5.metric(
        f"🚨 Total de Incidentes{filtro_label}", format_number_br(total_incidents)
    )

    st.write("")

    # 3. Abas Analíticas
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📈 Tendências Mensais",
            "💼 Performance por Especialidade",
            "🏆 Scorecard de Prestadores",
            "⚠️ Eficiência & Churn",
        ]
    )

    with tab1:
        st.subheader(f"📈 Evolução Mensal de Faturamento e Ordens{filtro_label}")
        if not df_monthly.empty:
            chart_gmv = df_monthly.set_index("order_month")[["total_gmv"]]
            chart_gmv.columns = ["GMV Mensal (R$)"]
            st.line_chart(chart_gmv, use_container_width=True)

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 📊 Chamados Concluídos vs Cancelados")
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

            # Tabela Mensal com nomes em português e formatação brasileira
            st.markdown("#### 📑 Histórico Mensal Consolidado")
            df_monthly_display = df_monthly.rename(
                columns={
                    "order_month": "Mês de Referência",
                    "total_orders": "Total de Chamados",
                    "completed_orders": "Ordens Concluídas",
                    "canceled_orders": "Ordens Canceladas",
                    "completion_rate_pct": "Taxa de Conclusão (%)",
                    "total_gmv": "GMV Total (R$)",
                    "avg_ticket": "Ticket Médio (R$)",
                    "avg_rating": "CSAT Médio",
                    "total_incidents": "Incidentes Reportados",
                }
            )
            st.dataframe(
                df_monthly_display.style.format(
                    {
                        "Total de Chamados": lambda x: format_number_br(x),
                        "Ordens Concluídas": lambda x: format_number_br(x),
                        "Ordens Canceladas": lambda x: format_number_br(x),
                        "Taxa de Conclusão (%)": lambda x: format_percent_br(x),
                        "GMV Total (R$)": lambda x: format_currency_brl(x),
                        "Ticket Médio (R$)": lambda x: format_currency_brl(x),
                        "CSAT Médio": lambda x: format_decimal_br(x, 2),
                        "Incidentes Reportados": lambda x: format_number_br(x),
                    }
                ),
                use_container_width=True,
            )
        else:
            st.warning("Nenhum dado mensal encontrado para os filtros selecionados.")

    with tab2:
        st.subheader(f"💼 Desempenho e Faturamento por Categoria{filtro_label}")
        if not df_spec.empty:
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

            # Tabela de Especialidades em Português
            st.markdown("#### 📑 Demonstrativo Detalhado por Especialidade")
            df_spec_display = df_spec.rename(
                columns={
                    "specialty": "Especialidade de Serviço",
                    "total_orders": "Total de Ordens",
                    "completed_orders": "Ordens Concluídas",
                    "canceled_orders": "Ordens Canceladas",
                    "total_gmv": "GMV Total (R$)",
                    "avg_ticket": "Ticket Médio (R$)",
                    "resolution_rate_pct": "Taxa de Resolução (%)",
                }
            )
            st.dataframe(
                df_spec_display.style.format(
                    {
                        "Total de Ordens": lambda x: format_number_br(x),
                        "Ordens Concluídas": lambda x: format_number_br(x),
                        "Ordens Canceladas": lambda x: format_number_br(x),
                        "GMV Total (R$)": lambda x: format_currency_brl(x),
                        "Ticket Médio (R$)": lambda x: format_currency_brl(x),
                        "Taxa de Resolução (%)": lambda x: format_percent_br(x),
                    }
                ),
                use_container_width=True,
            )
        else:
            st.warning("Nenhuma especialidade localizada.")

    with tab3:
        st.subheader(f"🏆 Scorecard e Classificação de Prestadores{filtro_label}")
        if not df_contractors.empty:
            st.markdown(f"Exibindo **{len(df_contractors)} prestadores** cadastrados:")
            df_contractors_display = df_contractors.rename(
                columns={
                    "contractor_id": "ID",
                    "contractor_name": "Nome do Prestador",
                    "specialty": "Especialidade",
                    "city": "Cidade",
                    "experience_years": "Experiência (Anos)",
                    "total_orders_assigned": "Ordens Atribuídas",
                    "completed_orders": "Ordens Concluídas",
                    "completion_rate_pct": "Taxa de Conclusão (%)",
                    "total_gmv_generated": "GMV Gerado (R$)",
                    "avg_rating": "CSAT Médio",
                    "incidents_count": "Total de Incidentes",
                    "is_active": "Ativo?",
                }
            )
            st.dataframe(
                df_contractors_display.style.format(
                    {
                        "Experiência (Anos)": lambda x: format_number_br(x),
                        "Ordens Atribuídas": lambda x: format_number_br(x),
                        "Ordens Concluídas": lambda x: format_number_br(x),
                        "Taxa de Conclusão (%)": lambda x: format_percent_br(x),
                        "GMV Gerado (R$)": lambda x: format_currency_brl(x),
                        "CSAT Médio": lambda x: format_decimal_br(x, 2),
                        "Total de Incidentes": lambda x: format_number_br(x),
                        "Ativo?": lambda x: "Sim" if x else "Não",
                    }
                ),
                use_container_width=True,
            )
        else:
            st.warning("Nenhum prestador encontrado para a seleção.")

    with tab4:
        st.subheader(
            f"⚠️ Eficiência Operacional, Cancelamentos e Risco de Churn{filtro_label}"
        )
        if not df_eff.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### ⏱️ Tempo Médio de Ciclo (Dias até Conclusão)")
                chart_cycle = df_eff.set_index("service_category")[
                    ["avg_cycle_time_days"]
                ]
                chart_cycle.columns = ["Dias Médios"]
                st.bar_chart(chart_cycle, use_container_width=True)

            with c2:
                st.markdown("#### ❌ Taxa de Cancelamento por Categoria (%)")
                chart_canc = df_eff.set_index("service_category")[
                    ["cancellation_rate_pct"]
                ]
                chart_canc.columns = ["Cancelamento (%)"]
                st.bar_chart(chart_canc, use_container_width=True)

            st.markdown("#### 📑 Métricas de Conversão Operacional")
            df_eff_display = df_eff.rename(
                columns={
                    "service_category": "Categoria de Serviço",
                    "total_orders": "Total de Chamados",
                    "completed_orders": "Concluídos",
                    "canceled_orders": "Cancelados",
                    "resolution_rate_pct": "Taxa de Resolução (%)",
                    "cancellation_rate_pct": "Taxa de Cancelamento (%)",
                    "avg_cycle_time_days": "Tempo Médio de Ciclo (Dias)",
                }
            )
            st.dataframe(
                df_eff_display.style.format(
                    {
                        "Total de Chamados": lambda x: format_number_br(x),
                        "Concluídos": lambda x: format_number_br(x),
                        "Cancelados": lambda x: format_number_br(x),
                        "Taxa de Resolução (%)": lambda x: format_percent_br(x),
                        "Taxa de Cancelamento (%)": lambda x: format_percent_br(x),
                        "Tempo Médio de Ciclo (Dias)": lambda x: format_decimal_br(
                            x, 1
                        ),
                    }
                ),
                use_container_width=True,
            )

        st.markdown("---")
        st.subheader(
            f"🚨 Incidentes Críticos & Clientes sob Risco de Churn{filtro_label}"
        )
        if not df_churn.empty:
            churn_high = df_churn[df_churn["churn_risk_status"] == "ALTO_RISCO_CHURN"]
            st.warning(
                f"Identificados **{len(churn_high)} chamados** com incidentes operacionais cujos clientes "
                f"encontram-se em **ALTO RISCO DE CHURN** (compra única ou sem nova contratação após o problema)."
            )
            df_churn_display = df_churn.rename(
                columns={
                    "order_id": "Nº da Ordem",
                    "client_id": "ID Cliente",
                    "client_name": "Nome do Cliente",
                    "client_city": "Cidade",
                    "contractor_name": "Prestador Alocado",
                    "service_category": "Categoria do Serviço",
                    "order_date": "Data da Ordem",
                    "total_final_amount": "Valor Final (R$)",
                    "rating": "Nota CSAT",
                    "incident_type": "Classificação do Incidente",
                    "review_comment": "Comentário da Avaliação",
                    "churn_risk_status": "Risco de Churn",
                }
            )
            st.dataframe(
                df_churn_display.style.format(
                    {
                        "Valor Final (R$)": lambda x: format_currency_brl(x),
                        "Nota CSAT": lambda x: format_number_br(x),
                    }
                ),
                use_container_width=True,
            )
        else:
            st.info("Nenhum incidente registrado para os filtros aplicados.")


if __name__ == "__main__":
    render_dashboard()
