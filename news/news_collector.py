import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yfinance as yf
from dotenv import load_dotenv
from supabase import create_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

LOOKBACK_HOURS = 2
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
BATCH_SIZE = 100

STOCK_SYMBOLS = [
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "AVGO",
    "TSLA", "WMT", "COST", "NFLX", "AMD", "CSCO", "ADBE", "QCOM",
    "INTC", "AMAT", "INTU", "TXN",
]

STOCK_ALIASES = {
    "NVDA": ["NVDA", "NVIDIA"], "AAPL": ["AAPL", "Apple"],
    "MSFT": ["MSFT", "Microsoft"], "AMZN": ["AMZN", "Amazon"],
    "GOOGL": ["GOOGL", "GOOG", "Alphabet", "Google"],
    "GOOG": ["GOOG", "GOOGL", "Alphabet", "Google"],
    "META": ["META", "Meta", "Facebook"], "AVGO": ["AVGO", "Broadcom"],
    "TSLA": ["TSLA", "Tesla"], "WMT": ["WMT", "Walmart"],
    "COST": ["COST", "Costco"], "NFLX": ["NFLX", "Netflix"],
    "AMD": ["AMD", "Advanced Micro Devices"], "CSCO": ["CSCO", "Cisco"],
    "ADBE": ["ADBE", "Adobe"], "QCOM": ["QCOM", "Qualcomm"],
    "INTC": ["INTC", "Intel"], "AMAT": ["AMAT", "Applied Materials"],
    "INTU": ["INTU", "Intuit"], "TXN": ["TXN", "Texas Instruments"],
}

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")
if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is missing from .env")
if not SUPABASE_SECRET_KEY:
    raise RuntimeError("SUPABASE_SECRET_KEY is missing from .env")
supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY")
MARKETAUX_KEY = os.getenv("MARKETAUX_API_KEY")

api_enabled = {name: True for name in ("Alpha Vantage", "Finnhub", "Marketaux", "yfinance")}
api_article_counts = {name: 0 for name in api_enabled}


def get_time_window():
    end_time = datetime.now(timezone.utc)
    return end_time - timedelta(hours=LOOKBACK_HOURS), end_time


def request_with_retry(method, url, **kwargs):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
        except requests.RequestException as error:
            last_error = error
            print(f"Request failed (attempt {attempt}/{MAX_RETRIES}): {error}")
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
    raise last_error


def response_is_limit(response, data):
    if response.status_code in (401, 403, 429):
        return True
    text = str(data).lower()
    return any(word in text for word in (
        "rate limit", "rate_limit", "quota", "limit reached",
        "api call frequency", "thank you for using alpha vantage",
        "premium endpoint",
    ))


def find_related_stocks(article):
    text = f"{article.get('title') or ''} {article.get('description') or ''}".lower()
    matches = []
    for symbol in STOCK_SYMBOLS:
        if any(alias.lower() in text for alias in STOCK_ALIASES.get(symbol, [symbol])):
            matches.append(symbol)
    return matches


def fetch_alpha_vantage(symbol, start_time, end_time):
    api_name = "Alpha Vantage"
    if not api_enabled[api_name] or not ALPHA_VANTAGE_KEY:
        if not ALPHA_VANTAGE_KEY:
            print("Alpha Vantage: API KEY MISSING")
        return []
    try:
        response = request_with_retry("GET", "https://www.alphavantage.co/query", params={
            "function": "NEWS_SENTIMENT", "tickers": symbol,
            "time_from": start_time.strftime("%Y%m%dT%H%M"),
            "time_to": end_time.strftime("%Y%m%dT%H%M"), "limit": 1000,
            "apikey": ALPHA_VANTAGE_KEY,
        })
        data = response.json()
        if response_is_limit(response, data):
            print("Alpha Vantage: API LIMIT/QUOTA DETECTED")
            api_enabled[api_name] = False
            return []
        feed = data.get("feed", [])
        if not isinstance(feed, list):
            return []
        articles = []
        for item in feed:
            published_at = None
            raw_time = item.get("time_published")
            if raw_time:
                try:
                    published_at = datetime.strptime(raw_time, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).isoformat()
                except ValueError:
                    pass
            articles.append({
                "source_api": api_name, "symbol": symbol,
                "title": item.get("title"), "description": item.get("summary"),
                "source": item.get("source"), "url": item.get("url"),
                "published_at": published_at,
                "image_url": item.get("banner_image"),
            })
        api_article_counts[api_name] += len(articles)
        return articles
    except Exception as error:
        print(f"Alpha Vantage ERROR: {error}")
        return []


def fetch_finnhub(symbol, start_time, end_time):
    api_name = "Finnhub"
    if not api_enabled[api_name] or not FINNHUB_KEY:
        if not FINNHUB_KEY:
            print("Finnhub: API KEY MISSING")
        return []
    try:
        response = request_with_retry("GET", "https://finnhub.io/api/v1/company-news", params={
            "symbol": symbol, "from": start_time.strftime("%Y-%m-%d"),
            "to": end_time.strftime("%Y-%m-%d"), "token": FINNHUB_KEY,
        })
        data = response.json()
        if response_is_limit(response, data):
            print("Finnhub: API LIMIT/QUOTA DETECTED")
            api_enabled[api_name] = False
            return []
        if not isinstance(data, list):
            return []
        articles = []
        for item in data:
            published_at = None
            timestamp = item.get("datetime")
            if timestamp:
                try:
                    published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
                except (ValueError, OSError, OverflowError):
                    pass
            articles.append({
                "source_api": api_name, "symbol": symbol,
                "title": item.get("headline"), "description": item.get("summary"),
                "source": item.get("source"), "url": item.get("url"),
                "published_at": published_at,
                "image_url": item.get("image"),
            })
        api_article_counts[api_name] += len(articles)
        return articles
    except Exception as error:
        print(f"Finnhub ERROR: {error}")
        return []


def fetch_marketaux(symbol, start_time, end_time):
    api_name = "Marketaux"
    if not api_enabled[api_name] or not MARKETAUX_KEY:
        if not MARKETAUX_KEY:
            print("Marketaux: API KEY MISSING")
        return []
    try:
        response = request_with_retry("GET", "https://api.marketaux.com/v1/news/all", params={
            "symbols": symbol,
            "published_after": start_time.strftime("%Y-%m-%dT%H:%M"),
            "published_before": end_time.strftime("%Y-%m-%dT%H:%M"),
            "language": "en", "filter_entities": "true", "limit": 3,
            "api_token": MARKETAUX_KEY,
        })
        data = response.json()
        if response_is_limit(response, data):
            print("Marketaux: API LIMIT/QUOTA DETECTED")
            api_enabled[api_name] = False
            return []
        feed = data.get("data", [])
        if not isinstance(feed, list):
            return []
        articles = [{
            "source_api": api_name, "symbol": symbol,
            "title": item.get("title"), "description": item.get("description"),
            "source": item.get("source"), "url": item.get("url"),
            "published_at": item.get("published_at"),
            "image_url": item.get("image_url"),
        } for item in feed]
        api_article_counts[api_name] += len(articles)
        return articles
    except Exception as error:
        print(f"Marketaux ERROR: {error}")
        return []


def get_yfinance_image(content):
    thumbnail = content.get("thumbnail")
    if isinstance(thumbnail, dict):
        resolutions = thumbnail.get("resolutions") or []
        if isinstance(resolutions, list) and resolutions:
            valid = [item for item in resolutions if isinstance(item, dict) and item.get("url")]
            if valid:
                return valid[-1].get("url")
        if thumbnail.get("url"):
            return thumbnail.get("url")
    return None


def fetch_yfinance(symbol, start_time, end_time):
    api_name = "yfinance"
    if not api_enabled[api_name]:
        return []
    try:
        news = yf.Ticker(symbol).news
        if not isinstance(news, list):
            return []
        articles = []
        for item in news:
            content = item.get("content", {})
            if not isinstance(content, dict):
                continue
            published_at = None
            raw_time = content.get("pubDate")
            if raw_time:
                try:
                    published_at = datetime.fromisoformat(raw_time.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
                except ValueError:
                    pass
            if published_at:
                try:
                    article_time = datetime.fromisoformat(published_at)
                    if article_time < start_time or article_time > end_time:
                        continue
                except ValueError:
                    pass
            provider = content.get("provider") or {}
            canonical_url = content.get("canonicalUrl") or {}
            click_url = content.get("clickThroughUrl") or {}
            if not isinstance(provider, dict):
                provider = {}
            if not isinstance(canonical_url, dict):
                canonical_url = {}
            if not isinstance(click_url, dict):
                click_url = {}
            article_url = canonical_url.get("url") or click_url.get("url")
            if not article_url:
                continue
            articles.append({
                "source_api": api_name, "symbol": symbol,
                "title": content.get("title"),
                "description": content.get("summary") or content.get("description"),
                "source": provider.get("displayName"), "url": article_url,
                "published_at": published_at, "image_url": get_yfinance_image(content),
            })
        api_article_counts[api_name] += len(articles)
        return articles
    except Exception as error:
        print(f"yfinance ERROR: {error}")
        return []


def load_stock_map():
    response = supabase.table("stocks").select("id,symbol").execute()
    stock_map = {row["symbol"]: row["id"] for row in response.data}
    missing = [symbol for symbol in STOCK_SYMBOLS if symbol not in stock_map]
    if missing:
        raise RuntimeError("These stocks are missing from Supabase: " + ", ".join(missing))
    print(f"Stocks loaded: {len(stock_map)}")
    return stock_map


def get_existing_urls(urls):
    urls = list({url for url in urls if url})
    existing = set()
    for start in range(0, len(urls), BATCH_SIZE):
        batch = urls[start:start + BATCH_SIZE]
        if not batch:
            continue
        response = supabase.table("news_articles").select("url").in_("url", batch).execute()
        existing.update(row["url"] for row in response.data if row.get("url"))
    return existing


def remove_duplicates(articles):
    valid = [a for a in articles if a.get("url") and a.get("title")]
    unique = {}
    for article in valid:
        unique.setdefault(article["url"], article)
    unique_articles = list(unique.values())
    print(f"Unique articles from current fetch: {len(unique_articles)}")
    existing_urls = get_existing_urls([a["url"] for a in unique_articles])
    print(f"Already in Supabase: {len(existing_urls)}")
    new_articles = [a for a in unique_articles if a["url"] not in existing_urls]
    print(f"New article URLs: {len(new_articles)}")
    return new_articles


def assign_stocks_to_articles(articles):
    assigned = []
    unmatched = 0
    for article in articles:
        matches = find_related_stocks(article)
        if not matches:
            original_symbol = article.get("symbol")
            if original_symbol:
                matches = [original_symbol]
            else:
                unmatched += 1
                continue
        article_copy = dict(article)
        article_copy["symbol"] = matches[0]
        assigned.append(article_copy)
    print(f"Articles without stock match: {unmatched}")
    print(f"Stock-associated articles: {len(assigned)}")
    return assigned


def store_news(articles, stock_map):
    if not articles:
        return 0
    records = []
    for article in articles:
        symbol = article.get("symbol")
        stock_id = stock_map.get(symbol)
        if stock_id is None:
            continue
        records.append({
            "stock_id": stock_id, "symbol": symbol,
            "title": article.get("title"), "description": article.get("description"),
            "text": None, "source": article.get("source"), "url": article.get("url"),
            "published_at": article.get("published_at"),
            "source_api": article.get("source_api"),
            "image_url": article.get("image_url"),
        })
    inserted = 0
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]
        try:
            response = supabase.table("news_articles").upsert(batch, on_conflict="url", ignore_duplicates=True).execute()
            inserted_count = len(response.data)
            inserted += inserted_count
            print(f"Supabase batch: {inserted_count} new rows")
        except Exception as error:
            print("Supabase insert error:")
            print(error)
    return inserted


def fetch_all_news(start_time, end_time):
    all_articles = []
    fetchers = [
        ("Alpha Vantage", fetch_alpha_vantage),
        ("Finnhub", fetch_finnhub),
        ("Marketaux", fetch_marketaux),
        ("yfinance", fetch_yfinance),
    ]
    for api_name, fetcher in fetchers:
        print(f"\nFetching {api_name}...")
        if not api_enabled[api_name]:
            print(f"{api_name}: SKIPPED")
            continue
        for symbol in STOCK_SYMBOLS:
            try:
                articles = fetcher(symbol, start_time, end_time)
                print(f"{api_name} | {symbol}: {len(articles)}")
                all_articles.extend(articles)
            except Exception as error:
                print(f"{api_name} {symbol} ERROR: {error}")
    print(f"\nTotal raw articles fetched: {len(all_articles)}")
    return all_articles


def main():
    print("\n" + "=" * 60)
    print("FINANCIAL NEWS COLLECTOR")
    print("=" * 60)
    print(f".env file: {ENV_FILE}")
    print("\nEnvironment loaded:")
    for name, value in (
        ("Supabase URL", SUPABASE_URL),
        ("Supabase secret", SUPABASE_SECRET_KEY),
        ("Alpha Vantage", ALPHA_VANTAGE_KEY),
        ("Finnhub", FINNHUB_KEY),
        ("Marketaux", MARKETAUX_KEY),
    ):
        print(f"{name}: {'READY' if value else 'MISSING'}")
    start_time, end_time = get_time_window()
    print(f"\nWindow: {start_time.isoformat()} -> {end_time.isoformat()}")
    print(f"\nStocks configured: {len(STOCK_SYMBOLS)}")
    stock_map = load_stock_map()
    print("\n" + "=" * 60)
    print("FETCHING FINANCIAL NEWS")
    print("=" * 60)
    all_articles = fetch_all_news(start_time, end_time)
    print("\n" + "=" * 60)
    print("DEDUPLICATION")
    print("=" * 60)
    new_articles = remove_duplicates(all_articles)
    print("\n" + "=" * 60)
    print("STOCK ASSOCIATION")
    print("=" * 60)
    assigned_articles = assign_stocks_to_articles(new_articles)
    print("\n" + "=" * 60)
    print("SUPABASE STORAGE")
    print("=" * 60)
    total_new = store_news(assigned_articles, stock_map)
    print("\n" + "=" * 60)
    print("COLLECTION COMPLETE")
    print("=" * 60)
    print(f"Raw articles fetched: {len(all_articles)}")
    print(f"New unique article URLs: {len(new_articles)}")
    print(f"Stock-associated articles: {len(assigned_articles)}")
    print(f"New database rows: {total_new}")
    print("\nAPI ARTICLE COUNTS")
    for api_name in api_enabled:
        print(f"{api_name}: {api_article_counts[api_name]}")
    print("\nFINAL API STATUS")
    for api_name in api_enabled:
        status = "ACTIVE" if api_enabled[api_name] else "LIMIT HIT - DISABLED THIS RUN"
        print(f"{api_name}: {status}")
    print("\n")


if __name__ == "__main__":
    main()
