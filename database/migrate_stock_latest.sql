-- Normalize the market quote table used by the website.
ALTER TABLE public.stock_latest
    ADD COLUMN IF NOT EXISTS previous_close DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS price_type TEXT DEFAULT 'previous_close';

UPDATE public.stock_latest
SET price_type = COALESCE(price_type, 'previous_close');

-- The collector writes UTC timestamps for every successful quote.
CREATE INDEX IF NOT EXISTS stock_latest_timestamp_idx
    ON public.stock_latest (timestamp DESC);
