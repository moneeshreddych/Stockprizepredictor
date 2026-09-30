"""Collect the configured US equity closing quotes into Supabase."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.supabase_client import supabase
from news.stock_config import get_nasdaq_stocks

load_dotenv(PROJECT_ROOT / ".env")

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY") or os.getenv("TWELVEDATA_API_KEY")
TWELVE_DATA_URL = "https://api.twelvedata.com/quote"


def fetch_quote(symbol: str) -> Dict[str, Any]:
    if not TWELVE_DATA_API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY is missing")

    response = requests.get(
        TWELVE_DATA_URL,
        params={"symbol": symbol, "apikey": TWELVE_DATA_API_KEY},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") == "error" or payload.get("code"):
        raise RuntimeError(payload.get("message", "Twelve Data returned an error"))

    price = payload.get("close")
    previous_close = payload.get("previous_close")
    if price is None or previous_close is None:
        raise RuntimeError(f"Incomplete quote returned for {symbol}")

    price = float(price)
    previous_close = float(previous_close)
    change_percent = ((price - previous_close) / previous_close * 100) if previous_close else 0.0

    raw_timestamp = payload.get("datetime") or payload.get("timestamp")
    try:
        if raw_timestamp and isinstance(raw_timestamp, str):
            timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        else:
            timestamp = datetime.now(timezone.utc).isoformat()
    except ValueError:
        timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "symbol": symbol,
        "price": price,
        "previous_close": previous_close,
        "change": change_percent,
        "timestamp": timestamp,
        "price_type": "previous_close",
    }


def collect_live_prices() -> int:
    stored = 0
    symbols = list(get_nasdaq_stocks().keys())
    print(f"Collecting {len(symbols)} configured stocks...")
    for symbol in symbols:
        try:
            quote = fetch_quote(symbol)
            supabase.table("stock_latest").upsert(quote, on_conflict="symbol").execute()
            stored += 1
            print(f"{symbol}: {quote['price']:.2f} ({quote['change']:+.2f}%) @ {quote['timestamp']}")
        except Exception as exc:
            print(f"{symbol}: failed - {exc}")
    print(f"Stored {stored}/{len(symbols)} quotes in stock_latest")
    return stored


if __name__ == "__main__":
    collect_live_prices()
