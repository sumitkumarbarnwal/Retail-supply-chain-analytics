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

PROJECT_ID = "retailiq-analytics-502010"
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
        from google.cloud import bigquery
        _bq_client = bigquery.Client(project=PROJECT_ID)
    return _bq_client


SCHEMA_CONTEXT = """
You are an expert supply chain data analyst AI for RetailIQ — a retail analytics platform.
Your job is to convert business questions into accurate BigQuery SQL queries.

=== CURRENCY ===
All monetary columns (revenue, unit_price, standard_price, price_variance, revenue_at_risk) are in Indian Rupees (INR/₹). Never use USD or $ when referring to these values.

=== DATABASE: retailiq-analytics-502010.retailiq_transformed ===

=== TABLE 1: fct_sales_daily ===
Purpose: Daily sales transactions — use for revenue, sales volume, product and store performance
Columns:
  sale_date          DATE        -- transaction date
  sale_year          INT64       -- year extracted from sale_date
  sale_month         INT64       -- month number (1-12)
  sale_week          INT64       -- week number
  is_festive_season  BOOL        -- TRUE for Oct/Nov/Dec, FALSE otherwise
  store_id           STRING      -- store identifier e.g. STR01
  store_name         STRING      -- full store name e.g. Mumbai Retail Hub
  city               STRING      -- city name
  region             STRING      -- East, West, North, South
  product_id         STRING      -- product identifier e.g. PRD001
  product_name       STRING      -- full product name
  category           STRING      -- Electronics, Apparel, Grocery, Home & Kitchen, Sports
  supplier_id        STRING      -- supplier identifier e.g. SUP01
  quantity_sold      INT64       -- number of units sold
  unit_price         FLOAT64     -- actual selling price
  revenue            FLOAT64     -- total revenue = quantity_sold * unit_price
  standard_price     FLOAT64     -- standard product price
  price_variance     FLOAT64     -- difference between revenue and standard cost

=== TABLE 2: fct_inventory_health ===
Purpose: Inventory snapshot — use for stockout risk, understocking, days of supply
IMPORTANT: For any question about stockout risk, understocking, or revenue impact, ALWAYS include revenue_at_risk in the SELECT clause.
NOTE: This table does NOT have supplier_id. To get supplier info join with fct_sales_daily on product_id.
Columns:
  snapshot_date      STRING      -- inventory snapshot date
  store_id           STRING      -- store identifier
  store_name         STRING      -- full store name
  city               STRING      -- city name
  region             STRING      -- East, West, North, South
  product_id         STRING      -- product identifier
  product_name       STRING      -- full product name
  category           STRING      -- Electronics, Apparel, Grocery, Home & Kitchen, Sports
  unit_price         FLOAT64     -- product unit price
  current_stock      INT64       -- current stock quantity
  reorder_point      INT64       -- minimum safe stock level
  days_of_supply     FLOAT64     -- estimated days until stockout
  is_understocked    INT64       -- 1 = below reorder point, 0 = healthy (NOT BOOL — use 1 or 0)
  stock_status       STRING      -- exactly one of: 'Stockout', 'Critical', 'Low', 'Healthy'
  revenue_at_risk    FLOAT64     -- potential revenue loss if stockout occurs
  buffer_days        FLOAT64     -- days until reorder is needed

=== TABLE 3: agg_store_performance ===
Purpose: Aggregated store KPIs — use for store-level comparisons and rankings
NOTE: This table does NOT have supplier_id or product-level details.
Columns:
  store_id              STRING   -- store identifier
  store_name            STRING   -- full store name
  city                  STRING   -- city name
  region                STRING   -- East, West, North, South
  active_selling_days   INT64    -- number of days with sales
  unique_products_sold  INT64    -- distinct products sold
  total_units_sold      INT64    -- total quantity sold
  total_revenue         FLOAT64  -- total revenue across all products
  avg_daily_revenue     FLOAT64  -- average revenue per day
  revenue_per_day       FLOAT64  -- total revenue / active selling days
  festive_revenue       FLOAT64  -- revenue during Oct/Nov/Dec
  non_festive_revenue   FLOAT64  -- revenue outside Oct/Nov/Dec

=== STRICT SQL RULES ===
1. Always use fully qualified table names:
   retailiq-analytics-502010.retailiq_transformed.fct_sales_daily
   retailiq-analytics-502010.retailiq_transformed.fct_inventory_health
   retailiq-analytics-502010.retailiq_transformed.agg_store_performance

2. DATA TYPE RULES — follow exactly:
   - is_festive_season is BOOL → use: WHERE is_festive_season = TRUE or FALSE
   - is_understocked is INT64 → use: WHERE is_understocked = 1 or = 0
   - stock_status is STRING → use: WHERE stock_status = 'Stockout' (exact match, case sensitive)
   - Never mix BOOL and INT64 comparisons

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


def generate_sql(question: str) -> str:
    global _groq_client
    prompt = f"{SCHEMA_CONTEXT}\n\nBusiness Question: {question}\n\nSQL Query:"
    try:
        response = get_groq().chat.completions.create(
            model=get_model(),
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        if "401" in str(e) or "invalid_api_key" in str(e):
            _groq_client = None
        raise HTTPException(status_code=502, detail=f"Groq error: {e}")
    sql = response.choices[0].message.content.strip()
    sql = sql.replace("```sql", "").replace("```", "").strip()
    return sql


def run_query(sql: str):
    try:
        from google.cloud.bigquery import QueryJobConfig
        job_config = QueryJobConfig(use_query_cache=False)
        df = get_bq().query(sql, job_config=job_config).to_dataframe()
        return df, None
    except Exception as e:
        err_msg = str(e)
        if "DefaultCredentialsError" in err_msg or "default credentials were not found" in err_msg:
            err_msg = (
                "Google Cloud credentials not found. Run 'gcloud auth application-default login' "
                "in your terminal to connect to BigQuery, or use 'Generate SQL Only' to inspect queries."
            )
        return None, err_msg


def generate_insight(question: str, df: pd.DataFrame) -> str:
    global _groq_client
    data_summary = df.to_string(index=False)
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
    try:
        response = get_groq().chat.completions.create(
            model=get_model(),
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        if "401" in str(e) or "invalid_api_key" in str(e):
            _groq_client = None
        raise HTTPException(status_code=502, detail=f"Groq error: {e}")
    return response.choices[0].message.content.strip()


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


@app.post("/api/ask", response_model=AskResponse)
async def ask(payload: QuestionRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    sql = generate_sql(question)

    df, error = run_query(sql)
    if error:
        if "credentials not found" in error.lower():
            return AskResponse(
                sql=sql,
                columns=["Notice"],
                rows=[["BigQuery credentials required for live table execution. SQL successfully generated above."]],
                insight=(
                    "SQL generated successfully via Groq AI! To execute this query live against Google BigQuery, "
                    "authenticate Google Cloud by running 'gcloud auth application-default login' in your terminal."
                ),
                row_count=0
            )
        raise HTTPException(status_code=500, detail=f"BigQuery error: {error}")

    insight = generate_insight(question, df)

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
