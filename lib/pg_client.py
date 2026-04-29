from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL


class PostgresSettings(BaseSettings):
    database_url: str = ""
    use_cloud_sql_proxy: bool = True
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_db: str = "usstock"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_identifier(identifier: str) -> str:
    if not _IDENTIFIER_RE.match(identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier}")
    return f'"{identifier}"'


class PostgresClient:
    def __init__(self, settings: PostgresSettings | None = None):
        self.settings = settings or PostgresSettings()
        self.engine = self._create_engine()

    def _create_engine(self) -> Engine:
        if self.settings.database_url:
            return create_engine(self.settings.database_url, pool_pre_ping=True, future=True)
        url = URL.create(
            "postgresql+psycopg",
            username=self.settings.postgres_user,
            password=self.settings.postgres_password or None,
            host=self.settings.postgres_host,
            port=self.settings.postgres_port,
            database=self.settings.postgres_db,
        )
        return create_engine(url, pool_pre_ping=True, future=True)

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        with self.engine.begin() as conn:
            conn.execute(text(sql), params or {})

    def executemany(self, sql: str, rows: Sequence[dict[str, Any]]) -> None:
        if not rows:
            return
        with self.engine.begin() as conn:
            conn.execute(text(sql), list(rows))

    def fetch_scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params or {}).scalar()

    def upsert(
        self,
        table: str,
        rows: Sequence[dict[str, Any]],
        conflict_cols: Sequence[str],
        update_cols: Sequence[str],
        batch_size: int = 500,
    ) -> None:
        if not rows:
            return
        quoted_table = _quote_identifier(table)
        columns = list(rows[0].keys())
        quoted_columns = ", ".join(_quote_identifier(col) for col in columns)
        values = ", ".join(f":{col}" for col in columns)
        conflict = ", ".join(_quote_identifier(col) for col in conflict_cols)
        update_targets = [col for col in update_cols if col not in conflict_cols]
        set_clause = ", ".join(
            f"{_quote_identifier(col)} = EXCLUDED.{_quote_identifier(col)}" for col in update_targets
        )
        if "updated_at" not in update_targets:
            set_clause = f"{set_clause}, updated_at = now()" if set_clause else "updated_at = now()"
        sql = (
            f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({values}) "
            f"ON CONFLICT ({conflict}) DO UPDATE SET {set_clause}"
        )
        for batch in _chunks(rows, batch_size):
            self.executemany(sql, batch)


def _chunks(rows: Sequence[dict[str, Any]], batch_size: int) -> Iterable[list[dict[str, Any]]]:
    for idx in range(0, len(rows), batch_size):
        yield list(rows[idx : idx + batch_size])
