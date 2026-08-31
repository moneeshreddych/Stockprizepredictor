import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.supabase_client import supabase
from src.logging_config import setup_logging
from news.stock_config import get_nasdaq_stocks

logger = setup_logging("price_collector")

ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

DATA_DIR = PROJECT_ROOT / "data" / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PRICE_CSV_FILE = DATA_DIR / "stock_prices.csv"

STOCK_SYMBOLS = list(get_nasdaq_stocks().keys())


def load_stock_map() -> Dict[str, int]:
    try:
        response = supabase.table("stocks").select("id,symbol").execute()
        stock_map = {row["symbol"]: row["id"] for row in response.data or []}
        return stock_map
    except Exception as exc:
        logger.warning("Could not load stocks from Supabase: %s", exc)
        return {symbol: idx + 1 for idx, symbol in enumerate(STOCK_SYMBOLS)}


def validate_price_row(row: Dict[str, Any]) -> bool:
    try:
        op = float(row["open"])
        hi = float(row["high"])
        lo = float(row["low"])
        cl = float(row["close"])
        vol = int(row["volume"])

        if math.isnan(op) or math.isnan(hi) or math.isnan(lo) or math.isnan(cl) or math.isnan(vol):
            return False

        if op <= 0 or hi <= 0 or lo <= 0 or cl <= 0 or vol < 0:
            return False

        if hi < lo or hi < op or hi < cl or lo > op or lo > cl:
            return False

        return True
    except (ValueError, TypeError, KeyError):
        return False


def fetch_symbol_prices(symbol: str, period: str = "2y") -> List[Dict[str, Any]]:
    logger.info("Fetching price history for %s (period=%s)...", symbol, period)
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="1d", auto_adjust=False)

        if df is None or df.empty:
            logger.warning("No price data returned for %s", symbol)
            return []

        df = df.reset_index()
        records = []

        for _, row in df.iterrows():
            raw_date = row.get("Date")
            if pd.isna(raw_date):
                continue

            if hasattr(raw_date, "strftime"):
                date_str = raw_date.strftime("%Y-%m-%d")
            else:
                date_str = str(raw_date)[:10]

            open_val = row.get("Open")
            high_val = row.get("High")
            low_val = row.get("Low")
            close_val = row.get("Close")
            vol_val = row.get("Volume")

            if pd.isna(open_val) or pd.isna(high_val) or pd.isna(low_val) or pd.isna(close_val) or pd.isna(vol_val):
                continue

            record = {
                "symbol": symbol,
                "date": date_str,
                "open": round(float(open_val), 4),
                "high": round(float(high_val), 4),
                "low": round(float(low_val), 4),
                "close": round(float(close_val), 4),
                "volume": int(vol_val),
            }

            if validate_price_row(record):
                records.append(record)

        return records
    except Exception as exc:
        logger.error("Error fetching price history for %s: %s", symbol, exc)
        return []


def store_prices(records: List[Dict[str, Any]], stock_map: Dict[str, int]) -> int:
    if not records:
        return 0

    # Save to local CSV store
    new_df = pd.DataFrame(records)
    if PRICE_CSV_FILE.exists():
        try:
            existing_df = pd.read_csv(PRICE_CSV_FILE)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=["symbol", "date"])
            combined_df.to_csv(PRICE_CSV_FILE, index=False)
        except Exception as exc:
            logger.error("Error updating local price CSV: %s", exc)
            new_df.to_csv(PRICE_CSV_FILE, index=False)
    else:
        new_df.to_csv(PRICE_CSV_FILE, index=False)

    # Attempt Supabase save
    db_payload = []
    for r in records:
        symbol = r["symbol"]
        stock_id = stock_map.get(symbol, 1)
        db_payload.append({
            "stock_id": stock_id,
            "symbol": symbol,
            "date": r["date"],
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
            "volume": r["volume"],
        })

    inserted = 0
    batch_size = 100
    for start in range(0, len(db_payload), batch_size):
        batch = db_payload[start:start + batch_size]
        try:
            response = (
                supabase.table("stock_prices")
                .upsert(batch, on_conflict="stock_id,date", ignore_duplicates=False)
                .execute()
            )
            inserted += len(response.data or [])
        except Exception as exc:
            logger.debug("Supabase stock_prices sync deferred: %s", exc)

    return len(records)


def collect_all_prices(period: str = "2y") -> int:
    logger.info("=" * 60)
    logger.info("STARTING OHLCV PRICE COLLECTION (period=%s)", period)
    logger.info("=" * 60)

    stock_map = load_stock_map()
    total_stored = 0

    for symbol in STOCK_SYMBOLS:
        records = fetch_symbol_prices(symbol, period=period)
        count = store_prices(records, stock_map)
        total_stored += count
        logger.info("%s: %d valid price records processed", symbol, count)

    logger.info("=" * 60)
    logger.info("PRICE COLLECTION COMPLETE | Total Records: %d", total_stored)
    logger.info("=" * 60)
    return total_stored


if __name__ == "__main__":
    period_arg = sys.argv[1] if len(sys.argv) > 1 else "2y"
    collect_all_prices(period=period_arg)
