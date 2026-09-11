def parse_price_response(symbol: str, data: dict) -> dict:
    """Parse Twelve Data price response.

    Expected format:
    {
        "price": "123.45",
        "datetime": "2024-01-01 12:00:00",
        ...
    }
    Returns a dict with keys: symbol, price (float), timestamp (ISO string).
    """
    price_str = data.get("price")
    timestamp = data.get("datetime") or data.get("timestamp")
    try:
        price = float(price_str) if price_str is not None else None
    except Exception:
        price = None
    return {"symbol": symbol, "price": price, "timestamp": timestamp}
