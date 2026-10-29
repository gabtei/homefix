-- ==============================================================================
-- Query: kpi_contractor_scorecard.sql
-- Descrição: Scorecard de desempenho e ranking de prestadores por especialidade,
--            utilizando Window Functions (ROW_NUMBER, DENSE_RANK e AVG OVER).
-- ==============================================================================

WITH contractor_aggregates AS (
    SELECT
        c.contractor_id,
        c.contractor_name,
        c.specialty,
        c.experience_years,
        c.city,
        c.is_active,
        COUNT(so.order_id) AS total_orders,
        COUNT(CASE WHEN so.order_status = 'CONCLUIDO' THEN 1 END) AS completed_orders,
        ROUND(COALESCE(SUM(CASE WHEN so.order_status = 'CONCLUIDO' THEN so.total_final_amount ELSE 0.00 END), 0.00), 2) AS total_gmv,
        ROUND(COALESCE(AVG(r.rating), 0.0), 2) AS avg_rating,
        COUNT(CASE WHEN r.incident_reported THEN 1 END) AS total_incidents
    FROM silver.contractors c
    LEFT JOIN silver.service_orders so ON c.contractor_id = so.contractor_id
    LEFT JOIN silver.reviews r ON so.order_id = r.order_id
    GROUP BY
        c.contractor_id,
        c.contractor_name,
        c.specialty,
        c.experience_years,
        c.city,
        c.is_active
)
SELECT
    contractor_id,
    contractor_name,
    specialty,
    city,
    is_active,
    total_orders,
    completed_orders,
    total_gmv,
    avg_rating,
    total_incidents,
    -- Window Functions:
    ROUND(AVG(avg_rating) OVER (PARTITION BY specialty), 2) AS specialty_avg_rating,
    ROUND(AVG(total_gmv) OVER (PARTITION BY specialty), 2) AS specialty_avg_gmv,
    ROW_NUMBER() OVER (
        PARTITION BY specialty
        ORDER BY total_gmv DESC, avg_rating DESC
    ) AS rank_in_specialty,
    DENSE_RANK() OVER (
        ORDER BY total_gmv DESC
    ) AS overall_gmv_rank
FROM contractor_aggregates
ORDER BY
    specialty,
    rank_in_specialty;
