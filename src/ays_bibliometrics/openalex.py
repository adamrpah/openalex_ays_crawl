from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .cache import ResponseCache
from .config import OpenAlexConfig
from .logging import bind
from .util import cache_key

logger = logging.getLogger(__name__)


class OpenAlexClient:
    def __init__(self, config: OpenAlexConfig, cache: ResponseCache) -> None:
        self.config = config
        self.cache = cache
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self._user_agent()})

    def _user_agent(self) -> str:
        email = self.config.polite_pool_email or "unset@example.com"
        return f"ays-bibliometrics/0.1 (mailto:{email})"

    def _request_params(self, params: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(params or {})
        if self.config.polite_pool_email:
            merged.setdefault("mailto", self.config.polite_pool_email)
        if self.config.api_key:
            merged.setdefault("api_key", self.config.api_key)
        return merged

    def _safe_params(self, params: dict[str, Any]) -> dict[str, Any]:
        safe = dict(params)
        if "api_key" in safe:
            safe["api_key"] = "***REDACTED***"
        return safe

    @retry(
        retry=retry_if_exception_type((requests.RequestException, ValueError)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def get(self, endpoint: str, params: dict[str, Any] | None = None, use_cache: bool = True) -> dict:
        url = f"{self.config.base_url}/{endpoint.lstrip('/')}"
        request_params = self._request_params(params)
        safe_params = self._safe_params(request_params)
        key = cache_key(url, request_params)
        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                logger.debug("openalex_cache_hit", extra=bind(url=url, params=safe_params))
                return cached

        logger.info("openalex_request", extra=bind(url=url, params=safe_params))
        response = self.session.get(url, params=request_params, timeout=60)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "30"))
            logger.warning("openalex_rate_limited", extra=bind(wait_seconds=retry_after))
            time.sleep(retry_after)
        response.raise_for_status()
        payload = response.json()
        self.cache.set(key, payload)
        time.sleep(self.config.rate_limit_seconds)
        return payload

    def search_authors(self, query: str, per_page: int = 5) -> list[dict[str, Any]]:
        payload = self.get("authors", {"search": query, "per-page": per_page})
        return list(payload.get("results", []))

    def iter_works_for_author(self, author_id: str) -> Iterator[dict[str, Any]]:
        cursor = "*"
        while cursor:
            payload = self.get(
                "works",
                {
                    "filter": f"author.id:{author_id}",
                    "per-page": self.config.per_page,
                    "cursor": cursor,
                },
            )
            yield from payload.get("results", [])
            cursor = payload.get("meta", {}).get("next_cursor")
            if not cursor:
                break

    def iter_institution_authors(self, institution_id: str) -> Iterator[dict[str, Any]]:
        cursor = "*"
        while cursor:
            payload = self.get(
                "authors",
                {
                    "filter": f"last_known_institution.id:{institution_id}",
                    "per-page": self.config.per_page,
                    "cursor": cursor,
                },
            )
            yield from payload.get("results", [])
            cursor = payload.get("meta", {}).get("next_cursor")
            if not cursor:
                break
