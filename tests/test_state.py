from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ai_news_sniffer.models import ChannelResult, DailyReport, RunStatus
from ai_news_sniffer.state import RuntimeStore


def report() -> DailyReport:
    return DailyReport(
        date=date(2026, 7, 23),
        generated_at=datetime(2026, 7, 23, 13, tzinfo=UTC),
        run_id="2026-07-23-a1b2c3",
        daily_summary_zh="今日摘要",
        events=[],
    )


def test_runtime_store_advances_prepared_published_notified(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path)
    prepared = store.save_prepared(report(), {"fingerprint-a"})
    assert prepared.status is RunStatus.PREPARED
    assert store.load_seen_fingerprints() == set()

    published = store.mark_published(prepared.run_id, "https://ai.example.com/2026/07/23/")
    assert published.status is RunStatus.PUBLISHED
    assert store.load_seen_fingerprints() == {"fingerprint-a"}

    notified = store.mark_notified(
        prepared.run_id,
        [ChannelResult(channel_id="meow", success=True, attempts=1)],
    )
    assert notified.status is RunStatus.NOTIFIED


def test_runtime_store_rejects_invalid_transition(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path)
    store.save_prepared(report(), set())

    with pytest.raises(ValueError, match="published"):
        store.mark_notified("2026-07-23-a1b2c3", [])


def test_seen_fingerprints_round_trip(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path)
    store.save_seen_fingerprints({"a", "b"}, date(2026, 7, 23))
    assert store.load_seen_fingerprints() == {"a", "b"}
    assert store.load_seen_fingerprints(excluding_date=date(2026, 7, 23)) == set()


def test_load_run_is_public(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path)
    saved = store.save_prepared(report(), set())
    assert store.load_run(saved.run_id) == saved


def test_partial_notification_can_advance_after_failed_channel_retry(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path)
    saved = store.save_prepared(report(), set())
    store.mark_published(saved.run_id, "https://ai.example.com/2026/07/23/")
    partial = store.mark_notified(
        saved.run_id,
        [
            ChannelResult(channel_id="meow", success=True, attempts=1),
            ChannelResult(channel_id="wecom", success=False, attempts=3),
        ],
    )
    completed = store.mark_notified(
        saved.run_id,
        [
            ChannelResult(channel_id="meow", success=True, attempts=1),
            ChannelResult(channel_id="wecom", success=True, attempts=1),
        ],
    )
    assert partial.status is RunStatus.PARTIALLY_NOTIFIED
    assert completed.status is RunStatus.NOTIFIED


def test_partial_notification_retains_successful_channels_when_retrying_failures(
    tmp_path: Path,
) -> None:
    store = RuntimeStore(tmp_path)
    saved = store.save_prepared(report(), set())
    store.mark_published(saved.run_id, "https://ai.example.com/2026/07/23/")
    store.mark_notified(
        saved.run_id,
        [
            ChannelResult(channel_id="meow", success=True, attempts=1),
            ChannelResult(channel_id="wecom", success=False, attempts=3),
        ],
    )

    completed = store.mark_notified(
        saved.run_id,
        [ChannelResult(channel_id="wecom", success=True, attempts=1)],
    )

    assert completed.status is RunStatus.NOTIFIED
    assert completed.channel_results == [
        ChannelResult(channel_id="meow", success=True, attempts=1),
        ChannelResult(channel_id="wecom", success=True, attempts=1),
    ]


def test_save_prepared_preserves_completed_run_idempotently(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path)
    first = store.save_prepared(report(), set())
    store.mark_published(first.run_id, "https://ai.example.com/2026/07/23/")
    completed = store.mark_notified(
        first.run_id,
        [ChannelResult(channel_id="meow", success=True, attempts=1)],
    )
    second = store.save_prepared(report(), set())
    assert first.run_id == second.run_id
    assert second.status is RunStatus.NOTIFIED
    assert second == completed
    assert len(store.load_reports()) == 1
