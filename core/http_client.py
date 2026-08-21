"""Shared HTTP client with caching, retry, and error handling."""
import json
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Optional, Dict
from functools import wraps
import logging

from config.settings import get_config


logger = logging.getLogger(__name__)


class HTTPClient:
    """HTTP client with short-TTL caching, timeout handling, and structured errors."""

    def __init__(self, default_timeout: int = 12, cache_ttl: int = 45):
        self.default_timeout = default_timeout
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple[float, Any]] = {}  # url -> (expiry, data)

    def _make_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "RKM-Cinema/2.0"}
        if extra:
            headers.update(extra)
        return headers

    def _cache_get(self, url: str) -> Optional[Any]:
        now = time.time()
        hit = self._cache.get(url)
        if hit and hit[0] > now:
            logger.debug("Cache HIT: %s", url)
            return hit[1]
        if hit:
            logger.debug("Cache EXPIRED: %s", url)
            del self._cache[url]
        return None

    def _cache_set(self, url: str, data: Any) -> None:
        self._cache[url] = (time.time() + self.cache_ttl, data)
        logger.debug("Cache SET: %s (ttl=%ds)", url, self.cache_ttl)

    def clear_cache(self) -> None:
        """Clear the HTTP cache."""
        self._cache.clear()

    def get(self, url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, str]] = None, timeout: Optional[int] = None, use_cache: bool = False) -> Any:
        """GET request with optional caching and query params."""
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}" if "?" not in url else f"{url}&{query}"

        if use_cache:
            cached = self._cache_get(url)
            if cached is not None:
                return cached

        req = urllib.request.Request(url, headers=self._make_headers(headers))
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.default_timeout) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore") if e.fp else ""
            logger.error("HTTP %d %s: %s", e.code, url, body[:200])
            raise HTTPError(e.code, url, body) from e
        except urllib.error.URLError as e:
            logger.error("URL error %s: %s", url, e.reason)
            raise NetworkError(url, str(e.reason)) from e
        except json.JSONDecodeError as e:
            logger.error("JSON decode error %s: %s", url, e)
            raise ParseError(url, str(e)) from e

        if use_cache:
            self._cache_set(url, data)
        return data

    def post(self, url: str, data: Any, headers: Optional[Dict[str, str]] = None, timeout: Optional[int] = None) -> Any:
        """POST request with JSON body."""
        body = json.dumps(data).encode("utf-8")
        h = self._make_headers(headers)
        h["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.default_timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore") if e.fp else ""
            logger.error("POST HTTP %d %s: %s", e.code, url, body[:200])
            raise HTTPError(e.code, url, body) from e
        except urllib.error.URLError as e:
            logger.error("POST URL error %s: %s", url, e.reason)
            raise NetworkError(url, str(e.reason)) from e
        except json.JSONDecodeError as e:
            logger.error("POST JSON decode error %s: %s", url, e)
            raise ParseError(url, str(e)) from e


class HTTPError(Exception):
    """HTTP error with status code and response body."""
    def __init__(self, status_code: int, url: str, body: str):
        self.status_code = status_code
        self.url = url
        self.body = body
        super().__init__(f"HTTP {status_code} {url}: {body[:200]}")


class NetworkError(Exception):
    """Network-level error (DNS, connection refused, timeout)."""
    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"Network error {url}: {reason}")


class ParseError(Exception):
    """Response parsing error."""
    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"Parse error {url}: {reason}")


def safe(default=None):
    """Decorator: catch exceptions and return default (legacy compatibility)."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.debug("safe() caught %s: %s", type(e).__name__, e)
                return default
        return wrapper
    return decorator


# Singleton instance
_client: Optional[HTTPClient] = None


def get_http_client() -> HTTPClient:
    """Get singleton HTTP client."""
    global _client
    if _client is None:
        _client = HTTPClient()
    return _client


def reset_http_client() -> None:
    """Reset singleton HTTP client (for testing)."""
    global _client
    _client = None