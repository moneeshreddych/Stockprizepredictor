import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

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

IMAGE_HOSTS = {
    "s.yimg.com",
    "media.zenfs.com",
    "g.foolcdn.com",
    "cdn.proactiveinvestors.com",
    "247wallst.com",
    "s.tradingview.com",
}


def allowed_image_url(value):
    try:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        host = parsed.hostname.lower().rstrip(".")
        if host not in IMAGE_HOSTS and not any(host.endswith("." + item) for item in IMAGE_HOSTS):
            return False
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
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
        return jsonify({"error": "Image host is not allowed"}), 400
    try:
        response = requests.get(
            image_url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
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
