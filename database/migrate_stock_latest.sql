-- Run this once in Supabase SQL Editor for an existing project.
CREATE TABLE IF NOT EXISTS public.stock_latest (
    symbol TEXT PRIMARY KEY,
    price DOUBLE PRECISION NOT NULL,
    change DOUBLE PRECISION,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- If stock_latest was created earlier without the change column,
-- add it without affecting existing rows.
ALTER TABLE public.stock_latest
ADD COLUMN IF NOT EXISTS change DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_stock_latest_timestamp
ON public.stock_latest(timestamp DESC);
