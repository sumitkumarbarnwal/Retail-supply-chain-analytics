import pandas as pd
from google.cloud import bigquery
import logging
import os
import time

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/bigquery_load.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="a"
)
logger = logging.getLogger("bigquery_load")

PROJECT_ID = "retailiq-analytics-502010"
DATASET_ID = "retailiq_raw"
RAW_DATA   = "raw_data"

client = bigquery.Client(project=PROJECT_ID)


def create_dataset():
    dataset_ref = f"{PROJECT_ID}.{DATASET_ID}"
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = "US"
    try:
        client.create_dataset(dataset, exists_ok=True)
        logger.info(f"Dataset {DATASET_ID} ready")
        print(f"Dataset {DATASET_ID} ready")
    except Exception as e:
        logger.error(f"Error creating dataset: {e}")
        raise


def load_table(csv_file, table_name):
    file_path = os.path.join(RAW_DATA, csv_file)
    df = pd.read_csv(file_path)

    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{table_name}"
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True
    )

    start = time.time()
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()
    elapsed = round(time.time() - start, 2)

    logger.info(f"Loaded {len(df):,} rows into {table_name} in {elapsed}s")
    print(f"  {table_name}: {len(df):,} rows loaded in {elapsed}s")


if __name__ == "__main__":
    print("\nRetailIQ — BigQuery Data Load")
    logger.info("BigQuery Load Started")

    create_dataset()

    tables = {
        "products.csv"  : "raw_products",
        "stores.csv"    : "raw_stores",
        "sales.csv"     : "raw_sales",
        "inventory.csv" : "raw_inventory",
    }

    for csv_file, table_name in tables.items():
        print(f"Loading {csv_file}...")
        load_table(csv_file, table_name)

    print("\nAll tables loaded into BigQuery successfully")
    logger.info("BigQuery Load Complete")