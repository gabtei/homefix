-- ==============================================================================
-- Query: joins_incidents_churn.sql
-- Descrição: JOINs múltiplos entre 4 tabelas (clients, orders, contractors, reviews)
--            para mapear incidentes operacionais e identificar risco de churn.
-- ==============================================================================

WITH client_order_counts AS (
    SELECT
        client_id,
        COUNT(order_id) AS total_client_lifetime_orders,
        MAX(order_date) AS client_last_order_date
    FROM silver.service_orders
    GROUP BY client_id
),
incident_details AS (
    SELECT
        so.order_id,
        so.client_id,
        cl.client_name,
        cl.client_city,
        cl.client_phone,
        so.contractor_id,
        co.contractor_name,
        co.specialty AS contractor_specialty,
        so.order_date,
        so.service_category,
        so.total_final_amount,
        r.rating,
        r.incident_type,
        r.review_comment,
        coc.total_client_lifetime_orders,
        coc.client_last_order_date,
        CASE
            -- Se o cliente só teve esse pedido ou se a data do incidente foi a última ordem dele
            WHEN coc.total_client_lifetime_orders = 1 OR coc.client_last_order_date = so.order_date
            THEN 'ALTO_RISCO_CHURN'
            ELSE 'RETIDO'
        END AS churn_risk_status
    FROM silver.service_orders so
    INNER JOIN silver.clients cl ON so.client_id = cl.client_id
    INNER JOIN silver.contractors co ON so.contractor_id = co.contractor_id
    INNER JOIN silver.reviews r ON so.order_id = r.order_id
    INNER JOIN client_order_counts coc ON so.client_id = coc.client_id
    WHERE r.incident_reported = TRUE
)
SELECT
    order_id,
    client_id,
    client_name,
    client_city,
    contractor_name,
    contractor_specialty,
    order_date,
    service_category,
    total_final_amount,
    rating,
    incident_type,
    review_comment,
    total_client_lifetime_orders,
    churn_risk_status
FROM incident_details
ORDER BY
    order_date DESC;
