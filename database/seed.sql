-- BullInsights Reference Seed Data (20 Nasdaq Stocks)

INSERT INTO stocks (symbol, name, exchange) VALUES
('NVDA', 'NVIDIA Corporation', 'NASDAQ'),
('AAPL', 'Apple Inc.', 'NASDAQ'),
('MSFT', 'Microsoft Corporation', 'NASDAQ'),
('AMZN', 'Amazon.com Inc.', 'NASDAQ'),
('GOOGL', 'Alphabet Inc. Class A', 'NASDAQ'),
('GOOG', 'Alphabet Inc. Class C', 'NASDAQ'),
('META', 'Meta Platforms Inc.', 'NASDAQ'),
('AVGO', 'Broadcom Inc.', 'NASDAQ'),
('TSLA', 'Tesla Inc.', 'NASDAQ'),
('WMT', 'Walmart Inc.', 'NASDAQ'),
('COST', 'Costco Wholesale Corporation', 'NASDAQ'),
('NFLX', 'Netflix Inc.', 'NASDAQ'),
('AMD', 'Advanced Micro Devices Inc.', 'NASDAQ'),
('CSCO', 'Cisco Systems Inc.', 'NASDAQ'),
('ADBE', 'Adobe Inc.', 'NASDAQ'),
('QCOM', 'QUALCOMM Incorporated', 'NASDAQ'),
('INTC', 'Intel Corporation', 'NASDAQ'),
('AMAT', 'Applied Materials Inc.', 'NASDAQ'),
('INTU', 'Intuit Inc.', 'NASDAQ'),
('TXN', 'Texas Instruments Incorporated', 'NASDAQ')
ON CONFLICT (symbol) DO NOTHING;
