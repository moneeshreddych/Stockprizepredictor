-- ML database migration for FinBERT + TFT.
-- Run once in the Supabase SQL editor.

CREATE UNIQUE INDEX IF NOT EXISTS uq_sentiment_scores_article_id
ON public.sentiment_scores(article_id);

CREATE INDEX IF NOT EXISTS idx_sentiment_scores_symbol
ON public.sentiment_scores(symbol);

CREATE INDEX IF NOT EXISTS idx_predictions_model_target
ON public.predictions(model_name, target_date DESC);
