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
