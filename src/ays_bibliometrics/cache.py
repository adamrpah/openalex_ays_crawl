from __future__ import annotations

from pathlib import Path
from typing import Any

from diskcache import Cache


class ResponseCache:
    def __init__(self, cache_dir: Path, namespace: str = "http") -> None:
        self.cache = Cache(str(cache_dir / namespace))

    def get(self, key: str) -> Any | None:
        return self.cache.get(key, default=None)

    def set(self, key: str, value: Any, expire: int | None = None) -> None:
        self.cache.set(key, value, expire=expire)

    def close(self) -> None:
        self.cache.close()

