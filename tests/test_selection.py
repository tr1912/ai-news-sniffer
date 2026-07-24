from datetime import UTC, datetime

from ai_news_sniffer.models import (
    Article,
    ConfirmationStatus,
    NewsEvent,
    SourceGroup,
    SourceRef,
)
from ai_news_sniffer.selection import build_degraded_events, select_diverse_events

NOW = datetime(2026, 7, 23, 13, tzinfo=UTC)


def source(source_id: str, suffix: str) -> SourceRef:
    return SourceRef(
        source_id=source_id,
        source_name=source_id,
        title=f"Source title {suffix}",
        url=f"https://example.com/{suffix}",
        published_at=NOW,
    )


def event(number: int, category: str, source_id: str) -> NewsEvent:
    return NewsEvent(
        id=f"event-{number}",
        candidate_ids=[f"article-{number}"],
        category=category,
        title_zh=f"新闻 {number}",
        summary_zh="事实摘要",
        why_it_matters_zh="重要性说明",
        importance_score=100 - number,
        confirmation_status=ConfirmationStatus.PRIMARY_CONFIRMED,
        primary_source=source(source_id, str(number)),
    )


def test_select_diverse_events_enforces_source_and_category_caps() -> None:
    events = [
        event(1, "models", "same"),
        event(2, "models", "same"),
        event(3, "models", "same"),
        event(4, "models", "other"),
        event(5, "policy", "policy-source"),
    ]

    selected = select_diverse_events(
        events,
        max_items=5,
        max_per_category=3,
        max_per_source=2,
    )

    assert [item.id for item in selected] == ["event-1", "event-2", "event-4", "event-5"]


def test_build_degraded_events_does_not_invent_why_it_matters() -> None:
    article = Article(
        id="a1",
        source_id="official",
        source_name="Official",
        source_group=SourceGroup.OFFICIAL,
        independence_group="official",
        title="Original title",
        url="https://example.com/a1",
        canonical_url="https://example.com/a1",
        normalized_title="original title",
        fingerprint="a" * 64,
        published_at=NOW,
        fetched_at=NOW,
        excerpt="Original source excerpt.",
        categories=["models"],
        rule_score=88,
    )

    degraded = build_degraded_events([article], max_items=15)

    assert degraded[0].summary_zh == "Original source excerpt."
    assert degraded[0].why_it_matters_zh == ""
