from __future__ import annotations

import logging
import time

import requests

from core.config import Config

logger = logging.getLogger(__name__)


class CollectorError(RuntimeError):
    pass


class BaseCollector:
    """Throttled, retrying HTTP client shared by all collectors."""

    def __init__(self, config: Config):
        self.cfg = config
        self.http = config.http
        self.session = requests.Session()
        self.session.headers["User-Agent"] = self.http.user_agent
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self.http.request_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def fetch(self, url: str, params: dict | None = None, **kwargs) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.http.max_retries + 1):
            self._throttle()
            try:
                resp = self.session.get(
                    url, params=params, timeout=self.http.request_timeout, **kwargs
                )
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "fetch failed (attempt %d/%d): %s -> %s", attempt + 1, self.http.max_retries + 1, url, exc
                )
                if attempt < self.http.max_retries:
                    time.sleep(min(2 ** attempt * 2, 30))
        raise CollectorError(f"Failed to fetch {url}: {last_error}") from last_error

    def fetch_json(self, url: str, params: dict | None = None, **kwargs) -> dict | list:
        resp = self.fetch(url, params=params, **kwargs)
        try:
            return resp.json()
        except ValueError as exc:
            raise CollectorError(f"Invalid JSON from {url}") from exc
