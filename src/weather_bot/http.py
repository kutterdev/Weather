"""Shared HTTP client with explicit timeouts and retry/backoff.

Every external call must go through here. We need this to behave 24/7 against
free APIs that occasionally rate-limit, time out, or return 5xx.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings

log = logging.getLogger("weather_bot.http")


# Errors we are willing to retry. Others (4xx other than 429) are real bugs.
_RETRY_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)


class RetriableHTTPStatus(Exception):
    """Wraps a 5xx or 429 response so tenacity will retry it."""

    def __init__(self, response: httpx.Response):
        self.response = response
        super().__init__(f"HTTP {response.status_code} from {response.request.url}")


async def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> Any:
    """GET a URL and return parsed JSON, with timeout and exponential backoff."""
    t = timeout or settings.http_timeout_s

    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type(_RETRY_EXCEPTIONS + (RetriableHTTPStatus,)),
        stop=stop_after_attempt(settings.http_max_retries),
        wait=wait_exponential(
            multiplier=settings.http_backoff_min_s,
            max=settings.http_backoff_max_s,
        ),
        reraise=True,
    ):
        with attempt:
            async with httpx.AsyncClient(timeout=t) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                    log.warning(
                        "Retriable HTTP %s on %s, attempt %d",
                        resp.status_code,
                        url,
                        attempt.retry_state.attempt_number,
                    )
                    raise RetriableHTTPStatus(resp)
                resp.raise_for_status()
                return resp.json()


async def get_text(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> str:
    """GET a URL and return raw text, with the same retry policy."""
    t = timeout or settings.http_timeout_s
    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type(_RETRY_EXCEPTIONS + (RetriableHTTPStatus,)),
        stop=stop_after_attempt(settings.http_max_retries),
        wait=wait_exponential(
            multiplier=settings.http_backoff_min_s,
            max=settings.http_backoff_max_s,
        ),
        reraise=True,
    ):
        with attempt:
            async with httpx.AsyncClient(timeout=t) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                    raise RetriableHTTPStatus(resp)
                resp.raise_for_status()
                return resp.text
