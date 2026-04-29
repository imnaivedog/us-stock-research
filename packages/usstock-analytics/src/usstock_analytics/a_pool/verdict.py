"""A-pool verdict generation with a deterministic fallback."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Any, Protocol


class VerdictClient(Protocol):
    def generate_content(self, prompt: str) -> Any:
        ...


@dataclass(frozen=True)
class VerdictResult:
    text: str
    source: str
    error: str | None = None


def strongest_signal_summary(signals: dict[str, dict[str, object]]) -> str:
    triggered = [
        (name, float(payload.get("strength", 0.0)))
        for name, payload in signals.items()
        if payload.get("triggered") is True
    ]
    if not triggered:
        return "无强触发信号"
    name, _strength = max(triggered, key=lambda item: (item[1], item[0]))
    return f"{name} 触发"


def fallback_verdict(
    *,
    symbol: str,
    score: float,
    signals: dict[str, dict[str, object]],
    thesis_stop_price: float | None,
    target_price: float | None,
) -> str:
    stop = "N/A" if thesis_stop_price is None else f"{thesis_stop_price:.2f}"
    target = "N/A" if target_price is None else f"{target_price:.2f}"
    return (
        f"【{symbol}】A_Score={score:.2f} · {strongest_signal_summary(signals)} · "
        f"入场 观察 / 止损 {stop} / 目标 {target}"
    )


def render_prompt(
    *,
    symbol: str,
    signals: dict[str, dict[str, object]],
    score: float,
    score_breakdown: dict[str, float],
    profile: dict[str, object],
    ohlc: dict[str, object],
) -> str:
    return (
        "你是个人美股长线辅助研究系统的 A 池评审器。"
        "请用中文输出 80-150 字，避免交易指令口吻，只总结信号、风险和观察位。\n"
        f"symbol={symbol}\n"
        f"score={score}\n"
        f"score_breakdown={score_breakdown}\n"
        f"profile={profile}\n"
        f"ohlc={ohlc}\n"
        f"signals={signals}\n"
    )


def _extract_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text).strip()
    if isinstance(response, str):
        return response.strip()
    return str(response).strip()


def generate_verdict(
    *,
    symbol: str,
    signals: dict[str, dict[str, object]],
    score: float,
    score_breakdown: dict[str, float],
    profile: dict[str, object] | None = None,
    ohlc: dict[str, object] | None = None,
    thesis_stop_price: float | None = None,
    target_price: float | None = None,
    client: VerdictClient | None = None,
    timeout_s: float = 3.0,
) -> VerdictResult:
    fallback = fallback_verdict(
        symbol=symbol,
        score=score,
        signals=signals,
        thesis_stop_price=thesis_stop_price,
        target_price=target_price,
    )
    if client is None:
        return VerdictResult(text=fallback, source="fallback", error="llm_client_missing")

    prompt = render_prompt(
        symbol=symbol,
        signals=signals,
        score=score,
        score_breakdown=score_breakdown,
        profile=profile or {},
        ohlc=ohlc or {},
    )
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(client.generate_content, prompt)
    try:
        text = _extract_text(future.result(timeout=timeout_s))
    except TimeoutError:
        executor.shutdown(wait=False, cancel_futures=True)
        return VerdictResult(text=fallback, source="fallback", error="llm_timeout")
    except Exception as exc:  # noqa: BLE001 - external LLM clients expose provider-specific errors
        executor.shutdown(wait=False, cancel_futures=True)
        return VerdictResult(text=fallback, source="fallback", error=type(exc).__name__)
    executor.shutdown(wait=False, cancel_futures=True)
    if not text:
        return VerdictResult(text=fallback, source="fallback", error="empty_llm_response")
    return VerdictResult(text=text, source="llm")
