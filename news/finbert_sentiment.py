from pathlib import Path

import pandas as pd
import torch
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification
)


# ============================================================
# CONFIGURATION
# ============================================================

MODEL_NAME = "ProsusAI/finbert"

BATCH_SIZE = 16

MAX_LENGTH = 512


# ============================================================
# PROJECT DIRECTORIES
# ============================================================

PROJECT_ROOT = (
    Path(__file__).resolve().parent.parent
)

INPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "news"
    / "nasdaq"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "sentiment"
    / "nasdaq"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# DEVICE
# ============================================================

if torch.cuda.is_available():

    DEVICE = torch.device("cuda")

    print("Device: CUDA GPU")

else:

    DEVICE = torch.device("cpu")

    print("Device: CPU")


# ============================================================
# LOAD FINBERT
# ============================================================

def load_finbert():

    print(
        "\n========================================"
    )

    print(
        "LOADING FINBERT"
    )

    print(
        "========================================"
    )

    print(
        f"Model: {MODEL_NAME}"
    )

    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_NAME
    )

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME
    )

    model.to(DEVICE)

    model.eval()

    print(
        "FinBERT loaded successfully."
    )

    return tokenizer, model


# ============================================================
# SENTIMENT SCORE
# ============================================================

def calculate_sentiment_score(
    positive,
    negative
):

    # Range: -1 to +1
    return positive - negative


# ============================================================
# FINBERT BATCH PREDICTION
# ============================================================

def predict_batch(
    texts,
    tokenizer,
    model
):

    encoded = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=MAX_LENGTH,
        return_tensors="pt"
    )

    encoded = {
        key: value.to(DEVICE)
        for key, value in encoded.items()
    }

    with torch.no_grad():

        outputs = model(
            **encoded
        )

    probabilities = torch.softmax(
        outputs.logits,
        dim=1
    )

    probabilities = (
        probabilities
        .cpu()
        .numpy()
    )

    id2label = model.config.id2label

    results = []

    for probability in probabilities:

        label_scores = {}

        for index, score in enumerate(
            probability
        ):

            label = (
                id2label[index]
                .lower()
                .strip()
            )

            label_scores[label] = float(
                score
            )

        positive = label_scores.get(
            "positive",
            0.0
        )

        neutral = label_scores.get(
            "neutral",
            0.0
        )

        negative = label_scores.get(
            "negative",
            0.0
        )

        sentiment_label = max(
            label_scores,
            key=label_scores.get
        )

        sentiment_score = (
            calculate_sentiment_score(
                positive,
                negative
            )
        )

        results.append({

            "sentiment_label":
                sentiment_label,

            "positive_score":
                positive,

            "neutral_score":
                neutral,

            "negative_score":
                negative,

            "sentiment_score":
                sentiment_score
        })

    return results


# ============================================================
# LOAD NEWS
# ============================================================

def load_news_file(
    file_path
):

    try:

        df = pd.read_csv(
            file_path
        )

    except Exception as error:

        print(
            f"ERROR reading "
            f"{file_path.name}: {error}"
        )

        return pd.DataFrame()

    if df.empty:

        print(
            f"{file_path.name}: empty file"
        )

        return pd.DataFrame()

    # Always use a clean unique row index
    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================
# VALIDATE
# ============================================================

def validate_news_data(
    df,
    file_path
):

    required_columns = [
        "symbol",
        "company",
        "published_at",
        "title",
        "text"
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:

        print(
            f"{file_path.name}: "
            f"missing columns: {missing}"
        )

        return False

    return True


# ============================================================
# PREPARE TEXT
# ============================================================

def prepare_text(
    df
):

    df = df.reset_index(
        drop=True
    )

    df["text"] = (
        df["text"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df = df[
        df["text"].str.len() > 0
    ].copy()

    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================
# REMOVE OLD API SENTIMENT
# ============================================================

def remove_old_sentiment_columns(
    df
):

    # --------------------------------------------------------
    # IMPORTANT
    #
    # process_news.py preserves sentiment fields coming from
    # Alpha Vantage / Marketaux.
    #
    # We do NOT want those columns when adding FinBERT's
    # sentiment columns because they would create duplicate
    # column names.
    # --------------------------------------------------------

    old_sentiment_columns = [

        "sentiment_score",

        "sentiment_label",

        "positive_score",

        "neutral_score",

        "negative_score"
    ]

    existing_columns = [
        column
        for column in old_sentiment_columns
        if column in df.columns
    ]

    if existing_columns:

        print(
            "    Removing existing API "
            "sentiment columns:"
        )

        print(
            f"    {existing_columns}"
        )

        df = df.drop(
            columns=existing_columns
        )

    return df


# ============================================================
# RUN FINBERT
# ============================================================

def run_finbert(
    df,
    tokenizer,
    model
):

    if df.empty:

        return df

    # --------------------------------------------------------
    # Clean index
    # --------------------------------------------------------

    df = df.reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # Remove API sentiment columns
    # BEFORE adding FinBERT columns
    # --------------------------------------------------------

    df = remove_old_sentiment_columns(
        df
    )

    df = df.reset_index(
        drop=True
    )

    texts = df[
        "text"
    ].tolist()

    total = len(
        texts
    )

    all_results = []

    # ========================================================
    # BATCH PROCESSING
    # ========================================================

    for start in range(
        0,
        total,
        BATCH_SIZE
    ):

        end = min(
            start + BATCH_SIZE,
            total
        )

        batch_texts = texts[
            start:end
        ]

        print(
            f"    FinBERT: "
            f"{start + 1}-{end} / {total}"
        )

        batch_results = predict_batch(
            batch_texts,
            tokenizer,
            model
        )

        all_results.extend(
            batch_results
        )

    # ========================================================
    # CREATE SENTIMENT DATAFRAME
    # ========================================================

    sentiment_df = pd.DataFrame(
        all_results
    )

    sentiment_df = sentiment_df.reset_index(
        drop=True
    )

    df = df.reset_index(
        drop=True
    )

    # ========================================================
    # SAFETY CHECK
    # ========================================================

    if len(df) != len(
        sentiment_df
    ):

        raise ValueError(
            "FinBERT result count "
            "does not match input article count."
        )

    # ========================================================
    # SAFETY CHECK FOR DUPLICATE COLUMNS
    # ========================================================

    if df.columns.duplicated().any():

        duplicated_columns = (
            df.columns[
                df.columns.duplicated()
            ]
            .tolist()
        )

        raise ValueError(
            "Input dataframe contains "
            "duplicate columns: "
            f"{duplicated_columns}"
        )

    if sentiment_df.columns.duplicated().any():

        duplicated_columns = (
            sentiment_df.columns[
                sentiment_df.columns.duplicated()
            ]
            .tolist()
        )

        raise ValueError(
            "FinBERT dataframe contains "
            "duplicate columns: "
            f"{duplicated_columns}"
        )

    # ========================================================
    # COMBINE
    # ========================================================

    df = pd.concat(
        [
            df,
            sentiment_df
        ],
        axis=1
    )

    # ========================================================
    # FINAL SAFETY CHECK
    # ========================================================

    if df.columns.duplicated().any():

        duplicated_columns = (
            df.columns[
                df.columns.duplicated()
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate columns after "
            "FinBERT merge: "
            f"{duplicated_columns}"
        )

    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================
# DATE FEATURES
# ============================================================

def create_date_features(
    df
):

    df = df.reset_index(
        drop=True
    )

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
    ).copy()

    df = df.reset_index(
        drop=True
    )

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

    return df


# ============================================================
# DAILY SENTIMENT
# ============================================================

def create_daily_sentiment(
    df
):

    if df.empty:

        return pd.DataFrame()

    # IMPORTANT
    # Always create a clean index before filtering/grouping.
    df = df.reset_index(
        drop=True
    )

    # ========================================================
    # VERIFY SENTIMENT COLUMNS
    # ========================================================

    required_sentiment_columns = [

        "sentiment_label",

        "positive_score",

        "neutral_score",

        "negative_score",

        "sentiment_score"
    ]

    missing = [
        column
        for column in required_sentiment_columns
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            "Missing FinBERT columns: "
            f"{missing}"
        )

    # ========================================================
    # DAILY MAIN METRICS
    # ========================================================

    daily = (
        df.groupby(
            [
                "symbol",
                "company",
                "published_date"
            ],
            as_index=False
        )
        .agg(

            article_count=(
                "sentiment_score",
                "count"
            ),

            average_sentiment=(
                "sentiment_score",
                "mean"
            ),

            sentiment_std=(
                "sentiment_score",
                "std"
            ),

            average_positive=(
                "positive_score",
                "mean"
            ),

            average_neutral=(
                "neutral_score",
                "mean"
            ),

            average_negative=(
                "negative_score",
                "mean"
            )
        )
    )

    # ========================================================
    # STANDARD DEVIATION
    # ========================================================

    daily["sentiment_std"] = (
        daily["sentiment_std"]
        .fillna(0)
    )

    # ========================================================
    # POSITIVE COUNTS
    # ========================================================

    positive_counts = (
        df[
            df["sentiment_label"]
            == "positive"
        ]
        .groupby(
            [
                "symbol",
                "published_date"
            ],
            as_index=False
        )
        .size()
        .rename(
            columns={
                "size":
                    "positive_articles"
            }
        )
    )

    # ========================================================
    # NEGATIVE COUNTS
    # ========================================================

    negative_counts = (
        df[
            df["sentiment_label"]
            == "negative"
        ]
        .groupby(
            [
                "symbol",
                "published_date"
            ],
            as_index=False
        )
        .size()
        .rename(
            columns={
                "size":
                    "negative_articles"
            }
        )
    )

    # ========================================================
    # NEUTRAL COUNTS
    # ========================================================

    neutral_counts = (
        df[
            df["sentiment_label"]
            == "neutral"
        ]
        .groupby(
            [
                "symbol",
                "published_date"
            ],
            as_index=False
        )
        .size()
        .rename(
            columns={
                "size":
                    "neutral_articles"
            }
        )
    )

    # ========================================================
    # MERGE COUNTS
    # ========================================================

    daily = daily.merge(
        positive_counts,
        on=[
            "symbol",
            "published_date"
        ],
        how="left"
    )

    daily = daily.merge(
        negative_counts,
        on=[
            "symbol",
            "published_date"
        ],
        how="left"
    )

    daily = daily.merge(
        neutral_counts,
        on=[
            "symbol",
            "published_date"
        ],
        how="left"
    )

    # ========================================================
    # FILL MISSING COUNTS
    # ========================================================

    count_columns = [

        "positive_articles",

        "negative_articles",

        "neutral_articles"
    ]

    for column in count_columns:

        if column not in daily.columns:

            daily[column] = 0

        daily[column] = (
            daily[column]
            .fillna(0)
            .astype(int)
        )

    # ========================================================
    # SENTIMENT BALANCE
    # ========================================================

    daily["sentiment_balance"] = (

        daily["positive_articles"]
        -
        daily["negative_articles"]

    ) / daily[
        "article_count"
    ].replace(
        0,
        1
    )

    # ========================================================
    # SORT
    # ========================================================

    daily = daily.sort_values(
        [
            "symbol",
            "published_date"
        ]
    )

    daily = daily.reset_index(
        drop=True
    )

    return daily


# ============================================================
# SAVE ARTICLE SENTIMENT
# ============================================================

def save_article_sentiment(
    df,
    symbol
):

    output_file = (
        OUTPUT_DIR
        / f"{symbol}_sentiment.csv"
    )

    df.to_csv(
        output_file,
        index=False
    )

    print(
        "    Saved article sentiment:"
    )

    print(
        f"    {output_file}"
    )


# ============================================================
# SAVE DAILY SENTIMENT
# ============================================================

def save_daily_sentiment(
    daily_df,
    symbol
):

    if daily_df.empty:

        print(
            "    No daily sentiment "
            "data generated."
        )

        return

    output_file = (
        OUTPUT_DIR
        / f"{symbol}_daily_sentiment.csv"
    )

    daily_df.to_csv(
        output_file,
        index=False
    )

    print(
        "    Saved daily sentiment:"
    )

    print(
        f"    {output_file}"
    )


# ============================================================
# PROCESS ONE STOCK
# ============================================================

def process_stock(
    file_path,
    tokenizer,
    model
):

    symbol = (
        file_path.stem
        .replace(
            "_processed",
            ""
        )
    )

    print(
        "\n========================================"
    )

    print(
        f"Processing: {symbol}"
    )

    print(
        "========================================"
    )

    # ========================================================
    # LOAD
    # ========================================================

    df = load_news_file(
        file_path
    )

    if df.empty:

        return None

    print(
        f"Input articles: {len(df)}"
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    if not validate_news_data(
        df,
        file_path
    ):

        return None

    # ========================================================
    # PREPARE
    # ========================================================

    df = prepare_text(
        df
    )

    if df.empty:

        print(
            "No usable text."
        )

        return None

    # ========================================================
    # DATE FEATURES
    # ========================================================

    df = create_date_features(
        df
    )

    if df.empty:

        print(
            "No valid dates."
        )

        return None

    # ========================================================
    # FINBERT
    # ========================================================

    df = run_finbert(
        df,
        tokenizer,
        model
    )

    # ========================================================
    # SAVE ARTICLE SENTIMENT
    # ========================================================

    save_article_sentiment(
        df,
        symbol
    )

    # ========================================================
    # CREATE DAILY SENTIMENT
    # ========================================================

    daily_df = create_daily_sentiment(
        df
    )

    # ========================================================
    # SAVE DAILY SENTIMENT
    # ========================================================

    save_daily_sentiment(
        daily_df,
        symbol
    )

    # ========================================================
    # DISPLAY SUMMARY
    # ========================================================

    print(
        "\nSentiment distribution:"
    )

    print(
        df[
            "sentiment_label"
        ]
        .value_counts()
        .to_string()
    )

    print(
        f"\nAverage sentiment: "
        f"{df['sentiment_score'].mean():.4f}"
    )

    print(
        f"Daily sentiment rows: "
        f"{len(daily_df)}"
    )

    return {

        "symbol":
            symbol,

        "articles":
            len(df),

        "average_sentiment":
            df[
                "sentiment_score"
            ].mean(),

        "positive":
            int(
                (
                    df[
                        "sentiment_label"
                    ]
                    == "positive"
                ).sum()
            ),

        "neutral":
            int(
                (
                    df[
                        "sentiment_label"
                    ]
                    == "neutral"
                ).sum()
            ),

        "negative":
            int(
                (
                    df[
                        "sentiment_label"
                    ]
                    == "negative"
                ).sum()
            )
    }


# ============================================================
# PROCESS ALL STOCKS
# ============================================================

def process_all_stocks():

    print(
        "\n========================================"
    )

    print(
        "FINBERT SENTIMENT ANALYSIS"
    )

    print(
        "========================================"
    )

    # ========================================================
    # CHECK INPUT DIRECTORY
    # ========================================================

    if not INPUT_DIR.exists():

        print(
            "Input directory not found:"
        )

        print(
            INPUT_DIR
        )

        return

    # ========================================================
    # FIND FILES
    # ========================================================

    files = sorted(
        INPUT_DIR.glob(
            "*_processed.csv"
        )
    )

    if not files:

        print(
            "No processed news files found."
        )

        print(
            "Expected files in:"
        )

        print(
            INPUT_DIR
        )

        return

    print(
        f"Stock files found: {len(files)}"
    )

    # ========================================================
    # LOAD MODEL ONCE
    # ========================================================

    tokenizer, model = (
        load_finbert()
    )

    # ========================================================
    # PROCESS STOCKS
    # ========================================================

    summary = []

    for file_path in files:

        try:

            result = process_stock(
                file_path,
                tokenizer,
                model
            )

            if result:

                summary.append(
                    result
                )

        except Exception as error:

            print(
                f"\nERROR processing "
                f"{file_path.name}:"
            )

            print(
                f"{error}"
            )

            print(
                "Continuing with next stock..."
            )

            continue

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    if not summary:

        print(
            "\nNo stocks were successfully processed."
        )

        return

    summary_df = pd.DataFrame(
        summary
    )

    summary_file = (
        OUTPUT_DIR
        / "finbert_summary.csv"
    )

    summary_df.to_csv(
        summary_file,
        index=False
    )

    print(
        "\n========================================"
    )

    print(
        "FINBERT ANALYSIS COMPLETE"
    )

    print(
        "========================================"
    )

    print(
        f"Stocks processed: "
        f"{len(summary_df)}"
    )

    print(
        f"Total articles: "
        f"{summary_df['articles'].sum()}"
    )

    print(
        f"Positive articles: "
        f"{summary_df['positive'].sum()}"
    )

    print(
        f"Neutral articles: "
        f"{summary_df['neutral'].sum()}"
    )

    print(
        f"Negative articles: "
        f"{summary_df['negative'].sum()}"
    )

    overall_sentiment = (
        summary_df[
            "average_sentiment"
        ].mean()
    )

    print(
        f"Overall average sentiment: "
        f"{overall_sentiment:.4f}"
    )

    print(
        "\nSummary saved to:"
    )

    print(
        summary_file
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    process_all_stocks()
