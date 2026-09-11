"""Fetch live quotes from Twelve Data and store them in Supabase."""

import os
import sys
from pathlib import Path
from typing import Dict, Any

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
        raise RuntimeError("TWELVE_DATA_API_KEY is missing from .env")

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
    if price is None:
        raise RuntimeError(f"No price returned for {symbol}")

    previous_close = payload.get("previous_close")
    if previous_close is not None:
        change = float(payload.get("percent_change") or 0)
    else:
        change = None

    return {
        "symbol": symbol,
        "price": float(price),
        "change": change,
    }


def collect_live_prices() -> int:
    stored = 0
    for symbol in get_nasdaq_stocks():
        try:
            quote = fetch_quote(symbol)
            supabase.table("stock_latest").upsert(quote, on_conflict="symbol").execute()
            stored += 1
            print(f"{symbol}: {quote['price']:.2f} ({quote['change']:+.2f}%)")
        except Exception as exc:
            print(f"{symbol}: failed - {exc}")
    print(f"Stored {stored} live quotes in stock_latest")
    return stored


if __name__ == "__main__":
    collect_live_prices()
