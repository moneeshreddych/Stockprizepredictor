# BullInsights ML training

The production prediction pipeline is now split into two stages:

1. **FinBERT** (`ProsusAI/finbert`) scores each financial-news article with positive/negative/neutral probabilities and a composite score `positive - negative`.
2. **Temporal Fusion Transformer (TFT)** forecasts the next trading-session log return from 60 trading days of OHLCV-derived features plus aggregated FinBERT sentiment.

## Setup

Use a GPU environment (Google Colab, Kaggle, or a local CUDA machine) for training. The Render web service intentionally does **not** install the heavy ML stack.

```bash
pip install -r requirements-ml.txt
```

Set the same Supabase variables used by the application:

```text
SUPABASE_URL=...
SUPABASE_SECRET_KEY=...
```

Run the database migration once:

```text
database/migrate_ml.sql
```

Then run:

```bash
python -m ml.pipeline all
```

or independently:

```bash
python -m ml.pipeline finbert
python -m ml.pipeline tft
```

The pipeline reads the historical `stock_prices` and `news_articles` tables, writes FinBERT results to `sentiment_scores`, trains TFT with chronological splits, evaluates on a held-out test period, and publishes the latest one-session probabilistic forecast into `predictions` as `FinBERT+TFT-v1`.

## Model design

- 60-session encoder window
- 70/15/15 chronological train/validation/test split
- No random time-series split
- Quantile loss with P10/P50/P90 outputs
- Group normalization by stock symbol
- OHLCV, 1/5/20-day returns, SMA ratios, RSI, MACD, ATR, volatility, volume z-score, market-relative return and FinBERT sentiment
- Early stopping, learning-rate monitoring and gradient clipping
- Test MAE, RMSE and directional accuracy are stored with the forecast

The model is a research forecast. It is not a guarantee of future market returns.
