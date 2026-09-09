-- Staging model for inventory snapshot

SELECT
    snapshot_date,
    store_id,
    product_id,
    current_stock,
    reorder_point,
    is_understocked,
    days_of_supply,
    CASE
        WHEN current_stock = 0           THEN 'Stockout'
        WHEN is_understocked = 1         THEN 'Critical'
        WHEN days_of_supply <= 7         THEN 'Low'
        ELSE                                  'Healthy'
    END AS stock_status
FROM
    {{ source('retailiq_raw', 'raw_inventory') }}