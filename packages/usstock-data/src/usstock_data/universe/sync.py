"""Universe sync orchestration."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from usstock_data.universe import a_pool, m_pool


async def sync_all(engine: Engine | None = None, dry_run: bool = False) -> dict[str, dict[str, int]]:
    m_result = await m_pool.sync(engine=engine, dry_run=dry_run)
    a_result = {"synced": 0} if dry_run else a_pool.sync(engine=engine)
    return {"m": m_result, "a": a_result}
