"""Postgres connection helpers for analytics."""

from __future__ import annotations

import os

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine


def database_url_from_env() -> str:
    direct_url = os.getenv("DATABASE_URL", "").strip()
    if direct_url:
        return direct_url
    return str(
        URL.create(
            "postgresql+psycopg",
            username=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD") or None,
            host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "usstock"),
        )
    )


def create_postgres_engine(database_url: str | None = None) -> Engine:
    return create_engine(database_url or database_url_from_env(), pool_pre_ping=True, future=True)
