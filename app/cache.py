"""Caching backends and utilities for FinOps dashboard.

Provides a unified interface supporting an in-memory backend by default and an
optional Redis backend (activated when CACHE_BACKEND=redis and redis-py is
installed). Designed to be lightweight and dependency-optional so the project
does not require Redis for basic usage or tests.

Features:
 - Per-key TTL handling with lazy expiration
 - Max entries enforcement (simple eviction: oldest by insertion time)
 - Decorator to cache function results with custom key generation
 - Namespaced keys for different FinOps data domains
 - Graceful degradation if Redis backend fails (falls back to memory)

NOTE: This code was created with accessibility and reliability considerations
in mind; please still review and test in your environment.
"""

from __future__ import annotations

import time
import threading
import logging
from typing import Any, Callable, Dict, Optional, Tuple
from functools import wraps

from .config import get_settings

logger = logging.getLogger(__name__)


class CacheEntry:
    __slots__ = ("value", "expires_at", "created_at")

    def __init__(self, value: Any, ttl: int):
        now = time.time()
        self.value = value
        self.created_at = now
        self.expires_at = now + ttl if ttl > 0 else float("inf")

    def expired(self) -> bool:
        return time.time() >= self.expires_at


class InMemoryCache:
    """Thread-safe in-memory cache with TTL and max entry enforcement."""

    def __init__(self, max_entries: int):
        self._data: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._max = max_entries

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            if entry.expired():
                self._data.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            if len(self._data) >= self._max:
                # Evict oldest
                oldest_key, _ = min(self._data.items(), key=lambda kv: kv[1].created_at)
                self._data.pop(oldest_key, None)
            self._data[key] = CacheEntry(value, ttl)

    def invalidate(self, prefix: Optional[str] = None) -> int:
        with self._lock:
            if prefix is None:
                removed = len(self._data)
                self._data.clear()
                return removed
            to_remove = [k for k in self._data if k.startswith(prefix)]
            for k in to_remove:
                self._data.pop(k, None)
            return len(to_remove)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            valid = sum(1 for e in self._data.values() if not e.expired())
            return {"entries": len(self._data), "valid": valid, "max": self._max}


class RedisCache:
    """Redis-backed cache wrapper (optional dependency)."""

    def __init__(self, url: str, max_entries: int):
        try:
            import redis  # type: ignore
        except ImportError:  # pragma: no cover - optional path
            raise RuntimeError("redis package not installed; cannot use redis backend")

        self._r = redis.from_url(url)
        self._max = max_entries
        self._prefix = "finops:cache:"

    def _fq(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def get(self, key: str) -> Optional[Any]:  # pragma: no cover (requires redis runtime)
        try:
            data = self._r.get(self._fq(key))
            if data is None:
                return None
            import pickle
            return pickle.loads(data)
        except Exception as e:  # Resilient fallback
            logger.warning("Redis get failed; falling back to miss", extra={"error": str(e)})
            return None

    def set(self, key: str, value: Any, ttl: int) -> None:  # pragma: no cover (requires redis runtime)
        try:
            # Basic max entries enforcement via random sampling of keys
            current = self._r.dbsize()
            if current >= self._max:
                # naive eviction of a few keys
                for k in self._r.scan_iter(f"{self._prefix}*"):
                    self._r.delete(k)
                    break
            import pickle
            self._r.set(self._fq(key), pickle.dumps(value), ex=ttl)
        except Exception as e:
            logger.warning("Redis set failed", extra={"error": str(e)})

    def invalidate(self, prefix: Optional[str] = None) -> int:  # pragma: no cover
        pattern = f"{self._prefix}{prefix}*" if prefix else f"{self._prefix}*"
        count = 0
        for k in self._r.scan_iter(pattern):
            self._r.delete(k)
            count += 1
        return count

    def stats(self) -> Dict[str, Any]:  # pragma: no cover
        return {"approx_db_size": self._r.dbsize(), "max": self._max}


def _build_cache():
    settings = get_settings()
    if settings.cache_backend == "redis" and settings.redis_url:
        try:
            return RedisCache(settings.redis_url, settings.cache_max_entries)
        except Exception as e:  # pragma: no cover - fallback path
            logger.warning(
                "Falling back to in-memory cache due to redis initialization failure",
                extra={"error": str(e)},
            )
    return InMemoryCache(settings.cache_max_entries)


_CACHE = _build_cache()


def cache_key(namespace: str, parts: Tuple[Any, ...]) -> str:
    safe_parts = [str(p) for p in parts]
    return f"{namespace}:" + ":".join(safe_parts)


def cached(namespace: str, ttl_resolver: Callable[[Any], int]):
    """Decorator to cache function results.

    ttl_resolver receives the settings object and returns ttl seconds.
    The wrapped function's cache key is derived from its args+kwargs (basic tuple hash approach).
    """

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            settings = get_settings()
            ttl = ttl_resolver(settings)
            key = cache_key(namespace, (func.__name__, args, tuple(sorted(kwargs.items()))))
            val = _CACHE.get(key)
            if val is not None:
                return val
            result = func(*args, **kwargs)
            try:
                _CACHE.set(key, result, ttl)
            except Exception as e:
                logger.debug("Cache set failed", extra={"error": str(e)})
            return result

        return wrapper

    return decorator


def invalidate_cache(prefix: Optional[str] = None) -> int:
    return _CACHE.invalidate(prefix)


def cache_stats() -> Dict[str, Any]:
    return _CACHE.stats()
