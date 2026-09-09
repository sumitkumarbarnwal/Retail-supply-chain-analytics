-- Staging model for store master

SELECT
    store_id,
    store_name,
    city,
    region,
    store_size_sqft
FROM
    {{ source('retailiq_raw', 'raw_stores') }}