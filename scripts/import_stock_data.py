import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

CSV_FILE = (
    ROOT
    / ".venv"
    / "data"
    / "NASDAQ20_2016_2025_FULL.csv"
)

ENV_FILE = ROOT / ".env"

TABLE_NAME = "stock_prices"

BATCH_SIZE = 500


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv(ENV_FILE)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not SUPABASE_URL:
    raise RuntimeError(
        "SUPABASE_URL is missing from .env"
    )

if not SUPABASE_SECRET_KEY:
    raise RuntimeError(
        "SUPABASE_SECRET_KEY is missing from .env"
    )


# ============================================================
# CONNECT TO SUPABASE
# ============================================================

print("Connecting to Supabase...")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY,
)

print("Supabase connection ready.")


# ============================================================
# CHECK CSV FILE
# ============================================================

if not CSV_FILE.exists():
    raise FileNotFoundError(
        f"Dataset not found:\n{CSV_FILE}"
    )

print()
print(f"Loading dataset: {CSV_FILE}")


# ============================================================
# LOAD CSV
# ============================================================

df = pd.read_csv(CSV_FILE)

print(f"CSV rows: {len(df):,}")


# ============================================================
# VALIDATE CSV COLUMNS
# ============================================================

required_columns = [
    "Ticker",
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "Adj Close",
    "Volume",
]

missing_columns = [
    column
    for column in required_columns
    if column not in df.columns
]

if missing_columns:
    raise RuntimeError(
        f"Missing CSV columns: {missing_columns}"
    )

print("CSV columns validated.")


# ============================================================
# LOAD STOCKS FROM SUPABASE
# ============================================================

print()
print("Loading stocks from Supabase...")

response = (
    supabase
    .table("stocks")
    .select("id,symbol")
    .execute()
)

stocks = response.data or []

if not stocks:
    raise RuntimeError(
        "No records found in Supabase stocks table."
    )


stock_map = {
    stock["symbol"]: stock["id"]
    for stock in stocks
}

print(
    f"Stocks found in Supabase: {len(stock_map)}"
)


# ============================================================
# CHECK CSV TICKERS
# ============================================================

csv_tickers = set(
    df["Ticker"]
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
)

missing_tickers = (
    csv_tickers - set(stock_map.keys())
)

if missing_tickers:
    raise RuntimeError(
        "These CSV tickers are missing from "
        f"Supabase stocks table: "
        f"{sorted(missing_tickers)}"
    )

print(
    "All CSV tickers exist in Supabase stocks table."
)


# ============================================================
# CLEAN TICKER VALUES
# ============================================================

df["Ticker"] = (
    df["Ticker"]
    .astype(str)
    .str.strip()
)


# ============================================================
# CONVERT DATE
# ============================================================

# IMPORTANT:
# Convert the date directly to a string.
# This prevents Python datetime.date objects from
# reaching the JSON serializer.

df["Date"] = (
    pd.to_datetime(
        df["Date"],
        errors="raise",
    )
    .dt.strftime("%Y-%m-%d")
)


# ============================================================
# CREATE STOCK ID
# ============================================================

df["stock_id"] = df["Ticker"].map(stock_map)


if df["stock_id"].isna().any():
    bad_tickers = (
        df.loc[
            df["stock_id"].isna(),
            "Ticker",
        ]
        .unique()
        .tolist()
    )

    raise RuntimeError(
        f"Could not map stock IDs for: {bad_tickers}"
    )


# ============================================================
# RENAME COLUMNS
# ============================================================

df = df.rename(
    columns={
        "Ticker": "symbol",
        "Date": "price_date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adjusted_close",
        "Volume": "volume",
    }
)


# ============================================================
# FORCE DATE TO STRING AGAIN
# ============================================================

# Extra safety check to guarantee that price_date
# is JSON serializable.

df["price_date"] = (
    df["price_date"]
    .astype(str)
)


# ============================================================
# CONVERT NUMERIC COLUMNS
# ============================================================

numeric_columns = [
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
]

for column in numeric_columns:

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce",
    )


# ============================================================
# CONVERT VOLUME
# ============================================================

df["volume"] = pd.to_numeric(
    df["volume"],
    errors="coerce",
)

if df["volume"].isna().any():
    raise RuntimeError(
        "Volume contains invalid or missing values."
    )

df["volume"] = df["volume"].astype("int64")


# ============================================================
# CHECK FOR INVALID VALUES
# ============================================================

print()
print("Checking dataset...")

null_counts = df.isnull().sum()

if null_counts.any():

    print(
        "Warning: NULL values detected:"
    )

    print(
        null_counts[
            null_counts > 0
        ]
    )

else:

    print(
        "No NULL values detected."
    )


# ============================================================
# SELECT DATABASE COLUMNS
# ============================================================

database_columns = [
    "stock_id",
    "symbol",
    "price_date",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
]

df = df[
    database_columns
]


# ============================================================
# CONVERT DATAFRAME TO RECORDS
# ============================================================

records = df.to_dict(
    orient="records"
)


# ============================================================
# MAKE ALL VALUES JSON SAFE
# ============================================================

for record in records:

    # Date must always be a string.
    record["price_date"] = str(
        record["price_date"]
    )

    # Convert pandas NA / NaN values to None.
    for key, value in record.items():

        if pd.isna(value):

            record[key] = None

        elif hasattr(value, "item"):

            record[key] = value.item()


# ============================================================
# FINAL DATE CHECK
# ============================================================

first_date = records[0]["price_date"]

print()
print(
    f"First record date: {first_date}"
)

print(
    f"Date Python type: {type(first_date).__name__}"
)

if not isinstance(first_date, str):

    raise RuntimeError(
        "price_date is not a string. "
        "Import stopped for safety."
    )


# ============================================================
# UPLOAD TO SUPABASE
# ============================================================

total_rows = len(records)

print()
print(
    f"Uploading {total_rows:,} rows..."
)

uploaded = 0


for start in range(
    0,
    total_rows,
    BATCH_SIZE,
):

    end = min(
        start + BATCH_SIZE,
        total_rows,
    )

    batch = records[start:end]

    try:

        (
            supabase
            .table(TABLE_NAME)
            .insert(batch)
            .execute()
        )

    except Exception as error:

        print()
        print(
            "ERROR while uploading batch."
        )

        print(
            f"Rows attempted: {start + 1}-{end}"
        )

        print(
            f"Error: {error}"
        )

        raise

    uploaded = end

    print(
        f"Uploaded "
        f"{uploaded:,}/{total_rows:,}"
    )


# ============================================================
# VERIFY DATABASE COUNT
# ============================================================

print()
print("Import completed.")
print(
    f"Expected rows: {total_rows:,}"
)

count_response = (
    supabase
    .table(TABLE_NAME)
    .select(
        "id",
        count="exact",
    )
    .execute()
)

database_count = (
    count_response.count
)


print(
    f"Database rows: {database_count:,}"
)


# ============================================================
# FINAL RESULT
# ============================================================

if database_count == total_rows:

    print()
    print(
        "SUCCESS!"
    )

    print(
        "All 50,280 dataset rows are "
        "present in Supabase."
    )

else:

    print()
    print(
        "WARNING!"
    )

    print(
        "Database row count does not "
        "match the CSV row count."
    )