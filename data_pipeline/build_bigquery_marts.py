import os
import time
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

PROJECT_ID = os.getenv("BIGQUERY_PROJECT_ID", "retailiq-analytics-508120")
RAW_DATASET = "retailiq_raw"
TRANS_DATASET = "retailiq_transformed"

client = bigquery.Client(project=PROJECT_ID)


def build_marts():
    print(f"\nBuilding RetailIQ Data Marts on BigQuery ({PROJECT_ID})...\n")

    # 1. Create transformed dataset if needed
    dataset_ref = f"{PROJECT_ID}.{TRANS_DATASET}"
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = "US"
    client.create_dataset(dataset, exists_ok=True)
    print(f"[OK] Dataset '{TRANS_DATASET}' verified.")

    # 2. Build Staging Views
    staging_models = {
        "stg_products": f"""
            CREATE OR REPLACE VIEW `{PROJECT_ID}.{TRANS_DATASET}.stg_products` AS
            SELECT
                product_id,
                product_name,
                category,
                unit_price,
                reorder_point,
                lead_time_days,
                supplier_id
            FROM
                `{PROJECT_ID}.{RAW_DATASET}.raw_products`
        """,
        "stg_stores": f"""
            CREATE OR REPLACE VIEW `{PROJECT_ID}.{TRANS_DATASET}.stg_stores` AS
            SELECT
                store_id,
                store_name,
                city,
                region,
                store_size_sqft
            FROM
                `{PROJECT_ID}.{RAW_DATASET}.raw_stores`
        """,
        "stg_sales": f"""
            CREATE OR REPLACE VIEW `{PROJECT_ID}.{TRANS_DATASET}.stg_sales` AS
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
                `{PROJECT_ID}.{RAW_DATASET}.raw_sales`
            WHERE
                quantity_sold > 0
                AND revenue   > 0
        """,
        "stg_inventory": f"""
            CREATE OR REPLACE VIEW `{PROJECT_ID}.{TRANS_DATASET}.stg_inventory` AS
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
                `{PROJECT_ID}.{RAW_DATASET}.raw_inventory`
        """
    }

    for name, query in staging_models.items():
        t0 = time.time()
        client.query(query).result()
        print(f"[OK] View '{name}' built in {time.time()-t0:.2f}s")

    # 3. Build Analytics Tables
    table_models = {
        "fct_sales_daily": f"""
            CREATE OR REPLACE TABLE `{PROJECT_ID}.{TRANS_DATASET}.fct_sales_daily` AS
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
                `{PROJECT_ID}.{TRANS_DATASET}.stg_sales`    s
            LEFT JOIN `{PROJECT_ID}.{TRANS_DATASET}.stg_products` p  ON s.product_id = p.product_id
            LEFT JOIN `{PROJECT_ID}.{TRANS_DATASET}.stg_stores`   st ON s.store_id   = st.store_id
        """,
        "fct_inventory_health": f"""
            CREATE OR REPLACE TABLE `{PROJECT_ID}.{TRANS_DATASET}.fct_inventory_health` AS
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
                ROUND(i.reorder_point * p.unit_price, 2)        AS revenue_at_risk,
                GREATEST(i.days_of_supply - p.lead_time_days, 0) AS buffer_days
            FROM
                `{PROJECT_ID}.{TRANS_DATASET}.stg_inventory`  i
            LEFT JOIN `{PROJECT_ID}.{TRANS_DATASET}.stg_products` p  ON i.product_id = p.product_id
            LEFT JOIN `{PROJECT_ID}.{TRANS_DATASET}.stg_stores`   st ON i.store_id   = st.store_id
        """,
        "agg_store_performance": f"""
            CREATE OR REPLACE TABLE `{PROJECT_ID}.{TRANS_DATASET}.agg_store_performance` AS
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
                `{PROJECT_ID}.{TRANS_DATASET}.fct_sales_daily`
            GROUP BY
                store_id, store_name, city, region
        """
    }

    for name, query in table_models.items():
        t0 = time.time()
        client.query(query).result()
        count_res = list(client.query(f"SELECT COUNT(*) as cnt FROM `{PROJECT_ID}.{TRANS_DATASET}.{name}`").result())[0]
        print(f"[OK] Table '{name}' materialized ({count_res.cnt:,} rows) in {time.time()-t0:.2f}s")

    print("\nAll BigQuery transformed models built successfully!\n")


if __name__ == "__main__":
    build_marts()
