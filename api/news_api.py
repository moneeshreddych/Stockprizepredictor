import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory, request
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
    has_next = len(rows) == limit

    return jsonify({
        "data": rows,
        "page": page,
        "limit": limit,
        "count": len(rows),
        "has_next": has_next,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)
