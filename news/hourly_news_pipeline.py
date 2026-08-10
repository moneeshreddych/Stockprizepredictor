import os
import sys
import time
import subprocess
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

# Fetch a small overlapping window every hour.
# The overlap helps prevent missing articles around the
# boundary between two hourly runs.

LOOKBACK_HOURS = 2

# Maximum number of articles requested from APIs
LIMIT = 100

# HTTP timeout
REQUEST_TIMEOUT = 30

# Number of retries for temporary network/server errors
MAX_RETRIES = 3

# Initial retry delay
RETRY_DELAY = 3

# Delay between stocks
STOCK_DELAY = 2


# ============================================================
# DIRECTORIES
# ============================================================

# Project root:
# C:\stockpricepredictor

PROJECT_ROOT = (
    Path(__file__).resolve().parent.parent
)


# Raw news directory
BASE_DIR = (
    PROJECT_ROOT /
    "data" /
    "raw" /
    "news"
)


# NASDAQ raw news
NASDAQ_DIR = (
    BASE_DIR /
    "nasdaq"
)


# Create directory if necessary
NASDAQ_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# PROCESSING SCRIPT
# ============================================================

PROCESS_SCRIPT = (
    Path(__file__).resolve().parent /
    "process_news.py"
)


# ============================================================
# LOG FILE
# ============================================================

LOG_FILE = (
    BASE_DIR /
    "hourly_collection_log.csv"
)


# ============================================================
# CURRENT HOURLY WINDOW
# ============================================================

END_TIME = datetime.now(
    timezone.utc
)

START_TIME = (
    END_TIME -
    timedelta(
        hours=LOOKBACK_HOURS
    )
)


# ============================================================
# DATE FORMATS
# ============================================================

START_ISO = (
    START_TIME.strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
)


FROM_DATE = (
    START_TIME.strftime(
        "%Y-%m-%d"
    )
)


TO_DATE = (
    END_TIME.strftime(
        "%Y-%m-%d"
    )
)


# ============================================================
# API STATUS
#
# IMPORTANT:
#
# Every new hourly run starts with ALL APIs enabled.
#
# If an API actually hits a limit during the run,
# only that API is disabled for the remainder of the run.
#
# The next hourly run resets everything.
# ============================================================

API_ENABLED = {
    "Alpha Vantage": True,
    "Finnhub": True,
    "Marketaux": True,
}


# ============================================================
# RESET API STATUS
# ============================================================

def reset_api_status():

    global API_ENABLED

    API_ENABLED = {

        "Alpha Vantage": True,

        "Finnhub": True,

        "Marketaux": True
    }


# ============================================================
# DISPLAY API STATUS
# ============================================================

def print_api_status():

    print(
        "\nAPI STATUS"
    )

    print(
        "----------------------------------------"
    )


    for api_name, enabled in API_ENABLED.items():

        status = (
            "ENABLED"
            if enabled
            else "DISABLED"
        )

        print(
            f"{api_name}: {status}"
        )


    print(
        "----------------------------------------"
    )


# ============================================================
# DISABLE API FOR CURRENT RUN
# ============================================================

def disable_api(
    api_name
):

    global API_ENABLED

    API_ENABLED[
        api_name
    ] = False


    print(
        f"    {api_name}: "
        f"DISABLED FOR THIS RUN"
    )


# ============================================================
# DETECT API LIMIT / QUOTA
# ============================================================

def is_limit_response(
    response,
    data=None
):

    # --------------------------------------------------------
    # HTTP status codes
    # --------------------------------------------------------

    if response.status_code in (
        401,
        402,
        403,
        429
    ):

        return True


    # --------------------------------------------------------
    # Response text
    # --------------------------------------------------------

    response_text = (
        response.text
        .lower()
    )


    limit_keywords = [

        "rate limit",

        "rate-limit",

        "rate_limit",

        "api call frequency",

        "standard api rate limit",

        "requests per day",

        "request limit",

        "daily limit",

        "daily quota",

        "quota exceeded",

        "too many requests",

        "payment required",

        "premium plans",

        "premium plan",

        "credits exhausted",

        "usage limit",

        "limit reached"
    ]


    for keyword in limit_keywords:

        if keyword in response_text:

            return True


    # --------------------------------------------------------
    # JSON response
    # --------------------------------------------------------

    if isinstance(
        data,
        dict
    ):

        data_text = (
            str(data)
            .lower()
        )


        for keyword in limit_keywords:

            if keyword in data_text:

                return True


    return False


# ============================================================
# REQUEST WITH RETRY
# ============================================================

def request_with_retry(
    api_name,
    url,
    params
):

    # --------------------------------------------------------
    # If this API already hit a limit during this run,
    # don't call it again.
    # --------------------------------------------------------

    if not API_ENABLED.get(
        api_name,
        True
    ):

        print(
            f"    {api_name}: "
            f"SKIPPED "
            f"(limit reached earlier)"
        )

        return None


    last_error = None


    # ========================================================
    # RETRY LOOP
    # ========================================================

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


            # =================================================
            # CHECK API LIMIT
            # =================================================

            if is_limit_response(
                response
            ):

                print(
                    f"    {api_name}: "
                    f"API LIMIT/QUOTA DETECTED"
                )

                print(
                    f"    HTTP status: "
                    f"{response.status_code}"
                )


                disable_api(
                    api_name
                )


                return None


            # =================================================
            # TEMPORARY SERVER ERRORS
            # =================================================

            if response.status_code in (
                500,
                502,
                503,
                504
            ):

                raise requests.HTTPError(
                    f"HTTP "
                    f"{response.status_code}"
                )


            # =================================================
            # OTHER HTTP ERRORS
            # =================================================

            response.raise_for_status()


            # =================================================
            # PARSE JSON
            # =================================================

            try:

                data = response.json()

            except ValueError:

                data = None


            # =================================================
            # CHECK LIMIT MESSAGE INSIDE JSON
            # =================================================

            if is_limit_response(
                response,
                data
            ):

                print(
                    f"    {api_name}: "
                    f"API LIMIT/QUOTA DETECTED"
                )


                disable_api(
                    api_name
                )


                return None


            return response


        except requests.RequestException as error:

            last_error = error


            print(
                f"    {api_name}: "
                f"request failed "
                f"(attempt "
                f"{attempt}/"
                f"{MAX_RETRIES})"
            )


            print(
                f"    Error: {error}"
            )


            # ------------------------------------------------
            # Retry only if attempts remain
            # ------------------------------------------------

            if attempt < MAX_RETRIES:

                wait_time = (
                    RETRY_DELAY *
                    (
                        2 ** (
                            attempt - 1
                        )
                    )
                )


                print(
                    f"    Retrying in "
                    f"{wait_time} seconds..."
                )


                time.sleep(
                    wait_time
                )


    # ========================================================
    # ALL RETRIES FAILED
    # ========================================================

    print(
        f"    {api_name}: "
        f"request failed after "
        f"{MAX_RETRIES} attempts"
    )


    return None


# ============================================================
# 1. ALPHA VANTAGE
# ============================================================

def fetch_alpha_vantage(
    symbol,
    company_name
):

    if not ALPHA_VANTAGE_API_KEY:

        print(
            "    Alpha Vantage: "
            "API key missing"
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
            START_TIME.strftime(
                "%Y%m%dT%H%M"
            ),

        "limit":
            LIMIT,

        "apikey":
            ALPHA_VANTAGE_API_KEY
    }


    response = request_with_retry(
        "Alpha Vantage",
        url,
        params
    )


    if response is None:

        return []


    data = response.json()


    # --------------------------------------------------------
    # Alpha Vantage messages
    # --------------------------------------------------------

    if "Error Message" in data:

        print(
            "    Alpha Vantage ERROR: "
            f"{data['Error Message']}"
        )

        return []


    if "Note" in data:

        print(
            "    Alpha Vantage NOTE: "
            f"{data['Note']}"
        )

        return []


    if "Information" in data:

        print(
            "    Alpha Vantage INFO: "
            f"{data['Information']}"
        )

        return []


    articles = []


    # ========================================================
    # PARSE ARTICLES
    # ========================================================

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

    if not FINNHUB_API_KEY:

        print(
            "    Finnhub: "
            "API key missing"
        )

        return []


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
        "Finnhub",
        url,
        params
    )


    if response is None:

        return []


    data = response.json()


    # --------------------------------------------------------
    # Finnhub error response
    # --------------------------------------------------------

    if isinstance(
        data,
        dict
    ):

        if "error" in data:

            print(
                "    Finnhub ERROR: "
                f"{data['error']}"
            )

            return []


    articles = []


    # ========================================================
    # PARSE ARTICLES
    # ========================================================

    for item in data:

        published_time = (
            item.get(
                "datetime"
            )
        )


        if published_time:

            try:

                published_time = (
                    datetime.fromtimestamp(
                        published_time,
                        tz=timezone.utc
                    ).isoformat()
                )

            except (
                ValueError,
                TypeError,
                OSError
            ):

                published_time = None


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

    if not MARKETAUX_API_KEY:

        print(
            "    Marketaux: "
            "API key missing"
        )

        return []


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
            START_ISO
    }


    response = request_with_retry(
        "Marketaux",
        url,
        params
    )


    if response is None:

        return []


    data = response.json()


    # --------------------------------------------------------
    # Marketaux error
    # --------------------------------------------------------

    if "error" in data:

        print(
            "    Marketaux ERROR: "
            f"{data['error']}"
        )

        return []


    articles = []


    # ========================================================
    # PARSE ARTICLES
    # ========================================================

    for item in data.get(
        "data",
        []
    ):

        sentiment_score = None


        # ----------------------------------------------------
        # Find sentiment associated with target symbol
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
# CLEAN ARTICLES
# ============================================================

def clean_articles(
    articles
):

    if not articles:

        return pd.DataFrame()


    df = pd.DataFrame(
        articles
    )


    # --------------------------------------------------------
    # Missing titles
    # --------------------------------------------------------

    if "title" in df.columns:

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
    # URL
    # --------------------------------------------------------

    if "url" not in df.columns:

        df["url"] = ""

    else:

        df["url"] = (
            df["url"]
            .fillna("")
            .astype(str)
            .str.strip()
        )


    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------

    if "published_at" in df.columns:

        df["published_at"] = (
            pd.to_datetime(
                df["published_at"],
                errors="coerce",
                utc=True
            )
        )


        df = df.dropna(
            subset=[
                "published_at"
            ]
        )


    return df


# ============================================================
# REMOVE DUPLICATES INSIDE CURRENT FETCH
# ============================================================

def remove_duplicates(
    df
):

    if df.empty:

        return df


    # --------------------------------------------------------
    # URL duplicates
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
    # Title duplicates
    # --------------------------------------------------------

    df["title_normalized"] = (
        df["title"]
        .fillna("")
        .astype(str)
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
# LOAD EXISTING STOCK DATA
# ============================================================

def load_existing_data(
    symbol
):

    file_path = (
        NASDAQ_DIR /
        f"{symbol}.csv"
    )


    if not file_path.exists():

        return pd.DataFrame()


    try:

        return pd.read_csv(
            file_path
        )

    except Exception as error:

        print(
            f"    Could not read "
            f"{file_path}"
        )

        print(
            f"    Error: {error}"
        )

        return pd.DataFrame()


# ============================================================
# REMOVE ARTICLES ALREADY STORED
# ============================================================

def remove_existing_articles(
    new_df,
    existing_df
):

    if new_df.empty:

        return new_df


    if existing_df.empty:

        return new_df


    # --------------------------------------------------------
    # Existing URLs
    # --------------------------------------------------------

    existing_urls = set()


    if "url" in existing_df.columns:

        existing_urls = set(
            existing_df["url"]
            .fillna("")
            .astype(str)
            .str.strip()
        )


        existing_urls.discard(
            ""
        )


    # --------------------------------------------------------
    # Existing titles
    # --------------------------------------------------------

    existing_titles = set()


    if "title" in existing_df.columns:

        existing_titles = set(
            existing_df["title"]
            .fillna("")
            .astype(str)
            .str.lower()
            .str.strip()
        )


        existing_titles.discard(
            ""
        )


    # --------------------------------------------------------
    # Filter new articles
    # --------------------------------------------------------

    keep_rows = []


    for _, row in new_df.iterrows():

        url = str(
            row.get(
                "url",
                ""
            )
        ).strip()


        title = str(
            row.get(
                "title",
                ""
            )
        ).lower().strip()


        is_new = True


        # Existing URL
        if url:

            if url in existing_urls:

                is_new = False


        # Existing title
        if title:

            if title in existing_titles:

                is_new = False


        keep_rows.append(
            is_new
        )


    return new_df[
        keep_rows
    ].copy()


# ============================================================
# SAVE NEW ARTICLES
# ============================================================

def save_new_articles(
    symbol,
    new_df
):

    if new_df.empty:

        return 0


    file_path = (
        NASDAQ_DIR /
        f"{symbol}.csv"
    )


    existing_df = load_existing_data(
        symbol
    )


    # --------------------------------------------------------
    # Remove existing articles
    # --------------------------------------------------------

    new_df = remove_existing_articles(
        new_df,
        existing_df
    )


    if new_df.empty:

        return 0


    # --------------------------------------------------------
    # Combine
    # --------------------------------------------------------

    if existing_df.empty:

        combined_df = new_df

    else:

        combined_df = pd.concat(
            [
                existing_df,
                new_df
            ],
            ignore_index=True
        )


    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    combined_df = clean_articles(
        combined_df.to_dict(
            orient="records"
        )
    )


    # --------------------------------------------------------
    # Final deduplication
    # --------------------------------------------------------

    combined_df = remove_duplicates(
        combined_df
    )


    # --------------------------------------------------------
    # Sort newest first
    # --------------------------------------------------------

    combined_df = combined_df.sort_values(
        "published_at",
        ascending=False
    )


    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    combined_df.to_csv(
        file_path,
        index=False
    )


    return len(new_df)


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
        f"{symbol} | "
        f"{company_name} | "
        f"NASDAQ"
    )


    print(
        "----------------------------------------"
    )


    all_articles = []


    # ========================================================
    # ALPHA VANTAGE
    # ========================================================

    if API_ENABLED[
        "Alpha Vantage"
    ]:

        data = fetch_alpha_vantage(
            symbol,
            company_name
        )


        print(
            f"Alpha Vantage: "
            f"{len(data)} articles"
        )


        all_articles.extend(
            data
        )

    else:

        print(
            "Alpha Vantage: "
            "SKIPPED"
        )


    # ========================================================
    # FINNHUB
    # ========================================================

    if API_ENABLED[
        "Finnhub"
    ]:

        data = fetch_finnhub(
            symbol,
            company_name
        )


        print(
            f"Finnhub: "
            f"{len(data)} articles"
        )


        all_articles.extend(
            data
        )

    else:

        print(
            "Finnhub: "
            "SKIPPED"
        )


    # ========================================================
    # MARKETAUX
    # ========================================================

    if API_ENABLED[
        "Marketaux"
    ]:

        data = fetch_marketaux(
            symbol,
            company_name
        )


        print(
            f"Marketaux: "
            f"{len(data)} articles"
        )


        all_articles.extend(
            data
        )

    else:

        print(
            "Marketaux: "
            "SKIPPED"
        )


    # ========================================================
    # CLEAN
    # ========================================================

    new_df = clean_articles(
        all_articles
    )


    # ========================================================
    # REMOVE DUPLICATES WITHIN CURRENT FETCH
    # ========================================================

    new_df = remove_duplicates(
        new_df
    )


    fetched_count = len(
        new_df
    )


    # ========================================================
    # SAVE ONLY NEW ARTICLES
    # ========================================================

    new_count = save_new_articles(
        symbol,
        new_df
    )


    print(
        f"New articles added: "
        f"{new_count}"
    )


    return (
        fetched_count,
        new_count
    )


# ============================================================
# SAVE COLLECTION LOG
# ============================================================

def save_log(
    results
):

    log_df = pd.DataFrame(
        results
    )


    log_df[
        "run_time"
    ] = datetime.now(
        timezone.utc
    ).isoformat()


    log_df[
        "lookback_start"
    ] = START_TIME.isoformat()


    log_df[
        "lookback_end"
    ] = END_TIME.isoformat()


    # --------------------------------------------------------
    # Append to previous log
    # --------------------------------------------------------

    if LOG_FILE.exists():

        try:

            old_log = pd.read_csv(
                LOG_FILE
            )


            log_df = pd.concat(
                [
                    old_log,
                    log_df
                ],
                ignore_index=True
            )


        except Exception:

            pass


    log_df.to_csv(
        LOG_FILE,
        index=False
    )


# ============================================================
# RUN NEWS PROCESSING
# ============================================================

def run_news_processing():

    print(
        "\n========================================"
    )


    print(
        "STARTING NEWS PROCESSING"
    )


    print(
        "========================================"
    )


    # --------------------------------------------------------
    # Check process_news.py exists
    # --------------------------------------------------------

    if not PROCESS_SCRIPT.exists():

        print(
            "\nERROR:"
        )


        print(
            f"Could not find:"
        )


        print(
            PROCESS_SCRIPT
        )


        return False


    try:

        # ----------------------------------------------------
        # Run process_news.py using the SAME Python executable
        # ----------------------------------------------------

        result = subprocess.run(

            [
                sys.executable,

                str(
                    PROCESS_SCRIPT
                )
            ],

            cwd=str(
                PROJECT_ROOT
            ),

            check=False
        )


        # ----------------------------------------------------
        # Check result
        # ----------------------------------------------------

        if result.returncode == 0:

            print(
                "\nNews processing "
                "completed successfully."
            )


            return True


        print(
            "\nNews processing FAILED."
        )


        print(
            f"Exit code: "
            f"{result.returncode}"
        )


        return False


    except Exception as error:

        print(
            "\nCould not start "
            "news processing."
        )


        print(
            f"Error: {error}"
        )


        return False


# ============================================================
# MAIN HOURLY PIPELINE
# ============================================================

def run_hourly_pipeline():

    # ========================================================
    # RESET ALL API STATUS
    #
    # Every hourly run gets a fresh chance to use every API.
    # ========================================================

    reset_api_status()


    print(
        "\n========================================"
    )


    print(
        "HOURLY NASDAQ NEWS PIPELINE"
    )


    print(
        "========================================"
    )


    print(
        f"Date range: "
        f"{START_TIME.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        f" → "
        f"{END_TIME.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )


    print(
        f"Stocks: "
        f"{len(NASDAQ_STOCKS)}"
    )


    print_api_status()


    results = []


    # ========================================================
    # PROCESS ALL STOCKS
    # ========================================================

    for symbol, info in NASDAQ_STOCKS.items():

        start_time = time.time()


        try:

            fetched, added = process_stock(
                symbol,
                info
            )


            status = "SUCCESS"


        except Exception as error:

            fetched = 0

            added = 0

            status = (
                f"ERROR: {error}"
            )


            print(
                f"    Stock ERROR: "
                f"{error}"
            )


        elapsed = (
            time.time()
            - start_time
        )


        results.append({

            "symbol":
                symbol,

            "company":
                info["name"],

            "fetched":
                fetched,

            "new_articles":
                added,

            "status":
                status,

            "duration_seconds":
                round(
                    elapsed,
                    2
                )
        })


        # ----------------------------------------------------
        # Small delay between stocks
        # ----------------------------------------------------

        time.sleep(
            STOCK_DELAY
        )


    # ========================================================
    # SAVE LOG
    # ========================================================

    save_log(
        results
    )


    # ========================================================
    # COLLECTION SUMMARY
    # ========================================================

    results_df = pd.DataFrame(
        results
    )


    total_fetched = int(
        results_df[
            "fetched"
        ].sum()
    )


    total_added = int(
        results_df[
            "new_articles"
        ].sum()
    )


    successful = int(
        (
            results_df[
                "status"
            ]
            == "SUCCESS"
        ).sum()
    )


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
        f"{len(results_df)}"
    )


    print(
        f"Successful: "
        f"{successful}"
    )


    print(
        f"Articles fetched: "
        f"{total_fetched}"
    )


    print(
        f"New articles added: "
        f"{total_added}"
    )


    print(
        "\nAPI status at end of collection:"
    )


    print_api_status()


    print(
        f"\nCollection log:"
    )


    print(
        LOG_FILE
    )


    # ========================================================
    # AUTOMATIC PROCESSING
    #
    # IMPORTANT:
    #
    # API quota failures are NOT treated as a reason to stop
    # processing. If collection completed, process whatever
    # data is available.
    # ========================================================

    processing_success = (
        run_news_processing()
    )


    # ========================================================
    # FINAL PIPELINE STATUS
    # ========================================================

    print(
        "\n========================================"
    )


    if processing_success:

        print(
            "HOURLY PIPELINE COMPLETE"
        )


        print(
            "Collection + Processing: SUCCESS"
        )


    else:

        print(
            "HOURLY PIPELINE PARTIALLY COMPLETE"
        )


        print(
            "Collection: SUCCESS"
        )


        print(
            "Processing: FAILED"
        )


    print(
        "========================================"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    run_hourly_pipeline()
