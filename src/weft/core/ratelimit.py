"""Per-key async token-bucket rate limiter.

Free sources throttle hard, so every module call passes through a bucket keyed by the
module name. Each bucket refills at a steady rate up to a small burst capacity;
``acquire`` waits until a token is available. This matters more here than it would
with paid APIs.
"""
from __future__ import annotations

import asyncio
import time


class _Bucket:
    __slots__ = ("rate", "capacity", "tokens", "updated")

    def __init__(self, rate: float, capacity: float):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.updated = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now


class TokenBucketRateLimiter:
    """One bucket per key. ``rate`` is tokens per second; ``capacity`` the burst size."""

    def __init__(self, *, rate: float = 2.0, capacity: float = 4.0):
        self._rate = rate
        self._capacity = capacity
        self._buckets: dict[str, _Bucket] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _bucket(self, key: str) -> _Bucket:
        if key not in self._buckets:
            self._buckets[key] = _Bucket(self._rate, self._capacity)
            self._locks[key] = asyncio.Lock()
        return self._buckets[key]

    async def acquire(self, key: str) -> None:
        bucket = self._bucket(key)
        async with self._locks[key]:
            while True:
                bucket._refill()
                if bucket.tokens >= 1.0:
                    bucket.tokens -= 1.0
                    return
                deficit = 1.0 - bucket.tokens
                await asyncio.sleep(deficit / bucket.rate)


class NoopRateLimiter:
    """A limiter that never waits. Used in tests."""

    async def acquire(self, key: str) -> None:  # noqa: D401
        return None
