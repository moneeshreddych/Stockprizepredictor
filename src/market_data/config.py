# src/market_data/config.py
"""Configuration for Twelve Data collector.
Defines the list of supported symbols and reads environment variables.
"""
import os

# List of exactly 20 symbols (U.S. equities/ETFs)
STOCK_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "NFLX",
    "JPM",
    "V",
    "MA",
    "WMT",
    "KO",
    "PEP",
    "MCD",
    "INTC",
    "AMD",
    "ADBE",
    "ORCL",
    "QCOM",
]

# Environment variables (loaded from .env by the Flask app / collector)
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
TWELVE_DATA_POLL_SECONDS = int(os.getenv("TWELVE_DATA_POLL_SECONDS", "60"))
TWELVE_DATA_DAILY_LIMIT = int(os.getenv("TWELVE_DATA_DAILY_LIMIT", "700"))

if not TWELVE_DATA_API_KEY:
    raise RuntimeError("TWELVE_DATA_API_KEY is required in environment")

def build_batch_url():
    symbols_param = ",".join(STOCK_SYMBOLS)
    return f"https://api.twelvedata.com/quote?symbol={symbols_param}&apikey={TWELVE_DATA_API_KEY}"
