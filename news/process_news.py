import re
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(
    "data/raw/news/nasdaq"
)

OUTPUT_DIR = Path(
    "data/processed/news/nasdaq"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# REQUIRED COLUMNS
# ============================================================

REQUIRED_COLUMNS = [
    "source_api",
    "exchange",
    "symbol",
    "company",
    "published_at",
    "title",
    "description",
    "source",
    "url"
]


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):
    """
    Clean news text while preserving the actual meaning.
    """

    if pd.isna(text):

        return ""

    text = str(text)

    # Remove HTML tags
    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    # Replace URLs
    text = re.sub(
        r"https?://\S+|www\.\S+",
        " ",
        text
    )

    # Replace multiple whitespace
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    # Remove leading/trailing whitespace
    text = text.strip()

    return text


# ============================================================
# NORMALIZE TITLE
# ============================================================

def clean_title(title):

    return clean_text(
        title
    )


# ============================================================
# NORMALIZE DESCRIPTION
# ============================================================

def clean_description(description):

    return clean_text(
        description
    )


# ============================================================
# CREATE MODEL TEXT
# ============================================================

def create_model_text(row):
    """
    Combine title and description.

    Title is placed first because it generally contains
    the main information about the news event.
    """

    title = str(
        row.get(
            "title",
            ""
        )
    ).strip()

    description = str(
        row.get(
            "description",
            ""
        )
    ).strip()


    if title and description:

        return (
            title
            + ". "
            + description
        )


    if title:

        return title


    return description


# ============================================================
# LOAD NEWS FILE
# ============================================================

def load_news_file(
    file_path
):

    print(
        f"\nReading: {file_path}"
    )


    try:

        df = pd.read_csv(
            file_path
        )

    except Exception as error:

        print(
            f"ERROR reading file: "
            f"{error}"
        )

        return pd.DataFrame()


    if df.empty:

        print(
            "File is empty."
        )

        return pd.DataFrame()


    return df


# ============================================================
# VALIDATE COLUMNS
# ============================================================

def validate_columns(
    df,
    file_path
):

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]


    if missing:

        print(
            f"Missing columns in "
            f"{file_path}: "
            f"{missing}"
        )

        return False


    return True


# ============================================================
# PROCESS NEWS DATA
# ============================================================

def process_dataframe(
    df
):

    if df.empty:

        return df


    # --------------------------------------------------------
    # Make sure expected columns exist
    # --------------------------------------------------------

    for column in REQUIRED_COLUMNS:

        if column not in df.columns:

            df[column] = ""


    # --------------------------------------------------------
    # Clean title
    # --------------------------------------------------------

    df["title"] = (
        df["title"]
        .fillna("")
        .apply(clean_title)
    )


    # --------------------------------------------------------
    # Clean description
    # --------------------------------------------------------

    df["description"] = (
        df["description"]
        .fillna("")
        .apply(clean_description)
    )


    # --------------------------------------------------------
    # Create combined text
    # --------------------------------------------------------

    df["text"] = df.apply(
        create_model_text,
        axis=1
    )


    # --------------------------------------------------------
    # Normalize timestamp
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

    before = len(df)

    df = df.dropna(
        subset=[
            "published_at"
        ]
    )

    removed = (
        before - len(df)
    )


    if removed:

        print(
            f"Removed {removed} "
            f"records with invalid dates."
        )


    # --------------------------------------------------------
    # Create useful date/time features
    # --------------------------------------------------------

    df["published_date"] = (
        df["published_at"]
        .dt.strftime(
            "%Y-%m-%d"
        )
    )


    df["published_hour"] = (
        df["published_at"]
        .dt.hour
    )


    # --------------------------------------------------------
    # Remove records without usable text
    # --------------------------------------------------------

    before = len(df)

    df = df[
        df["text"].str.len() > 10
    ].copy()


    removed = (
        before - len(df)
    )


    if removed:

        print(
            f"Removed {removed} "
            f"records with insufficient text."
        )


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
    # Normalize source
    # --------------------------------------------------------

    df["source"] = (
        df["source"]
        .fillna("")
        .astype(str)
        .str.strip()
    )


    # --------------------------------------------------------
    # Remove duplicate URLs
    # --------------------------------------------------------

    before = len(df)


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


    removed = (
        before - len(df)
    )


    if removed:

        print(
            f"Removed {removed} "
            f"duplicate URLs."
        )


    # --------------------------------------------------------
    # Remove duplicate titles
    # --------------------------------------------------------

    before = len(df)


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


    removed = (
        before - len(df)
    )


    if removed:

        print(
            f"Removed {removed} "
            f"duplicate titles."
        )


    # --------------------------------------------------------
    # Sort newest first
    # --------------------------------------------------------

    df = df.sort_values(
        "published_at",
        ascending=False
    )


    # --------------------------------------------------------
    # Reset index
    # --------------------------------------------------------

    df = df.reset_index(
        drop=True
    )


    return df


# ============================================================
# SELECT OUTPUT COLUMNS
# ============================================================

def select_output_columns(
    df
):

    columns = [

        "source_api",

        "exchange",

        "symbol",

        "company",

        "published_at",

        "published_date",

        "published_hour",

        "title",

        "description",

        "text",

        "source",

        "url",

        "sentiment_score",

        "sentiment_label"
    ]


    # Add sentiment columns if they don't exist yet
    if "sentiment_score" not in df.columns:

        df["sentiment_score"] = None


    if "sentiment_label" not in df.columns:

        df["sentiment_label"] = None


    # Keep only columns that exist
    columns = [
        column
        for column in columns
        if column in df.columns
    ]


    return df[
        columns
    ]


# ============================================================
# PROCESS ONE STOCK
# ============================================================

def process_stock(
    file_path
):

    symbol = (
        file_path.stem
    )


    print(
        "\n========================================"
    )

    print(
        f"Processing {symbol}"
    )

    print(
        "========================================"
    )


    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    df = load_news_file(
        file_path
    )


    if df.empty:

        return 0


    original_count = len(
        df
    )


    print(
        f"Raw articles: "
        f"{original_count}"
    )


    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if not validate_columns(
        df,
        file_path
    ):

        return 0


    # --------------------------------------------------------
    # Process
    # --------------------------------------------------------

    df = process_dataframe(
        df
    )


    # --------------------------------------------------------
    # Select columns
    # --------------------------------------------------------

    df = select_output_columns(
        df
    )


    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    output_file = (
        OUTPUT_DIR /
        f"{symbol}_processed.csv"
    )


    df.to_csv(
        output_file,
        index=False
    )


    print(
        f"Processed articles: "
        f"{len(df)}"
    )


    print(
        f"Saved to: "
        f"{output_file}"
    )


    return len(df)


# ============================================================
# PROCESS ALL STOCKS
# ============================================================

def process_all_news():

    print(
        "\n========================================"
    )

    print(
        "NASDAQ NEWS PROCESSING"
    )

    print(
        "========================================"
    )


    # --------------------------------------------------------
    # Find all raw CSV files
    # --------------------------------------------------------

    files = sorted(
        BASE_DIR.glob(
            "*.csv"
        )
    )


    # Don't accidentally process summary/log files
    files = [
        file
        for file in files
        if file.name
        not in [
            "collection_summary.csv",
            "hourly_collection_log.csv"
        ]
    ]


    if not files:

        print(
            "No news CSV files found."
        )

        return


    print(
        f"Stock files found: "
        f"{len(files)}"
    )


    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary = []


    # --------------------------------------------------------
    # Process each stock
    # --------------------------------------------------------

    for file_path in files:

        processed_count = process_stock(
            file_path
        )


        summary.append({

            "symbol":
                file_path.stem,

            "processed_articles":
                processed_count
        })


    # --------------------------------------------------------
    # Save processing summary
    # --------------------------------------------------------

    summary_df = pd.DataFrame(
        summary
    )


    summary_file = (
        OUTPUT_DIR /
        "processing_summary.csv"
    )


    summary_df.to_csv(
        summary_file,
        index=False
    )


    # --------------------------------------------------------
    # Final report
    # --------------------------------------------------------

    print(
        "\n========================================"
    )

    print(
        "NEWS PROCESSING COMPLETE"
    )

    print(
        "========================================"
    )


    print(
        f"Stocks processed: "
        f"{len(summary_df)}"
    )


    print(
        f"Total processed articles: "
        f"{summary_df['processed_articles'].sum()}"
    )


    print(
        "\nArticles by stock:"
    )


    print(
        summary_df.to_string(
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

    process_all_news()