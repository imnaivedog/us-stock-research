"""Postgres connection helpers for the data package."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = _REPO_ROOT / ".env"


def _load_repo_dotenv(env_file: Path = _ENV_FILE) -> bool:
    if not env_file.exists():
        return False
    return load_dotenv(env_file)


_load_repo_dotenv()


def _normalize_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def database_url_from_env() -> str:
    direct_url = os.getenv("DATABASE_URL", "").strip()
    if direct_url:
        return _normalize_db_url(direct_url)

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
    return create_engine(
        _normalize_db_url(database_url or database_url_from_env()),
        pool_pre_ping=True,
        future=True,
    )
