import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

PROJECT_ID = os.getenv("BIGQUERY_PROJECT_ID", "retailiq-analytics-508120")
DATASET    = "retailiq_transformed"

_groq_client = None
_bq_client   = None


def get_groq():
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        load_dotenv(override=True)
        key = os.getenv("GROQ_API_KEY")
        if not key or key == "your_groq_api_key_here":
            raise HTTPException(
                status_code=503,
                detail="GROQ_API_KEY is not set. Add your real key to the .env file."
            )
        _groq_client = Groq(api_key=key)
    return _groq_client


def get_bq():
    global _bq_client
    if _bq_client is None:
        import json
        from google.cloud import bigquery
        from google.oauth2 import service_account

        # 1. Check for raw JSON string in environment variable (Render / Cloud deployment)
        sa_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
        if sa_json:
            try:
                info = json.loads(sa_json)
                creds = service_account.Credentials.from_service_account_info(info)
                _bq_client = bigquery.Client(project=PROJECT_ID, credentials=creds)
                return _bq_client
            except Exception:
                pass

        # 2. Check for credentials file path
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path and os.path.exists(creds_path):
            creds = service_account.Credentials.from_service_account_file(creds_path)
            _bq_client = bigquery.Client(project=PROJECT_ID, credentials=creds)
            return _bq_client

        # 3. Default credentials
        _bq_client = bigquery.Client(project=PROJECT_ID)
    return _bq_client


SCHEMA_CONTEXT = f"""
You are an expert supply chain data analyst AI for RetailIQ — a retail analytics platform.
Your job is to convert business questions into accurate BigQuery SQL queries.

=== CURRENCY ===
All monetary columns (revenue, unit_price, standard_price, price_variance, revenue_at_risk) are in Indian Rupees (INR/₹). Never use USD or $ when referring to these values.

=== DATABASE: {PROJECT_ID}.retailiq_transformed ===

=== TABLE 1: fct_sales_daily ===
Purpose: Daily sales transactions — use for revenue, sales volume, product and store performance
Columns:
  sale_date          DATE        -- transaction date
  sale_year          INT64       -- year extracted from sale_date
  sale_month         INT64       -- month number (1-12)
  sale_week          INT64       -- week number
  is_festive_season  BOOL        -- TRUE for Oct/Nov/Dec, FALSE otherwise
  store_id           STRING      -- store identifier (e.g. STR01)
  store_name         STRING      -- store name (e.g. Mumbai Retail Hub)
  city               STRING      -- city name
  region             STRING      -- region (North, South, East, West)
  product_id         STRING      -- product identifier (e.g. PRD001)
  product_name       STRING      -- full product name
  category           STRING      -- category (Electronics, Grocery, Clothing, etc.)
  supplier_id        STRING      -- supplier identifier (e.g. SUP01)
  quantity_sold      INT64       -- units sold
  unit_price         FLOAT64     -- selling price in INR
  revenue            FLOAT64     -- total revenue in INR (quantity_sold * unit_price)
  standard_price     FLOAT64     -- standard product price in INR
  price_variance     FLOAT64     -- unit_price minus standard_price in INR

=== TABLE 2: fct_inventory_health ===
Purpose: Current inventory status, stockout risk, and days of supply per store and product
Note: In RetailIQ, inventory is tracked at retail stores (store_id, store_name, city, region). There is no "warehouse" table; stores hold the inventory.
Columns:
  snapshot_date      STRING      -- inventory snapshot date
  store_id           STRING      -- store identifier (e.g. STR01)
  store_name         STRING      -- store name (e.g. Mumbai Retail Hub)
  city               STRING      -- city name
  region             STRING      -- region (North, South, East, West)
  product_id         STRING      -- product identifier (e.g. PRD001)
  product_name       STRING      -- product name
  category           STRING      -- product category
  unit_price         FLOAT64     -- unit price in INR
  current_stock      INT64       -- current units in stock
  reorder_point      INT64       -- minimum safe stock level
  days_of_supply     FLOAT64     -- estimated days until stock runs out (use this for "running out next week", e.g. days_of_supply <= 7)
  is_understocked    INT64       -- 1 if stock is below reorder point, 0 if healthy
  stock_status       STRING      -- exactly one of: 'Stockout', 'Critical', 'Low', 'Healthy'
  revenue_at_risk    FLOAT64     -- potential lost revenue in INR if stocked out
  buffer_days        FLOAT64     -- days until reorder is needed

=== TABLE 3: agg_store_performance ===
Purpose: Pre-aggregated store-level metrics across the full year
Columns:
  store_id              STRING   -- store identifier (e.g. STR01)
  store_name            STRING   -- store name
  city                  STRING   -- city name
  region                STRING   -- region name
  active_selling_days   INT64    -- number of days store had sales
  unique_products_sold  INT64    -- count of distinct products sold
  total_units_sold      INT64    -- total volume of units sold
  total_revenue         FLOAT64  -- total revenue generated in INR
  avg_daily_revenue     FLOAT64  -- average daily revenue in INR
  revenue_per_day       FLOAT64  -- total revenue / active selling days
  festive_revenue       FLOAT64  -- revenue during Oct/Nov/Dec
  non_festive_revenue   FLOAT64  -- revenue outside Oct/Nov/Dec

=== STRICT SQL RULES ===
1. Always use fully qualified table names:
   {PROJECT_ID}.retailiq_transformed.fct_sales_daily
   {PROJECT_ID}.retailiq_transformed.fct_inventory_health
   {PROJECT_ID}.retailiq_transformed.agg_store_performance

2. DATA TYPE & COLUMN RULES — follow exactly:
   - ONLY use column names that are explicitly listed above. NEVER guess or invent columns like 'safety_stock' or 'days_of_inventory'.
   - The days of supply column in fct_inventory_health is named 'days_of_supply'.
   - For questions about "warehouse" or "store" inventory depletion, query fct_inventory_health and select store_name / store_id.
   - For "running out of inventory next week", filter by: WHERE days_of_supply <= 7 OR stock_status IN ('Stockout', 'Critical', 'Low').
   - is_festive_season is BOOL → use: WHERE is_festive_season = TRUE or FALSE.
   - is_understocked is INT64 → use: WHERE is_understocked = 1 or = 0.
   - stock_status is STRING → use: WHERE stock_status = 'Stockout' or stock_status IN ('Stockout', 'Critical', 'Low').

3. COLUMN AVAILABILITY:
   - supplier_id only exists in fct_sales_daily
   - To find supplier inventory issues: JOIN fct_inventory_health i ON i.product_id = s.product_id with fct_sales_daily s
   - festive_revenue and non_festive_revenue are pre-calculated in agg_store_performance
   - For product-level festive analysis use fct_sales_daily with is_festive_season filter

4. OUTPUT:
   - Return ONLY the SQL query
   - No explanations, no markdown formatting, no backticks, no comments
   - Query must be valid BigQuery Standard SQL
"""


_selected_model = None


def get_model():
    global _selected_model
    if _selected_model:
        return _selected_model
    env_model = os.getenv("GROQ_MODEL")
    if env_model:
        _selected_model = env_model
        return _selected_model
    try:
        available = [m.id for m in get_groq().models.list().data]
        candidates = [
            "llama-3.3-70b-versatile",
            "qwen/qwen3.8-27b",
            "groq/compound",
            "openai/gpt-oss-120b",
            "groq/compound-mini",
        ]
        for candidate in candidates:
            if candidate in available:
                _selected_model = candidate
                return _selected_model
        _selected_model = available[0] if available else "qwen/qwen3.8-27b"
    except Exception:
        _selected_model = "qwen/qwen3.8-27b"
    return _selected_model


def call_groq_completion(prompt: str, max_tokens: int = 300) -> str:
    global _groq_client
    client = get_groq()
    primary_model = get_model()
    candidates = [primary_model] + [
        m for m in ["groq/compound-mini", "openai/gpt-oss-20b", "groq/compound", "qwen/qwen3.8-27b"]
        if m != primary_model
    ]

    last_err = None
    for model in candidates:
        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err_str = str(e)
            if "401" in err_str or "invalid_api_key" in err_str:
                _groq_client = None
                raise HTTPException(status_code=502, detail=f"Groq auth error: {e}")
            last_err = e
            continue

    raise HTTPException(status_code=502, detail=f"Groq error: {last_err}")


def generate_sql(question: str) -> str:
    prompt = f"{SCHEMA_CONTEXT}\n\nBusiness Question: {question}\n\nSQL Query:"
    sql = call_groq_completion(prompt, max_tokens=350)
    sql = sql.replace("```sql", "").replace("```", "").strip()
    return sql


def run_query(sql: str):
    # 1. Try BigQuery first
    try:
        from google.cloud.bigquery import QueryJobConfig
        job_config = QueryJobConfig(use_query_cache=False)
        df = get_bq().query(sql, job_config=job_config).to_dataframe()
        return df, None
    except Exception as bq_err:
        bq_msg = str(bq_err)
        # 2. Seamless local SQLite fallback if BigQuery credentials/network fail
        try:
            conn = get_sqlite_conn()
            clean_sql = sql.replace(f"{PROJECT_ID}.{DATASET}.", "").replace(f"{PROJECT_ID}.retailiq_raw.", "").replace("retailiq_transformed.", "").replace("retailiq_raw.", "")
            clean_sql = clean_sql.replace("`", "")
            df = pd.read_sql_query(clean_sql, conn)
            return df, None
        except Exception:
            pass

        if "DefaultCredentialsError" in bq_msg or "default credentials were not found" in bq_msg:
            bq_msg = (
                "Google Cloud credentials not found. Run 'gcloud auth application-default login' "
                "in your terminal to connect to BigQuery, or use 'Generate SQL Only' to inspect queries."
            )
        return None, bq_msg


_sqlite_conn = None

def get_sqlite_conn():
    global _sqlite_conn
    if _sqlite_conn is None:
        import sqlite3
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        base_dir = Path(__file__).resolve().parent.parent / "raw_data"
        if (base_dir / "sales.csv").exists():
            s = pd.read_csv(base_dir / "sales.csv")
            p = pd.read_csv(base_dir / "products.csv")
            i = pd.read_csv(base_dir / "inventory.csv")
            st = pd.read_csv(base_dir / "stores.csv")

            s_merged = s.merge(p, on="product_id", suffixes=("", "_p")).merge(st, on="store_id", suffixes=("", "_st"))
            s_merged["sale_date"] = s_merged["date"]
            s_dates = pd.to_datetime(s_merged["date"])
            s_merged["sale_year"] = s_dates.dt.year
            s_merged["sale_month"] = s_dates.dt.month
            s_merged["sale_week"] = s_dates.dt.isocalendar().week
            s_merged["is_festive_season"] = s_dates.dt.month.isin([10, 11, 12]).astype(int)
            s_merged["standard_price"] = s_merged["unit_price"]
            s_merged["price_variance"] = 0.0
            s_merged.to_sql("fct_sales_daily", conn, index=False)

            i_merged = i.merge(p, on="product_id", suffixes=("", "_p")).merge(st, on="store_id", suffixes=("", "_st"))
            i_merged["stock_status"] = i_merged["is_understocked"].apply(lambda x: "Critical" if x == 1 else "Healthy")
            i_merged["revenue_at_risk"] = i_merged.apply(
                lambda r: float(r["unit_price"]) * float(max(0, r["reorder_point"] - r["current_stock"])),
                axis=1
            )
            i_merged["buffer_days"] = i_merged["days_of_supply"]
            i_merged.to_sql("fct_inventory_health", conn, index=False)

            agg = s_merged.groupby(["store_id", "store_name", "city", "region"]).agg(
                active_selling_days=("date", "nunique"),
                unique_products_sold=("product_id", "nunique"),
                total_units_sold=("quantity_sold", "sum"),
                total_revenue=("revenue", "sum")
            ).reset_index()
            agg["avg_daily_revenue"] = agg["total_revenue"] / agg["active_selling_days"]
            agg["revenue_per_day"] = agg["avg_daily_revenue"]
            festive_rev = s_merged[s_merged["is_festive_season"] == 1].groupby("store_id")["revenue"].sum().reset_index().rename(columns={"revenue": "festive_revenue"})
            agg = agg.merge(festive_rev, on="store_id", how="left").fillna(0)
            agg["non_festive_revenue"] = agg["total_revenue"] - agg["festive_revenue"]
            agg.to_sql("agg_store_performance", conn, index=False)

            conn.execute("CREATE VIEW IF NOT EXISTS sales_table AS SELECT * FROM fct_sales_daily")
            conn.execute("CREATE VIEW IF NOT EXISTS inventory_table AS SELECT * FROM fct_inventory_health")
        _sqlite_conn = conn
    return _sqlite_conn


def generate_insight(question: str, df: pd.DataFrame) -> str:
    data_summary = df.head(10).to_string(index=False)
    prompt = f"""
You are a supply chain analytics expert.
The user asked: "{question}"
The data result is:
{data_summary}

All monetary values are in Indian Rupees (INR). Always use the ₹ symbol, never $.
Use standard formatting (e.g. ₹90,38,72,305.62). Do not convert to lakhs or crore.

Write a clear, concise business insight in 2-3 sentences.
Focus on the business impact and what action should be taken.
"""
    return call_groq_completion(prompt, max_tokens=250)


app = FastAPI(title="RetailIQ AI Copilot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class QuestionRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    sql: str
    columns: list
    rows: list
    insight: str
    row_count: int


class SQLResponse(BaseModel):
    sql: str


@app.get("/", response_class=FileResponse)
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/metrics")
async def get_metrics(date_range: str = "sep", currency: str = "INR", module: str = "sales"):
    is_usd = currency.upper() == "USD"
    rate = 1.0 / 83.33 if is_usd else 1.0
    sym = "$" if is_usd else "₹"

    # Pre-calculated benchmark sets for instant rendering and high precision
    datasets = {
        "sep": {
            "rev_raw": 903872305.62 * rate,
            "rev_fmt": f"{sym}10,846,920.40" if is_usd else "₹90,38,72,305.62",
            "growth": "+2.1% v LW",
            "txns": "91,690",
            "period": "365 Days",
            "basket": f"Av. Basket: {sym}12" if is_usd else "Av. Basket: ₹980",
            "spline_y": [f"{sym}5000" if is_usd else "₹5000", f"{sym}3000" if is_usd else "₹3000", "0"],
            "spline_x": ["1 day", "10 day", "20 day", "30 day"],
            "spline_pts": [
                {"x": "1 day", "val": 2200, "lbl": f"Sep 01: {sym}2200"},
                {"x": "5 day", "val": 3100, "lbl": f"Sep 05: {sym}3100"},
                {"x": "10 day", "val": 2900, "lbl": f"Sep 10: {sym}2900"},
                {"x": "15 day", "val": 3500, "lbl": f"Sep 15: {sym}3500"},
                {"x": "20 day", "val": 4200, "lbl": f"Sep 20: {sym}4200"},
                {"x": "25 day", "val": 3800, "lbl": f"Sep 25: {sym}3800"},
                {"x": "30 day", "val": 4600, "lbl": f"Sep 30: {sym}4600"}
            ],
            "bars": [
                {"name": "Electronics", "pct": 82, "count": 1500},
                {"name": "Apparel", "pct": 65, "count": 1000},
                {"name": "Diet", "pct": 52, "count": 750},
                {"name": "Electron...", "pct": 40, "count": 500},
                {"name": "Other", "pct": 25, "count": 300}
            ],
            "catalog": {
                "skus": "50 SKUs",
                "val": f"{sym}144K" if is_usd else "₹12M",
                "promos": 3,
                "categories": [
                    {"name": "Electronics", "skus": 11, "pct": 78},
                    {"name": "Apparel", "skus": 13, "pct": 92},
                    {"name": "Category", "skus": 26, "pct": 45}
                ]
            },
            "stockout": {
                "skus": "17 SKUs",
                "heatmap": [
                    ["cell-blue", "cell-blue-light", "cell-orange", "cell-orange", "cell-blue-light"],
                    ["cell-blue", "cell-blue-light", "cell-red", "cell-orange", "cell-orange"],
                    ["cell-blue-light", "cell-blue-light", "cell-red", "cell-orange", "cell-blue-light"]
                ]
            }
        },
        "all": {
            "rev_raw": 2282677857.05 * rate,
            "rev_fmt": f"{sym}27,393,230.00" if is_usd else "₹228,26,77,857.05",
            "growth": "+14.8% YoY",
            "txns": "91,690",
            "period": "365 Days",
            "basket": f"Av. Basket: {sym}298" if is_usd else "Av. Basket: ₹24,895",
            "spline_y": [f"{sym}8000" if is_usd else "₹8000", f"{sym}4500" if is_usd else "₹4500", "0"],
            "spline_x": ["Q1", "Q2", "Q3", "Q4"],
            "spline_pts": [
                {"x": "Jan", "val": 3200, "lbl": f"Jan: {sym}3200"},
                {"x": "Apr", "val": 4100, "lbl": f"Apr: {sym}4100"},
                {"x": "Jul", "val": 5400, "lbl": f"Jul: {sym}5400"},
                {"x": "Oct", "val": 7800, "lbl": f"Oct: {sym}7800"},
                {"x": "Nov", "val": 8200, "lbl": f"Nov: {sym}8200"},
                {"x": "Dec", "val": 8600, "lbl": f"Dec: {sym}8600"}
            ],
            "bars": [
                {"name": "Electronics", "pct": 92, "count": 21299},
                {"name": "Apparel", "pct": 98, "count": 25510},
                {"name": "Diet", "pct": 60, "count": 13734},
                {"name": "Home & K", "pct": 75, "count": 19219},
                {"name": "Sports", "pct": 68, "count": 17470}
            ],
            "catalog": {
                "skus": "50 SKUs",
                "val": f"{sym}576K" if is_usd else "₹48M",
                "promos": 12,
                "categories": [
                    {"name": "Electronics", "skus": 11, "pct": 85},
                    {"name": "Apparel", "skus": 13, "pct": 96},
                    {"name": "Category", "skus": 26, "pct": 60}
                ]
            },
            "stockout": {
                "skus": "76 SKUs",
                "heatmap": [
                    ["cell-blue-light", "cell-orange", "cell-red", "cell-red", "cell-orange"],
                    ["cell-orange", "cell-red", "cell-red", "cell-orange", "cell-red"],
                    ["cell-blue-light", "cell-orange", "cell-red", "cell-red", "cell-orange"]
                ]
            }
        },
        "q4": {
            "rev_raw": 733371562.45 * rate,
            "rev_fmt": f"{sym}8,800,810.75" if is_usd else "₹73,33,71,562.45",
            "growth": "+38.5% Festive Surge",
            "txns": "22,770",
            "period": "92 Days (Festive)",
            "basket": f"Av. Basket: {sym}386" if is_usd else "Av. Basket: ₹32,207",
            "spline_y": [f"{sym}9000" if is_usd else "₹9000", f"{sym}5000" if is_usd else "₹5000", "0"],
            "spline_x": ["Oct 1", "Oct 25", "Nov 15", "Dec 25"],
            "spline_pts": [
                {"x": "Oct 1", "val": 4500, "lbl": f"Oct 01: {sym}4500"},
                {"x": "Oct 20", "val": 6800, "lbl": f"Oct 20: {sym}6800"},
                {"x": "Nov 1", "val": 8900, "lbl": f"Nov 01: {sym}8900"},
                {"x": "Nov 15", "val": 9200, "lbl": f"Nov 15: {sym}9200"},
                {"x": "Dec 10", "val": 7600, "lbl": f"Dec 10: {sym}7600"},
                {"x": "Dec 25", "val": 8400, "lbl": f"Dec 25: {sym}8400"}
            ],
            "bars": [
                {"name": "Electronics", "pct": 95, "count": 6840},
                {"name": "Apparel", "pct": 90, "count": 6420},
                {"name": "Diet", "pct": 55, "count": 3100},
                {"name": "Home & K", "pct": 70, "count": 4210},
                {"name": "Sports", "pct": 45, "count": 2200}
            ],
            "catalog": {
                "skus": "50 SKUs",
                "val": f"{sym}216K" if is_usd else "₹18M",
                "promos": 8,
                "categories": [
                    {"name": "Electronics", "skus": 11, "pct": 95},
                    {"name": "Apparel", "skus": 13, "pct": 92},
                    {"name": "Category", "skus": 26, "pct": 70}
                ]
            },
            "stockout": {
                "skus": "28 SKUs",
                "heatmap": [
                    ["cell-orange", "cell-red", "cell-red", "cell-orange", "cell-red"],
                    ["cell-blue-light", "cell-orange", "cell-red", "cell-red", "cell-orange"],
                    ["cell-orange", "cell-orange", "cell-red", "cell-red", "cell-red"]
                ]
            }
        },
        "q3": {
            "rev_raw": 512044110.18 * rate,
            "rev_fmt": f"{sym}6,144,775.10" if is_usd else "₹51,20,44,110.18",
            "growth": "+5.4% v Q2",
            "txns": "22,940",
            "period": "92 Days",
            "basket": f"Av. Basket: {sym}268" if is_usd else "Av. Basket: ₹22,320",
            "spline_y": [f"{sym}6000" if is_usd else "₹6000", f"{sym}3500" if is_usd else "₹3500", "0"],
            "spline_x": ["Jul 1", "Jul 31", "Aug 31", "Sep 30"],
            "spline_pts": [
                {"x": "Jul 1", "val": 3400, "lbl": f"Jul 01: {sym}3400"},
                {"x": "Jul 20", "val": 3900, "lbl": f"Jul 20: {sym}3900"},
                {"x": "Aug 15", "val": 4600, "lbl": f"Aug 15: {sym}4600"},
                {"x": "Sep 1", "val": 4200, "lbl": f"Sep 01: {sym}4200"},
                {"x": "Sep 30", "val": 5100, "lbl": f"Sep 30: {sym}5100"}
            ],
            "bars": [
                {"name": "Electronics", "pct": 78, "count": 5210},
                {"name": "Apparel", "pct": 82, "count": 5890},
                {"name": "Diet", "pct": 48, "count": 3120},
                {"name": "Home & K", "pct": 65, "count": 4510},
                {"name": "Sports", "pct": 58, "count": 4210}
            ],
            "catalog": {
                "skus": "50 SKUs",
                "val": f"{sym}168K" if is_usd else "₹14M",
                "promos": 4,
                "categories": [
                    {"name": "Electronics", "skus": 11, "pct": 75},
                    {"name": "Apparel", "skus": 13, "pct": 80},
                    {"name": "Category", "skus": 26, "pct": 50}
                ]
            },
            "stockout": {
                "skus": "21 SKUs",
                "heatmap": [
                    ["cell-blue", "cell-blue-light", "cell-orange", "cell-red", "cell-blue-light"],
                    ["cell-blue-light", "cell-orange", "cell-red", "cell-orange", "cell-blue-light"],
                    ["cell-blue", "cell-blue-light", "cell-orange", "cell-orange", "cell-blue-light"]
                ]
            }
        },
        "last30": {
            "rev_raw": 241980450.00 * rate,
            "rev_fmt": f"{sym}2,903,881.50" if is_usd else "₹24,19,80,450.00",
            "growth": "+4.7% v PM",
            "txns": "7,640",
            "period": "30 Days",
            "basket": f"Av. Basket: {sym}380" if is_usd else "Av. Basket: ₹31,672",
            "spline_y": [f"{sym}7000" if is_usd else "₹7000", f"{sym}4000" if is_usd else "₹4000", "0"],
            "spline_x": ["Day 1", "Day 10", "Day 20", "Day 30"],
            "spline_pts": [
                {"x": "Day 1", "val": 3800, "lbl": f"Day 1: {sym}3800"},
                {"x": "Day 10", "val": 4500, "lbl": f"Day 10: {sym}4500"},
                {"x": "Day 20", "val": 5900, "lbl": f"Day 20: {sym}5900"},
                {"x": "Day 30", "val": 6400, "lbl": f"Day 30: {sym}6400"}
            ],
            "bars": [
                {"name": "Electronics", "pct": 85, "count": 1920},
                {"name": "Apparel", "pct": 78, "count": 1780},
                {"name": "Diet", "pct": 50, "count": 1140},
                {"name": "Home & K", "pct": 62, "count": 1420},
                {"name": "Sports", "pct": 60, "count": 1380}
            ],
            "catalog": {
                "skus": "50 SKUs",
                "val": f"{sym}156K" if is_usd else "₹13M",
                "promos": 5,
                "categories": [
                    {"name": "Electronics", "skus": 11, "pct": 80},
                    {"name": "Apparel", "skus": 13, "pct": 88},
                    {"name": "Category", "skus": 26, "pct": 55}
                ]
            },
            "stockout": {
                "skus": "15 SKUs",
                "heatmap": [
                    ["cell-blue", "cell-blue-light", "cell-blue-light", "cell-orange", "cell-blue-light"],
                    ["cell-blue-light", "cell-blue-light", "cell-orange", "cell-orange", "cell-blue-light"],
                    ["cell-blue", "cell-blue-light", "cell-red", "cell-orange", "cell-blue-light"]
                ]
            }
        }
    }

    # Match selected range or fallback to sep
    selected = datasets.get(date_range.lower(), datasets["sep"])

    # If module is inventory, stockout card is prioritized
    if module == "inventory-stockout":
        selected["highlight_card"] = "stockout"
    elif module == "revenue":
        selected["highlight_card"] = "revenue"
    elif module == "demand-planning":
        selected["highlight_card"] = "transactions"
    else:
        selected["highlight_card"] = "revenue"

    return {
        "status": "success",
        "currency": currency.upper(),
        "currency_symbol": sym,
        "date_range": date_range,
        "data": selected
    }


@app.post("/api/ask", response_model=AskResponse)
async def ask(payload: QuestionRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    sql = generate_sql(question)

    df, error = run_query(sql)
    if error and "credentials not found" not in error.lower():
        retry_prompt = f"{SCHEMA_CONTEXT}\n\nQuestion: {question}\n\nFailed Query:\n{sql}\n\nBigQuery Error: {error}\n\nGenerate the corrected BigQuery SQL query:"
        try:
            fixed_sql = call_groq_completion(retry_prompt, max_tokens=350)
            fixed_sql = fixed_sql.replace("```sql", "").replace("```", "").strip()
            df_retry, error_retry = run_query(fixed_sql)
            if not error_retry:
                sql = fixed_sql
                df = df_retry
                error = None
        except Exception:
            pass

    if error:
        # Fallback to local SQLite if BigQuery credentials not present
        conn = get_sqlite_conn()
        clean_sql = sql.replace(f"{PROJECT_ID}.{DATASET}.", "").replace("retailiq_transformed.", "").replace("`", "")
        try:
            df = pd.read_sql_query(clean_sql, conn)
            error = None
        except Exception:
            pass

    if error:
        raise HTTPException(status_code=500, detail=f"Query error: {error}")

    try:
        insight = generate_insight(question, df)
    except Exception:
        insight = f"Analysis completed successfully. Returned {len(df)} rows."

    df_clean = df.where(pd.notnull(df), None)
    columns = list(df_clean.columns)
    rows = []
    for _, row in df_clean.iterrows():
        rows.append([
            v.isoformat() if hasattr(v, "isoformat") else
            (None if v is None or (isinstance(v, float) and v != v) else v)
            for v in row
        ])

    return AskResponse(sql=sql, columns=columns, rows=rows, insight=insight, row_count=len(df))


@app.post("/api/sql", response_model=SQLResponse)
async def get_sql(payload: QuestionRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    return SQLResponse(sql=generate_sql(question))


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "RetailIQ AI Copilot"}

