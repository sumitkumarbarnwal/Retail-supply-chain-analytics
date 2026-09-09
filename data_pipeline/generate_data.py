import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import os

np.random.seed(42)
random.seed(42)

N_PRODUCTS = 50
N_STORES   = 10
N_DAYS     = 365
START_DATE = datetime(2024, 1, 1)

categories = ["Electronics", "Apparel", "Grocery", "Home & Kitchen", "Sports"]
brands     = ["Samsung", "Nike", "Nestlé", "IKEA", "Adidas",
              "Apple", "Puma", "Britannia", "Philips", "Reebok"]

products = []
for i in range(1, N_PRODUCTS + 1):
    category = random.choice(categories)
    products.append({
        "product_id"    : f"PRD{i:03d}",
        "product_name"  : f"{random.choice(brands)} {category} Item {i}",
        "category"      : category,
        "unit_price"    : round(random.uniform(50, 5000), 2),
        "reorder_point" : random.randint(10, 50),
        "lead_time_days": random.randint(3, 14),
        "supplier_id"   : f"SUP{random.randint(1, 10):02d}",
    })

products_df = pd.DataFrame(products)
print(f"Products generated: {len(products_df)}")

cities = ["Mumbai", "Delhi", "Bengaluru", "Pune", "Hyderabad",
          "Chennai", "Kolkata", "Ahmedabad", "Surat", "Jaipur"]

stores = []
for i in range(1, N_STORES + 1):
    stores.append({
        "store_id"        : f"STR{i:02d}",
        "store_name"      : f"{cities[i-1]} Retail Hub",
        "city"            : cities[i-1],
        "region"          : "North" if cities[i-1] in ["Delhi", "Jaipur"] else
                            "West"  if cities[i-1] in ["Mumbai", "Pune", "Ahmedabad", "Surat"] else
                            "South" if cities[i-1] in ["Bengaluru", "Hyderabad", "Chennai"] else "East",
        "store_size_sqft" : random.randint(2000, 10000),
    })

stores_df = pd.DataFrame(stores)
print(f"Stores generated: {len(stores_df)}")

sales = []
for day in range(N_DAYS):
    date = START_DATE + timedelta(days=day)
    is_weekend  = date.weekday() >= 5
    is_festive  = date.month in [10, 11, 12]
    multiplier  = 1.5 if is_festive else 1.0
    multiplier *= 1.3 if is_weekend else 1.0

    for store in stores:
        active_products = random.sample(products, k=random.randint(15, 35))
        for product in active_products:
            quantity   = int(np.random.poisson(8) * multiplier) + 1
            unit_price = product["unit_price"] * random.uniform(0.95, 1.05)
            sales.append({
                "sale_id"      : f"SL{day:04d}{store['store_id']}{product['product_id']}",
                "date"         : date.strftime("%Y-%m-%d"),
                "store_id"     : store["store_id"],
                "product_id"   : product["product_id"],
                "quantity_sold": quantity,
                "unit_price"   : round(unit_price, 2),
                "revenue"      : round(quantity * unit_price, 2),
            })

sales_df = pd.DataFrame(sales)
print(f"Sales records generated: {len(sales_df):,}")

inventory = []
for store in stores:
    for product in products:
        current_stock = random.randint(0, 200)
        inventory.append({
            "snapshot_date"  : "2024-12-31",
            "store_id"       : store["store_id"],
            "product_id"     : product["product_id"],
            "current_stock"  : current_stock,
            "reorder_point"  : product["reorder_point"],
            "is_understocked": 1 if current_stock < product["reorder_point"] else 0,
            "days_of_supply" : round(current_stock / max(random.randint(1, 20), 1), 1),
        })

inventory_df = pd.DataFrame(inventory)
print(f"Inventory records generated: {len(inventory_df):,}")

os.makedirs("raw_data", exist_ok=True)
products_df.to_csv("raw_data/products.csv",   index=False)
stores_df.to_csv("raw_data/stores.csv",       index=False)
sales_df.to_csv("raw_data/sales.csv",         index=False)
inventory_df.to_csv("raw_data/inventory.csv", index=False)

print("\nAll files saved to raw_data/")
print(f"  products.csv   : {len(products_df):,} rows")
print(f"  stores.csv     : {len(stores_df):,} rows")
print(f"  sales.csv      : {len(sales_df):,} rows")
print(f"  inventory.csv  : {len(inventory_df):,} rows")