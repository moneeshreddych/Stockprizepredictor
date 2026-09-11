import os
import asyncio
import datetime
import logging
from typing import List, Dict, Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

from src.collector.config import STOCK_SYMBOLS, POLL_INTERVAL_SECONDS, INDICATORS, API_DAILY_LIMIT, TABLE_LATEST
from src.collector.rate_limiter import TokenBucket
from src.collector.utils import parse_price_response
from src.database.supabase_client import supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("collector")

app = FastAPI()

# Initialise token bucket for API request limiting (800 requests per day)
api_token_bucket = TokenBucket(max_tokens=API_DAILY_LIMIT, refill_interval_seconds=24*60*60)

def build_twelvedata_url(symbol: str) -> str:
    base = "https://api.twelvedata.com/price"
    api_key = os.getenv("TWELVEDATA_API_KEY")
    return f"{base}?symbol={symbol}&apikey={api_key}"

async def fetch_price(symbol: str) -> Dict[str, Any]:
    if not api_token_bucket.consume(1):
        logger.warning("API daily limit exhausted, skipping fetch for %s", symbol)
        return {"symbol": symbol, "price": None, "timestamp": None}
    url = build_twelvedata_url(symbol)
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return parse_price_response(symbol, data)
        except Exception as exc:
            logger.error("Failed to fetch price for %s: %s", symbol, exc)
            return {"symbol": symbol, "price": None, "timestamp": None}

async def collect_prices() -> List[Dict[str, Any]]:
    tasks = [fetch_price(sym) for sym in STOCK_SYMBOLS]
    results = await asyncio.gather(*tasks)
    # Upsert into Supabase (stock_latest table)
    for rec in results:
        if rec.get("price") is not None:
            try:
                supabase.table(TABLE_LATEST).upsert([rec], on_conflict="symbol").execute()
            except Exception as exc:
                logger.error("Supabase upsert failed for %s: %s", rec["symbol"], exc)
    return results

@app.get("/api/latest-prices")
async def latest_prices():
    try:
        resp = supabase.table(TABLE_LATEST).select("symbol,price,updated_at").order("symbol").execute()
        data = resp.data or []
        return JSONResponse(content={"data": data})
    except Exception as exc:
        logger.error("Failed to fetch latest prices from Supabase: %s", exc)
        return JSONResponse(content={"error": "Unable to retrieve data"}, status_code=500)

async def background_collector():
    logger.info("Starting price collector loop with interval %s seconds", POLL_INTERVAL_SECONDS)
    while True:
        await collect_prices()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(background_collector())

if __name__ == "__main__":
    port = int(os.getenv("COLLECTOR_PORT", "8001"))
    uvicorn.run("src.collector.main:app", host="0.0.0.0", port=port, reload=False)
