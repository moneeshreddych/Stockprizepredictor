-- Multi-horizon ML database migration for FinBERT + direct TFT/scenario forecasts.
-- Run once in the Supabase SQL editor.

CREATE UNIQUE INDEX IF NOT EXISTS uq_sentiment_scores_article_id
ON public.sentiment_scores(article_id);

CREATE INDEX IF NOT EXISTS idx_sentiment_scores_symbol
ON public.sentiment_scores(symbol);

ALTER TABLE public.predictions
  ADD COLUMN IF NOT EXISTS horizon text,
  ADD COLUMN IF NOT EXISTS horizon_sessions integer,
  ADD COLUMN IF NOT EXISTS forecast_type text,
  ADD COLUMN IF NOT EXISTS lower_return double precision,
  ADD COLUMN IF NOT EXISTS upper_return double precision,
  ADD COLUMN IF NOT EXISTS lower_price double precision,
  ADD COLUMN IF NOT EXISTS upper_price double precision;

UPDATE public.predictions
SET horizon = COALESCE(
  horizon,
  CASE
    WHEN target_date - prediction_date <= 2 THEN '1d'
    WHEN target_date - prediction_date <= 10 THEN '7d'
    WHEN target_date - prediction_date <= 45 THEN '1m'
    WHEN target_date - prediction_date <= 200 THEN '6m'
    WHEN target_date - prediction_date <= 500 THEN '1y'
    WHEN target_date - prediction_date <= 2000 THEN '5y'
    WHEN target_date - prediction_date <= 4000 THEN '10y'
    ELSE '20y'
  END
);

UPDATE public.predictions
SET horizon_sessions = COALESCE(
  horizon_sessions,
  CASE horizon
    WHEN '1d' THEN 1
    WHEN '7d' THEN 5
    WHEN '1m' THEN 21
    WHEN '6m' THEN 126
    WHEN '1y' THEN 252
    WHEN '5y' THEN 1260
    WHEN '10y' THEN 2520
    WHEN '20y' THEN 5040
  END
);

UPDATE public.predictions
SET forecast_type = COALESCE(forecast_type, 'model');

CREATE INDEX IF NOT EXISTS idx_predictions_horizon
ON public.predictions(model_name, horizon, target_date DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_predictions_multihorizon
ON public.predictions(stock_id, prediction_date, target_date, model_name, horizon);
