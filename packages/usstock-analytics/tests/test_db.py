from __future__ import annotations

import os

from usstock_analytics import db


def test_load_dotenv_called(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ANALYTICS_DOTENV_VALUE=loaded\n", encoding="utf-8")
    monkeypatch.delenv("ANALYTICS_DOTENV_VALUE", raising=False)

    assert db._load_repo_dotenv(env_file) is True

    assert os.environ["ANALYTICS_DOTENV_VALUE"] == "loaded"


def test_database_url_from_env_adds_postgres_password(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://stock_user@127.0.0.1:5432/usstock")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")

    assert (
        db.database_url_from_env()
        == "postgresql+psycopg://stock_user:secret@127.0.0.1:5432/usstock"
    )


def test_database_url_from_env_keeps_existing_password(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://stock_user:direct@127.0.0.1:5432/usstock")
    monkeypatch.setenv("POSTGRES_PASSWORD", "fallback")

    assert (
        db.database_url_from_env()
        == "postgresql+psycopg://stock_user:direct@127.0.0.1:5432/usstock"
    )
