from __future__ import annotations

import json
from typing import Any

from usstock_reports.discord.webhook import (
    build_webhook_message,
    send_discord_report,
    split_message,
)


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeConn:
    def __init__(self) -> None:
        self.executed: list[dict[str, Any]] = []

    def execute(self, query, params):
        self.executed.append(params)


class FakeEngine:
    def __init__(self) -> None:
        self.conn = FakeConn()

    def begin(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, traceback):
        return False


def discord_report(sample_report) -> dict[str, Any]:
    report = {**sample_report, "daily": {**sample_report["daily"], "vix": 18.4}}
    report["alerts"] = [{"severity": "WARN", "message": "breadth diverged"}]
    report["stocks"] = [
        {**report["stocks"][0], "primary_sector": "Technology", "top_signal": "B1"},
        {**report["stocks"][1], "primary_sector": "Software"},
    ]
    return report


def test_webhook_payload_snapshot(sample_report, fixtures_dir) -> None:
    expected = json.loads(
        (fixtures_dir / "webhook_payload_expected.json").read_text(encoding="utf-8")
    )
    assert build_webhook_message(discord_report(sample_report)) == expected["content"]


def test_discord_webhook_success_path(sample_report) -> None:
    calls = []

    def post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(204)

    exit_code = send_discord_report(
        discord_report(sample_report),
        webhook_url="https://discord.test/webhook",
        post=post,
        sleep=lambda seconds: None,
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["json"]["content"].startswith("📊 2026-04-30 · Dial A")


def test_discord_webhook_500_retries_three_times_and_alerts(sample_report) -> None:
    calls = []
    sleeps = []
    engine = FakeEngine()

    def post(url, json, timeout):
        calls.append(json)
        return FakeResponse(500)

    exit_code = send_discord_report(
        discord_report(sample_report),
        engine=engine,
        webhook_url="https://discord.test/webhook",
        post=post,
        sleep=sleeps.append,
    )

    assert exit_code == 1
    assert len(calls) == 3
    assert sleeps == [1, 2]
    assert engine.conn.executed[0]["severity"] == "ERROR"
    assert "failed after 3 attempts" in engine.conn.executed[0]["message"]


def test_discord_webhook_missing_url_skips_and_writes_info(sample_report) -> None:
    engine = FakeEngine()
    exit_code = send_discord_report(
        discord_report(sample_report),
        engine=engine,
        webhook_url="",
        post=lambda **kwargs: FakeResponse(204),
    )

    assert exit_code == 0
    assert engine.conn.executed[0]["severity"] == "INFO"
    assert "DISCORD_WEBHOOK_URL missing" in engine.conn.executed[0]["message"]


def test_payload_length_boundary_1900_chars_not_split() -> None:
    chunks = split_message("x" * 1900)
    assert chunks == ["x" * 1900]


def test_payload_length_boundary_2500_chars_splits_two_segments() -> None:
    chunks = split_message("x" * 2500)
    assert len(chunks) == 2
    assert chunks[1].startswith("续 1/1\n")
