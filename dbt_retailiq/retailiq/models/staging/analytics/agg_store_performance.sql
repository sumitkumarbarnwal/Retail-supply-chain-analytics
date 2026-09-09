-- Store performance aggregation
-- Executive KPIs per store for dashboard

SELECT
    store_id,
    store_name,
    city,
    region,
    COUNT(DISTINCT sale_date)               AS active_selling_days,
    COUNT(DISTINCT product_id)              AS unique_products_sold,
    SUM(quantity_sold)                      AS total_units_sold,
    ROUND(SUM(revenue), 2)                  AS total_revenue,
    ROUND(AVG(revenue), 2)                  AS avg_daily_revenue,
    ROUND(SUM(revenue) / COUNT(DISTINCT sale_date), 2) AS revenue_per_day,
    SUM(CASE WHEN is_festive_season THEN revenue ELSE 0 END) AS festive_revenue,
    SUM(CASE WHEN NOT is_festive_season THEN revenue ELSE 0 END) AS non_festive_revenue
FROM
    {{ ref('fct_sales_daily') }}
GROUP BY
    store_id, store_name, city, region
