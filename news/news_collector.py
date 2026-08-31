import os
import sys
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin

import requests
import yfinance as yf
from dotenv import load_dotenv
from supabase import create_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.logging_config import setup_logging
from news.stock_config import ALL_STOCKS, get_nasdaq_stocks

logger = setup_logging("news_collector")

ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

LOOKBACK_HOURS = 2
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
BATCH_SIZE = 100

STOCK_SYMBOLS = list(get_nasdaq_stocks().keys())

STOCK_ALIASES: Dict[str, List[str]] = {
    "NVDA": ["NVDA", "NVIDIA"],
    "AAPL": ["AAPL", "Apple"],
    "MSFT": ["MSFT", "Microsoft"],
    "AMZN": ["AMZN", "Amazon"],
    "GOOGL": ["GOOGL", "GOOG", "Alphabet", "Google"],
    "GOOG": ["GOOG", "GOOGL", "Alphabet", "Google"],
    "META": ["META", "Meta", "Facebook"],
    "AVGO": ["AVGO", "Broadcom"],
    "TSLA": ["TSLA", "Tesla"],
    "WMT": ["WMT", "Walmart"],
    "COST": ["COST", "Costco"],
    "NFLX": ["NFLX", "Netflix"],
    "AMD": ["AMD", "Advanced Micro Devices"],
    "CSCO": ["CSCO", "Cisco"],
    "ADBE": ["ADBE", "Adobe"],
    "QCOM": ["QCOM", "Qualcomm"],
    "INTC": ["INTC", "Intel"],
    "AMAT": ["AMAT", "Applied Materials"],
    "INTU": ["INTU", "Intuit"],
    "TXN": ["TXN", "Texas Instruments"],
}

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY")
MARKETAUX_KEY = os.getenv("MARKETAUX_API_KEY")

api_enabled = {
    "Alpha Vantage": True,
    "Finnhub": True,
    "Marketaux": True,
    "yfinance": True,
}

api_article_counts = {
    "Alpha Vantage": 0,
    "Finnhub": 0,
    "Marketaux": 0,
    "yfinance": 0,
}


class ImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Any]]) -> None:
        if tag.lower() != "meta":
            return
        values = {key.lower(): value for key, value in attrs if value}
        name = (values.get("property") or values.get("name") or "").lower()
        content = values.get("content")
        if not content:
            return
        if name in {
            "og:image",
            "og:image:url",
            "og:image:secure_url",
            "twitter:image",
            "twitter:image:src",
        }:
            self.images.append(content.strip())


session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    }
)


def extract_image_url(article_url: str) -> Any:
    if not article_url:
        return None
    try:
        response = session.get(article_url, timeout=10, allow_redirects=True)
        response.raise_for_status()
        parser = ImageParser()
        parser.feed(response.text[:1_500_000])
        for image in parser.images:
            image_url = urljoin(response.url, image)
            if image_url.startswith(("http://", "https://")):
                return image_url
    except requests.RequestException as exc:
        logger.debug("Failed to scrape image from %s: %s", article_url, exc)
    except Exception as exc:
        logger.debug("Parsing error for image from %s: %s", article_url, exc)
    return None


def get_time_window() -> Tuple[datetime, datetime]:
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=LOOKBACK_HOURS)
    return start_time, end_time


def request_with_retry(method: str, url: str, **kwargs: Any) -> requests.Response:
    last_error: Any = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            return response
        except requests.RequestException as error:
            last_error = error
            logger.warning("Request failed (attempt %d/%d): %s", attempt, MAX_RETRIES, error)
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
    raise last_error


def response_is_limit(response: requests.Response, data: Any) -> bool:
    if response.status_code in (401, 403, 429):
        return True
    text = str(data).lower()
    limit_words = [
        "rate limit",
        "rate_limit",
        "quota",
        "limit reached",
        "api call frequency",
        "thank you for using alpha vantage",
        "premium endpoint",
    ]
    return any(word in text for word in limit_words)


def find_related_stocks(article: Dict[str, Any]) -> List[str]:
    title = article.get("title") or ""
    description = article.get("description") or ""
    text = f"{title} {description}".lower()
    matches = []
    for symbol in STOCK_SYMBOLS:
        aliases = STOCK_ALIASES.get(symbol, [symbol])
        for alias in aliases:
            if alias.lower() in text:
                matches.append(symbol)
                break
    return matches


def fetch_alpha_vantage(symbol: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    api_name = "Alpha Vantage"
    if not api_enabled[api_name]:
        return []
    if not ALPHA_VANTAGE_KEY:
        logger.warning("%s: API KEY MISSING", api_name)
        return []

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": symbol,
        "time_from": start_time.strftime("%Y%m%dT%H%M"),
        "time_to": end_time.strftime("%Y%m%dT%H%M"),
        "limit": 1000,
        "apikey": ALPHA_VANTAGE_KEY,
    }

    try:
        response = request_with_retry("GET", url, params=params)
        data = response.json()
        if response_is_limit(response, data):
            logger.warning("%s: API limit reached. Disabling for this run.", api_name)
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
                    published_at = (
                        datetime.strptime(raw_time, "%Y%m%dT%H%M%S")
                        .replace(tzinfo=timezone.utc)
                        .isoformat()
                    )
                except ValueError:
                    published_at = None

            articles.append({
                "source_api": api_name,
                "symbol": symbol,
                "title": item.get("title"),
                "description": item.get("summary"),
                "source": item.get("source"),
                "url": item.get("url"),
                "published_at": published_at,
                "image_url": item.get("banner_image"),
            })

        api_article_counts[api_name] += len(articles)
        return articles
    except requests.RequestException as error:
        logger.error("%s ERROR fetching %s: %s", api_name, symbol, error)
        return []


def fetch_finnhub(symbol: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    api_name = "Finnhub"
    if not api_enabled[api_name]:
        return []
    if not FINNHUB_KEY:
        logger.warning("%s: API KEY MISSING", api_name)
        return []

    url = "https://finnhub.io/api/v1/company-news"
    params = {
        "symbol": symbol,
        "from": start_time.strftime("%Y-%m-%d"),
        "to": end_time.strftime("%Y-%m-%d"),
        "token": FINNHUB_KEY,
    }

    try:
        response = request_with_retry("GET", url, params=params)
        data = response.json()
        if response_is_limit(response, data):
            logger.warning("%s: API limit reached. Disabling for this run.", api_name)
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
                    published_at = None

            articles.append({
                "source_api": api_name,
                "symbol": symbol,
                "title": item.get("headline"),
                "description": item.get("summary"),
                "source": item.get("source"),
                "url": item.get("url"),
                "published_at": published_at,
                "image_url": item.get("image"),
            })

        api_article_counts[api_name] += len(articles)
        return articles
    except requests.RequestException as error:
        logger.error("%s ERROR fetching %s: %s", api_name, symbol, error)
        return []


def fetch_marketaux(symbol: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    api_name = "Marketaux"
    if not api_enabled[api_name]:
        return []
    if not MARKETAUX_KEY:
        logger.warning("%s: API KEY MISSING", api_name)
        return []

    url = "https://api.marketaux.com/v1/news/all"
    params = {
        "symbols": symbol,
        "published_after": start_time.strftime("%Y-%m-%dT%H:%M"),
        "published_before": end_time.strftime("%Y-%m-%dT%H:%M"),
        "language": "en",
        "filter_entities": "true",
        "limit": 3,
        "api_token": MARKETAUX_KEY,
    }

    try:
        response = request_with_retry("GET", url, params=params)
        data = response.json()
        if response_is_limit(response, data):
            logger.warning("%s: API limit reached. Disabling for this run.", api_name)
            api_enabled[api_name] = False
            return []
        feed = data.get("data", [])
        if not isinstance(feed, list):
            return []

        articles = []
        for item in feed:
            articles.append({
                "source_api": api_name,
                "symbol": symbol,
                "title": item.get("title"),
                "description": item.get("description"),
                "source": item.get("source"),
                "url": item.get("url"),
                "published_at": item.get("published_at"),
                "image_url": item.get("image_url"),
            })

        api_article_counts[api_name] += len(articles)
        return articles
    except requests.RequestException as error:
        logger.error("%s ERROR fetching %s: %s", api_name, symbol, error)
        return []


def fetch_yfinance(symbol: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    api_name = "yfinance"
    if not api_enabled[api_name]:
        return []
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
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
                    published_at = (
                        datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                        .astimezone(timezone.utc)
                        .isoformat()
                    )
                except ValueError:
                    published_at = None

            if published_at:
                try:
                    article_time = datetime.fromisoformat(published_at)
                    if article_time < start_time or article_time > end_time:
                        continue
                except ValueError:
                    pass

            provider = content.get("provider", {})
            canonical_url = content.get("canonicalUrl", {})
            click_url = content.get("clickThroughUrl", {})

            if not isinstance(provider, dict):
                provider = {}
            if not isinstance(canonical_url, dict):
                canonical_url = {}
            if not isinstance(click_url, dict):
                click_url = {}

            article_url = canonical_url.get("url") or click_url.get("url")
            if not article_url:
                continue

            thumbnail = content.get("thumbnail")
            image_url = None
            if isinstance(thumbnail, dict):
                image_url = thumbnail.get("originalUrl")

            articles.append({
                "source_api": api_name,
                "symbol": symbol,
                "title": content.get("title"),
                "description": content.get("summary") or content.get("description"),
                "source": provider.get("displayName"),
                "url": article_url,
                "published_at": published_at,
                "image_url": image_url,
            })

        api_article_counts[api_name] += len(articles)
        return articles
    except Exception as error:
        logger.error("%s ERROR fetching %s: %s", api_name, symbol, error)
        return []


def load_stock_map() -> Dict[str, int]:
    logger.info("Loading stocks from Supabase...")
    response = supabase.table("stocks").select("id,symbol").execute()
    stock_map = {row["symbol"]: row["id"] for row in response.data or []}

    missing = [symbol for symbol in STOCK_SYMBOLS if symbol not in stock_map]
    if missing:
        raise RuntimeError("These stocks are missing from Supabase: " + ", ".join(missing))

    logger.info("Stocks loaded: %d", len(stock_map))
    return stock_map


def get_existing_urls(urls: List[str]) -> set:
    urls = list({url for url in urls if url})
    existing = set()

    for start in range(0, len(urls), BATCH_SIZE):
        batch = urls[start:start + BATCH_SIZE]
        if not batch:
            continue
        response = supabase.table("news_articles").select("url").in_("url", batch).execute()
        for row in response.data or []:
            url = row.get("url")
            if url:
                existing.add(url)
    return existing


def remove_duplicates(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    valid_articles = [a for a in articles if a.get("url") and a.get("title")]
    unique_articles = {a["url"]: a for a in valid_articles}
    unique_list = list(unique_articles.values())

    logger.info("Unique articles from current fetch: %d", len(unique_list))
    existing_urls = get_existing_urls([a["url"] for a in unique_list])
    logger.info("Already in Supabase: %d", len(existing_urls))

    new_articles = [a for a in unique_list if a["url"] not in existing_urls]
    logger.info("New article URLs: %d", len(new_articles))
    return new_articles


def assign_stocks_to_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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

    logger.info("Articles without stock match: %d | Stock-associated: %d", unmatched, len(assigned))
    return assigned


def store_news(articles: List[Dict[str, Any]], stock_map: Dict[str, int]) -> int:
    if not articles:
        return 0

    records = []
    for article in articles:
        symbol = article.get("symbol")
        stock_id = stock_map.get(symbol)
        if stock_id is None:
            continue

        image_url = article.get("image_url") or extract_image_url(article.get("url"))

        records.append({
            "stock_id": stock_id,
            "symbol": symbol,
            "title": article.get("title"),
            "description": article.get("description"),
            "text": None,
            "source": article.get("source"),
            "url": article.get("url"),
            "published_at": article.get("published_at"),
            "source_api": article.get("source_api"),
            "image_url": image_url,
        })

    inserted = 0
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]
        try:
            response = (
                supabase.table("news_articles")
                .upsert(batch, on_conflict="url", ignore_duplicates=True)
                .execute()
            )
            inserted_count = len(response.data or [])
            inserted += inserted_count
            logger.info("Supabase batch inserted %d rows", inserted_count)
        except Exception as error:
            logger.error("Supabase insert error: %s", error)

    return inserted


def fetch_all_news(start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    all_articles = []
    for api_name, fetch_fn in [
        ("Alpha Vantage", fetch_alpha_vantage),
        ("Finnhub", fetch_finnhub),
        ("Marketaux", fetch_marketaux),
        ("yfinance", fetch_yfinance),
    ]:
        logger.info("Fetching %s...", api_name)
        if api_enabled[api_name]:
            for symbol in STOCK_SYMBOLS:
                try:
                    articles = fetch_fn(symbol, start_time, end_time)
                    all_articles.extend(articles)
                except Exception as error:
                    logger.error("%s %symbol ERROR: %s", api_name, symbol, error)
        else:
            logger.info("%s: SKIPPED (Limit Reached)", api_name)
    logger.info("Total raw articles fetched: %d", len(all_articles))
    return all_articles


def main() -> None:
    logger.info("=" * 60)
    logger.info("FINANCIAL NEWS COLLECTOR")
    logger.info("=" * 60)

    start_time, end_time = get_time_window()
    logger.info("Window: %s -> %s", start_time.isoformat(), end_time.isoformat())

    stock_map = load_stock_map()
    all_articles = fetch_all_news(start_time, end_time)
    new_articles = remove_duplicates(all_articles)
    assigned_articles = assign_stocks_to_articles(new_articles)
    total_new = store_news(assigned_articles, stock_map)

    logger.info("=" * 60)
    logger.info("COLLECTION COMPLETE | New database rows: %d", total_new)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
