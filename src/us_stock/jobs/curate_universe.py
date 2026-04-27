from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import traceback
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from loguru import logger
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from lib.fmp_client import FMPClient
from lib.pg_client import PostgresClient

MARKET_CAP_MIN = 1_000_000_000
MIN_FMP_ELIGIBLE_ROWS = 500
MIN_FINAL_ACTIVE_ROWS = 500
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
DISCORD_WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"
ALLOWED_EXCHANGES = {"NASDAQ", "NYSE", "AMEX"}


@dataclass(frozen=True)
class UniverseMember:
    symbol: str
    market_cap: Decimal | None = None
    name: str | None = None
    sector: str | None = None


@dataclass(frozen=True)
class UniverseSnapshot:
    fmp_eligible: dict[str, UniverseMember]
    watchlist_symbols: set[str]
    current_active: set[str]
    all_known: set[str]


@dataclass(frozen=True)
class UniverseDiff:
    should_be_active: set[str]
    to_add: set[str]
    to_remove: set[str]
    forced_in: set[str]
    to_create: set[str]

    @property
    def unchanged_count(self) -> int:
        return len(self.should_be_active) - len(self.to_add)


@dataclass(frozen=True)
class CurateResult:
    diff: UniverseDiff
    created: int
    added: int
    removed: int
    forced_in: int
    final_active_count: int | None
    audit_rows: int
    dry_run: bool


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, level=os.getenv("LOG_LEVEL", "INFO"), format="[{level}] {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Curate weekly symbol_universe membership.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the diff without writing tables.",
    )
    parser.add_argument("--no-alert", action="store_true", help="Disable Discord alert attempts.")
    return parser.parse_args()


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace(".", "-")


def parse_market_cap(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except Exception:
        return None


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def is_common_stock_candidate(item: dict[str, Any]) -> bool:
    if truthy(item.get("isEtf")) or truthy(item.get("isFund")):
        return False
    country = str(item.get("country") or "").strip().upper()
    if country and country != "US":
        return False
    exchange_value = (
        item.get("exchangeShortName")
        or item.get("exchange")
        or item.get("exchange_short_name")
        or ""
    )
    exchange = str(exchange_value).strip().upper()
    return not exchange or exchange in ALLOWED_EXCHANGES


def build_diff(snapshot: UniverseSnapshot) -> UniverseDiff:
    should_be_active = set(snapshot.fmp_eligible) | snapshot.watchlist_symbols
    to_add = should_be_active - snapshot.current_active
    to_remove = snapshot.current_active - should_be_active
    forced_in = (snapshot.watchlist_symbols & to_add) - set(snapshot.fmp_eligible)
    to_create = should_be_active - snapshot.all_known
    return UniverseDiff(
        should_be_active=should_be_active,
        to_add=to_add,
        to_remove=to_remove,
        forced_in=forced_in,
        to_create=to_create,
    )


def audit_rows_for_diff(
    diff: UniverseDiff,
    fmp_eligible: dict[str, UniverseMember],
    today: date,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in sorted(diff.to_add - diff.forced_in):
        rows.append(
            {
                "symbol": symbol,
                "change_date": today,
                "change_type": "added",
                "reason": "market_cap>=1B",
                "market_cap": fmp_eligible.get(symbol, UniverseMember(symbol)).market_cap,
            }
        )
    for symbol in sorted(diff.forced_in):
        rows.append(
            {
                "symbol": symbol,
                "change_date": today,
                "change_type": "forced_in",
                "reason": "watchlist",
                "market_cap": fmp_eligible.get(symbol, UniverseMember(symbol)).market_cap,
            }
        )
    for symbol in sorted(diff.to_remove):
        rows.append(
            {
                "symbol": symbol,
                "change_date": today,
                "change_type": "removed",
                "reason": "market_cap<1B AND symbol NOT IN watchlist",
                "market_cap": fmp_eligible.get(symbol, UniverseMember(symbol)).market_cap,
            }
        )
    return rows


def _symbol_params(symbols: Iterable[str]) -> dict[str, list[str]]:
    return {"symbols": sorted(set(symbols))}


def fetch_watchlist_symbols(conn: Connection) -> set[str]:
    table_exists = conn.execute(text("SELECT to_regclass('public.watchlist')")).scalar_one()
    if not table_exists:
        logger.warning("watchlist table not found; using market-cap rule only")
        return set()
    return set(conn.execute(text("SELECT symbol FROM watchlist")).scalars().all())


def insert_new_symbols(
    conn: Connection,
    members: Sequence[UniverseMember],
    today: date,
) -> int:
    rows = [
        {
            "symbol": member.symbol,
            "source": "fmp_screener",
            "is_candidate": True,
            "is_active": False,
            "market_cap": member.market_cap,
            "added_date": today,
            "as_of_date": today,
            "filter_reason": "pending_curation",
        }
        for member in members
    ]
    if not rows:
        return 0
    conn.execute(
        text(
            """
            INSERT INTO symbol_universe (
                symbol, source, is_candidate, is_active, market_cap,
                added_date, as_of_date, filter_reason
            )
            VALUES (
                :symbol, :source, :is_candidate, :is_active, :market_cap,
                :added_date, :as_of_date, :filter_reason
            )
            ON CONFLICT (symbol) DO NOTHING
            """
        ),
        rows,
    )
    return len(rows)


def update_added_symbols(conn: Connection, symbols: set[str], today: date) -> int:
    if not symbols:
        return 0
    result = conn.execute(
        text(
            """
            UPDATE symbol_universe
            SET is_active = true,
                first_seen = COALESCE(first_seen, :today),
                last_seen = NULL,
                as_of_date = :today,
                updated_at = CURRENT_TIMESTAMP
            WHERE symbol IN :symbols
            """
        ).bindparams(bindparam("symbols", expanding=True)),
        {"today": today, **_symbol_params(symbols)},
    )
    return result.rowcount or 0


def update_removed_symbols(conn: Connection, symbols: set[str], today: date) -> int:
    if not symbols:
        return 0
    result = conn.execute(
        text(
            """
            UPDATE symbol_universe
            SET is_active = false,
                last_seen = :today,
                as_of_date = :today,
                updated_at = CURRENT_TIMESTAMP
            WHERE symbol IN :symbols
            """
        ).bindparams(bindparam("symbols", expanding=True)),
        {"today": today, **_symbol_params(symbols)},
    )
    return result.rowcount or 0


def insert_audit_rows(conn: Connection, rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    normalized_rows = [
        {
            **row,
            "market_cap": (
                float(row["market_cap"])
                if isinstance(row["market_cap"], Decimal)
                else row["market_cap"]
            ),
        }
        for row in rows
    ]
    conn.execute(
        text(
            """
            INSERT INTO symbol_universe_changes (
                symbol, change_date, change_type, reason, market_cap
            )
            VALUES (:symbol, :change_date, :change_type, :reason, :market_cap)
            """
        ),
        normalized_rows,
    )
    return len(rows)


def apply_diff(
    conn: Connection,
    snapshot: UniverseSnapshot,
    diff: UniverseDiff,
    today: date,
) -> CurateResult:
    create_members = [
        snapshot.fmp_eligible[symbol]
        for symbol in sorted(diff.to_create)
        if symbol in snapshot.fmp_eligible
    ]
    missing_profile_symbols = sorted(diff.to_create - set(snapshot.fmp_eligible))
    for symbol in missing_profile_symbols:
        logger.warning(f"Skipping {symbol}: missing sector/name field")

    created = insert_new_symbols(conn, create_members, today)
    added = update_added_symbols(conn, diff.to_add, today)
    removed = update_removed_symbols(conn, diff.to_remove, today)
    audit_rows = audit_rows_for_diff(diff, snapshot.fmp_eligible, today)
    audit_count = insert_audit_rows(conn, audit_rows)
    final_active_count = conn.execute(
        text("SELECT COUNT(*) FROM symbol_universe WHERE is_active IS TRUE")
    ).scalar_one()
    if int(final_active_count) < MIN_FINAL_ACTIVE_ROWS:
        raise RuntimeError(f"final active count below safety floor: {final_active_count}")
    return CurateResult(
        diff=diff,
        created=created,
        added=added,
        removed=removed,
        forced_in=len(diff.forced_in),
        final_active_count=int(final_active_count),
        audit_rows=audit_count,
        dry_run=False,
    )


def dry_run_result(snapshot: UniverseSnapshot, diff: UniverseDiff) -> CurateResult:
    final_active_count = len((snapshot.current_active | diff.to_add) - diff.to_remove)
    return CurateResult(
        diff=diff,
        created=len(diff.to_create),
        added=len(diff.to_add),
        removed=len(diff.to_remove),
        forced_in=len(diff.forced_in),
        final_active_count=final_active_count,
        audit_rows=len(diff.to_add) + len(diff.to_remove),
        dry_run=True,
    )


def log_plan(snapshot: UniverseSnapshot, diff: UniverseDiff) -> None:
    logger.info(f"FMP screener returned {len(snapshot.fmp_eligible)} symbols (market_cap >= 1B)")
    if snapshot.watchlist_symbols:
        logger.info(f"Watchlist contains {len(snapshot.watchlist_symbols)} symbols")
    else:
        logger.info("Watchlist is empty; using market-cap rule only")
    logger.info(f"Should-be-active universe size: {len(diff.should_be_active)}")
    logger.info(f"Currently active: {len(snapshot.current_active)}")
    logger.info(
        "Diff: "
        f"+{len(diff.to_add)} to_add (incl. {len(diff.forced_in)} forced_in) / "
        f"-{len(diff.to_remove)} to_remove / {diff.unchanged_count} unchanged"
    )
    logger.info(f"Creating {len(diff.to_create)} new symbols never seen before")


def log_result(result: CurateResult, elapsed: float) -> None:
    mode = "Dry-run" if result.dry_run else "Transaction committed"
    logger.info(
        f"{mode}: {result.added} added, {result.removed} removed, "
        f"{result.forced_in} forced_in audit rows written"
    )
    logger.info(f"Final active count: {result.final_active_count}")
    logger.info(f"curate_universe completed in {elapsed:.1f}s")


async def fetch_fmp_eligible(client: FMPClient) -> dict[str, UniverseMember]:
    payload = await client._request(
        "/company-screener",
        params={
            "marketCapMoreThan": MARKET_CAP_MIN,
            "isActivelyTrading": "true",
            "isEtf": "false",
            "isFund": "false",
            "country": "US",
            "exchangeShortName": ",".join(sorted(ALLOWED_EXCHANGES)),
            "limit": 10_000,
        },
    )
    if not isinstance(payload, list):
        raise RuntimeError("FMP screener returned non-list payload")
    if len(payload) < MIN_FMP_ELIGIBLE_ROWS:
        raise RuntimeError(f"FMP screener returned too few rows: {len(payload)}")

    members: dict[str, UniverseMember] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        if not is_common_stock_candidate(item):
            continue
        symbol = normalize_symbol(item.get("symbol"))
        if not symbol:
            continue
        sector = item.get("sector")
        name = item.get("companyName") or item.get("company_name") or item.get("name")
        if not sector or not name:
            logger.warning(f"Skipping {symbol}: missing sector/name field")
            continue
        members[symbol] = UniverseMember(
            symbol=symbol,
            market_cap=parse_market_cap(item.get("marketCap")),
            name=str(name),
            sector=str(sector),
        )
    if len(members) < MIN_FMP_ELIGIBLE_ROWS:
        raise RuntimeError(f"FMP screener usable rows below floor: {len(members)}")
    return members


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def load_db_snapshot(pg: PostgresClient) -> tuple[set[str], set[str], set[str]]:
    with pg.engine.begin() as conn:
        watchlist_symbols = fetch_watchlist_symbols(conn)
        current_active = set(
            conn.execute(
                text("SELECT symbol FROM symbol_universe WHERE is_active IS TRUE")
            ).scalars().all()
        )
        all_known = set(conn.execute(text("SELECT symbol FROM symbol_universe")).scalars().all())
    return watchlist_symbols, current_active, all_known


async def build_snapshot(pg: PostgresClient, client: FMPClient) -> UniverseSnapshot:
    fmp_eligible = await fetch_fmp_eligible(client)
    watchlist_symbols, current_active, all_known = load_db_snapshot(pg)
    return UniverseSnapshot(
        fmp_eligible=fmp_eligible,
        watchlist_symbols={normalize_symbol(symbol) for symbol in watchlist_symbols},
        current_active={normalize_symbol(symbol) for symbol in current_active},
        all_known={normalize_symbol(symbol) for symbol in all_known},
    )


def send_discord_alert(job_name: str, run_id: str, exc: BaseException) -> None:
    webhook_url = os.getenv(DISCORD_WEBHOOK_ENV)
    if not webhook_url:
        logger.warning("Discord webhook env not set; alert skipped")
        return
    stack_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    stack_preview = "".join(stack_lines).splitlines()[:10]
    console_url = (
        "https://console.cloud.google.com/run/jobs/details/us-central1/"
        f"{job_name}/executions?project=naive-usstock-live"
    )
    payload = {
        "content": "\n".join(
            [
                f"ALERT: {job_name} failed",
                f"run_id={run_id}",
                f"console={console_url}",
                "```",
                *stack_preview,
                "```",
            ]
        )
    }
    try:
        response = httpx.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as alert_exc:
        logger.warning(f"Discord alert failed: {alert_exc}")


async def run_curate_universe(
    pg: PostgresClient,
    fmp_factory: Callable[[], FMPClient] = FMPClient,
    dry_run: bool = False,
    today: date | None = None,
) -> CurateResult:
    today = today or datetime.now(LOCAL_TZ).date()
    async with fmp_factory() as client:
        snapshot = await build_snapshot(pg, client)
    diff = build_diff(snapshot)
    log_plan(snapshot, diff)
    if dry_run:
        result = dry_run_result(snapshot, diff)
        final_active_count = result.final_active_count
        if final_active_count is not None and final_active_count < MIN_FINAL_ACTIVE_ROWS:
            raise RuntimeError(f"final active count below safety floor: {final_active_count}")
        return result

    with pg.engine.begin() as conn:
        return apply_diff(conn, snapshot, diff, today)


async def async_main() -> None:
    configure_logging()
    args = parse_args()
    started = time.monotonic()
    started_at = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    logger.info(f"curate_universe started at {started_at}")
    run_id = os.getenv("CLOUD_RUN_EXECUTION", datetime.now(UTC).isoformat())
    try:
        result = await run_curate_universe(PostgresClient(), dry_run=args.dry_run)
    except Exception as exc:
        if not args.no_alert:
            send_discord_alert("curate-universe-job", run_id, exc)
        raise
    log_result(result, time.monotonic() - started)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
