-- Inventory health model
-- Calculates stockout risk, days of supply, and revenue at risk

SELECT
    i.snapshot_date,
    i.store_id,
    st.store_name,
    st.city,
    st.region,
    i.product_id,
    p.product_name,
    p.category,
    p.unit_price,
    i.current_stock,
    i.reorder_point,
    i.days_of_supply,
    i.is_understocked,
    i.stock_status,
    -- Revenue at risk if stockout occurs
    ROUND(i.reorder_point * p.unit_price, 2)        AS revenue_at_risk,
    -- How many days until reorder needed
    GREATEST(i.days_of_supply - p.lead_time_days, 0) AS buffer_days
FROM
    {{ ref('stg_inventory') }}  i
LEFT JOIN {{ ref('stg_products') }} p  ON i.product_id = p.product_id
LEFT JOIN {{ ref('stg_stores') }}   st ON i.store_id   = st.store_id