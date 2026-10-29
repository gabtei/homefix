-- ==============================================================================
-- Query: kpi_resolution_rate.sql
-- Descrição: Taxa de resolução (conclusão vs cancelamento) e tempo médio de ciclo
--            por categoria de serviço, identificando eficiência operacional.
-- ==============================================================================

WITH order_cycle AS (
    SELECT
        service_category,
        order_status,
        cancellation_reason,
        DATEDIFF('day', order_date, completion_date) AS cycle_time_days
    FROM silver.service_orders
)
SELECT
    service_category,
    COUNT(*) AS total_orders,
    COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END) AS completed_orders,
    COUNT(CASE WHEN order_status = 'CANCELADO' THEN 1 END) AS canceled_orders,
    COUNT(CASE WHEN order_status IN ('EM_ANDAMENTO', 'ABERTO') THEN 1 END) AS in_progress_orders,
    ROUND(
        (COUNT(CASE WHEN order_status = 'CONCLUIDO' THEN 1 END)::DOUBLE / NULLIF(COUNT(*), 0)) * 100.0,
        2
    ) AS resolution_rate_pct,
    ROUND(
        (COUNT(CASE WHEN order_status = 'CANCELADO' THEN 1 END)::DOUBLE / NULLIF(COUNT(*), 0)) * 100.0,
        2
    ) AS cancellation_rate_pct,
    ROUND(
        COALESCE(AVG(CASE WHEN order_status = 'CONCLUIDO' THEN cycle_time_days END), 0.0),
        1
    ) AS avg_cycle_time_days
FROM order_cycle
GROUP BY service_category
ORDER BY resolution_rate_pct DESC;
