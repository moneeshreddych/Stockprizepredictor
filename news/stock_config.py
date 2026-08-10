
# ============================================================
# STOCK CONFIGURATION
#  20 NASDAQ STOCKS
# ============================================================

# ============================================================
# NASDAQ STOCKS
# ============================================================

NASDAQ_STOCKS = {

    "NVDA": {
        "name": "NVIDIA",
        "exchange": "NASDAQ",
        "symbol": "NVDA",
        "news_symbol": "NVDA",
        "yahoo": "NVDA"
    },

    "AAPL": {
        "name": "Apple",
        "exchange": "NASDAQ",
        "symbol": "AAPL",
        "news_symbol": "AAPL",
        "yahoo": "AAPL"
    },

    "MSFT": {
        "name": "Microsoft",
        "exchange": "NASDAQ",
        "symbol": "MSFT",
        "news_symbol": "MSFT",
        "yahoo": "MSFT"
    },

    "AMZN": {
        "name": "Amazon",
        "exchange": "NASDAQ",
        "symbol": "AMZN",
        "news_symbol": "AMZN",
        "yahoo": "AMZN"
    },

    "GOOGL": {
        "name": "Alphabet Class A",
        "exchange": "NASDAQ",
        "symbol": "GOOGL",
        "news_symbol": "GOOGL",
        "yahoo": "GOOGL"
    },

    "GOOG": {
        "name": "Alphabet Class C",
        "exchange": "NASDAQ",
        "symbol": "GOOG",
        "news_symbol": "GOOG",
        "yahoo": "GOOG"
    },

    "META": {
        "name": "Meta Platforms",
        "exchange": "NASDAQ",
        "symbol": "META",
        "news_symbol": "META",
        "yahoo": "META"
    },

    "AVGO": {
        "name": "Broadcom",
        "exchange": "NASDAQ",
        "symbol": "AVGO",
        "news_symbol": "AVGO",
        "yahoo": "AVGO"
    },

    "TSLA": {
        "name": "Tesla",
        "exchange": "NASDAQ",
        "symbol": "TSLA",
        "news_symbol": "TSLA",
        "yahoo": "TSLA"
    },

    "WMT": {
        "name": "Walmart",
        "exchange": "NASDAQ",
        "symbol": "WMT",
        "news_symbol": "WMT",
        "yahoo": "WMT"
    },

    "COST": {
        "name": "Costco Wholesale",
        "exchange": "NASDAQ",
        "symbol": "COST",
        "news_symbol": "COST",
        "yahoo": "COST"
    },

    "NFLX": {
        "name": "Netflix",
        "exchange": "NASDAQ",
        "symbol": "NFLX",
        "news_symbol": "NFLX",
        "yahoo": "NFLX"
    },

    "AMD": {
        "name": "Advanced Micro Devices",
        "exchange": "NASDAQ",
        "symbol": "AMD",
        "news_symbol": "AMD",
        "yahoo": "AMD"
    },

    "CSCO": {
        "name": "Cisco Systems",
        "exchange": "NASDAQ",
        "symbol": "CSCO",
        "news_symbol": "CSCO",
        "yahoo": "CSCO"
    },

    "ADBE": {
        "name": "Adobe",
        "exchange": "NASDAQ",
        "symbol": "ADBE",
        "news_symbol": "ADBE",
        "yahoo": "ADBE"
    },

    "QCOM": {
        "name": "Qualcomm",
        "exchange": "NASDAQ",
        "symbol": "QCOM",
        "news_symbol": "QCOM",
        "yahoo": "QCOM"
    },

    "INTC": {
        "name": "Intel",
        "exchange": "NASDAQ",
        "symbol": "INTC",
        "news_symbol": "INTC",
        "yahoo": "INTC"
    },

    "AMAT": {
        "name": "Applied Materials",
        "exchange": "NASDAQ",
        "symbol": "AMAT",
        "news_symbol": "AMAT",
        "yahoo": "AMAT"
    },

    "INTU": {
        "name": "Intuit",
        "exchange": "NASDAQ",
        "symbol": "INTU",
        "news_symbol": "INTU",
        "yahoo": "INTU"
    },

    "TXN": {
        "name": "Texas Instruments",
        "exchange": "NASDAQ",
        "symbol": "TXN",
        "news_symbol": "TXN",
        "yahoo": "TXN"
    }
}


# ============================================================
# COMBINED
# ============================================================

ALL_STOCKS = {
    **NASDAQ_STOCKS
}


# ============================================================
# HELPERS
# ============================================================

def get_stock(symbol):
    return ALL_STOCKS.get(symbol)





def get_nasdaq_stocks():
    return NASDAQ_STOCKS


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("========================================")
    print("STOCK CONFIGURATION")
    print("========================================")

    
    print(f"NASDAQ stocks: {len(NASDAQ_STOCKS)}")
    print(f"Total stocks: {len(ALL_STOCKS)}")


    print(get_stock("INFY"))

    print(get_stock("AAPL"))