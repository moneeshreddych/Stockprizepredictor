from typing import Any, Dict, List, Optional
from src.database.supabase_client import supabase
from src.logging_config import logger

class NewsRepository:
    """Lightweight repository for Supabase news_articles table operations."""

    @staticmethod
    def get_news(page: int = 1, limit: int = 100) -> List[Dict[str, Any]]:
        start = (page - 1) * limit
        end = start + limit - 1
        try:
            response = (
                supabase.table("news_articles")
                .select("symbol,title,description,source,url,published_at,source_api,image_url")
                .order("published_at", desc=True)
                .range(start, end)
                .execute()
            )
            return response.data or []
        except Exception as exc:
            logger.error("Failed to fetch news from database: %s", exc)
            return []

    @staticmethod
    def get_news_for_symbol(symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            response = (
                supabase.table("news_articles")
                .select("id,symbol,title,description,url,published_at,image_url")
                .eq("symbol", symbol)
                .order("published_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data or []
        except Exception as exc:
            logger.error("Failed to fetch news for symbol %s: %s", symbol, exc)
            return []

    @staticmethod
    def upsert_articles(records: List[Dict[str, Any]]) -> int:
        if not records:
            return 0
        try:
            response = (
                supabase.table("news_articles")
                .upsert(records, on_conflict="url", ignore_duplicates=True)
                .execute()
            )
            return len(response.data or [])
        except Exception as exc:
            logger.error("Error upserting news articles: %s", exc)
            return 0
