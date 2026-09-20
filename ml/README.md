# BullInsights ML training and prediction

BullInsights uses a two-stage production pipeline:

1. **FinBERT** (ProsusAI/finbert) scores financial news as positive/neutral/negative and stores the probabilities in `sentiment_scores`.
2. **Temporal Fusion Transformer (TFT)** learns horizon-specific stock-return distributions from a 60-session encoder containing OHLCV/technical features and aggregated FinBERT sentiment.

The current model name published to Supabase is **FinBERT+TFT-v2**.

## Forecast horizons

| Horizon | Sessions | Method |
|---|---:|---|
| 1d | 1 | TFT quantile forecast |
| 7d | 5 | TFT quantile forecast |
| 1m | 21 | TFT quantile forecast |
| 6m | 126 | TFT quantile forecast |
| 1y | 252 | TFT quantile forecast |
| 5y | 1260 | CAGR/volatility scenario |
| 10y | 2520 | CAGR/volatility scenario |
| 20y | 5040 | CAGR/volatility scenario |

The 1d–1y horizons are actual TFT model outputs with P10/P50/P90 return estimates. The 5y–20y values are explicitly marked as scenario forecasts; the system does not extrapolate a one-day neural forecast for decades.

## Setup

Use a GPU machine such as Google Colab, Kaggle, or a local CUDA environment for training. Render intentionally does not install the heavy ML stack.

    pip install -r requirements-ml.txt

Set:

    SUPABASE_URL=...
    SUPABASE_SECRET_KEY=...

Run the Supabase migration **before the first v2 publication**:

    database/migrate_ml.sql

The migration adds horizon, quantile/scenario fields, and the v2 upsert key.

## Train and publish

Run FinBERT first, then train the TFT horizons:

    python -m ml.pipeline finbert
    python -m ml.pipeline tft --horizons 1d 7d 1m 6m 1y

Or run both stages:

    python -m ml.pipeline all --horizons 1d 7d 1m 6m 1y

The pipeline:

- loads all configured stock OHLCV history from stock_prices;
- scores recent news with FinBERT;
- builds technical and sentiment features;
- uses chronological training/validation boundaries;
- trains one TFT per short/medium horizon;
- performs inference using the latest 60-session encoder;
- publishes P10/P50/P90 forecasts to predictions;
- publishes separate long-horizon scenario forecasts;
- writes checkpoint and training metadata under artifacts/ml/.

PyTorch Forecasting documents the workflow of creating inference datasets from the training dataset and loading trained checkpoints for prediction. citeturn0search0turn0search6

## GitHub Actions

A manual workflow is available at:

    .github/workflows/ml-pipeline.yml

In GitHub:

**Actions → Train ML Predictions → Run workflow**

The workflow accepts the TFT horizons and maximum epoch count, uses the Supabase secrets, and publishes predictions directly to the database. Standard GitHub-hosted runners are CPU-only, so GPU training is preferable for the initial full training run.

## Prediction API

The Flask API now reads FinBERT+TFT-v2:

    GET /api/predictions
    GET /api/predictions?symbol=AAPL
    GET /api/predictions?horizon=1d
    GET /api/predictions?symbol=AAPL&horizon=1d

The frontend groups the returned rows by stock and horizon.

## Important

A checkpoint file existing in Git does **not** by itself create predictions. The model must be trained against the current Supabase data and the resulting forecast rows must be published to predictions. The API only serves published database forecasts.

This is a research forecasting system, not a guarantee of future market returns or investment advice.
