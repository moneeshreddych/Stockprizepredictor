"""Market-aware quote service for BullInsights.

Regular U.S. session: fetch live quotes from Finnhub.
Outside the regular session: serve the latest completed close from Supabase,
backfilling missing/zero prices from Yahoo Finance only when necessary.
"""

import os
import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

import requests
import yfinance as yf
from flask import jsonify

from api.news_api import app, supabase
from news.stock_config import get_nasdaq_stocks

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
MARKET_TZ = ZoneInfo("America/New_York")
SYMBOLS = get_nasdaq_stocks()
CLOSE_CACHE = {"created": 0.0, "data": []}
CLOSE_CACHE_SECONDS = 900


def _fallback_market_status():
    now = datetime.now(MARKET_TZ)
    if now.weekday() >= 5:
        return {"is_open": False, "session": None, "source": "schedule"}
    is_open = dt_time(9, 30) <= now.time() < dt_time(16, 0)
    return {"is_open": is_open, "session": "regular" if is_open else None, "source": "schedule"}


def market_status():
    if FINNHUB_API_KEY:
        try:
            response = requests.get(
                f"{FINNHUB_BASE_URL}/stock/market-status",
                params={"exchange": "US", "token": FINNHUB_API_KEY},
                timeout=5,
            )
            response.raise_for_status()
            payload = response.json()
            return {
                "is_open": bool(payload.get("isOpen")) and payload.get("session") == "regular",
                "session": payload.get("session"),
                "holiday": payload.get("holiday"),
                "source": "Finnhub",
            }
        except requests.RequestException:
            app.logger.exception("Finnhub market-status request failed; using schedule fallback")
    return _fallback_market_status()


def fetch_live_quotes():
    rows = []
    if not FINNHUB_API_KEY:
        return rows
    for symbol in SYMBOLS:
        try:
            response = requests.get(
                f"{FINNHUB_BASE_URL}/quote",
                params={"symbol": symbol, "token": FINNHUB_API_KEY},
                timeout=5,
            )
            response.raise_for_status()
            quote = response.json()
            price = float(quote.get("c") or 0)
            if price <= 0:
                continue
            rows.append({
                "symbol": symbol,
                "price": price,
                "change": float(quote.get("dp") or 0),
                "timestamp": quote.get("t"),
                "price_type": "live",
            })
        except (requests.RequestException, TypeError, ValueError):
            app.logger.exception("Finnhub quote request failed for %s", symbol)
    return rows


def load_previous_closes(existing_rows):
    by_symbol = {str(row.get("symbol", "")).upper(): row for row in existing_rows}
    missing = [symbol for symbol in SYMBOLS if float(by_symbol.get(symbol, {}).get("price") or 0) <= 0]
    if missing and (time.time() - CLOSE_CACHE["created"] >= CLOSE_CACHE_SECONDS):
        try:
            data = yf.download(
                tickers=missing,
                period="5d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                group_by="ticker",
                threads=True,
            )
            fallback = []
            for symbol in missing:
                try:
                    frame = data[symbol] if hasattr(data.columns, "levels") and symbol in data.columns.get_level_values(0) else data
                    closes = frame["Close"].dropna()
                    if len(closes):
                        fallback.append({"symbol": symbol, "price": float(closes.iloc[-1]), "change": 0.0, "price_type": "previous_close"})
                except Exception:
                    app.logger.exception("Unable to recover previous close for %s", symbol)
            if fallback:
                CLOSE_CACHE["created"] = time.time()
                CLOSE_CACHE["data"] = fallback
                existing_rows = existing_rows + fallback
                by_symbol.update({row["symbol"]: row for row in fallback})
        except Exception:
            app.logger.exception("Yahoo Finance previous-close fallback failed")

    cached = {row["symbol"]: row for row in CLOSE_CACHE["data"]}
    result = []
    for symbol in SYMBOLS:
        row = by_symbol.get(symbol) or cached.get(symbol) or {"symbol": symbol, "price": None, "change": None}
        price = float(row.get("price") or 0)
        if price > 0:
            result.append({
                "symbol": symbol,
                "price": price,
                "change": row.get("change"),
                "timestamp": row.get("timestamp"),
                "price_type": "previous_close",
            })
        else:
            result.append({"symbol": symbol, "price": None, "change": None, "timestamp": None, "price_type": "previous_close"})
    return result



def market_latest_prices():
    status = market_status()
    if status["is_open"]:
        rows = fetch_live_quotes()
        if rows:
            try:
                supabase.table("stock_latest").upsert(
                    [{"symbol": row["symbol"], "price": row["price"], "change": row["change"]} for row in rows],
                    on_conflict="symbol",
                ).execute()
            except Exception:
                app.logger.exception("Unable to persist live quotes")
        return jsonify({"data": rows, "market_status": "open", "price_type": "live", "source": "Finnhub"})

    try:
        response = supabase.table("stock_latest").select("symbol,price,change,timestamp").order("symbol").execute()
        rows = load_previous_closes(response.data or [])
    except Exception:
        app.logger.exception("Unable to retrieve previous closes from Supabase")
        rows = load_previous_closes([])
    return jsonify({
        "data": rows,
        "market_status": "closed",
        "price_type": "previous_close",
        "source": "Supabase/Yahoo Finance",
        "holiday": status.get("holiday"),
    })


# Replace the original route without changing the rest of the existing API.
app.view_functions["latest_prices"] = market_latest_prices

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
