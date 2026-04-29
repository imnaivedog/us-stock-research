"""Postgres connection helpers for the data package."""

from __future__ import annotations

import os

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine


def database_url_from_env() -> str:
    direct_url = os.getenv("DATABASE_URL", "").strip()
    if direct_url:
        return direct_url

    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    database = os.getenv("POSTGRES_DB", "usstock")
    return str(
        URL.create(
            "postgresql+psycopg",
            username=user,
            password=password or None,
            host=host,
            port=port,
            database=database,
        )
    )


def create_postgres_engine(database_url: str | None = None) -> Engine:
    return create_engine(database_url or database_url_from_env(), pool_pre_ping=True, future=True)
