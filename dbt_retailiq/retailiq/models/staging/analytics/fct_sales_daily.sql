-- Daily sales fact table
-- Joins sales + products + stores for complete analytical view

SELECT
    s.sale_date,
    s.sale_year,
    s.sale_month,
    s.sale_week,
    s.is_festive_season,
    s.store_id,
    st.store_name,
    st.city,
    st.region,
    s.product_id,
    p.product_name,
    p.category,
    p.supplier_id,
    s.quantity_sold,
    s.unit_price,
    s.revenue,
    p.unit_price                                    AS standard_price,
    ROUND(s.revenue - (s.quantity_sold * p.unit_price), 2) AS price_variance
FROM
    {{ ref('stg_sales') }}    s
LEFT JOIN {{ ref('stg_products') }} p  ON s.product_id = p.product_id
LEFT JOIN {{ ref('stg_stores') }}   st ON s.store_id   = st.store_id