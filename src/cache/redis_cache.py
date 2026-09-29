"""Small Redis cache adapter with a safe no-Redis fallback.

The application remains functional when REDIS_URL is unset or Redis is unavailable.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

_client = None
_disabled = False


def get_client():
    global _client, _disabled
    if _disabled or redis is None:
        return None
    if _client is None:
        url = os.getenv("REDIS_URL", "").strip()
        if not url:
            _disabled = True
            return None
        try:
            _client = redis.Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
                health_check_interval=30,
            )
            _client.ping()
        except Exception:
            _client = None
            _disabled = True
    return _client


def get_json(key: str) -> Optional[Any]:
    client = get_client()
    if client is None:
        return None
    try:
        value = client.get(key)
        return json.loads(value) if value else None
    except Exception:
        return None


def set_json(key: str, value: Any, ttl: int) -> bool:
    client = get_client()
    if client is None:
        return False
    try:
        client.setex(key, ttl, json.dumps(value, default=str))
        return True
    except Exception:
        return False


def delete(key: str) -> bool:
    client = get_client()
    if client is None:
        return False
    try:
        return bool(client.delete(key))
    except Exception:
        return False
