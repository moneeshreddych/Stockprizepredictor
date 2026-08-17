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


STOCK_ALIASES = {

    "NVDA": [
        "NVDA",
        "NVIDIA",
    ],

    "AAPL": [
        "AAPL",
        "Apple",
    ],

    "MSFT": [
        "MSFT",
        "Microsoft",
    ],

    "AMZN": [
        "AMZN",
        "Amazon",
    ],

    "GOOGL": [
        "GOOGL",
        "GOOG",
        "Alphabet",
        "Google",
    ],

    "GOOG": [
        "GOOG",
        "GOOGL",
        "Alphabet",
        "Google",
    ],

    "META": [
        "META",
        "Meta",
        "Facebook",
    ],

    "AVGO": [
        "AVGO",
        "Broadcom",
    ],

    "TSLA": [
        "TSLA",
        "Tesla",
    ],

    "WMT": [
        "WMT",
        "Walmart",
    ],

    "COST": [
        "COST",
        "Costco",
    ],

    "NFLX": [
        "NFLX",
        "Netflix",
    ],

    "AMD": [
        "AMD",
        "Advanced Micro Devices",
    ],

    "CSCO": [
        "CSCO",
        "Cisco",
    ],

    "ADBE": [
        "ADBE",
        "Adobe",
    ],

    "QCOM": [
        "QCOM",
        "Qualcomm",
    ],

    "INTC": [
        "INTC",
        "Intel",
    ],

    "AMAT": [
        "AMAT",
        "Applied Materials",
    ],

    "INTU": [
        "INTU",
        "Intuit",
    ],

    "TXN": [
        "TXN",
        "Texas Instruments",
    ],
}


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


supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY,
)


ALPHA_VANTAGE_KEY = os.getenv(
    "ALPHA_VANTAGE_API_KEY"
)

FINNHUB_KEY = os.getenv(
    "FINNHUB_API_KEY"
)

MARKETAUX_KEY = os.getenv(
    "MARKETAUX_API_KEY"
)


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

    return (
        start_time,
        end_time,
    )


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

                wait_time = (
                    attempt * 2
                )

                print(
                    f"Retrying in "
                    f"{wait_time} seconds..."
                )

                time.sleep(
                    wait_time
                )

    raise last_error


def response_is_limit(
    response,
    data
):

    if response.status_code in (
        401,
        403,
        429,
    ):

        return True


    text = str(
        data
    ).lower()


    limit_words = [

        "rate limit",

        "rate_limit",

        "quota",

        "limit reached",

        "api call frequency",

        "thank you for using alpha vantage",

        "premium endpoint",

    ]


    for word in limit_words:

        if word in text:

            return True


    return False


def find_related_stocks(
    article
):

    title = (
        article.get(
            "title"
        )
        or ""
    )

    description = (
        article.get(
            "description"
        )
        or ""
    )


    text = (
        f"{title} "
        f"{description}"
    ).lower()


    matches = []


    for symbol in STOCK_SYMBOLS:

        aliases = STOCK_ALIASES.get(
            symbol,
            [symbol]
        )


        for alias in aliases:

            if alias.lower() in text:

                matches.append(
                    symbol
                )

                break


    return matches


def fetch_alpha_vantage(
    symbol,
    start_time,
    end_time
):

    api_name = "Alpha Vantage"


    if not api_enabled[
        api_name
    ]:

        return []


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
        ] += len(
            articles
        )


        return articles


    except Exception as error:

        print(
            f"Alpha Vantage ERROR: "
            f"{error}"
        )

        return []


def fetch_finnhub(
    symbol,
    start_time,
    end_time
):

    api_name = "Finnhub"


    if not api_enabled[
        api_name
    ]:

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
        ] += len(
            articles
        )


        return articles


    except Exception as error:

        print(
            f"Finnhub ERROR: "
            f"{error}"
        )

        return []


def fetch_marketaux(
    symbol,
    start_time,
    end_time
):

    api_name = "Marketaux"


    if not api_enabled[
        api_name
    ]:

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
            start_time.strftime(
                "%Y-%m-%dT%H:%M"
            ),

        "published_before":
            end_time.strftime(
                "%Y-%m-%dT%H:%M"
            ),

        "language":
            "en",

        "filter_entities":
            "true",

        "limit":
            3,

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
        ] += len(
            articles
        )


        return articles


    except Exception as error:

        print(
            f"Marketaux ERROR: "
            f"{error}"
        )

        return []


def fetch_yfinance(
    symbol,
    start_time,
    end_time
):

    api_name = "yfinance"


    if not api_enabled[
        api_name
    ]:

        return []


    try:

        ticker = yf.Ticker(
            symbol
        )


        news = ticker.news


        if not isinstance(
            news,
            list
        ):

            return []


        articles = []


        for item in news:

            content = item.get(
                "content",
                {}
            )


            if not isinstance(
                content,
                dict
            ):

                continue


            published_at = None


            raw_time = content.get(
                "pubDate"
            )


            if raw_time:

                try:

                    published_at = (

                        datetime.fromisoformat(
                            raw_time.replace(
                                "Z",
                                "+00:00"
                            )
                        )

                        .astimezone(
                            timezone.utc
                        )

                        .isoformat()

                    )

                except ValueError:

                    published_at = None


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


            provider = content.get(
                "provider",
                {}
            )


            canonical_url = content.get(
                "canonicalUrl",
                {}
            )


            click_url = content.get(
                "clickThroughUrl",
                {}
            )


            if not isinstance(
                provider,
                dict
            ):

                provider = {}


            if not isinstance(
                canonical_url,
                dict
            ):

                canonical_url = {}


            if not isinstance(
                click_url,
                dict
            ):

                click_url = {}


            article_url = (

                canonical_url.get(
                    "url"
                )

                or

                click_url.get(
                    "url"
                )

            )


            if not article_url:

                continue


            articles.append({

                "source_api":
                    api_name,

                "symbol":
                    symbol,

                "title":
                    content.get(
                        "title"
                    ),

                "description":
                    (
                        content.get(
                            "summary"
                        )

                        or

                        content.get(
                            "description"
                        )
                    ),

                "source":
                    provider.get(
                        "displayName"
                    ),

                "url":
                    article_url,

                "published_at":
                    published_at,

            })


        api_article_counts[
            api_name
        ] += len(
            articles
        )


        return articles


    except Exception as error:

        print(
            f"yfinance ERROR: "
            f"{error}"
        )

        return []


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


def remove_duplicates(
    articles
):

    valid_articles = [

        article

        for article in articles

        if article.get(
            "url"
        )

        and article.get(
            "title"
        )

    ]


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
        f"Unique articles from "
        f"current fetch: "
        f"{len(unique_articles)}"
    )


    existing_urls = (
        get_existing_urls(
            [
                article["url"]
                for article in unique_articles
            ]
        )
    )


    print(
        f"Already in Supabase: "
        f"{len(existing_urls)}"
    )


    new_articles = [

        article

        for article in unique_articles

        if article["url"]
        not in existing_urls

    ]


    print(
        f"New article URLs: "
        f"{len(new_articles)}"
    )


    return new_articles


def assign_stocks_to_articles(
    articles
):

    assigned = []

    unmatched = 0


    for article in articles:

        matches = (
            find_related_stocks(
                article
            )
        )


        if not matches:

            original_symbol = article.get(
                "symbol"
            )


            if original_symbol:

                matches = [
                    original_symbol
                ]


            else:

                unmatched += 1

                continue


        article_copy = dict(
            article
        )


        article_copy[
            "symbol"
        ] = matches[0]


        assigned.append(
            article_copy
        )


    print(
        f"Articles without "
        f"stock match: "
        f"{unmatched}"
    )


    print(
        f"Stock-associated articles: "
        f"{len(assigned)}"
    )


    return assigned


def store_news(
    articles,
    stock_map
):

    if not articles:

        return 0


    records = []


    for article in articles:

        symbol = article.get(
            "symbol"
        )


        stock_id = stock_map.get(
            symbol
        )


        if stock_id is None:

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


def fetch_all_news(
    start_time,
    end_time
):

    all_articles = []


    print(
        "\nFetching Alpha Vantage..."
    )


    if api_enabled[
        "Alpha Vantage"
    ]:

        for symbol in STOCK_SYMBOLS:

            try:

                articles = (
                    fetch_alpha_vantage(
                        symbol,
                        start_time,
                        end_time
                    )
                )


                print(

                    f"Alpha Vantage | "
                    f"{symbol}: "
                    f"{len(articles)}"

                )


                all_articles.extend(
                    articles
                )


            except Exception as error:

                print(

                    f"Alpha Vantage "
                    f"{symbol} ERROR: "
                    f"{error}"

                )


    else:

        print(
            "Alpha Vantage: SKIPPED"
        )


    print(
        "\nFetching Finnhub..."
    )


    if api_enabled[
        "Finnhub"
    ]:

        for symbol in STOCK_SYMBOLS:

            try:

                articles = (
                    fetch_finnhub(
                        symbol,
                        start_time,
                        end_time
                    )
                )


                print(

                    f"Finnhub | "
                    f"{symbol}: "
                    f"{len(articles)}"

                )


                all_articles.extend(
                    articles
                )


            except Exception as error:

                print(

                    f"Finnhub "
                    f"{symbol} ERROR: "
                    f"{error}"

                )


    else:

        print(
            "Finnhub: SKIPPED"
        )


    print(
        "\nFetching Marketaux..."
    )


    if api_enabled[
        "Marketaux"
    ]:

        for symbol in STOCK_SYMBOLS:

            try:

                articles = (
                    fetch_marketaux(
                        symbol,
                        start_time,
                        end_time
                    )
                )


                print(

                    f"Marketaux | "
                    f"{symbol}: "
                    f"{len(articles)}"

                )


                all_articles.extend(
                    articles
                )


            except Exception as error:

                print(

                    f"Marketaux "
                    f"{symbol} ERROR: "
                    f"{error}"

                )


    else:

        print(
            "Marketaux: SKIPPED"
        )


    print(
        "\nFetching yfinance..."
    )


    if api_enabled[
        "yfinance"
    ]:

        for symbol in STOCK_SYMBOLS:

            try:

                articles = (
                    fetch_yfinance(
                        symbol,
                        start_time,
                        end_time
                    )
                )


                print(

                    f"yfinance | "
                    f"{symbol}: "
                    f"{len(articles)}"

                )


                all_articles.extend(
                    articles
                )


            except Exception as error:

                print(

                    f"yfinance "
                    f"{symbol} ERROR: "
                    f"{error}"

                )


    else:

        print(
            "yfinance: SKIPPED"
        )


    print(
        "\nTotal raw articles fetched: "
        f"{len(all_articles)}"
    )


    return all_articles


def main():

    print("\n")

    print("=" * 60)

    print(
        "FINANCIAL NEWS COLLECTOR"
    )

    print("=" * 60)


    print(
        "\n.env file:"
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


    start_time, end_time = (
        get_time_window()
    )


    print(
        "\nWindow:"
    )


    print(

        f"{start_time.isoformat()} "
        f"-> "
        f"{end_time.isoformat()}"

    )


    print(

        f"\nStocks configured: "
        f"{len(STOCK_SYMBOLS)}"

    )


    stock_map = (
        load_stock_map()
    )


    print(
        "\n"
        + "=" * 60
    )


    print(
        "FETCHING FINANCIAL NEWS"
    )


    print(
        "=" * 60
    )


    all_articles = (
        fetch_all_news(
            start_time,
            end_time
        )
    )


    print(
        "\n"
        + "=" * 60
    )


    print(
        "DEDUPLICATION"
    )


    print(
        "=" * 60
    )


    new_articles = (
        remove_duplicates(
            all_articles
        )
    )


    print(
        "\n"
        + "=" * 60
    )


    print(
        "STOCK ASSOCIATION"
    )


    print(
        "=" * 60
    )


    assigned_articles = (
        assign_stocks_to_articles(
            new_articles
        )
    )


    print(
        "\n"
        + "=" * 60
    )


    print(
        "SUPABASE STORAGE"
    )


    print(
        "=" * 60
    )


    total_new = store_news(

        assigned_articles,

        stock_map

    )


    print(
        "\n"
        + "=" * 60
    )


    print(
        "COLLECTION COMPLETE"
    )


    print(
        "=" * 60
    )


    print(

        f"Raw articles fetched: "
        f"{len(all_articles)}"

    )


    print(

        f"New unique article URLs: "
        f"{len(new_articles)}"

    )


    print(

        f"Stock-associated articles: "
        f"{len(assigned_articles)}"

    )


    print(

        f"New database rows: "
        f"{total_new}"

    )


    print(
        "\nAPI ARTICLE COUNTS"
    )


    for api_name in (

        "Alpha Vantage",

        "Finnhub",

        "Marketaux",

        "yfinance",

    ):

        print(

            f"{api_name}: "
            f"{api_article_counts[api_name]}"

        )


    print(
        "\nFINAL API STATUS"
    )


    for api_name in (

        "Alpha Vantage",

        "Finnhub",

        "Marketaux",

        "yfinance",

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


if __name__ == "__main__":

    main()
