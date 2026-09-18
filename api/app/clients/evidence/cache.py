import time
from typing import Any


class TTLCache:
    """Cache em memória simples com expiração por TTL (Time-To-Live)."""

    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None

        cached_at, value = self._cache[key]
        if time.monotonic() - cached_at > self.ttl_seconds:
            del self._cache[key]
            return None

        return value

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (time.monotonic(), value)

    def clear(self) -> None:
        self._cache.clear()