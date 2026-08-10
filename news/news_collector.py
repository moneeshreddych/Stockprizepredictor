import os
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests
import pandas as pd
from dotenv import load_dotenv

from stock_config import NASDAQ_STOCKS


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# API KEYS
# ============================================================

ALPHA_VANTAGE_API_KEY = os.getenv(
    "ALPHA_VANTAGE_API_KEY"
)

FINNHUB_API_KEY = os.getenv(
    "FINNHUB_API_KEY"
)

MARKETAUX_API_KEY = os.getenv(
    "MARKETAUX_API_KEY"
)


# ============================================================
# CONFIGURATION
# ============================================================

DAYS_BACK = 7

LIMIT = 100

REQUEST_TIMEOUT = 30

MAX_RETRIES = 3

RETRY_DELAY = 3

STOCK_DELAY = 2


# ============================================================
# DIRECTORIES
# ============================================================

BASE_DIR = Path(
    "data/raw/news"
)

NASDAQ_DIR = (
    BASE_DIR / "nasdaq"
)

NASDAQ_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# DATE RANGE
# ============================================================

END_DATE = datetime.now(
    timezone.utc
)

START_DATE = (
    END_DATE -
    timedelta(days=DAYS_BACK)
)

FROM_DATE = START_DATE.strftime(
    "%Y-%m-%d"
)

TO_DATE = END_DATE.strftime(
    "%Y-%m-%d"
)


# ============================================================
# REQUEST WITH RETRY
# ============================================================

def request_with_retry(
    url,
    params
):

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            response = requests.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT
            )

            response.raise_for_status()

            return response

        except requests.RequestException as error:

            last_error = error

            print(
                f"    Request failed "
                f"(attempt {attempt}/{MAX_RETRIES}): "
                f"{error}"
            )

            if attempt < MAX_RETRIES:

                wait_time = (
                    RETRY_DELAY *
                    (2 ** (attempt - 1))
                )

                print(
                    f"    Retrying in "
                    f"{wait_time} seconds..."
                )

                time.sleep(
                    wait_time
                )

    raise last_error


# ============================================================
# API KEY STATUS
# ============================================================

def check_api_keys():

    print("\nAPI KEY STATUS")
    print("----------------------------------------")

    print(
        "Alpha Vantage:",
        "OK"
        if ALPHA_VANTAGE_API_KEY
        else "MISSING"
    )

    print(
        "Finnhub:",
        "OK"
        if FINNHUB_API_KEY
        else "MISSING"
    )

    print(
        "Marketaux:",
        "OK"
        if MARKETAUX_API_KEY
        else "MISSING"
    )

    print("----------------------------------------")


# ============================================================
# 1. ALPHA VANTAGE
# ============================================================

def fetch_alpha_vantage(
    symbol,
    company_name
):

    url = (
        "https://www.alphavantage.co/query"
    )

    params = {

        "function":
            "NEWS_SENTIMENT",

        "tickers":
            symbol,

        "time_from":
            START_DATE.strftime(
                "%Y%m%dT%H%M"
            ),

        "limit":
            LIMIT,

        "apikey":
            ALPHA_VANTAGE_API_KEY
    }

    response = request_with_retry(
        url,
        params
    )

    data = response.json()


    # --------------------------------------------------------
    # API errors
    # --------------------------------------------------------

    if "Error Message" in data:

        raise Exception(
            data["Error Message"]
        )

    if "Note" in data:

        raise Exception(
            data["Note"]
        )

    if "Information" in data:

        raise Exception(
            data["Information"]
        )


    articles = []


    # --------------------------------------------------------
    # Parse articles
    # --------------------------------------------------------

    for item in data.get(
        "feed",
        []
    ):

        articles.append({

            "source_api":
                "Alpha Vantage",

            "exchange":
                "NASDAQ",

            "symbol":
                symbol,

            "company":
                company_name,

            "published_at":
                item.get(
                    "time_published"
                ),

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

            "sentiment_score":
                item.get(
                    "overall_sentiment_score"
                ),

            "sentiment_label":
                item.get(
                    "overall_sentiment_label"
                )
        })


    return articles


# ============================================================
# 2. FINNHUB
# ============================================================

def fetch_finnhub(
    symbol,
    company_name
):

    url = (
        "https://finnhub.io/api/v1/company-news"
    )

    params = {

        "symbol":
            symbol,

        "from":
            FROM_DATE,

        "to":
            TO_DATE,

        "token":
            FINNHUB_API_KEY
    }

    response = request_with_retry(
        url,
        params
    )

    data = response.json()


    if isinstance(
        data,
        dict
    ):

        if "error" in data:

            raise Exception(
                data["error"]
            )


    articles = []


    for item in data:

        published_time = (
            item.get(
                "datetime"
            )
        )


        if published_time:

            published_time = (
                datetime.fromtimestamp(
                    published_time,
                    tz=timezone.utc
                ).isoformat()
            )


        articles.append({

            "source_api":
                "Finnhub",

            "exchange":
                "NASDAQ",

            "symbol":
                symbol,

            "company":
                company_name,

            "published_at":
                published_time,

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

            "sentiment_score":
                None,

            "sentiment_label":
                None
        })


    return articles


# ============================================================
# 3. MARKETAUX
# ============================================================

def fetch_marketaux(
    symbol,
    company_name
):

    url = (
        "https://api.marketaux.com/v1/news/all"
    )

    params = {

        "api_token":
            MARKETAUX_API_KEY,

        "symbols":
            symbol,

        "language":
            "en",

        "filter_entities":
            "true",

        "limit":
            LIMIT,

        "published_after":
            START_DATE.strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
    }


    response = request_with_retry(
        url,
        params
    )

    data = response.json()


    if "error" in data:

        error = data["error"]

        if isinstance(
            error,
            dict
        ):

            message = error.get(
                "message",
                str(error)
            )

        else:

            message = str(error)

        raise Exception(
            message
        )


    articles = []


    for item in data.get(
        "data",
        []
    ):

        sentiment_score = None


        # ----------------------------------------------------
        # Find sentiment for target symbol
        # ----------------------------------------------------

        for entity in item.get(
            "entities",
            []
        ):

            if entity.get(
                "symbol"
            ) == symbol:

                sentiment_score = (
                    entity.get(
                        "sentiment_score"
                    )
                )

                break


        articles.append({

            "source_api":
                "Marketaux",

            "exchange":
                "NASDAQ",

            "symbol":
                symbol,

            "company":
                company_name,

            "published_at":
                item.get(
                    "published_at"
                ),

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

            "sentiment_score":
                sentiment_score,

            "sentiment_label":
                None
        })


    return articles


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def remove_duplicates(df):

    if df.empty:

        return df


    # --------------------------------------------------------
    # Remove missing titles
    # --------------------------------------------------------

    df = df.dropna(
        subset=[
            "title"
        ]
    )


    df["title"] = (
        df["title"]
        .astype(str)
        .str.strip()
    )


    df = df[
        df["title"] != ""
    ]


    # --------------------------------------------------------
    # Normalize URL
    # --------------------------------------------------------

    df["url"] = (
        df["url"]
        .fillna("")
        .astype(str)
        .str.strip()
    )


    # --------------------------------------------------------
    # Remove duplicate URLs
    # --------------------------------------------------------

    with_url = df[
        df["url"] != ""
    ].drop_duplicates(
        subset=[
            "url"
        ],
        keep="first"
    )


    without_url = df[
        df["url"] == ""
    ]


    df = pd.concat(
        [
            with_url,
            without_url
        ],
        ignore_index=True
    )


    # --------------------------------------------------------
    # Remove duplicate headlines
    # --------------------------------------------------------

    df["title_normalized"] = (
        df["title"]
        .str.lower()
        .str.strip()
    )


    df = df.drop_duplicates(
        subset=[
            "title_normalized"
        ],
        keep="first"
    )


    df = df.drop(
        columns=[
            "title_normalized"
        ]
    )


    return df


# ============================================================
# SAVE STOCK NEWS
# ============================================================

def save_stock_news(
    symbol,
    articles
):

    if not articles:

        print(
            f"    No articles collected for {symbol}"
        )

        return 0


    df = pd.DataFrame(
        articles
    )


    df = remove_duplicates(
        df
    )


    # --------------------------------------------------------
    # Convert timestamp
    # --------------------------------------------------------

    df["published_at"] = (
        pd.to_datetime(
            df["published_at"],
            errors="coerce",
            utc=True
        )
    )


    # --------------------------------------------------------
    # Remove invalid timestamps
    # --------------------------------------------------------

    df = df.dropna(
        subset=[
            "published_at"
        ]
    )


    # --------------------------------------------------------
    # Sort newest first
    # --------------------------------------------------------

    df = df.sort_values(
        "published_at",
        ascending=False
    )


    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    output_file = (
        NASDAQ_DIR /
        f"{symbol}.csv"
    )


    df.to_csv(
        output_file,
        index=False
    )


    print(
        f"    Saved {len(df)} articles → "
        f"{output_file}"
    )


    return len(df)


# ============================================================
# PROCESS ONE STOCK
# ============================================================

def process_stock(
    symbol,
    info
):

    company_name = info[
        "name"
    ]


    print(
        "\n----------------------------------------"
    )

    print(
        f"{symbol} | {company_name} | NASDAQ"
    )

    print(
        "----------------------------------------"
    )


    all_articles = []


    # ========================================================
    # ALPHA VANTAGE
    # ========================================================

    try:

        data = fetch_alpha_vantage(
            symbol,
            company_name
        )

        print(
            f"    Alpha Vantage: "
            f"{len(data)} articles"
        )

        all_articles.extend(
            data
        )

    except Exception as error:

        print(
            f"    Alpha Vantage ERROR: "
            f"{error}"
        )


    # ========================================================
    # FINNHUB
    # ========================================================

    try:

        data = fetch_finnhub(
            symbol,
            company_name
        )

        print(
            f"    Finnhub: "
            f"{len(data)} articles"
        )

        all_articles.extend(
            data
        )

    except Exception as error:

        print(
            f"    Finnhub ERROR: "
            f"{error}"
        )


    # ========================================================
    # MARKETAUX
    # ========================================================

    try:

        data = fetch_marketaux(
            symbol,
            company_name
        )

        print(
            f"    Marketaux: "
            f"{len(data)} articles"
        )

        all_articles.extend(
            data
        )

    except Exception as error:

        print(
            f"    Marketaux ERROR: "
            f"{error}"
        )


    # ========================================================
    # SAVE
    # ========================================================

    total = save_stock_news(
        symbol,
        all_articles
    )


    return total


# ============================================================
# COLLECT ALL NASDAQ NEWS
# ============================================================

def collect_all_news():

    print(
        "\n========================================"
    )

    print(
        "NASDAQ NEWS COLLECTION"
    )

    print(
        "========================================"
    )

    print(
        f"Date range: "
        f"{FROM_DATE} → {TO_DATE}"
    )

    print(
        f"Stocks: "
        f"{len(NASDAQ_STOCKS)}"
    )


    check_api_keys()


    # ========================================================
    # SUMMARY
    # ========================================================

    summary = []


    # ========================================================
    # PROCESS STOCKS
    # ========================================================

    for symbol, info in NASDAQ_STOCKS.items():

        total = process_stock(
            symbol,
            info
        )


        summary.append({

            "exchange":
                "NASDAQ",

            "symbol":
                symbol,

            "company":
                info["name"],

            "articles":
                total
        })


        time.sleep(
            STOCK_DELAY
        )


    # ========================================================
    # SUMMARY DATAFRAME
    # ========================================================

    summary_df = pd.DataFrame(
        summary
    )


    summary_file = (
        BASE_DIR /
        "collection_summary.csv"
    )


    summary_df.to_csv(
        summary_file,
        index=False
    )


    # ========================================================
    # FINAL REPORT
    # ========================================================

    print(
        "\n========================================"
    )

    print(
        "NEWS COLLECTION COMPLETE"
    )

    print(
        "========================================"
    )


    print(
        f"Stocks processed: "
        f"{len(summary_df)}"
    )


    print(
        f"Total unique articles: "
        f"{summary_df['articles'].sum()}"
    )


    print(
        "\nArticles by stock:"
    )


    print(
        summary_df[
            [
                "symbol",
                "company",
                "articles"
            ]
        ].to_string(
            index=False
        )
    )


    print(
        f"\nSummary saved to:"
    )


    print(
        summary_file
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    collect_all_news()