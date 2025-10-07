import time
import pytest

from app.cache import InMemoryCache, cache_key, cached, invalidate_cache, cache_stats
from app.config import get_settings


def test_inmemory_cache_set_get_and_expire():
    c = InMemoryCache(max_entries=10)
    c.set("k1", 123, ttl=1)
    assert c.get("k1") == 123
    time.sleep(1.1)
    assert c.get("k1") is None  # expired


def test_inmemory_cache_eviction_oldest():
    c = InMemoryCache(max_entries=3)
    c.set("a", 1, ttl=10)
    time.sleep(0.01)  # ensure ordering difference
    c.set("b", 2, ttl=10)
    time.sleep(0.01)
    c.set("c", 3, ttl=10)
    # Fourth insert should evict 'a'
    c.set("d", 4, ttl=10)
    assert c.get("a") is None
    assert c.get("b") == 2
    assert c.get("c") == 3
    assert c.get("d") == 4


def test_cache_key_namespacing():
    k = cache_key("cost", ("func", (1, 2), ()))
    assert k.startswith("cost:")


def test_cached_decorator_basic(monkeypatch):
    # Force small TTL for test
    settings = get_settings()
    monkeypatch.setenv("CACHE_DEFAULT_TTL_SECONDS", "1")
    # Re-fetch settings so changed env var is applied (lru_cache prevents refresh otherwise) - skip complexity here

    calls = {"count": 0}

    @cached("test", ttl_resolver=lambda s: 1)
    def add(x, y):
        calls["count"] += 1
        return x + y

    first = add(2, 3)
    second = add(2, 3)
    assert first == 5 and second == 5
    assert calls["count"] == 1  # second call cached
    time.sleep(1.1)
    third = add(2, 3)
    assert third == 5
    assert calls["count"] == 2  # expired


def test_invalidate_cache_namespace():
    # Use module-level cache via decorator
    calls = {"count": 0}

    @cached("invalidate", ttl_resolver=lambda s: 30)
    def mul(x, y):
        calls["count"] += 1
        return x * y

    mul(2, 5)
    mul(2, 5)
    assert calls["count"] == 1
    removed = invalidate_cache("invalidate")
    assert removed >= 1
    mul(2, 5)
    assert calls["count"] == 2


def test_cache_stats():
    stats = cache_stats()
    assert "max" in stats