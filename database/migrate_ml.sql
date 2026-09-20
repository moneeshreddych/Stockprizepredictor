-- ML database migration for FinBERT + TFT v2.
-- Run once in the Supabase SQL editor before publishing predictions.

CREATE UNIQUE INDEX IF NOT EXISTS uq_sentiment_scores_article_id
ON public.sentiment_scores(article_id);

CREATE INDEX IF NOT EXISTS idx_sentiment_scores_symbol
ON public.sentiment_scores(symbol);

-- Multi-horizon prediction metadata.
ALTER TABLE public.predictions
    ADD COLUMN IF NOT EXISTS horizon VARCHAR(20);

ALTER TABLE public.predictions
    ADD COLUMN IF NOT EXISTS horizon_sessions INTEGER;

ALTER TABLE public.predictions
    ADD COLUMN IF NOT EXISTS forecast_type VARCHAR(30);

ALTER TABLE public.predictions
    ADD COLUMN IF NOT EXISTS lower_return NUMERIC(10, 6);

ALTER TABLE public.predictions
    ADD COLUMN IF NOT EXISTS upper_return NUMERIC(10, 6);

ALTER TABLE public.predictions
    ADD COLUMN IF NOT EXISTS lower_price NUMERIC(14, 4);

ALTER TABLE public.predictions
    ADD COLUMN IF NOT EXISTS upper_price NUMERIC(14, 4);

UPDATE public.predictions
SET horizon = CASE
    WHEN target_date <= prediction_date + 2 THEN '1d'
    WHEN target_date <= prediction_date + 10 THEN '7d'
    WHEN target_date <= prediction_date + 45 THEN '1m'
    WHEN target_date <= prediction_date + 200 THEN '6m'
    WHEN target_date <= prediction_date + 500 THEN '1y'
    WHEN target_date <= prediction_date + 2000 THEN '5y'
    WHEN target_date <= prediction_date + 4000 THEN '10y'
    ELSE '20y'
END
WHERE horizon IS NULL;

UPDATE public.predictions
SET horizon_sessions = CASE horizon
    WHEN '1d' THEN 1
    WHEN '7d' THEN 5
    WHEN '1m' THEN 21
    WHEN '6m' THEN 126
    WHEN '1y' THEN 252
    WHEN '5y' THEN 1260
    WHEN '10y' THEN 2520
    WHEN '20y' THEN 5040
    ELSE NULL
END
WHERE horizon_sessions IS NULL;

UPDATE public.predictions
SET forecast_type = 'legacy'
WHERE forecast_type IS NULL;

ALTER TABLE public.predictions
    ALTER COLUMN horizon SET DEFAULT '1d';

ALTER TABLE public.predictions
    ALTER COLUMN horizon SET NOT NULL;

ALTER TABLE public.predictions
    DROP CONSTRAINT IF EXISTS unique_stock_pred_target;

ALTER TABLE public.predictions
    ADD CONSTRAINT unique_stock_pred_target_horizon
    UNIQUE (stock_id, prediction_date, target_date, model_name, horizon);

CREATE INDEX IF NOT EXISTS idx_predictions_model_horizon_target
ON public.predictions(model_name, horizon, target_date DESC);

CREATE INDEX IF NOT EXISTS idx_predictions_symbol_horizon
ON public.predictions(symbol, horizon, target_date DESC);
