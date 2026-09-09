-- Staging model for raw sales data
-- Cleans dates, renames columns, filters bad data

SELECT
    sale_id,
    PARSE_DATE('%Y-%m-%d', date)      AS sale_date,
    store_id,
    product_id,
    quantity_sold,
    unit_price,
    revenue,
    EXTRACT(YEAR  FROM PARSE_DATE('%Y-%m-%d', date)) AS sale_year,
    EXTRACT(MONTH FROM PARSE_DATE('%Y-%m-%d', date)) AS sale_month,
    EXTRACT(WEEK  FROM PARSE_DATE('%Y-%m-%d', date)) AS sale_week,
    CASE
        WHEN EXTRACT(MONTH FROM PARSE_DATE('%Y-%m-%d', date)) IN (10, 11, 12)
        THEN TRUE ELSE FALSE
    END AS is_festive_season
FROM
    {{ source('retailiq_raw', 'raw_sales') }}
WHERE
    quantity_sold > 0
    AND revenue   > 0