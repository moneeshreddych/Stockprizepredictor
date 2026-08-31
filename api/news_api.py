import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlparse, quote

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, Response
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
load_dotenv(ROOT / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")

supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
app = Flask(__name__, static_folder=str(FRONTEND), static_url_path="")


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
    return response


@app.get("/")
def home():
    return send_from_directory(FRONTEND, "index.html")


@app.get("/dashboard.html")
def dashboard():
    return send_from_directory(FRONTEND, "dashboard.html")


@app.get("/news.html")
def news_page():
    return send_from_directory(FRONTEND, "news.html")


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
        image_url = row.get("image_url")
        symbol = row.get("symbol")
        if not image_url:
            image_url = STOCK_FALLBACK_IMAGES.get(symbol, DEFAULT_STOCK_IMAGE)
            row["image_url"] = image_url
        row["image_proxy_url"] = f"/api/news-image?url={quote(image_url, safe=':/?#[]@!$&\'()*+,;=')}"
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
    if not allowed_image_url(image_url):
        return jsonify({"error": "Image URL is not allowed"}), 400
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }
        response = requests.get(
            image_url,
            timeout=10,
            headers=headers,
            allow_redirects=True,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if not content_type.startswith("image/"):
            return jsonify({"error": "URL did not return an image"}), 415
        return Response(
            response.content,
            status=200,
            content_type=content_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except requests.RequestException:
        return jsonify({"error": "Unable to fetch image"}), 502


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)
