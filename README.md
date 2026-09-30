# 📈 Stock Price Predictor

A machine learning project that predicts stock price movements by combining financial news sentiment analysis with historical market data.

## Features
- 📊 Historical stock price analysis
- 📰 Financial news sentiment analysis using FinBERT
- 🤖 Temporal Fusion Transformer (TFT) for time-series forecasting
- 📈 Trend prediction and visualization
- 📉 Performance evaluation using regression metrics

## Tech Stack
- Python
- PyTorch
- FinBERT
- Temporal Fusion Transformer (TFT)
- Pandas
- Scikit-learn
- Matplotlib


## Production completion checklist

The repository now includes the complete application path: market/news collection → Supabase → FinBERT sentiment → horizon-specific TFT/scenario forecasts → prediction persistence → Flask API → Redis caching → frontend. The API falls back to an in-process TTL cache when Redis is unavailable, while Docker Compose provisions Redis for local end-to-end operation.

Before publishing the first v2 forecasts, apply `database/migrate_ml.sql` in Supabase. The ML workflow uses Python 3.12 and the pinned-compatible training stack in `requirements-ml.txt`.
