import time
from typing import Any


class TTLCache:
    """Cache em memória com expiração por TTL e tamanho máximo.

    Ao passar de `max_entries`, descarta as entradas mais antigas: sem o teto,
    um worker de longa duração acumularia uma entrada por consulta distinta.
    """

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 1000):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
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
        self._cache.pop(key, None)
        self._cache[key] = (time.monotonic(), value)
        while len(self._cache) > self.max_entries:
            del self._cache[next(iter(self._cache))]

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)
