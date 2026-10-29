-- ==============================================================================
-- Query: kpi_gmv_by_specialty.sql
-- Descrição: Volume financeiro bruto (GMV), ticket médio e representatividade (%)
--            de cada especialidade de serviço, utilizando CTEs.
-- ==============================================================================

WITH specialty_metrics AS (
    SELECT
        so.service_category AS specialty,
        COUNT(so.order_id) AS total_orders,
        COUNT(CASE WHEN so.order_status = 'CONCLUIDO' THEN 1 END) AS completed_orders,
        COUNT(CASE WHEN so.order_status = 'CANCELADO' THEN 1 END) AS canceled_orders,
        ROUND(COALESCE(SUM(CASE WHEN so.order_status = 'CONCLUIDO' THEN so.total_final_amount ELSE 0.00 END), 0.00), 2) AS total_gmv,
        ROUND(COALESCE(AVG(CASE WHEN so.order_status = 'CONCLUIDO' THEN so.total_final_amount END), 0.00), 2) AS avg_ticket
    FROM silver.service_orders so
    GROUP BY so.service_category
),
total_marketplace AS (
    SELECT
        COALESCE(SUM(total_gmv), 0.01) AS marketplace_total_gmv
    FROM specialty_metrics
)
SELECT
    sm.specialty,
    sm.total_orders,
    sm.completed_orders,
    sm.canceled_orders,
    sm.total_gmv,
    sm.avg_ticket,
    ROUND((sm.total_gmv / tm.marketplace_total_gmv) * 100.0, 2) AS share_of_total_gmv_pct
FROM specialty_metrics sm
CROSS JOIN total_marketplace tm
ORDER BY sm.total_gmv DESC;
