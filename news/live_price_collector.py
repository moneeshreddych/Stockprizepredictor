"""Collect completed daily closes into Supabase."""

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
TWELVE_DATA_URL = "https://api.twelvedata.com/time_series"


def _parse_timestamp(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


def fetch_quote(symbol: str) -> Dict[str, Any]:
    if not TWELVE_DATA_API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY is missing")

    response = requests.get(
        TWELVE_DATA_URL,
        params={
            "symbol": symbol,
            "interval": "1day",
            "outputsize": 3,
            "apikey": TWELVE_DATA_API_KEY,
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") == "error" or payload.get("code"):
        raise RuntimeError(payload.get("message", "Twelve Data returned an error"))

    values = payload.get("values") or []
    if len(values) < 2:
        raise RuntimeError(f"Not enough completed daily candles for {symbol}")

    latest = values[0]
    prior = values[1]
    close = float(latest["close"])
    prior_close = float(prior["close"])
    change = ((close - prior_close) / prior_close * 100) if prior_close else 0.0

    return {
        "symbol": symbol,
        "price": close,
        "previous_close": prior_close,
        "change": change,
        "timestamp": _parse_timestamp(latest.get("datetime")),
        "price_type": "previous_close",
    }


def collect_live_prices() -> int:
    stored = 0
    symbols = list(get_nasdaq_stocks().keys())
    print(f"Collecting {len(symbols)} completed daily closes...")
    for symbol in symbols:
        try:
            row = fetch_quote(symbol)
            supabase.table("stock_latest").upsert(row, on_conflict="symbol").execute()
            stored += 1
            print(f"{symbol}: {row['price']:.2f} ({row['change']:+.2f}%) @ {row['timestamp']}")
        except Exception as exc:
            print(f"{symbol}: failed - {exc}")
    print(f"Stored {stored}/{len(symbols)} completed closes in stock_latest")
    return stored


if __name__ == "__main__":
    collect_live_prices()
