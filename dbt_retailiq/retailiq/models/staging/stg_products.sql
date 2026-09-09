-- Staging model for product master

SELECT
    product_id,
    product_name,
    category,
    unit_price,
    reorder_point,
    lead_time_days,
    supplier_id
FROM
    {{ source('retailiq_raw', 'raw_products') }}