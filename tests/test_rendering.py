from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ai_news_sniffer.models import (
    ConfirmationStatus,
    DailyReport,
    NewsEvent,
    SourceRef,
)
from ai_news_sniffer.rendering.site import SiteRenderer


def make_report() -> DailyReport:
    source = SourceRef(
        source_id="official",
        source_name="Official",
        title="Original title",
        url="https://example.com/original",
        published_at=datetime(2026, 7, 23, 10, tzinfo=UTC),
    )
    event = NewsEvent(
        id="event-1",
        candidate_ids=["a1"],
        category="models",
        title_zh="新模型发布",
        summary_zh="这是事实摘要。",
        why_it_matters_zh="这会影响开发者。",
        importance_score=95,
        confirmation_status=ConfirmationStatus.PRIMARY_CONFIRMED,
        primary_source=source,
    )
    return DailyReport(
        date=date(2026, 7, 23),
        generated_at=datetime(2026, 7, 23, 13, tzinfo=UTC),
        run_id="run-1",
        daily_summary_zh="今日共一条重要新闻。",
        events=[event],
        source_coverage={
            "enabled": 12,
            "ai_candidates": 20,
            "estimated_input_tokens": 8000,
            "failed_source_ids": [],
            "newly_auto_paused_source_ids": [],
        },
    )


def test_render_creates_latest_dated_archive_and_noindex(tmp_path: Path) -> None:
    renderer = SiteRenderer(Path("templates"))
    created = renderer.render([make_report()], "default", tmp_path)

    assert tmp_path / "index.html" in created
    assert (tmp_path / "2026/07/23/index.html").exists()
    assert (tmp_path / "archive/index.html").exists()
    html = (tmp_path / "2026/07/23/index.html").read_text(encoding="utf-8")
    assert '<meta name="robots" content="noindex,nofollow">' in html
    assert "为什么重要" in html
    assert "https://example.com/original" in html
    assert "来源覆盖" in html
    assert "启用 12" in html


def test_render_notification_includes_only_three_headlines() -> None:
    report = make_report()
    report.events = report.events * 4
    text = SiteRenderer(Path("templates")).render_notification(report, "default")
    assert text.count("阅读原文") == 3


def test_renderer_rejects_template_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="template name"):
        SiteRenderer(Path("templates")).render(
            [make_report()],
            "../outside",
            tmp_path,
        )
