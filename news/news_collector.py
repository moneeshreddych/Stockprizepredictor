import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from supabase import create_client


# ============================================================
# PROJECT ROOT / .ENV
# ============================================================

# File:
# C:\stockpricepredictor\news\news_collector.py
#
# Project root:
# C:\stockpricepredictor

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)


# ============================================================
# CONFIGURATION
# ============================================================

LOOKBACK_HOURS = 2

REQUEST_TIMEOUT = 30

MAX_RETRIES = 3

BATCH_SIZE = 100


# ============================================================
# SUPABASE CONFIGURATION
# ============================================================

SUPABASE_URL = os.getenv(
    "SUPABASE_URL"
)

SUPABASE_SECRET_KEY = os.getenv(
    "SUPABASE_SECRET_KEY"
)


if not SUPABASE_URL:

    raise RuntimeError(
        "SUPABASE_URL is missing from .env"
    )


if not SUPABASE_SECRET_KEY:

    raise RuntimeError(
        "SUPABASE_SECRET_KEY is missing from .env"
    )


# Create Supabase client

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# NEWS API KEYS
# ============================================================

ALPHA_VANTAGE_KEY = os.getenv(
    "ALPHA_VANTAGE_API_KEY"
)

FINNHUB_KEY = os.getenv(
    "FINNHUB_API_KEY"
)

MARKETAUX_KEY = os.getenv(
    "MARKETAUX_API_KEY"
)


# ============================================================
# STOCKS
# ============================================================

STOCK_SYMBOLS = [

    "NVDA",
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "GOOG",
    "META",
    "AVGO",
    "TSLA",
    "WMT",
    "COST",
    "NFLX",
    "AMD",
    "CSCO",
    "ADBE",
    "QCOM",
    "INTC",
    "AMAT",
    "INTU",
    "TXN",

]


# ============================================================
# API RUN STATUS
# ============================================================
#
# IMPORTANT:
#
# Every execution of this Python file starts with all APIs
# enabled.
#
# If an API hits its quota/rate limit:
#
#     API → disabled for THIS RUN ONLY
#
# Other APIs continue.
#
# When the next hourly Cloud Run execution starts:
#
#     all APIs → enabled again
#
# ============================================================

api_enabled = {

    "Alpha Vantage": True,

    "Finnhub": True,

    "Marketaux": True,

}


# ============================================================
# API ARTICLE COUNTERS
# ============================================================

api_article_counts = {

    "Alpha Vantage": 0,

    "Finnhub": 0,

    "Marketaux": 0,

}


# ============================================================
# TIME WINDOW
# ============================================================

def get_time_window():

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time
        - timedelta(
            hours=LOOKBACK_HOURS
        )
    )

    return start_time, end_time


# ============================================================
# HTTP REQUEST WITH RETRY
# ============================================================

def request_with_retry(
    method,
    url,
    **kwargs
):

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            response = requests.request(
                method,
                url,
                timeout=REQUEST_TIMEOUT,
                **kwargs
            )

            return response

        except requests.RequestException as error:

            last_error = error

            print(
                f"Request failed "
                f"(attempt {attempt}/"
                f"{MAX_RETRIES}): "
                f"{error}"
            )

            if attempt < MAX_RETRIES:

                wait_time = attempt * 2

                print(
                    f"Retrying in "
                    f"{wait_time} seconds..."
                )

                time.sleep(
                    wait_time
                )

    raise last_error


# ============================================================
# API LIMIT / QUOTA DETECTION
# ============================================================

def response_is_limit(
    response,
    data=None
):

    # --------------------------------------------------------
    # HTTP status codes
    # --------------------------------------------------------

    if response is not None:

        if response.status_code in (

            401,
            403,
            429,

        ):

            return True


    # --------------------------------------------------------
    # API response text
    # --------------------------------------------------------

    if data is not None:

        try:

            text = str(
                data
            ).lower()

        except Exception:

            text = ""


        limit_phrases = [

            "rate limit",

            "rate_limit",

            "rate-limit",

            "quota",

            "quota reached",

            "limit reached",

            "api limit",

            "too many requests",

            "premium endpoint",

            "call frequency",

            "frequency limit",

            "daily limit",

        ]


        for phrase in limit_phrases:

            if phrase in text:

                return True


    return False


# ============================================================
# ALPHA VANTAGE
# ============================================================

def fetch_alpha_vantage(
    symbol,
    start_time,
    end_time
):

    api_name = "Alpha Vantage"


    # --------------------------------------------------------
    # Already disabled during this run
    # --------------------------------------------------------

    if not api_enabled[api_name]:

        return []


    # --------------------------------------------------------
    # API key check
    # --------------------------------------------------------

    if not ALPHA_VANTAGE_KEY:

        print(
            "Alpha Vantage: "
            "API KEY MISSING"
        )

        return []


    url = (
        "https://www.alphavantage.co/query"
    )


    params = {

        "function":
            "NEWS_SENTIMENT",

        "tickers":
            symbol,

        "time_from":
            start_time.strftime(
                "%Y%m%dT%H%M"
            ),

        "time_to":
            end_time.strftime(
                "%Y%m%dT%H%M"
            ),

        "limit":
            1000,

        "apikey":
            ALPHA_VANTAGE_KEY,

    }


    try:

        response = request_with_retry(
            "GET",
            url,
            params=params
        )


        data = response.json()


        # ----------------------------------------------------
        # LIMIT DETECTION
        # ----------------------------------------------------

        if response_is_limit(
            response,
            data
        ):

            print(
                "Alpha Vantage: "
                "API LIMIT/QUOTA DETECTED"
            )

            print(
                "Alpha Vantage: "
                "DISABLED FOR THIS RUN"
            )

            api_enabled[
                api_name
            ] = False

            return []


        # ----------------------------------------------------
        # Extract feed
        # ----------------------------------------------------

        feed = data.get(
            "feed",
            []
        )


        if not isinstance(
            feed,
            list
        ):

            return []


        articles = []


        for item in feed:

            published_at = None


            raw_time = item.get(
                "time_published"
            )


            if raw_time:

                try:

                    published_at = (

                        datetime.strptime(
                            raw_time,
                            "%Y%m%dT%H%M%S"
                        )

                        .replace(
                            tzinfo=timezone.utc
                        )

                        .isoformat()

                    )

                except ValueError:

                    published_at = None


            articles.append({

                "source_api":
                    api_name,

                "symbol":
                    symbol,

                "title":
                    item.get(
                        "title"
                    ),

                "description":
                    item.get(
                        "summary"
                    ),

                "source":
                    item.get(
                        "source"
                    ),

                "url":
                    item.get(
                        "url"
                    ),

                "published_at":
                    published_at,

            })


        api_article_counts[
            api_name
        ] += len(articles)


        return articles


    except Exception as error:

        print(
            f"Alpha Vantage ERROR: "
            f"{error}"
        )

        return []


# ============================================================
# FINNHUB
# ============================================================

def fetch_finnhub(
    symbol,
    start_time,
    end_time
):

    api_name = "Finnhub"


    if not api_enabled[api_name]:

        return []


    if not FINNHUB_KEY:

        print(
            "Finnhub: "
            "API KEY MISSING"
        )

        return []


    url = (
        "https://finnhub.io/api/v1/company-news"
    )


    params = {

        "symbol":
            symbol,

        "from":
            start_time.strftime(
                "%Y-%m-%d"
            ),

        "to":
            end_time.strftime(
                "%Y-%m-%d"
            ),

        "token":
            FINNHUB_KEY,

    }


    try:

        response = request_with_retry(
            "GET",
            url,
            params=params
        )


        data = response.json()


        # ----------------------------------------------------
        # LIMIT DETECTION
        # ----------------------------------------------------

        if response_is_limit(
            response,
            data
        ):

            print(
                "Finnhub: "
                "API LIMIT/QUOTA DETECTED"
            )

            print(
                "Finnhub: "
                "DISABLED FOR THIS RUN"
            )

            api_enabled[
                api_name
            ] = False

            return []


        if not isinstance(
            data,
            list
        ):

            return []


        articles = []


        for item in data:

            published_at = None


            timestamp = item.get(
                "datetime"
            )


            if timestamp:

                try:

                    published_at = (

                        datetime.fromtimestamp(
                            timestamp,
                            tz=timezone.utc
                        )

                        .isoformat()

                    )

                except (
                    ValueError,
                    OSError,
                    OverflowError
                ):

                    published_at = None


            # ------------------------------------------------
            # Check actual article time
            # ------------------------------------------------

            if published_at:

                try:

                    article_time = (
                        datetime.fromisoformat(
                            published_at
                        )
                    )


                    if (

                        article_time
                        < start_time

                        or

                        article_time
                        > end_time

                    ):

                        continue


                except ValueError:

                    pass


            articles.append({

                "source_api":
                    api_name,

                "symbol":
                    symbol,

                "title":
                    item.get(
                        "headline"
                    ),

                "description":
                    item.get(
                        "summary"
                    ),

                "source":
                    item.get(
                        "source"
                    ),

                "url":
                    item.get(
                        "url"
                    ),

                "published_at":
                    published_at,

            })


        api_article_counts[
            api_name
        ] += len(articles)


        return articles


    except Exception as error:

        print(
            f"Finnhub ERROR: "
            f"{error}"
        )

        return []


# ============================================================
# MARKETAUX
# ============================================================

def fetch_marketaux(
    symbol,
    start_time,
    end_time
):

    api_name = "Marketaux"


    if not api_enabled[api_name]:

        return []


    if not MARKETAUX_KEY:

        print(
            "Marketaux: "
            "API KEY MISSING"
        )

        return []


    url = (
        "https://api.marketaux.com/v1/news/all"
    )


    params = {

        "symbols":
            symbol,

        "published_after":
            start_time.isoformat(),

        "published_before":
            end_time.isoformat(),

        "language":
            "en",

        "filter_entities":
            "true",

        "limit":
            100,

        "api_token":
            MARKETAUX_KEY,

    }


    try:

        response = request_with_retry(
            "GET",
            url,
            params=params
        )


        data = response.json()


        # ----------------------------------------------------
        # LIMIT DETECTION
        # ----------------------------------------------------

        if response_is_limit(
            response,
            data
        ):

            print(
                "Marketaux: "
                "API LIMIT/QUOTA DETECTED"
            )

            print(
                "Marketaux: "
                "DISABLED FOR THIS RUN"
            )

            api_enabled[
                api_name
            ] = False

            return []


        feed = data.get(
            "data",
            []
        )


        if not isinstance(
            feed,
            list
        ):

            return []


        articles = []


        for item in feed:

            articles.append({

                "source_api":
                    api_name,

                "symbol":
                    symbol,

                "title":
                    item.get(
                        "title"
                    ),

                "description":
                    item.get(
                        "description"
                    ),

                "source":
                    item.get(
                        "source"
                    ),

                "url":
                    item.get(
                        "url"
                    ),

                "published_at":
                    item.get(
                        "published_at"
                    ),

            })


        api_article_counts[
            api_name
        ] += len(articles)


        return articles


    except Exception as error:

        print(
            f"Marketaux ERROR: "
            f"{error}"
        )

        return []


# ============================================================
# LOAD STOCKS FROM SUPABASE
# ============================================================

def load_stock_map():

    print(
        "\nLoading stocks from Supabase..."
    )


    response = (

        supabase

        .table(
            "stocks"
        )

        .select(
            "id,symbol"
        )

        .execute()

    )


    stock_map = {

        row["symbol"]:
            row["id"]

        for row in response.data

    }


    missing = [

        symbol

        for symbol in STOCK_SYMBOLS

        if symbol not in stock_map

    ]


    if missing:

        raise RuntimeError(

            "These stocks are missing "
            "from Supabase: "

            + ", ".join(
                missing
            )

        )


    print(
        f"Stocks loaded: "
        f"{len(stock_map)}"
    )


    return stock_map


# ============================================================
# CHECK EXISTING URLS IN SUPABASE
# ============================================================

def get_existing_urls(
    urls
):

    urls = list({

        url

        for url in urls

        if url

    })


    existing = set()


    for start in range(

        0,

        len(urls),

        BATCH_SIZE

    ):

        batch = urls[
            start:
            start + BATCH_SIZE
        ]


        if not batch:

            continue


        response = (

            supabase

            .table(
                "news_articles"
            )

            .select(
                "url"
            )

            .in_(
                "url",
                batch
            )

            .execute()

        )


        for row in response.data:

            url = row.get(
                "url"
            )


            if url:

                existing.add(
                    url
                )


    return existing


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def remove_duplicates(
    articles
):

    # --------------------------------------------------------
    # Remove articles without URL
    # --------------------------------------------------------

    valid_articles = [

        article

        for article in articles

        if article.get(
            "url"
        )

    ]


    # --------------------------------------------------------
    # Remove duplicate URLs from current fetch
    # --------------------------------------------------------

    unique_articles = {}


    for article in valid_articles:

        url = article[
            "url"
        ]


        if url not in unique_articles:

            unique_articles[
                url
            ] = article


    unique_articles = list(
        unique_articles.values()
    )


    print(
        f"Unique in current fetch: "
        f"{len(unique_articles)}"
    )


    # --------------------------------------------------------
    # Check Supabase
    # --------------------------------------------------------

    urls = [

        article["url"]

        for article in unique_articles

    ]


    existing_urls = (
        get_existing_urls(
            urls
        )
    )


    print(
        f"Already in Supabase: "
        f"{len(existing_urls)}"
    )


    # --------------------------------------------------------
    # Only new articles
    # --------------------------------------------------------

    new_articles = [

        article

        for article in unique_articles

        if article["url"]
        not in existing_urls

    ]


    print(
        f"New articles: "
        f"{len(new_articles)}"
    )


    return new_articles


# ============================================================
# STORE RAW NEWS IN SUPABASE
# ============================================================

def store_news(
    articles,
    stock_map
):

    if not articles:

        return 0


    records = []


    for article in articles:

        symbol = article[
            "symbol"
        ]


        stock_id = stock_map.get(
            symbol
        )


        if stock_id is None:

            print(
                f"Skipping {symbol}: "
                "stock not found"
            )

            continue


        records.append({

            "stock_id":
                stock_id,

            "symbol":
                symbol,

            "title":
                article.get(
                    "title"
                ),

            "description":
                article.get(
                    "description"
                ),

            "text":
                None,

            "source":
                article.get(
                    "source"
                ),

            "url":
                article.get(
                    "url"
                ),

            "published_at":
                article.get(
                    "published_at"
                ),

            "source_api":
                article.get(
                    "source_api"
                ),

        })


    inserted = 0


    # --------------------------------------------------------
    # Insert in batches
    # --------------------------------------------------------

    for start in range(

        0,

        len(records),

        BATCH_SIZE

    ):

        batch = records[
            start:
            start + BATCH_SIZE
        ]


        try:

            response = (

                supabase

                .table(
                    "news_articles"
                )

                .upsert(

                    batch,

                    on_conflict="url",

                    ignore_duplicates=True

                )

                .execute()

            )


            inserted_count = len(
                response.data
            )


            inserted += (
                inserted_count
            )


            print(

                f"Supabase batch: "
                f"{inserted_count} "
                f"new rows"

            )


        except Exception as error:

            print(
                "Supabase insert error:"
            )

            print(error)


    return inserted


# ============================================================
# PROCESS ONE STOCK
# ============================================================

def process_stock(

    symbol,

    stock_map,

    start_time,

    end_time

):

    print("\n" + "=" * 60)

    print(
        f"{symbol} | NASDAQ"
    )

    print("=" * 60)


    all_articles = []


    # ========================================================
    # ALPHA VANTAGE
    # ========================================================

    if api_enabled[
        "Alpha Vantage"
    ]:

        articles = (

            fetch_alpha_vantage(

                symbol,

                start_time,

                end_time

            )

        )


        print(

            f"Alpha Vantage: "
            f"{len(articles)} articles"

        )


        all_articles.extend(
            articles
        )


    else:

        print(
            "Alpha Vantage: SKIPPED"
        )


    # ========================================================
    # FINNHUB
    # ========================================================

    if api_enabled[
        "Finnhub"
    ]:

        articles = (

            fetch_finnhub(

                symbol,

                start_time,

                end_time

            )

        )


        print(

            f"Finnhub: "
            f"{len(articles)} articles"

        )


        all_articles.extend(
            articles
        )


    else:

        print(
            "Finnhub: SKIPPED"
        )


    # ========================================================
    # MARKETAUX
    # ========================================================

    if api_enabled[
        "Marketaux"
    ]:

        articles = (

            fetch_marketaux(

                symbol,

                start_time,

                end_time

            )

        )


        print(

            f"Marketaux: "
            f"{len(articles)} articles"

        )


        all_articles.extend(
            articles
        )


    else:

        print(
            "Marketaux: SKIPPED"
        )


    # ========================================================
    # DEDUPLICATION
    # ========================================================

    new_articles = (
        remove_duplicates(
            all_articles
        )
    )


    # ========================================================
    # STORE
    # ========================================================

    inserted = store_news(

        new_articles,

        stock_map

    )


    print(

        f"New articles added: "
        f"{inserted}"

    )


    return inserted


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")

    print("=" * 60)

    print(
        "HOURLY RAW NEWS COLLECTOR"
    )

    print("=" * 60)


    # ========================================================
    # SHOW ENVIRONMENT
    # ========================================================

    print(
        f"\n.env file:"
    )

    print(
        str(ENV_FILE)
    )


    print(
        "\nEnvironment loaded:"
    )


    print(

        "Supabase URL:",
        "READY"
        if SUPABASE_URL
        else "MISSING"

    )


    print(

        "Supabase secret:",
        "READY"
        if SUPABASE_SECRET_KEY
        else "MISSING"

    )


    print(

        "Alpha Vantage:",
        "READY"
        if ALPHA_VANTAGE_KEY
        else "MISSING"

    )


    print(

        "Finnhub:",
        "READY"
        if FINNHUB_KEY
        else "MISSING"

    )


    print(

        "Marketaux:",
        "READY"
        if MARKETAUX_KEY
        else "MISSING"

    )


    # ========================================================
    # TIME WINDOW
    # ========================================================

    start_time, end_time = (
        get_time_window()
    )


    print(
        "\nWindow:"
    )


    print(

        start_time.isoformat()

        + " → "

        + end_time.isoformat()

    )


    print(

        f"\nStocks: "
        f"{len(STOCK_SYMBOLS)}"

    )


    # ========================================================
    # LOAD STOCKS
    # ========================================================

    stock_map = (
        load_stock_map()
    )


    # ========================================================
    # PROCESS STOCKS
    # ========================================================

    total_new = 0


    for symbol in STOCK_SYMBOLS:

        try:

            inserted = process_stock(

                symbol,

                stock_map,

                start_time,

                end_time

            )


            total_new += inserted


        except Exception as error:

            print("\n")

            print(
                f"{symbol} FAILED"
            )


            print(
                error
            )


            print(

                "Continuing with "
                "remaining stocks..."

            )


    # ========================================================
    # FINAL REPORT
    # ========================================================

    print("\n")

    print("=" * 60)

    print(
        "HOURLY COLLECTION COMPLETE"
    )

    print("=" * 60)


    print(

        f"Total new articles: "
        f"{total_new}"

    )


    # ========================================================
    # API TOTALS
    # ========================================================

    print("\nAPI ARTICLE COUNTS")


    for api_name in (

        "Alpha Vantage",

        "Finnhub",

        "Marketaux",

    ):

        print(

            f"{api_name}: "
            f"{api_article_counts[api_name]}"

        )


    # ========================================================
    # FINAL API STATUS
    # ========================================================

    print(
        "\nFINAL API STATUS"
    )


    for api_name in (

        "Alpha Vantage",

        "Finnhub",

        "Marketaux",

    ):

        if api_enabled[
            api_name
        ]:

            status = "ACTIVE"

        else:

            status = (
                "LIMIT HIT - "
                "DISABLED THIS RUN"
            )


        print(

            f"{api_name}: "
            f"{status}"

        )


    print("\n")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()