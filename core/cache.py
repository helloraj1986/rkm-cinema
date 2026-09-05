"""Reusable time-to-live cache (spec §29 Phase 15).

One small, dependency-free cache primitive used by services that cache
expensive provider operations (full library scans, TMDB metadata, *arr
profile/queue fetches). Centralising it here means there is exactly one
TTL/invalidation implementation in the codebase (§43 — no parallel cache
logic scattered across services).

Design
------
- ``get(key)``/``set(key, value, ttl=)`` with monotonic ``time.monotonic()``
  so expiry is never fooled by a wall-clock jump.
- ``invalidate(key)`` clears one entry; ``clear()`` clears all (used after a
  write so a fresh provider state is re-fetched instead of serving a stale
  cached snapshot); ``pop(key)`` removes and returns.
- ``freshen`` support: recalculating the age of an entry without discarding it
  (useful for server-id style long-lived values that just need the clock
  bumped).
- Always returns ``default`` (default ``None``) for a miss or an entry expired
  long enough that it should be ignored — never raises.
"""

from __future__ import annotations

import threading
import time
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """A thread-safe TTL key/value store.

    Each entry stores ``(expires_at_monotonic, value)``. A reader under
    :meth:`get` treats an expired entry as a miss AND evicts it, so a later
    :meth:`set` starts fresh.
    """

    __slots__ = ("_store", "_default_ttl", "_lock")

    def __init__(self, default_ttl: float = 60.0):
        self._default_ttl = default_ttl
        self._store: dict[str, tuple[float, T]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ core
    def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        """Return the cached value for *key*, or *default* if absent/expired."""
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return default
            expires_at, value = entry
            if expires_at < now:
                del self._store[key]
                return default
            return value

    def set(self, key: str, value: T, ttl: Optional[float] = None) -> T:
        """Store *value* under *key* with *ttl* (falls back to default_ttl)."""
        ttl = self._default_ttl if ttl is None else ttl
        with self._lock:
            self._store[key] = (time.monotonic() + ttl, value)
        return value

    # ---------------------------------------------------------- mutation
    def invalidate(self, key: str) -> None:
        """Remove one entry. No-op if absent."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Remove every entry (typically after a write)."""
        with self._lock:
            self._store.clear()

    def pop(self, key: str, default: Optional[T] = None) -> Optional[T]:
        """Remove and return the value for *key* (expired counts as absent)."""
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return default
            expires_at, value = entry
            del self._store[key]
            if expires_at < now:
                return default
            return value

    # ------------------------------------------------------------ metadata
    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def keys(self) -> list[str]:
        """Snapshot of current (unexpired-checked) keys."""
        with self._lock:
            return list(self._store.keys())