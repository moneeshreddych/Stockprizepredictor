# src/collector/config.py

# Centralized list of the 20 stock symbols
STOCK_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "NFLX",
    "JPM", "V", "MA", "WMT", "KO", "PEP", "MCD", "INTC", "AMD", "ADBE",
    "ORCL", "QCOM"
]

# Twelve Data API limits
API_DAILY_LIMIT = 800  # requests per day
WS_CONNECTION_LIMIT = 8   # trial websocket connections

# Collector behavior
POLL_INTERVAL_SECONDS = 60  # fetch latest prices every minute
# Technical indicators to request (Twelve Data API supports many)
INDICATORS = [
    "SMA", "EMA", "RSI", "MACD"
]

# Supabase table names
TABLE_PRICES = "stock_prices"
TABLE_LATEST = "stock_latest"
