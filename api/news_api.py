import ipaddress
import os
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, Response, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from supabase import create_client
import yfinance as yf
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from news.stock_config import NASDAQ_STOCKS

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
load_dotenv(ROOT / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY") or os.getenv("TWELVEDATA_API_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")

supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
app = Flask(__name__, static_folder=str(FRONTEND), static_url_path="")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def allowed_image_url(value):
    try:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        host = parsed.hostname.lower().rstrip(".")
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except (ValueError, socket.gaierror, OSError):
        return False


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.get("/")
def home():
    return jsonify({"service": "BullInsights API", "status": "ok"})


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "BullInsights API"})


STOCK_FALLBACK_IMAGES = {
    "NVDA": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80",
    "AAPL": "https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?w=600&auto=format&fit=crop&q=80",
    "MSFT": "https://images.unsplash.com/photo-1633419461186-7d40a38105ec?w=600&auto=format&fit=crop&q=80",
    "AMZN": "https://images.unsplash.com/photo-1523474253046-8cd2748b5fd2?w=600&auto=format&fit=crop&q=80",
    "GOOGL": "https://images.unsplash.com/photo-1573804633927-bfcbcd909acd?w=600&auto=format&fit=crop&q=80",
    "GOOG": "https://images.unsplash.com/photo-1573804633927-bfcbcd909acd?w=600&auto=format&fit=crop&q=80",
    "META": "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?w=600&auto=format&fit=crop&q=80",
    "AVGO": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&auto=format&fit=crop&q=80",
    "TSLA": "https://images.unsplash.com/photo-1563720223185-11003d516935?w=600&auto=format&fit=crop&q=80",
    "WMT": "https://images.unsplash.com/photo-1578916171728-46686eac8d58?w=600&auto=format&fit=crop&q=80",
    "COST": "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=600&auto=format&fit=crop&q=80",
    "NFLX": "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=600&auto=format&fit=crop&q=80",
    "AMD": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=600&auto=format&fit=crop&q=80",
    "CSCO": "https://images.unsplash.com/photo-1544197150-b99a580bb7a8?w=600&auto=format&fit=crop&q=80",
    "ADBE": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80",
    "QCOM": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&auto=format&fit=crop&q=80",
    "INTC": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=600&auto=format&fit=crop&q=80",
    "AMAT": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&auto=format&fit=crop&q=80",
    "INTU": "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=600&auto=format&fit=crop&q=80",
    "TXN": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&auto=format&fit=crop&q=80",
}
DEFAULT_STOCK_IMAGE = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=600&auto=format&fit=crop&q=80"


def make_svg_thumbnail(symbol):
    safe_symbol = "".join(ch for ch in (symbol or "MARKET") if ch.isalnum() or ch in " .-_-")[:12] or "MARKET"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="600" height="360" viewBox="0 0 600 360">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#0b6b52"/><stop offset="100%" stop-color="#082f26"/></linearGradient></defs>
<rect width="600" height="360" fill="url(#g)"/><path d="M0 285 C90 245 125 305 205 260 S350 220 430 250 S525 200 600 220" fill="none" stroke="#ffffff" stroke-opacity=".28" stroke-width="7"/>
<text x="300" y="170" text-anchor="middle" fill="white" font-family="Arial,sans-serif" font-size="64" font-weight="700">{safe_symbol}</text>
<text x="300" y="215" text-anchor="middle" fill="white" fill-opacity=".75" font-family="Arial,sans-serif" font-size="20" letter-spacing="4">FINANCIAL NEWS</text>
</svg>'''
    return Response(svg, status=200, content_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/latest-prices")
def latest_prices():
    try:
        response = (
            supabase.table("stock_latest")
            .select("symbol,price,change,timestamp")
            .order("symbol")
            .execute()
        )
        return jsonify({"data": response.data or []})
    except Exception:
        app.logger.exception("Unable to retrieve latest prices from Supabase")
        return jsonify({"error": "Unable to retrieve latest prices"}), 500


# Historical chart data is deliberately cached in memory. Twelve Data's free
# plan has a small per-minute quota, and a chart request should not compete
# with the live quote collector for every page refresh.
CHART_CACHE = {}
CHART_CACHE_SECONDS = 60


def normalize_chart_values(values):
    normalized = []
    for item in values or []:
        try:
            normalized.append({
                "datetime": item.get("datetime"),
                "open": float(item.get("open")),
                "high": float(item.get("high")),
                "low": float(item.get("low")),
                "close": float(item.get("close")),
                "volume": float(item.get("volume") or 0),
            })
        except (AttributeError, TypeError, ValueError):
            continue
    normalized.sort(key=lambda item: item["datetime"] or "")
    return normalized


def fetch_yfinance_history(symbol, period):
    presets = {
        "1D": {"period": "5d", "interval": "5m"},
        "1W": {"period": "1mo", "interval": "1h"},
        "1M": {"period": "3mo", "interval": "1d"},
        "1Y": {"period": "2y", "interval": "1wk"},
    }
    config = presets[period]
    history = yf.Ticker(symbol).history(
        period=config["period"],
        interval=config["interval"],
        auto_adjust=False,
        prepost=False,
    )
    if history is None or history.empty:
        return []
    values = []
    for timestamp, row in history.tail(500).iterrows():
        values.append({
            "datetime": timestamp.isoformat(),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row.get("Volume", 0) or 0),
        })
    return normalize_chart_values(values)


@app.get("/api/stock-history")
def stock_history():
    symbol = request.args.get("symbol", "AAPL").strip().upper()
    period = request.args.get("period", "1D").strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", symbol):
        return jsonify({"error": "Invalid stock symbol"}), 400
    presets = {
        "1D": {"interval": "5min", "outputsize": 100},
        "1W": {"interval": "1h", "outputsize": 120},
        "1M": {"interval": "1day", "outputsize": 35},
        "1Y": {"interval": "1week", "outputsize": 60},
    }
    if period not in presets:
        return jsonify({"error": "period must be 1D, 1W, 1M or 1Y"}), 400
    if not TWELVE_DATA_API_KEY:
        app.logger.warning("Twelve Data API key is not configured; using Yahoo Finance for %s", symbol)
    cache_key = f"{symbol}:{period}"
    cached = CHART_CACHE.get(cache_key)
    if cached and (request.args.get("refresh") != "1"):
        age = __import__("time").time() - cached["created"]
        if age < CHART_CACHE_SECONDS:
            return jsonify(cached["payload"])

    payload = None
    if TWELVE_DATA_API_KEY:
        config = presets[period]
        try:
            response = requests.get(
                "https://api.twelvedata.com/time_series",
                params={
                    "symbol": symbol,
                    "interval": config["interval"],
                    "outputsize": config["outputsize"],
                    "apikey": TWELVE_DATA_API_KEY,
                },
                timeout=20,
            )
            if response.status_code == 429:
                app.logger.warning("Twelve Data rate limit reached for %s; falling back to Yahoo Finance", symbol)
            else:
                response.raise_for_status()
                data = response.json()
                if data.get("status") != "error" and not data.get("code"):
                    values = normalize_chart_values(data.get("values"))
                    if values:
                        payload = {
                            "symbol": symbol,
                            "period": period,
                            "interval": config["interval"],
                            "meta": data.get("meta", {}),
                            "values": values,
                            "source": "Twelve Data",
                        }
        except requests.RequestException:
            app.logger.exception("Twelve Data chart request failed for %s", symbol)

    if payload is None:
        try:
            values = fetch_yfinance_history(symbol, period)
            if values:
                payload = {
                    "symbol": symbol,
                    "period": period,
                    "interval": presets[period]["interval"],
                    "meta": {"source": "Yahoo Finance"},
                    "values": values,
                    "source": "Yahoo Finance",
                }
        except Exception:
            app.logger.exception("Yahoo Finance chart fallback failed for %s", symbol)

    if payload is None:
        if cached:
            app.logger.warning("Using stale chart cache for %s", cache_key)
            return jsonify(cached["payload"])
        return jsonify({"error": "Unable to retrieve chart data from market data providers"}), 502

    CHART_CACHE[cache_key] = {"created": __import__("time").time(), "payload": payload}
    return jsonify(payload)


@app.get("/api/news")
def news():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        limit = min(max(int(request.args.get("limit", 100)), 1), 100)
    except ValueError:
        return jsonify({"error": "page and limit must be integers"}), 400

    start = (page - 1) * limit
    end = start + limit - 1
    response = (
        supabase.table("news_articles")
        .select("symbol,title,description,source,url,published_at,source_api,image_url")
        .order("published_at", desc=True)
        .range(start, end)
        .execute()
    )
    rows = response.data or []
    for row in rows:
        symbol = row.get("symbol") or "MARKET"
        fallback_image_url = STOCK_FALLBACK_IMAGES.get(symbol, DEFAULT_STOCK_IMAGE)
        image_url = row.get("image_url") or fallback_image_url
        row["image_url"] = image_url
        row["fallback_image_url"] = fallback_image_url
        row["image_proxy_url"] = url_for("news_image", url=image_url, symbol=symbol, _external=True)
    return jsonify({
        "data": rows,
        "page": page,
        "limit": limit,
        "count": len(rows),
        "has_next": len(rows) == limit,
    })


@app.get("/api/news-image")
def news_image():
    image_url = request.args.get("url", "")
    symbol = request.args.get("symbol", "MARKET")
    if not allowed_image_url(image_url):
        return make_svg_thumbnail(symbol)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }
        response = requests.get(image_url, timeout=10, headers=headers, allow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if not content_type.startswith("image/"):
            return make_svg_thumbnail(symbol)
        return Response(response.content, status=200, content_type=content_type, headers={"Cache-Control": "public, max-age=3600"})
    except requests.RequestException:
        return make_svg_thumbnail(symbol)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
