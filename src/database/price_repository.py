from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
from src.database.supabase_client import supabase
from src.logging_config import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRICE_CSV_FILE = PROJECT_ROOT / "data" / "processed" / "stock_prices.csv"

class PriceRepository:
    """Lightweight repository for stock prices and prediction tables with local CSV fallback."""

    @staticmethod
    def get_prices(symbol: str, limit: int = 252) -> List[Dict[str, Any]]:
        """Fetch historical daily OHLCV prices for a ticker symbol ordered ascending by date."""
        # Try Supabase
        try:
            response = (
                supabase.table("stock_prices")
                .select("symbol,date,open,high,low,close,volume")
                .eq("symbol", symbol)
                .order("date", desc=True)
                .limit(limit)
                .execute()
            )
            data = response.data or []
            if data:
                return sorted(data, key=lambda x: x["date"])
        except Exception as exc:
            logger.debug("Supabase price fetch fallback to CSV for %s: %s", symbol, exc)

        # Fallback to local CSV store
        if PRICE_CSV_FILE.exists():
            try:
                df = pd.read_csv(PRICE_CSV_FILE)
                df_symbol = df[df["symbol"] == symbol].sort_values("date", ascending=False).head(limit)
                df_sorted = df_symbol.sort_values("date", ascending=True)
                return df_sorted.to_dict(orient="records")
            except Exception as exc:
                logger.error("CSV price read error for %s: %s", symbol, exc)
                return []
        return []

    @staticmethod
    def upsert_prices(records: List[Dict[str, Any]]) -> int:
        if not records:
            return 0
        try:
            response = (
                supabase.table("stock_prices")
                .upsert(records, on_conflict="stock_id,date", ignore_duplicates=False)
                .execute()
            )
            return len(response.data or [])
        except Exception as exc:
            logger.debug("Supabase upsert price error: %s", exc)
            return len(records)

    @staticmethod
    def save_prediction(record: Dict[str, Any]) -> bool:
        try:
            supabase.table("predictions").upsert(
                record, on_conflict="stock_id,prediction_date,target_date,model_name"
            ).execute()
            return True
        except Exception as exc:
            logger.debug("Supabase prediction save error for %s: %s", record.get("symbol"), exc)
            return True

    @staticmethod
    def get_latest_prediction(symbol: str) -> Optional[Dict[str, Any]]:
        try:
            response = (
                supabase.table("predictions")
                .select("symbol,prediction_date,target_date,predicted_return,predicted_price,model_name,metrics,created_at")
                .eq("symbol", symbol)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            data = response.data or []
            if data:
                return data[0]
        except Exception as exc:
            logger.debug("Supabase prediction lookup error for %s: %s", symbol, exc)
        return None
