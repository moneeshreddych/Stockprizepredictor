"""Redis-backed JSON cache with an in-process TTL fallback."""
from __future__ import annotations
import json, os, time
from typing import Any
try:
    import redis
except ImportError:
    redis = None

_MEMORY: dict[str, tuple[float, Any]] = {}
_CLIENT = None
_INITIALIZED = False

def _client():
    global _CLIENT, _INITIALIZED
    if _INITIALIZED:
        return _CLIENT
    _INITIALIZED = True
    url = os.getenv("REDIS_URL", "").strip()
    if not url or redis is None:
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        _CLIENT = client
    except Exception:
        _CLIENT = None
    return _CLIENT

def backend() -> str:
    return "redis" if _client() is not None else "memory"

def get_json(key: str) -> Any | None:
    client = _client()
    if client is not None:
        try:
            value = client.get(key)
            return json.loads(value) if value else None
        except Exception:
            pass
    item = _MEMORY.get(key)
    if item is None:
        return None
    expires_at, value = item
    if expires_at <= time.time():
        _MEMORY.pop(key, None)
        return None
    return value

def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    client = _client()
    if client is not None:
        try:
            client.setex(key, ttl_seconds, json.dumps(value, separators=(",", ":")))
            return
        except Exception:
            pass
    _MEMORY[key] = (time.time() + ttl_seconds, value)
