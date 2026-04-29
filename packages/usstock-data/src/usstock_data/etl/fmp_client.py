"""Async Financial Modeling Prep client used by data ETL jobs."""

from __future__ import annotations

import asyncio
import os
from collections import deque
from time import monotonic
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

FMP_BASE_URL = "https://financialmodelingprep.com/stable"


class FMPTransientError(RuntimeError):
    """Retryable FMP transport or server error."""


_REQUEST_SEMAPHORE = asyncio.Semaphore(5)
_REQUEST_TIMESTAMPS: deque[float] = deque()
_RATE_LOCK = asyncio.Lock()
_RATE_LIMIT_PER_MINUTE = 300


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
    def __init__(self, api_key: str | None = None, base_url: str = FMP_BASE_URL):
        self.api_key = api_key or os.getenv("FMP_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("FMP_API_KEY is required")
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
    async def request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = dict(params or {})
        query["apikey"] = self.api_key
        async with _REQUEST_SEMAPHORE:
            await _wait_for_rate_slot()
            response = await self._client.get(path, params=query)
        if response.status_code in {429, 503} or response.status_code >= 500:
            raise FMPTransientError(f"FMP transient status {response.status_code} for {path}")
        response.raise_for_status()
        return response.json()

    async def get_historical(
        self, symbol: str, from_date: str, to_date: str
    ) -> list[dict[str, Any]]:
        payload = await self.request(
            "/historical-price-eod/full",
            params={"symbol": symbol, "from": from_date, "to": to_date},
        )
        if isinstance(payload, dict):
            historical = payload.get("historical", [])
            return historical if isinstance(historical, list) else []
        return payload if isinstance(payload, list) else []

    async def get_treasury_rates(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        payload = await self.request("/treasury-rates", params={"from": from_date, "to": to_date})
        return payload if isinstance(payload, list) else []

    async def get_etf_holdings(self, etf: str) -> list[dict[str, Any]]:
        payload = await self.request("/etf/holdings", params={"symbol": etf})
        if isinstance(payload, dict):
            for key in ("holdings", "data", "historical"):
                rows = payload.get(key)
                if isinstance(rows, list):
                    return rows
            return []
        return payload if isinstance(payload, list) else []

    async def get_sp500_constituents(self) -> list[dict[str, Any]]:
        payload = await self.request("/sp500-constituent")
        return payload if isinstance(payload, list) else []

    async def get_splits(self, symbol: str) -> list[dict[str, Any]]:
        payload = await self.request("/historical-price-full/stock_split", {"symbol": symbol})
        rows = payload.get("historical", []) if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []

    async def get_dividends(self, symbol: str) -> list[dict[str, Any]]:
        payload = await self.request("/historical-price-full/stock_dividend", {"symbol": symbol})
        rows = payload.get("historical", []) if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []

    async def get_income_statement(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        payload = await self.request(
            "/income-statement", {"symbol": symbol, "period": "quarter", "limit": limit}
        )
        return payload if isinstance(payload, list) else []

    async def get_cash_flow_statement(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        payload = await self.request(
            "/cash-flow-statement", {"symbol": symbol, "period": "quarter", "limit": limit}
        )
        return payload if isinstance(payload, list) else []

    async def get_earnings_surprises(self, symbol: str) -> list[dict[str, Any]]:
        payload = await self.request("/earnings-surprises", {"symbol": symbol})
        return payload if isinstance(payload, list) else []

    async def get_earnings_calendar(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        payload = await self.request("/earning-calendar", {"from": from_date, "to": to_date})
        return payload if isinstance(payload, list) else []

    async def get_company_screener(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        payload = await self.request("/company-screener", params)
        return payload if isinstance(payload, list) else []
