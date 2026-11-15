"""
Core Caching Module for External Aerospace Data Feeds
Provides thread-safe, async-safe in-memory caching with TTL, freshness status,
and graceful stale fallback during upstream outages.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Generic, Optional, Tuple, TypeVar
import asyncio

T = TypeVar("T")


class CacheStatus(str, Enum):
    """Indicates whether a response is live, freshly cached, or stale."""
    LIVE = "LIVE"
    CACHED = "CACHED"
    STALE = "STALE"


class CacheEntry(Generic[T]):
    """Holds a cached value alongside its temporal metadata."""

    def __init__(
        self,
        value: T,
        ttl_seconds: float,
        source_timestamp: Optional[datetime] = None,
    ):
        now = datetime.now(timezone.utc)
        self.value = value
        self.created_at = now
        self.ttl_seconds = ttl_seconds
        self.expires_at = datetime.fromtimestamp(
            now.timestamp() + ttl_seconds, tz=timezone.utc
        )
        self.source_timestamp = source_timestamp or now

    @property
    def is_expired(self) -> bool:
        """Returns True if current time has exceeded the configured TTL."""
        return datetime.now(timezone.utc) > self.expires_at


class AsyncCacheManager:
    """
    In-memory async cache with TTL enforcement, bounded capacity, FIFO/expired eviction,
    hit/miss metrics, and fallback to stale data when upstream requests fail.
    """

    def __init__(
        self,
        default_ttl_seconds: float = 300.0,
        max_entries: int = 1000,
    ) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self.max_entries = max(10, max_entries)
        self._store: Dict[str, CacheEntry[Any]] = {}
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0
        self.stale_hits = 0
        self.evictions = 0

    async def get(
        self, key: str, allow_stale: bool = False
    ) -> Tuple[Optional[Any], CacheStatus, Optional[datetime]]:
        """
        Retrieves an item from cache.

        Returns:
            (value, CacheStatus, retrieved_at) or (None, CacheStatus.LIVE, None) if miss.
        """
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None, CacheStatus.LIVE, None

            if not entry.is_expired:
                self.hits += 1
                return entry.value, CacheStatus.CACHED, entry.created_at

            if allow_stale:
                self.stale_hits += 1
                return entry.value, CacheStatus.STALE, entry.created_at

            self.misses += 1
            return None, CacheStatus.LIVE, None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
        source_timestamp: Optional[datetime] = None,
    ) -> None:
        """Stores an item in the cache with the given TTL, evicting if capacity is reached."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        entry = CacheEntry(
            value=value,
            ttl_seconds=ttl,
            source_timestamp=source_timestamp,
        )
        async with self._lock:
            if key not in self._store and len(self._store) >= self.max_entries:
                # Eviction policy: first try to purge an expired entry
                evicted_key = None
                for k, v in self._store.items():
                    if v.is_expired:
                        evicted_key = k
                        break
                # If no expired entries, evict the oldest entry (FIFO)
                if not evicted_key:
                    evicted_key = next(iter(self._store))
                del self._store[evicted_key]
                self.evictions += 1

            self._store[key] = entry

    async def invalidate(self, key: str) -> bool:
        """Removes a specific key from the cache."""
        async with self._lock:
            return self._store.pop(key, None) is not None

    async def clear(self) -> None:
        """Clears all entries and resets metrics."""
        async with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0
            self.stale_hits = 0
            self.evictions = 0

    async def size(self) -> int:
        """Returns the number of stored entries."""
        async with self._lock:
            return len(self._store)
