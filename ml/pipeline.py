"""FinBERT + direct multi-horizon TFT/scenario forecasting pipeline.

Short/medium horizons are trained as direct supervised targets:
1d, 7d, 1m, 6m and 1y map to 1, 5, 21, 126 and 252 trading sessions.
Long horizons (5y/10y/20y) are scenario forecasts based on historical
rolling annualized returns; they are deliberately not compounded 1-day forecasts.
"""
from __future__ import annotations

import argparse
import json
import math
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

HORIZONS = {
    "1d": {"sessions": 1, "label": "1 Day", "type": "model"},
    "7d": {"sessions": 5, "label": "7 Days / 1 Week", "type": "model"},
    "1m": {"sessions": 21, "label": "1 Month", "type": "model"},
    "6m": {"sessions": 126, "label": "6 Months", "type": "model"},
    "1y": {"sessions": 252, "label": "1 Year", "type": "model"},
    "5y": {"sessions": 1260, "label": "5 Years", "type": "scenario"},
    "10y": {"sessions": 2520, "label": "10 Years", "type": "scenario"},
    "20y": {"sessions": 5040, "label": "20 Years", "type": "scenario"},
}
MODEL_HORIZONS = tuple(k for k, v in HORIZONS.items() if v["type"] == "model")
SCENARIO_HORIZONS = tuple(k for k, v in HORIZONS.items() if v["type"] == "scenario")
FEATURES = [
    "open", "high", "low", "close", "volume", "ret_1d", "ret_5d", "ret_20d",
    "sma_5_ratio", "sma_20_ratio", "sma_60_ratio", "volatility_20", "rsi_14",
    "macd", "atr_14", "volume_z20", "market_ret_1d", "relative_ret_1d",
    "positive_prob", "negative_prob", "neutral_prob", "composite_score", "sent_count",
]

def seed_everything():
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(SEED)

def fetch_all(table, columns, page_size=1000):
    rows, offset = [], 0
    while True:
        batch = supabase.table(table).select(columns).range(offset, offset + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size: return rows
        offset += page_size

def load_prices():
    rows = fetch_all("stock_prices", "symbol,price_date,open,high,low,close,volume", page_size=1000)
    df = pd.DataFrame(rows)
    if df.empty: raise RuntimeError("No stock_prices rows found. Run news/price_collector.py first.")
    df = df.rename(columns={"price_date": "date"})
    df["symbol"] = df["symbol"].astype(str).str.upper(); df = df[df["symbol"].isin(SYMBOLS)].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    for col in ["open", "high", "low", "close", "volume"]: df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["symbol", "date", "open", "high", "low", "close", "volume"])
    return df.drop_duplicates(["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)

def score_finbert():
    news = pd.DataFrame(fetch_all("news_articles", "id,symbol,title,description,text,published_at"))
    if news.empty:
        print("No news_articles rows found; FinBERT produced no scores."); return 0
    news["symbol"] = news["symbol"].astype(str).str.upper(); news = news[news["symbol"].isin(SYMBOLS)].copy()
    news["published_at"] = pd.to_datetime(news["published_at"], utc=True, errors="coerce"); news = news[news["published_at"].notna()].copy()
    cutoff = pd.Timestamp(datetime.now(ET).date() - timedelta(days=LOOKBACK_DAYS), tz="UTC"); news = news[news["published_at"] >= cutoff].copy()
    news["text_for_model"] = (news["title"].fillna("").astype(str) + ". " + news["description"].fillna("").astype(str) + " " + news["text"].fillna("").astype(str)).str.replace(r"\s+", " ", regex=True).str.strip()
    news = news[news["text_for_model"].str.len() > 0].copy()
    tokenizer = AutoTokenizer.from_pretrained(FINBERT_MODEL); model = AutoModelForSequenceClassification.from_pretrained(FINBERT_MODEL)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu"); model.to(device).eval()
    labels = {int(k): str(v).lower() for k, v in model.config.id2label.items()}; batch_size = int(os.getenv("FINBERT_BATCH_SIZE", "32")); payload = []
    with torch.inference_mode():
        for start in range(0, len(news), batch_size):
            batch_df = news.iloc[start:start + batch_size]
            tokens = tokenizer(batch_df["text_for_model"].tolist(), padding=True, truncation=True, max_length=256, return_tensors="pt")
            tokens = {key: value.to(device) for key, value in tokens.items()}; probs = torch.softmax(model(**tokens).logits, dim=-1).cpu().numpy()
            for row, values in zip(batch_df.itertuples(index=False), probs):
                p = {labels[i]: float(values[i]) for i in range(len(values))}
                payload.append({"article_id": int(row.id), "symbol": row.symbol, "positive_prob": p.get("positive", 0.0), "negative_prob": p.get("negative", 0.0), "neutral_prob": p.get("neutral", 0.0), "composite_score": p.get("positive", 0.0) - p.get("negative", 0.0)})
    for start in range(0, len(payload), 100): supabase.table("sentiment_scores").upsert(payload[start:start + 100], on_conflict="article_id").execute()
    print(f"FinBERT scored {len(payload):,} articles on {device}."); return len(payload)

def load_sentiment():
    scores = pd.DataFrame(fetch_all("sentiment_scores", "article_id,symbol,positive_prob,negative_prob,neutral_prob,composite_score")); news = pd.DataFrame(fetch_all("news_articles", "id,published_at"))
    if scores.empty or news.empty: return pd.DataFrame(columns=["symbol", "date", "positive_prob", "negative_prob", "neutral_prob", "composite_score", "sent_count"])
    news["published_at"] = pd.to_datetime(news["published_at"], utc=True, errors="coerce"); news["date"] = news["published_at"].dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
    merged = scores.merge(news[["id", "date"]], left_on="article_id", right_on="id", how="inner")
    for col in ["positive_prob", "negative_prob", "neutral_prob", "composite_score"]: merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0)
    return merged.groupby(["symbol", "date"], as_index=False).agg(positive_prob=("positive_prob", "mean"), negative_prob=("negative_prob", "mean"), neutral_prob=("neutral_prob", "mean"), composite_score=("composite_score", "mean"), sent_count=("article_id", "nunique"))

def rsi(series, n=14):
    delta = series.diff(); up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean(); rs = up / down.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def build_frame(prices, sentiment):
    df = prices.copy().sort_values(["symbol", "date"]).reset_index(drop=True); group = df.groupby("symbol", group_keys=False)
    df["ret_1d"] = group["close"].pct_change(); df["log_return"] = group["close"].transform(lambda x: np.log(x).diff()); df["ret_5d"] = group["close"].pct_change(5); df["ret_20d"] = group["close"].pct_change(20)
    for n in (5, 20, 60): df[f"sma_{n}_ratio"] = group["close"].transform(lambda x, n=n: x / x.rolling(n).mean() - 1)
    df["volatility_20"] = group["log_return"].transform(lambda x: x.rolling(20).std()); df["rsi_14"] = group["close"].transform(rsi) / 100
    ema12 = group["close"].transform(lambda x: x.ewm(span=12, adjust=False).mean()); ema26 = group["close"].transform(lambda x: x.ewm(span=26, adjust=False).mean()); df["macd"] = (ema12 - ema26) / df["close"]
    prev = group["close"].shift(1); true_range = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    df["atr_14"] = true_range.groupby(df["symbol"]).transform(lambda x: x.rolling(14).mean()) / df["close"]
    log_volume = np.log1p(df["volume"]); vol_mean = log_volume.groupby(df["symbol"]).transform(lambda x: x.rolling(20).mean()); vol_std = log_volume.groupby(df["symbol"]).transform(lambda x: x.rolling(20).std()); df["volume_z20"] = (log_volume - vol_mean) / vol_std.replace(0, np.nan)
    df = df.merge(df.groupby("date")["ret_1d"].mean().rename("market_ret_1d"), on="date", how="left"); df["relative_ret_1d"] = df["ret_1d"] - df["market_ret_1d"]; df["dow"] = df["date"].dt.dayofweek.astype(str); df["month"] = df["date"].dt.month.astype(str)
    if not sentiment.empty: df = df.merge(sentiment, on=["symbol", "date"], how="left")
    else:
        for col in ["positive_prob", "negative_prob", "neutral_prob", "composite_score", "sent_count"]: df[col] = np.nan
    sentiment_cols = ["positive_prob", "negative_prob", "neutral_prob", "composite_score", "sent_count"]; df[sentiment_cols] = df[sentiment_cols].fillna(0); df = df.replace([np.inf, -np.inf], np.nan); df = df.dropna(subset=FEATURES).copy()
    df["time_idx"] = df.groupby("symbol").cumcount().astype(int)
    return df.sort_values(["symbol", "date"]).reset_index(drop=True)

def add_direct_target(frame, sessions):
    df = frame.copy(); df["target_return"] = df.groupby("symbol")["close"].transform(lambda x: np.log(x.shift(-sessions) / x)); df["target_close"] = df.groupby("symbol")["close"].shift(-sessions); df = df.replace([np.inf, -np.inf], np.nan)
    return df.dropna(subset=FEATURES + ["target_return", "target_close"]).copy()

def _make_tft_dataset(frame, target_name):
    from pytorch_forecasting import TimeSeriesDataSet
    from pytorch_forecasting.data import GroupNormalizer
    return TimeSeriesDataSet(frame, time_idx="time_idx", target=target_name, group_ids=["symbol"], max_encoder_length=ENCODER_LENGTH, min_encoder_length=ENCODER_LENGTH, max_prediction_length=1, static_categoricals=["symbol"], time_varying_known_reals=["time_idx"], time_varying_known_categoricals=["dow", "month"], time_varying_unknown_reals=FEATURES, target_normalizer=GroupNormalizer(groups=["symbol"]), allow_missing_timesteps=True, add_relative_time_idx=True, add_target_scales=True, add_encoder_length=True)

def _make_tft_dataset_from(training, frame, cutoff_date):
    from pytorch_forecasting import TimeSeriesDataSet
    eligible = frame[frame["date"] > cutoff_date]
    if eligible.empty: raise RuntimeError(f"No rows available after split date {cutoff_date}.")
    return TimeSeriesDataSet.from_dataset(training, frame, min_prediction_idx=int(eligible["time_idx"].min()), stop_randomization=True)

def _metrics(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float); y_pred = np.asarray(y_pred, dtype=float)
    return {"mae_return": float(np.mean(np.abs(y_pred - y_true))), "rmse_return": float(np.sqrt(np.mean((y_pred - y_true) ** 2))), "directional_accuracy": float(np.mean(np.sign(y_pred) == np.sign(y_true))), "samples": int(len(y_true))}

def train_one_horizon(frame, horizon, sessions):
    seed_everything()
    from lightning.pytorch import Trainer
    from lightning.pytorch.callbacks import EarlyStopping, LearningRateMonitor, ModelCheckpoint
    from pytorch_forecasting import TemporalFusionTransformer
    from pytorch_forecasting.metrics import QuantileLoss
    target_frame = add_direct_target(frame, sessions)
    if target_frame["date"].nunique() < max(300, sessions + 100): raise RuntimeError(f"{horizon} has insufficient usable history for direct TFT training.")
    first_dates = target_frame.groupby("symbol")["date"].min(); common_start = first_dates.max(); split_frame = target_frame[target_frame["date"] >= common_start].copy()
    dates = sorted(split_frame["date"].unique()); train_end = dates[int(len(dates) * 0.70)]; val_end = dates[int(len(dates) * 0.85)]; train_frame = split_frame[split_frame["date"] <= train_end].copy()
    if len(train_frame) < 1000: raise RuntimeError(f"{horizon} has too few training rows: {len(train_frame)}")
    training = _make_tft_dataset(train_frame, "target_return"); val = _make_tft_dataset_from(training, split_frame[split_frame["date"] <= val_end].copy(), train_end); test = _make_tft_dataset_from(training, split_frame, val_end)
    train_loader = training.to_dataloader(train=True, batch_size=int(os.getenv("TFT_BATCH_SIZE", "64")), num_workers=0); val_loader = val.to_dataloader(train=False, batch_size=256, num_workers=0); test_loader = test.to_dataloader(train=False, batch_size=256, num_workers=0)
    checkpoint = ModelCheckpoint(dirpath=str(ARTIFACTS), filename=f"tft-{horizon}-{{epoch:02d}}-{{val_loss:.5f}}", monitor="val_loss", mode="min", save_top_k=1)
    model = TemporalFusionTransformer.from_dataset(training, learning_rate=float(os.getenv("TFT_LR", "0.0003")), hidden_size=int(os.getenv("TFT_HIDDEN_SIZE", "32")), attention_head_size=int(os.getenv("TFT_HEADS", "4")), dropout=float(os.getenv("TFT_DROPOUT", "0.15")), hidden_continuous_size=int(os.getenv("TFT_HIDDEN_CONTINUOUS", "16")), lstm_layers=2, output_size=3, loss=QuantileLoss(quantiles=[0.1, 0.5, 0.9]), reduce_on_plateau_patience=3)
    trainer = Trainer(max_epochs=int(os.getenv("TFT_MAX_EPOCHS", "40")), accelerator="auto", devices=1, gradient_clip_val=0.1, callbacks=[checkpoint, EarlyStopping(monitor="val_loss", patience=6, mode="min"), LearningRateMonitor()], logger=False, enable_progress_bar=True); trainer.fit(model, train_loader, val_loader)
    best = TemporalFusionTransformer.load_from_checkpoint(checkpoint.best_model_path); prediction = best.predict(test_loader, mode="quantiles", return_y=True, trainer_kwargs={"accelerator": "cpu"}); quantiles = prediction.output.detach().cpu().numpy()[:, 0, :]; y = prediction.y[0].detach().cpu().numpy().reshape(-1)
    metrics = _metrics(y, quantiles[:, 1]); metrics.update({"horizon": horizon, "horizon_sessions": sessions, "train_end": str(pd.Timestamp(train_end).date()), "validation_end": str(pd.Timestamp(val_end).date()), "encoder_length": ENCODER_LENGTH, "model": "TemporalFusionTransformer", "quantiles": [0.1, 0.5, 0.9]})
    (ARTIFACTS / f"tft_{horizon}_best.ckpt").write_bytes(Path(checkpoint.best_model_path).read_bytes()); (ARTIFACTS / f"tft_{horizon}_metrics.json").write_text(json.dumps(metrics, indent=2)); print(json.dumps(metrics, indent=2))
    return best, training, target_frame, metrics

def _next_trading_date(last_date, sessions=1):
    return pd.Timestamp(last_date) + pd.tseries.offsets.BDay(sessions)

def _predict_current_tft(model, training, target_frame, horizon, sessions):
    from pytorch_forecasting import TimeSeriesDataSet
    last_by_symbol = target_frame.sort_values("date").groupby("symbol").tail(1)
    if last_by_symbol.empty: return []
    future = []
    for row in last_by_symbol.itertuples(index=False):
        item = row._asdict(); target_date = _next_trading_date(row.date, sessions); item.update({"date": target_date, "time_idx": int(row.time_idx) + sessions, "dow": str(target_date.dayofweek), "month": str(target_date.month), "target_return": 0.0, "target_close": float(row.close)}); future.append(item)
    infer = pd.concat([target_frame, pd.DataFrame(future)], ignore_index=True).sort_values(["symbol", "date"]); predict_ds = TimeSeriesDataSet.from_dataset(training, infer, predict=True, stop_randomization=True)
    quantiles = model.predict(predict_ds, mode="quantiles", trainer_kwargs={"accelerator": "cpu"}).detach().cpu().numpy()[:, 0, :]; latest = last_by_symbol.set_index("symbol"); output = []
    for idx, symbol in enumerate(latest.index):
        p10, p50, p90 = [float(v) for v in quantiles[idx]]; price = float(latest.loc[symbol, "close"]); target_date = _next_trading_date(latest.loc[symbol, "date"], sessions)
        output.append({"symbol": symbol, "horizon": horizon, "horizon_sessions": sessions, "forecast_type": "model", "prediction_date": pd.Timestamp(latest.loc[symbol, "date"]).date().isoformat(), "target_date": target_date.date().isoformat(), "predicted_return": p50, "predicted_price": price * math.exp(p50), "lower_return": p10, "upper_return": p90, "lower_price": price * math.exp(p10), "upper_price": price * math.exp(p90), "metrics": {"p10_return": p10, "p50_return": p50, "p90_return": p90, "sentiment": float(latest.loc[symbol, "composite_score"])}})
    return output

def _scenario_for_symbol(group, horizon, sessions):
    group = group.sort_values("date").copy(); available = len(group); window = min(sessions, available - 1)
    if window < 252: return None
    rolling_log_return = np.log(group["close"].shift(-window) / group["close"]).replace([np.inf, -np.inf], np.nan).dropna()
    if rolling_log_return.empty: return None
    years = window / 252.0; cagr = float(np.exp(rolling_log_return.median() / years) - 1.0); cagr_low = float(np.exp(rolling_log_return.quantile(0.10) / years) - 1.0); cagr_high = float(np.exp(rolling_log_return.quantile(0.90) / years) - 1.0); latest = group.iloc[-1]; price = float(latest["close"]); requested_years = sessions / 252.0
    predicted_price = price * ((1 + cagr) ** requested_years); low_price = price * ((1 + cagr_low) ** requested_years); high_price = price * ((1 + cagr_high) ** requested_years); exact_history = available > sessions
    return {"symbol": str(latest["symbol"]), "horizon": horizon, "horizon_sessions": sessions, "forecast_type": "scenario", "prediction_date": pd.Timestamp(latest["date"]).date().isoformat(), "target_date": _next_trading_date(latest["date"], sessions).date().isoformat(), "predicted_return": float(predicted_price / price - 1), "predicted_price": float(predicted_price), "lower_return": float(low_price / price - 1), "upper_return": float(high_price / price - 1), "lower_price": float(low_price), "upper_price": float(high_price), "metrics": {"historical_window_sessions": int(window), "historical_window_years": float(years), "historical_rolling_cagr_median": cagr, "historical_rolling_cagr_p10": cagr_low, "historical_rolling_cagr_p90": cagr_high, "data_quality": "sufficient_history" if exact_history else "proxy_from_longest_available_history", "scenario_warning": "Long-term scenario, not a precise price prediction."}}

def generate_scenario_predictions(frame):
    output = []
    for _, group in frame.groupby("symbol"):
        for horizon in SCENARIO_HORIZONS:
            result = _scenario_for_symbol(group, horizon, HORIZONS[horizon]["sessions"])
            if result: output.append(result)
    return output

def _load_stock_ids():
    rows = supabase.table("stocks").select("id,symbol").in_("symbol", SYMBOLS).execute().data or []
    return {str(row["symbol"]).upper(): row["id"] for row in rows}

def publish_predictions(rows, stock_ids):
    payload = []
    for row in rows:
        stock_id = stock_ids.get(str(row["symbol"]).upper())
        if stock_id is None: continue
        payload.append({"stock_id": stock_id, "symbol": str(row["symbol"]).upper(), "horizon": row["horizon"], "horizon_sessions": row["horizon_sessions"], "forecast_type": row["forecast_type"], "prediction_date": row["prediction_date"], "target_date": row["target_date"], "predicted_return": row["predicted_return"], "predicted_price": row["predicted_price"], "lower_return": row.get("lower_return"), "upper_return": row.get("upper_return"), "lower_price": row.get("lower_price"), "upper_price": row.get("upper_price"), "model_name": "FinBERT+TFT-v2", "metrics": row.get("metrics", {})})
    for start in range(0, len(payload), 50): supabase.table("predictions").upsert(payload[start:start + 50], on_conflict="stock_id,prediction_date,target_date,model_name,horizon").execute()
    print(f"Published {len(payload)} horizon forecasts."); return len(payload)

def train_models(requested_horizons=None):
    seed_everything(); frame = build_frame(load_prices(), load_sentiment()); requested = requested_horizons or list(HORIZONS); stock_ids = _load_stock_ids(); all_predictions = []; summary = {}
    for horizon in requested:
        spec = HORIZONS[horizon]
        if spec["type"] == "scenario":
            rows = [r for r in generate_scenario_predictions(frame) if r["horizon"] == horizon]; all_predictions.extend(rows); summary[horizon] = {"type": "scenario", "published_candidates": len(rows)}; continue
        model, training, target_frame, metrics = train_one_horizon(frame, horizon, spec["sessions"]); current = _predict_current_tft(model, training, target_frame, horizon, spec["sessions"]); all_predictions.extend(current); summary[horizon] = {"type": "model", "published_candidates": len(current), "metrics": metrics}
    published = publish_predictions(all_predictions, stock_ids); manifest = {"model_name": "FinBERT+TFT-v2", "generated_at_utc": datetime.now(tz=ZoneInfo("UTC")).isoformat(), "horizons": summary, "published_rows": published, "architecture": {"1d_to_1y": "direct TFT targets; no recursive compounding", "5y_to_20y": "historical rolling-CAGR scenario model", "sentiment": "FinBERT aggregate features for short/medium horizons", "validation": "chronological 70/15/15 split per direct TFT horizon"}}
    (ARTIFACTS / "manifest.json").write_text(json.dumps(manifest, indent=2)); print(json.dumps(manifest, indent=2)); return manifest

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("stage", choices=["finbert", "tft", "all"]); parser.add_argument("--horizons", nargs="+", choices=list(HORIZONS), help="Optional subset, e.g. --horizons 1d 7d 1m."); args = parser.parse_args()
    if args.stage in ("finbert", "all"): score_finbert()
    if args.stage in ("tft", "all"): train_models(args.horizons)

if __name__ == "__main__": main()
