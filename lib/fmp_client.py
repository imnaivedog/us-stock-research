from __future__ import annotations

import asyncio
from collections import deque
from time import monotonic
from typing import Any

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


FMP_BASE_URL = "https://financialmodelingprep.com/stable"


class FMPSettings(BaseSettings):
    fmp_api_key: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class FMPTransientError(RuntimeError):
    pass


_REQUEST_SEMAPHORE = asyncio.Semaphore(5)
_RATE_LIMIT_PER_MINUTE = 300
_REQUEST_TIMESTAMPS: deque[float] = deque()
_RATE_LOCK = asyncio.Lock()


async def _wait_for_rate_slot() -> None:
    while True:
        async with _RATE_LOCK:
            now = monotonic()
            while _REQUEST_TIMESTAMPS and now - _REQUEST_TIMESTAMPS[0] >= 60:
                _REQUEST_TIMESTAMPS.popleft()
            if len(_REQUEST_TIMESTAMPS) < _RATE_LIMIT_PER_MINUTE:
                _REQUEST_TIMESTAMPS.append(now)
                return
            sleep_for = max(0.0, 60 - (now - _REQUEST_TIMESTAMPS[0]))
        await asyncio.sleep(sleep_for)


class FMPClient:
    """Thin async wrapper for Financial Modeling Prep endpoints used by M1."""

    def __init__(self, api_key: str | None = None, base_url: str = FMP_BASE_URL):
        self.api_key = api_key or FMPSettings().fmp_api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(60.0))

    async def __aenter__(self) -> FMPClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type(FMPTransientError),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    async def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = dict(params or {})
        query["apikey"] = self.api_key
        async with _REQUEST_SEMAPHORE:
            await _wait_for_rate_slot()
            response = await self._client.get(path, params=query)
        if response.status_code in {429, 503} or response.status_code >= 500:
            raise FMPTransientError(f"FMP transient status {response.status_code} for {path}")
        response.raise_for_status()
        return response.json()

    async def get_profile(self, symbol: str) -> dict[str, Any]:
        payload = await self._request("/profile", params={"symbol": symbol})
        if isinstance(payload, list):
            return payload[0] if payload else {}
        return payload if isinstance(payload, dict) else {}

    async def get_historical(self, symbol: str, from_date: str, to_date: str) -> list[dict[str, Any]]:
        payload = await self._request(
            "/historical-price-eod/full",
            params={"symbol": symbol, "from": from_date, "to": to_date},
        )
        if isinstance(payload, dict):
            historical = payload.get("historical", [])
            return historical if isinstance(historical, list) else []
        return payload if isinstance(payload, list) else []

    async def get_treasury_rates(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        payload = await self._request(
            "/treasury-rates",
            params={"from": from_date, "to": to_date},
        )
        return payload if isinstance(payload, list) else []

    async def get_etf_holdings(self, etf: str) -> list[dict[str, Any]]:
        payload = await self._request("/etf/holdings", params={"symbol": etf})
        if isinstance(payload, dict):
            for key in ("holdings", "data", "historical"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
            return []
        return payload if isinstance(payload, list) else []

    async def get_etf_info(self, etf: str) -> dict[str, Any]:
        payload = await self._request("/etf/info", params={"symbol": etf})
        if isinstance(payload, list):
            return payload[0] if payload else {}
        return payload if isinstance(payload, dict) else {}
