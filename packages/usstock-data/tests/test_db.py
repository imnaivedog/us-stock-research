from __future__ import annotations

import os

from usstock_data import db


def test_load_dotenv_called(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("P1_DOTENV_VALUE=loaded\n", encoding="utf-8")
    monkeypatch.delenv("P1_DOTENV_VALUE", raising=False)

    assert db._load_repo_dotenv(env_file) is True

    assert os.environ["P1_DOTENV_VALUE"] == "loaded"


def test_load_dotenv_keeps_existing_env(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("P1_DOTENV_VALUE=from_file\n", encoding="utf-8")
    monkeypatch.setenv("P1_DOTENV_VALUE", "from_shell")

    assert db._load_repo_dotenv(env_file) is True

    assert os.environ["P1_DOTENV_VALUE"] == "from_shell"


def test_repo_root_points_to_workspace() -> None:
    assert db._REPO_ROOT.name == "us-stock-research"
    assert (db._REPO_ROOT / "packages" / "usstock-data").exists()


def test_normalize_db_url_postgresql() -> None:
    assert db._normalize_db_url("postgresql://u:p@h/d") == "postgresql+psycopg://u:p@h/d"


def test_normalize_db_url_already_psycopg() -> None:
    assert (
        db._normalize_db_url("postgresql+psycopg://u:p@h/d")
        == "postgresql+psycopg://u:p@h/d"
    )


def test_normalize_db_url_heroku_postgres() -> None:
    assert db._normalize_db_url("postgres://u:p@h/d") == "postgresql+psycopg://u:p@h/d"


def test_database_url_from_env_normalizes_direct_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")

    assert db.database_url_from_env() == "postgresql+psycopg://u:p@h/d"
