import sys
import time
from pathlib import Path

import pandas as pd

# ============================================================
# PROJECT PATH
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(DATABASE_DIR))

import supabase_client


# ============================================================
# DIRECTORIES
# ============================================================

RAW_NEWS_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "news"
    / "nasdaq"
)

SENTIMENT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "sentiment"
    / "nasdaq"
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
# SETTINGS
# ============================================================

BATCH_SIZE = 100

MAX_RETRIES = 5

RETRY_DELAY = 3


# ============================================================
# SUPABASE CLIENT
# ============================================================

def get_supabase():
    """
    Return the current Supabase client.
    """

    return supabase_client.supabase


def reconnect_supabase():
    """
    Recreate the Supabase client after a connection interruption.
    """

    print("\nReconnecting to Supabase...")

    try:

        from supabase import create_client

        supabase_client.supabase = create_client(
            supabase_client.SUPABASE_URL,
            supabase_client.SUPABASE_SECRET_KEY,
        )

        print("Supabase client recreated.")

    except Exception as error:

        print(
            f"Failed to recreate Supabase client: {error}"
        )

        raise


# ============================================================
# SAFE SUPABASE EXECUTION
# ============================================================

def execute_with_retry(operation_name, operation):

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            return operation()

        except Exception as error:

            last_error = error

            print(
                f"\n[{operation_name}] "
                f"attempt {attempt}/{MAX_RETRIES} failed:"
            )

            print(error)

            if attempt < MAX_RETRIES:

                wait_time = RETRY_DELAY * attempt

                print(
                    f"Waiting {wait_time} seconds..."
                )

                time.sleep(wait_time)

                try:
                    reconnect_supabase()
                except Exception:
                    pass

            else:

                print(
                    f"[{operation_name}] "
                    "all retries exhausted."
                )

    raise last_error


# ============================================================
# VALUE CLEANING
# ============================================================

def clean_value(value):

    if pd.isna(value):
        return None

    return value


def clean_float(value):

    value = clean_value(value)

    if value is None:
        return None

    try:

        return float(value)

    except (ValueError, TypeError):

        return None


def clean_int(value):

    value = clean_value(value)

    if value is None:
        return 0

    try:

        return int(float(value))

    except (ValueError, TypeError):

        return 0


# ============================================================
# GET STOCK IDS
# ============================================================

def get_stock_ids():

    print("\nLoading stock IDs from Supabase...")

    def operation():

        return (
            get_supabase()
            .table("stocks")
            .select("id,symbol")
            .execute()
        )

    response = execute_with_retry(
        "Load stock IDs",
        operation
    )

    stock_map = {
        row["symbol"]: row["id"]
        for row in response.data
    }

    print(
        f"Stocks found in database: "
        f"{len(stock_map)}"
    )

    missing = [
        symbol
        for symbol in STOCK_SYMBOLS
        if symbol not in stock_map
    ]

    if missing:

        raise RuntimeError(
            "Missing stocks in Supabase: "
            + ", ".join(missing)
        )

    return stock_map


# ============================================================
# READ EXISTING NEWS URLS
# ============================================================

def get_existing_article_urls(urls):

    """
    Find existing articles in batches.

    Returns:
        {
            url: article_id
        }
    """

    existing = {}

    urls = [
        url
        for url in urls
        if url
    ]

    if not urls:
        return existing

    for start in range(
        0,
        len(urls),
        BATCH_SIZE
    ):

        batch = urls[
            start:start + BATCH_SIZE
        ]

        def operation():

            return (
                get_supabase()
                .table("news_articles")
                .select("id,url")
                .in_("url", batch)
                .execute()
            )

        response = execute_with_retry(
            "Check existing articles",
            operation
        )

        for row in response.data:

            existing[row["url"]] = row["id"]

    return existing


# ============================================================
# MIGRATE NEWS
# ============================================================

def migrate_news_articles(stock_map):

    print("\n" + "=" * 60)
    print("MIGRATING NEWS ARTICLES")
    print("=" * 60)

    total_csv_rows = 0
    total_inserted = 0
    total_skipped = 0
    total_errors = 0

    for symbol in STOCK_SYMBOLS:

        file_path = (
            RAW_NEWS_DIR
            / f"{symbol}.csv"
        )

        if not file_path.exists():

            print(
                f"\n{symbol}: CSV not found"
            )

            continue

        print("\n" + "-" * 50)
        print(symbol)
        print("-" * 50)

        try:

            df = pd.read_csv(
                file_path
            )

        except Exception as error:

            print(
                f"Could not read {file_path}: "
                f"{error}"
            )

            total_errors += 1

            continue

        total_csv_rows += len(df)

        print(
            f"CSV rows: {len(df)}"
        )

        # ----------------------------------------------------
        # Remove rows without URL
        # ----------------------------------------------------

        df = df.dropna(
            subset=["url"]
        )

        # ----------------------------------------------------
        # Remove duplicate URLs inside this CSV
        # ----------------------------------------------------

        df = df.drop_duplicates(
            subset=["url"],
            keep="first"
        )

        rows = df.to_dict(
            orient="records"
        )

        urls = [
            clean_value(row.get("url"))
            for row in rows
        ]

        # ----------------------------------------------------
        # Find existing articles in batches
        # ----------------------------------------------------

        existing = get_existing_article_urls(
            urls
        )

        print(
            f"Already in database: "
            f"{len(existing)}"
        )

        new_records = []

        skipped = 0

        for row in rows:

            url = clean_value(
                row.get("url")
            )

            if not url:

                skipped += 1

                continue

            if url in existing:

                skipped += 1

                continue

            published_at = clean_value(
                row.get("published_at")
            )

            if published_at:

                try:

                    published_at = str(
                        pd.to_datetime(
                            published_at,
                            utc=True
                        )
                    )

                except Exception:

                    published_at = None

            record = {

                "stock_id":
                    stock_map[symbol],

                "symbol":
                    symbol,

                "title":
                    clean_value(
                        row.get("title")
                    ),

                "description":
                    clean_value(
                        row.get("description")
                    ),

                "text":
                    None,

                "source":
                    clean_value(
                        row.get("source")
                    ),

                "url":
                    url,

                "published_at":
                    published_at,

                "source_api":
                    clean_value(
                        row.get("source_api")
                    ),
            }

            new_records.append(
                record
            )

        # ----------------------------------------------------
        # Insert in batches
        # ----------------------------------------------------

        inserted = 0

        for start in range(
            0,
            len(new_records),
            BATCH_SIZE
        ):

            batch = new_records[
                start:start + BATCH_SIZE
            ]

            def operation(
                batch=batch
            ):

                return (
                    get_supabase()
                    .table("news_articles")
                    .insert(batch)
                    .execute()
                )

            try:

                execute_with_retry(
                    "Insert news batch",
                    operation
                )

                inserted += len(batch)

                print(
                    f"Inserted batch: "
                    f"{len(batch)}"
                )

            except Exception as error:

                print(
                    f"News batch failed for "
                    f"{symbol}: {error}"
                )

                total_errors += 1

        total_inserted += inserted
        total_skipped += skipped

        print(
            f"{symbol}: "
            f"Inserted={inserted}, "
            f"Skipped={skipped}"
        )

    print("\n" + "=" * 60)
    print("NEWS MIGRATION COMPLETE")
    print("=" * 60)

    print(
        f"CSV rows:       {total_csv_rows}"
    )

    print(
        f"Inserted:       {total_inserted}"
    )

    print(
        f"Skipped:        {total_skipped}"
    )

    print(
        f"Batch errors:   {total_errors}"
    )


# ============================================================
# GET EXISTING SENTIMENT NEWS IDS
# ============================================================

def get_existing_sentiment_ids(news_ids):

    existing = set()

    if not news_ids:
        return existing

    for start in range(
        0,
        len(news_ids),
        BATCH_SIZE
    ):

        batch = news_ids[
            start:start + BATCH_SIZE
        ]

        def operation():

            return (
                get_supabase()
                .table("news_sentiment")
                .select("news_id")
                .in_("news_id", batch)
                .execute()
            )

        response = execute_with_retry(
            "Check existing sentiment",
            operation
        )

        for row in response.data:

            existing.add(
                row["news_id"]
            )

    return existing


# ============================================================
# GET ARTICLE IDS BY URL
# ============================================================

def get_article_ids_by_urls(urls):

    result = {}

    urls = [
        url
        for url in urls
        if url
    ]

    for start in range(
        0,
        len(urls),
        BATCH_SIZE
    ):

        batch = urls[
            start:start + BATCH_SIZE
        ]

        def operation():

            return (
                get_supabase()
                .table("news_articles")
                .select("id,url")
                .in_("url", batch)
                .execute()
            )

        response = execute_with_retry(
            "Find article IDs",
            operation
        )

        for row in response.data:

            result[row["url"]] = row["id"]

    return result


# ============================================================
# MIGRATE FINBERT SENTIMENT
# ============================================================

def migrate_sentiment(stock_map):

    print("\n" + "=" * 60)
    print("MIGRATING FINBERT SENTIMENT")
    print("=" * 60)

    total_csv_rows = 0
    total_inserted = 0
    total_skipped = 0
    total_missing = 0
    total_errors = 0

    for symbol in STOCK_SYMBOLS:

        file_path = (
            SENTIMENT_DIR
            / f"{symbol}_sentiment.csv"
        )

        if not file_path.exists():

            print(
                f"\n{symbol}: sentiment file not found"
            )

            continue

        print("\n" + "-" * 50)
        print(symbol)
        print("-" * 50)

        try:

            df = pd.read_csv(
                file_path
            )

        except Exception as error:

            print(
                f"Could not read sentiment "
                f"file: {error}"
            )

            total_errors += 1

            continue

        total_csv_rows += len(df)

        print(
            f"Sentiment rows: "
            f"{len(df)}"
        )

        df = df.dropna(
            subset=["url"]
        )

        df = df.drop_duplicates(
            subset=["url"],
            keep="first"
        )

        rows = df.to_dict(
            orient="records"
        )

        urls = [
            clean_value(
                row.get("url")
            )
            for row in rows
        ]

        # ----------------------------------------------------
        # Find all article IDs in batches
        # ----------------------------------------------------

        article_map = (
            get_article_ids_by_urls(
                urls
            )
        )

        print(
            f"Articles matched: "
            f"{len(article_map)}"
        )

        # ----------------------------------------------------
        # Prepare candidate sentiment rows
        # ----------------------------------------------------

        candidates = []

        missing = 0

        for row in rows:

            url = clean_value(
                row.get("url")
            )

            if not url:

                continue

            news_id = article_map.get(
                url
            )

            if not news_id:

                missing += 1

                continue

            record = {

                "news_id":
                    news_id,

                "sentiment_label":
                    clean_value(
                        row.get(
                            "sentiment_label"
                        )
                    ),

                "positive_score":
                    clean_float(
                        row.get(
                            "positive_score"
                        )
                    ),

                "neutral_score":
                    clean_float(
                        row.get(
                            "neutral_score"
                        )
                    ),

                "negative_score":
                    clean_float(
                        row.get(
                            "negative_score"
                        )
                    ),

                "sentiment_score":
                    clean_float(
                        row.get(
                            "sentiment_score"
                        )
                    ),

                "model":
                    "ProsusAI/finbert",
            }

            candidates.append(
                record
            )

        total_missing += missing

        # ----------------------------------------------------
        # Find existing sentiment records
        # ----------------------------------------------------

        news_ids = [
            record["news_id"]
            for record in candidates
        ]

        existing_sentiment = (
            get_existing_sentiment_ids(
                news_ids
            )
        )

        # ----------------------------------------------------
        # Remove already migrated records
        # ----------------------------------------------------

        new_records = []

        skipped = 0

        for record in candidates:

            if (
                record["news_id"]
                in existing_sentiment
            ):

                skipped += 1

                continue

            new_records.append(
                record
            )

        # ----------------------------------------------------
        # Insert sentiment in batches
        # ----------------------------------------------------

        inserted = 0

        for start in range(
            0,
            len(new_records),
            BATCH_SIZE
        ):

            batch = new_records[
                start:start + BATCH_SIZE
            ]

            def operation(
                batch=batch
            ):

                return (
                    get_supabase()
                    .table("news_sentiment")
                    .insert(batch)
                    .execute()
                )

            try:

                execute_with_retry(
                    "Insert sentiment batch",
                    operation
                )

                inserted += len(batch)

                print(
                    f"Inserted sentiment batch: "
                    f"{len(batch)}"
                )

            except Exception as error:

                print(
                    f"Sentiment batch failed "
                    f"for {symbol}: {error}"
                )

                total_errors += 1

        total_inserted += inserted
        total_skipped += skipped

        print(
            f"{symbol}: "
            f"Inserted={inserted}, "
            f"Skipped={skipped}, "
            f"Missing articles={missing}"
        )

    print("\n" + "=" * 60)
    print("FINBERT MIGRATION COMPLETE")
    print("=" * 60)

    print(
        f"CSV rows:          {total_csv_rows}"
    )

    print(
        f"Inserted:          {total_inserted}"
    )

    print(
        f"Skipped:           {total_skipped}"
    )

    print(
        f"Missing articles:  {total_missing}"
    )

    print(
        f"Batch errors:      {total_errors}"
    )


# ============================================================
# MIGRATE DAILY SENTIMENT
# ============================================================

def migrate_daily_sentiment(stock_map):

    print("\n" + "=" * 60)
    print("MIGRATING DAILY SENTIMENT")
    print("=" * 60)

    total_csv_rows = 0
    total_inserted = 0
    total_skipped = 0
    total_errors = 0

    for symbol in STOCK_SYMBOLS:

        file_path = (
            SENTIMENT_DIR
            / f"{symbol}_daily_sentiment.csv"
        )

        if not file_path.exists():

            print(
                f"\n{symbol}: daily sentiment "
                f"file not found"
            )

            continue

        print("\n" + "-" * 50)
        print(symbol)
        print("-" * 50)

        try:

            df = pd.read_csv(
                file_path
            )

        except Exception as error:

            print(
                f"Could not read daily "
                f"sentiment file: {error}"
            )

            total_errors += 1

            continue

        total_csv_rows += len(df)

        print(
            f"Daily rows: {len(df)}"
        )

        records = []

        for _, row in df.iterrows():

            sentiment_date = clean_value(
                row.get(
                    "published_date"
                )
            )

            if not sentiment_date:
                continue

            record = {

                "stock_id":
                    stock_map[symbol],

                "symbol":
                    symbol,

                "sentiment_date":
                    str(sentiment_date),

                "article_count":
                    clean_int(
                        row.get(
                            "article_count"
                        )
                    ),

                "positive_articles":
                    clean_int(
                        row.get(
                            "positive_articles"
                        )
                    ),

                "neutral_articles":
                    clean_int(
                        row.get(
                            "neutral_articles"
                        )
                    ),

                "negative_articles":
                    clean_int(
                        row.get(
                            "negative_articles"
                        )
                    ),

                "average_positive":
                    clean_float(
                        row.get(
                            "average_positive"
                        )
                    ),

                "average_neutral":
                    clean_float(
                        row.get(
                            "average_neutral"
                        )
                    ),

                "average_negative":
                    clean_float(
                        row.get(
                            "average_negative"
                        )
                    ),

                "average_sentiment":
                    clean_float(
                        row.get(
                            "average_sentiment"
                        )
                    ),

                "sentiment_balance":
                    clean_float(
                        row.get(
                            "sentiment_balance"
                        )
                    ),
            }

            records.append(
                record
            )

        # ----------------------------------------------------
        # Upsert daily records
        #
        # Unique constraint:
        # (stock_id, sentiment_date)
        # ----------------------------------------------------

        inserted = 0
        skipped = 0

        for start in range(
            0,
            len(records),
            BATCH_SIZE
        ):

            batch = records[
                start:start + BATCH_SIZE
            ]

            def operation(
                batch=batch
            ):

                return (
                    get_supabase()
                    .table("daily_sentiment")
                    .upsert(
                        batch,
                        on_conflict=(
                            "stock_id,"
                            "sentiment_date"
                        )
                    )
                    .execute()
                )

            try:

                execute_with_retry(
                    "Upsert daily sentiment",
                    operation
                )

                inserted += len(batch)

            except Exception as error:

                print(
                    f"Daily sentiment batch "
                    f"failed for {symbol}: "
                    f"{error}"
                )

                total_errors += 1

        total_inserted += inserted

        print(
            f"{symbol}: "
            f"Processed={inserted}"
        )

    print("\n" + "=" * 60)
    print("DAILY SENTIMENT MIGRATION COMPLETE")
    print("=" * 60)

    print(
        f"CSV rows:       {total_csv_rows}"
    )

    print(
        f"Processed:      {total_inserted}"
    )

    print(
        f"Errors:         {total_errors}"
    )


# ============================================================
# DATABASE VERIFICATION
# ============================================================

def get_table_count(table_name):

    def operation():

        return (
            get_supabase()
            .table(table_name)
            .select(
                "id",
                count="exact"
            )
            .limit(1)
            .execute()
        )

    response = execute_with_retry(
        f"Count {table_name}",
        operation
    )

    return response.count


def verify_database():

    print("\n" + "=" * 60)
    print("DATABASE VERIFICATION")
    print("=" * 60)

    tables = [
        "stocks",
        "news_articles",
        "news_sentiment",
        "daily_sentiment",
        "stock_prices",
    ]

    for table in tables:

        try:

            count = get_table_count(
                table
            )

            print(
                f"{table:20} "
                f"{count} rows"
            )

        except Exception as error:

            print(
                f"{table:20} "
                f"ERROR: {error}"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")
    print("=" * 60)
    print("RESUMABLE CSV → SUPABASE MIGRATION")
    print("=" * 60)

    print(
        f"\nProject root:"
        f"\n{PROJECT_ROOT}"
    )

    print(
        f"\nRaw news:"
        f"\n{RAW_NEWS_DIR}"
    )

    print(
        f"\nSentiment:"
        f"\n{SENTIMENT_DIR}"
    )

    print(
        "\nThis migration is resumable."
    )

    print(
        "Existing Supabase records "
        "will be skipped."
    )

    # --------------------------------------------------------
    # Load stocks
    # --------------------------------------------------------

    stock_map = get_stock_ids()

    # --------------------------------------------------------
    # News
    # --------------------------------------------------------

    migrate_news_articles(
        stock_map
    )

    # --------------------------------------------------------
    # Article sentiment
    # --------------------------------------------------------

    migrate_sentiment(
        stock_map
    )

    # --------------------------------------------------------
    # Daily sentiment
    # --------------------------------------------------------

    migrate_daily_sentiment(
        stock_map
    )

    # --------------------------------------------------------
    # Final verification
    # --------------------------------------------------------

    verify_database()

    print("\n")
    print("=" * 60)
    print("MIGRATION FINISHED")
    print("=" * 60)


if __name__ == "__main__":
    main()