"""Production ML pipeline: FinBERT sentiment + Temporal Fusion Transformer forecasts."""
from __future__ import annotations

import argparse
import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from api.news_api import supabase
from news.stock_config import get_nasdaq_stocks

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "ml"
ARTIFACTS.mkdir(parents=True, exist_ok=True)

SYMBOLS = list(get_nasdaq_stocks().keys())
FINBERT_MODEL = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")
ENCODER_LENGTH = int(os.getenv("TFT_ENCODER_LENGTH", "60"))
LOOKBACK_DAYS = int(os.getenv("ML_LOOKBACK_DAYS", "756"))
SEED = int(os.getenv("ML_SEED", "42"))
MODEL_NAME = "FinBERT+TFT-v2"

HORIZONS = {
    "1d": 1, "7d": 5, "1m": 21, "6m": 126,
    "1y": 252, "5y": 1260, "10y": 2520, "20y": 5040,
}
TFT_HORIZONS = ("1d", "7d", "1m", "6m", "1y")
SCENARIO_HORIZONS = ("5y", "10y", "20y")


def seed_everything():
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)


def fetch_all(table, columns, page_size=1000):
    rows, offset = [], 0
    while True:
        batch = (
            supabase.table(table).select(columns)
            .range(offset, offset + page_size - 1).execute().data or []
        )
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        offset += page_size


def load_prices():
    # Supabase uses price_date in the production stock_prices table.
    rows = fetch_all(
        "stock_prices",
        "symbol,price_date,open,high,low,close,volume",
        1000,
    )
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("No stock_prices rows found. Run the price collector first.")

    df["symbol"] = df["symbol"].astype(str).str.upper()
    df = df[df["symbol"].isin(SYMBOLS)].copy()
    df["date"] = pd.to_datetime(df["price_date"], errors="coerce").dt.normalize()
    for column in ("open", "high", "low", "close", "volume"):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = (
        df.dropna(subset=["symbol", "date", "open", "high", "low", "close", "volume"])
        .drop_duplicates(["symbol", "date"])
        .sort_values(["symbol", "date"])
        .reset_index(drop=True)
    )

    counts = df.groupby("symbol")["date"].count()
    missing = [s for s in SYMBOLS if counts.get(s, 0) < ENCODER_LENGTH + 10]
    if missing:
        raise RuntimeError(
            "Insufficient historical price data for: "
            + ", ".join(missing)
            + f". Each symbol needs at least {ENCODER_LENGTH + 10} rows."
        )
    return df


def score_finbert():
    news = pd.DataFrame(fetch_all(
        "news_articles",
        "id,symbol,title,description,text,published_at",
        1000,
    ))
    if news.empty:
        print("No news articles found; skipping FinBERT.")
        return 0

    news["symbol"] = news["symbol"].astype(str).str.upper()
    news = news[news["symbol"].isin(SYMBOLS)].copy()
    news["published_at"] = pd.to_datetime(news["published_at"], utc=True, errors="coerce")
    news = news[news["published_at"].notna()].copy()
    cutoff = pd.Timestamp(
        datetime.now(ET).date() - timedelta(days=LOOKBACK_DAYS), tz="UTC"
    )
    news = news[news["published_at"] >= cutoff].copy()
    news["text_for_model"] = (
        news["title"].fillna("").astype(str) + ". "
        + news["description"].fillna("").astype(str) + " "
        + news["text"].fillna("").astype(str)
    ).str.replace(r"\s+", " ", regex=True).str.strip()
    news = news[news["text_for_model"].str.len() > 0].copy()
    if news.empty:
        print("No usable news articles found for FinBERT.")
        return 0

    tokenizer = AutoTokenizer.from_pretrained(FINBERT_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(FINBERT_MODEL)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    labels = {int(k): str(v).lower() for k, v in model.config.id2label.items()}
    batch_size = int(os.getenv("FINBERT_BATCH_SIZE", "32"))
    payload = []

    with torch.inference_mode():
        for start in range(0, len(news), batch_size):
            batch = news.iloc[start:start + batch_size]
            tokens = tokenizer(
                batch["text_for_model"].tolist(), padding=True, truncation=True,
                max_length=256, return_tensors="pt",
            )
            tokens = {k: v.to(device) for k, v in tokens.items()}
            probabilities = torch.softmax(model(**tokens).logits, dim=-1).cpu().numpy()
            for row, values in zip(batch.itertuples(index=False), probabilities):
                probability_map = {
                    labels[index]: float(values[index]) for index in range(len(values))
                }
                payload.append({
                    "article_id": int(row.id), "symbol": row.symbol,
                    "positive_prob": probability_map.get("positive", 0.0),
                    "negative_prob": probability_map.get("negative", 0.0),
                    "neutral_prob": probability_map.get("neutral", 0.0),
                    "composite_score": (
                        probability_map.get("positive", 0.0)
                        - probability_map.get("negative", 0.0)
                    ),
                })

    for start in range(0, len(payload), 100):
        supabase.table("sentiment_scores").upsert(
            payload[start:start + 100], on_conflict="article_id"
        ).execute()
    print(f"FinBERT scored {len(payload):,} articles on {device}.")
    return len(payload)


def load_sentiment():
    scores = pd.DataFrame(fetch_all(
        "sentiment_scores",
        "article_id,symbol,positive_prob,negative_prob,neutral_prob,composite_score",
        1000,
    ))
    news = pd.DataFrame(fetch_all("news_articles", "id,published_at", 1000))
    if scores.empty or news.empty:
        return pd.DataFrame(columns=[
            "symbol", "date", "positive_prob", "negative_prob",
            "neutral_prob", "composite_score", "sent_count",
        ])

    news["published_at"] = pd.to_datetime(news["published_at"], utc=True, errors="coerce")
    news["date"] = (
        news["published_at"].dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
    )
    merged = scores.merge(news[["id", "date"]], left_on="article_id", right_on="id", how="inner")
    for column in ("positive_prob", "negative_prob", "neutral_prob", "composite_score"):
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)

    return merged.groupby(["symbol", "date"], as_index=False).agg(
        positive_prob=("positive_prob", "mean"),
        negative_prob=("negative_prob", "mean"),
        neutral_prob=("neutral_prob", "mean"),
        composite_score=("composite_score", "mean"),
        sent_count=("article_id", "nunique"),
    )


def rsi(series, period=14):
    delta = series.diff()
    gains = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    losses = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    relative_strength = gains / losses.replace(0, np.nan)
    return 100 - 100 / (1 + relative_strength)


def features(prices, sentiment):
    df = prices.copy().sort_values(["symbol", "date"])
    grouped = df.groupby("symbol")
    df["ret_1d"] = grouped["close"].pct_change()
    df["log_return"] = grouped["close"].transform(lambda x: np.log(x).diff())
    df["ret_5d"] = grouped["close"].pct_change(5)
    df["ret_20d"] = grouped["close"].pct_change(20)

    for period in (5, 20, 60):
        df[f"sma_{period}_ratio"] = grouped["close"].transform(
            lambda x, p=period: x / x.rolling(p).mean() - 1
        )
    df["volatility_20"] = grouped["log_return"].transform(lambda x: x.rolling(20).std())
    df["rsi_14"] = grouped["close"].transform(rsi) / 100

    ema12 = grouped["close"].transform(lambda x: x.ewm(span=12, adjust=False).mean())
    ema26 = grouped["close"].transform(lambda x: x.ewm(span=26, adjust=False).mean())
    df["macd"] = (ema12 - ema26) / df["close"]

    previous_close = grouped["close"].shift(1)
    true_range = pd.concat([
        df["high"] - df["low"],
        (df["high"] - previous_close).abs(),
        (df["low"] - previous_close).abs(),
    ], axis=1).max(axis=1)
    df["atr_14"] = true_range.groupby(df["symbol"]).transform(
        lambda x: x.rolling(14).mean()
    ) / df["close"]

    log_volume = np.log1p(df["volume"])
    volume_mean = log_volume.groupby(df["symbol"]).transform(lambda x: x.rolling(20).mean())
    volume_std = log_volume.groupby(df["symbol"]).transform(lambda x: x.rolling(20).std())
    df["volume_z20"] = (log_volume - volume_mean) / volume_std.replace(0, np.nan)
    df["market_ret_1d"] = df.groupby("date")["ret_1d"].transform("mean")
    df["relative_ret_1d"] = df["ret_1d"] - df["market_ret_1d"]
    df["dow"] = df["date"].dt.dayofweek.astype(str)
    df["month"] = df["date"].dt.month.astype(str)

    if not sentiment.empty:
        df = df.merge(sentiment, on=["symbol", "date"], how="left")
    for column in ("positive_prob", "negative_prob", "neutral_prob", "composite_score", "sent_count"):
        if column not in df:
            df[column] = 0.0
        df[column] = df[column].fillna(0.0)

    df = df.replace([np.inf, -np.inf], np.nan)
    df["time_idx"] = (df["date"] - df["date"].min()).dt.days.astype(int)
    return df.sort_values(["symbol", "date"]).reset_index(drop=True)


UNKNOWN_FEATURES = [
    "open", "high", "low", "close", "volume", "ret_1d", "ret_5d", "ret_20d",
    "sma_5_ratio", "sma_20_ratio", "sma_60_ratio", "volatility_20", "rsi_14",
    "macd", "atr_14", "volume_z20", "market_ret_1d", "relative_ret_1d",
    "positive_prob", "negative_prob", "neutral_prob", "composite_score", "sent_count",
]


def add_target(frame, horizon_sessions):
    df = frame.copy()
    df["target_return"] = df.groupby("symbol")["close"].transform(
        lambda series: np.log(series.shift(-horizon_sessions) / series)
    )
    df["target_close"] = df.groupby("symbol")["close"].shift(-horizon_sessions)
    return df.dropna(subset=UNKNOWN_FEATURES + ["target_return", "target_close"]).copy()


def train_one(frame, horizon):
    from lightning.pytorch import Trainer
    from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint
    from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer
    from pytorch_forecasting.data import GroupNormalizer
    from pytorch_forecasting.metrics import QuantileLoss

    horizon_sessions = HORIZONS[horizon]
    supervised = add_target(frame, horizon_sessions)
    first_dates = supervised.groupby("symbol")["date"].min()
    supervised = supervised[supervised["date"] >= first_dates.max()].copy()
    dates = sorted(supervised["date"].unique())
    if len(dates) < 120:
        raise RuntimeError(f"Not enough training dates for {horizon}: {len(dates)}")

    train_end = dates[int(0.70 * len(dates))]
    validation_start = dates[int(0.70 * len(dates)) + 1]
    validation_end = dates[int(0.85 * len(dates))]
    train_df = supervised[supervised["date"] <= train_end].copy()

    training = TimeSeriesDataSet(
        train_df, time_idx="time_idx", target="target_return",
        group_ids=["symbol"], max_encoder_length=ENCODER_LENGTH,
        max_prediction_length=1, min_encoder_length=ENCODER_LENGTH,
        static_categoricals=["symbol"], time_varying_known_reals=["time_idx"],
        time_varying_known_categoricals=["dow", "month"],
        time_varying_unknown_reals=UNKNOWN_FEATURES,
        target_normalizer=GroupNormalizer(groups=["symbol"]),
        allow_missing_timesteps=True, add_relative_time_idx=True,
        add_target_scales=True, add_encoder_length=True,
    )
    validation = TimeSeriesDataSet.from_dataset(
        training, supervised,
        min_prediction_idx=int(train_df["time_idx"].max()) + 1,
        stop_randomization=True,
    )
    train_loader = training.to_dataloader(
        train=True, batch_size=int(os.getenv("TFT_BATCH_SIZE", "64")), num_workers=0
    )
    validation_loader = validation.to_dataloader(train=False, batch_size=256, num_workers=0)

    checkpoint = ModelCheckpoint(
        dirpath=str(ARTIFACTS), filename=f"tft-{horizon}-{{epoch:02d}}-{{val_loss:.5f}}",
        monitor="val_loss", mode="min", save_top_k=1,
    )
    early_stopping = EarlyStopping(
        monitor="val_loss",
        patience=int(os.getenv("TFT_EARLY_STOPPING_PATIENCE", "4")),
        mode="min",
    )
    model = TemporalFusionTransformer.from_dataset(
        training,
        learning_rate=float(os.getenv("TFT_LR", "0.0003")),
        hidden_size=int(os.getenv("TFT_HIDDEN_SIZE", "24")),
        attention_head_size=int(os.getenv("TFT_ATTENTION_HEADS", "2")),
        dropout=float(os.getenv("TFT_DROPOUT", "0.15")),
        hidden_continuous_size=int(os.getenv("TFT_HIDDEN_CONTINUOUS_SIZE", "12")),
        lstm_layers=int(os.getenv("TFT_LSTM_LAYERS", "1")),
        output_size=3,
        loss=QuantileLoss(quantiles=[0.1, 0.5, 0.9]),
        reduce_on_plateau_patience=2,
    )
    trainer = Trainer(
        max_epochs=int(os.getenv("TFT_MAX_EPOCHS", "15")),
        accelerator="auto", devices=1,
        gradient_clip_val=float(os.getenv("TFT_GRADIENT_CLIP", "0.1")),
        callbacks=[checkpoint, early_stopping], logger=False,
        enable_progress_bar=True,
    )
    trainer.fit(model, train_dataloaders=train_loader, val_dataloaders=validation_loader)

    if not checkpoint.best_model_path:
        raise RuntimeError(f"No checkpoint produced for horizon {horizon}")
    best_model = TemporalFusionTransformer.load_from_checkpoint(checkpoint.best_model_path)
    metrics = {
        "model_name": MODEL_NAME, "horizon": horizon,
        "horizon_sessions": horizon_sessions,
        "train_start": str(pd.Timestamp(dates[0]).date()),
        "train_end": str(pd.Timestamp(train_end).date()),
        "validation_start": str(pd.Timestamp(validation_start).date()),
        "validation_end": str(pd.Timestamp(validation_end).date()),
        "checkpoint": str(Path(checkpoint.best_model_path).name),
    }
    (ARTIFACTS / f"tft_{horizon}_metrics.json").write_text(json.dumps(metrics, indent=2))
    return best_model, training, metrics


def predict_latest_tft(model, training, frame, horizon_sessions):
    from pytorch_forecasting import TimeSeriesDataSet
    rows = []
    for symbol in SYMBOLS:
        symbol_frame = frame[frame["symbol"] == symbol].sort_values("date").tail(ENCODER_LENGTH + 1).copy()
        if len(symbol_frame) < ENCODER_LENGTH + 1:
            continue
        # Keep encoder target values intact; only the final decoder row
        # has an unknown future target at inference time.
        symbol_frame["target_return"] = symbol_frame.groupby("symbol")["close"].transform(
            lambda series: np.log(series.shift(-horizon_sessions) / series)
        )
        symbol_frame["target_close"] = symbol_frame.groupby("symbol")["close"].shift(
            -horizon_sessions
        )
        try:
            prediction_dataset = TimeSeriesDataSet.from_dataset(
                training, symbol_frame, predict=True, stop_randomization=True
            )
            loader = prediction_dataset.to_dataloader(train=False, batch_size=1, num_workers=0)
            quantiles = model.predict(loader, mode="quantiles")
            values = quantiles.detach().cpu().numpy()[0, 0, :]
            current = symbol_frame.iloc[-1]
            rows.append({
                "symbol": symbol,
                "prediction_date": pd.Timestamp(current["date"]).date().isoformat(),
                "current_price": float(current["close"]),
                "p10": float(values[0]), "p50": float(values[1]), "p90": float(values[2]),
            })
        except Exception as exc:
            print(f"Prediction skipped for {symbol}: {exc}")
    return rows


def publish_tft_predictions(frame, forecasts, horizon):
    stock_rows = supabase.table("stocks").select("id,symbol").in_("symbol", SYMBOLS).execute().data or []
    stock_ids = {row["symbol"]: row["id"] for row in stock_rows}
    horizon_sessions = HORIZONS[horizon]
    rows = []

    for forecast in forecasts:
        prediction_date = pd.Timestamp(forecast["prediction_date"])
        target_date = (prediction_date + pd.offsets.BDay(horizon_sessions)).date().isoformat()
        p50, price = forecast["p50"], forecast["current_price"]
        rows.append({
            "stock_id": stock_ids.get(forecast["symbol"]),
            "symbol": forecast["symbol"],
            "prediction_date": forecast["prediction_date"],
            "target_date": target_date,
            "predicted_return": p50,
            "predicted_price": price * np.exp(p50),
            "model_name": MODEL_NAME,
            "metrics": {
                "forecast_type": "tft_quantile",
                "sentiment": float(frame.loc[frame["symbol"] == forecast["symbol"], "composite_score"].iloc[-1]),
                "p10_return": forecast["p10"], "p50_return": p50, "p90_return": forecast["p90"],
            },
            "horizon": horizon, "horizon_sessions": horizon_sessions,
            "forecast_type": "tft_quantile",
            "lower_return": forecast["p10"], "upper_return": forecast["p90"],
            "lower_price": price * np.exp(forecast["p10"]),
            "upper_price": price * np.exp(forecast["p90"]),
        })

    for start in range(0, len(rows), 50):
        batch = rows[start:start + 50]
        if batch:
            supabase.table("predictions").upsert(
                batch, on_conflict="stock_id,prediction_date,target_date,model_name,horizon"
            ).execute()
    print(f"Published {len(rows)} {horizon} TFT forecasts.")
    return len(rows)


def publish_scenarios(frame):
    stock_rows = supabase.table("stocks").select("id,symbol").in_("symbol", SYMBOLS).execute().data or []
    stock_ids = {row["symbol"]: row["id"] for row in stock_rows}
    latest = frame.sort_values("date").groupby("symbol").tail(1)
    rows = []

    for _, row in latest.iterrows():
        symbol = row["symbol"]
        history = frame[frame["symbol"] == symbol].sort_values("date")["close"]
        years = max(len(history) / 252.0, 1.0)
        total_growth = max(float(history.iloc[-1] / history.iloc[0]), 1e-6)
        cagr = float(total_growth ** (1.0 / years) - 1.0)
        price = float(row["close"])
        volatility = float(row["volatility_20"]) if pd.notna(row["volatility_20"]) else 0.02
        volatility = max(volatility, 0.005)

        for horizon in SCENARIO_HORIZONS:
            horizon_years = HORIZONS[horizon] / 252.0
            center = float(np.clip(cagr * horizon_years, -0.80, 3.00))
            spread = 0.60 * np.sqrt(horizon_years) * volatility
            lower, upper = center - spread, center + spread
            target_date = (
                pd.Timestamp(row["date"]) + pd.offsets.BDay(HORIZONS[horizon])
            ).date().isoformat()
            rows.append({
                "stock_id": stock_ids.get(symbol), "symbol": symbol,
                "prediction_date": pd.Timestamp(row["date"]).date().isoformat(),
                "target_date": target_date,
                "predicted_return": center, "predicted_price": price * np.exp(center),
                "model_name": MODEL_NAME,
                "metrics": {"forecast_type": "scenario", "data_quality": "scenario", "long_term_cagr": cagr},
                "horizon": horizon, "horizon_sessions": HORIZONS[horizon],
                "forecast_type": "scenario", "lower_return": lower, "upper_return": upper,
                "lower_price": price * np.exp(lower), "upper_price": price * np.exp(upper),
            })

    for start in range(0, len(rows), 50):
        supabase.table("predictions").upsert(
            rows[start:start + 50],
            on_conflict="stock_id,prediction_date,target_date,model_name,horizon"
        ).execute()
    print(f"Published {len(rows)} long-horizon scenario forecasts.")
    return len(rows)


def train_tft(horizons=None):
    seed_everything()
    prices = load_prices()
    sentiment = load_sentiment()
    frame = features(prices, sentiment)
    requested = horizons or list(TFT_HORIZONS)
    requested_tft = [h for h in requested if h in TFT_HORIZONS]
    if not requested_tft:
        raise ValueError("At least one TFT horizon is required: " + ", ".join(TFT_HORIZONS))

    total = 0
    for horizon in requested_tft:
        model, training, _ = train_one(frame, horizon)
        forecasts = predict_latest_tft(model, training, frame, HORIZONS[horizon])
        total += publish_tft_predictions(frame, forecasts, horizon)

    if os.getenv("PUBLISH_LONG_TERM_SCENARIOS", "1") == "1":
        publish_scenarios(frame)
    print(
        f"ML pipeline complete: {total} TFT forecasts + "
        f"{len(SYMBOLS) * len(SCENARIO_HORIZONS)} scenario forecasts."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["finbert", "tft", "all"])
    parser.add_argument("--horizons", nargs="+", choices=list(HORIZONS), default=None)
    args = parser.parse_args()
    if args.stage in ("finbert", "all"):
        score_finbert()
    if args.stage in ("tft", "all"):
        train_tft(args.horizons)


if __name__ == "__main__":
    main()
