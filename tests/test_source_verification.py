from datetime import UTC, datetime, timedelta

import pytest

from ai_news_sniffer.dedup import deduplicate_articles
from ai_news_sniffer.models import (
    Article,
    ConfirmationStatus,
    InterestsConfig,
    NewsEvent,
    SourceGroup,
    SourceRef,
)
from ai_news_sniffer.scoring import score_articles
from ai_news_sniffer.source_verification import (
    confirmation_status,
    validate_event_sources,
)

NOW = datetime(2026, 7, 23, 13, tzinfo=UTC)


def article(
    article_id: str,
    source_id: str,
    group: SourceGroup,
    independence_group: str,
    title: str = "New reasoning model released",
) -> Article:
    return Article(
        id=article_id,
        source_id=source_id,
        source_name=source_id,
        source_group=group,
        independence_group=independence_group,
        title=title,
        url=f"https://{source_id}.example/{article_id}",
        canonical_url=f"https://{source_id}.example/{article_id}",
        normalized_title=title.casefold(),
        fingerprint=(article_id * 64)[:64],
        published_at=NOW - timedelta(hours=1),
        fetched_at=NOW,
        excerpt="An open-source reasoning model was released.",
        categories=["models", "open-source"],
    )


def test_dedup_and_score_prioritize_verified_relevant_sources() -> None:
    official = article("a", "official", SourceGroup.OFFICIAL, "official")
    duplicate = article(
        "b",
        "media",
        SourceGroup.MEDIA,
        "wire-a",
        "New reasoning model is released",
    )
    unique = deduplicate_articles([official, duplicate], set())
    ranked = score_articles(
        unique,
        InterestsConfig(
            topics=["models", "open-source"],
            entities=[],
            include_terms=["reasoning", "model"],
            exclude_terms=["sponsored"],
        ),
        {"official": 25, "media": 10},
        NOW,
    )

    assert ranked[0].source_id == "official"
    assert 0 <= ranked[0].rule_score <= 100


def test_confirmation_requires_primary_or_two_independent_media_origins() -> None:
    official = article("a", "official", SourceGroup.OFFICIAL, "official")
    first = article("b", "media-a", SourceGroup.MEDIA, "wire-a")
    syndication = article("c", "media-b", SourceGroup.MEDIA, "wire-a")
    independent = article("d", "media-c", SourceGroup.MEDIA, "wire-b")
    community = article("e", "hn", SourceGroup.COMMUNITY, "hn")

    assert confirmation_status([official]) == ConfirmationStatus.PRIMARY_CONFIRMED
    assert confirmation_status([first, syndication]) == ConfirmationStatus.UNVERIFIED
    assert (
        confirmation_status([first, independent])
        == ConfirmationStatus.CROSS_CONFIRMED
    )
    assert confirmation_status([community]) == ConfirmationStatus.UNVERIFIED


def test_editorial_output_cannot_reference_unknown_candidate() -> None:
    known = article("a", "official", SourceGroup.OFFICIAL, "official")
    event = NewsEvent(
        id="event-1",
        candidate_ids=["missing"],
        category="models",
        title_zh="模型发布",
        summary_zh="摘要",
        why_it_matters_zh="重要性",
        importance_score=90,
        confirmation_status=ConfirmationStatus.PRIMARY_CONFIRMED,
        primary_source=SourceRef(
            source_id=known.source_id,
            source_name=known.source_name,
            title=known.title,
            url=known.url,
            published_at=known.published_at,
        ),
    )

    with pytest.raises(ValueError, match="unknown candidate ids"):
        validate_event_sources(event, [known])


@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        ("source_id", "forged-source"),
        ("source_name", "Forged source"),
        ("title", "Forged title"),
        ("url", "https://official.example/forged"),
        ("published_at", NOW),
    ],
)
def test_editorial_output_rejects_primary_reference_not_matching_candidate(
    field: str,
    forged_value: str | datetime,
) -> None:
    known = article("a", "official", SourceGroup.OFFICIAL, "official")
    primary_source = SourceRef(
        source_id=known.source_id,
        source_name=known.source_name,
        title=known.title,
        url=known.url,
        published_at=known.published_at,
    ).model_copy(update={field: forged_value})
    event = NewsEvent(
        id="event-forged-primary",
        candidate_ids=[known.id],
        category="models",
        title_zh="模型发布",
        summary_zh="摘要",
        why_it_matters_zh="重要性",
        importance_score=90,
        confirmation_status=ConfirmationStatus.PRIMARY_CONFIRMED,
        primary_source=primary_source,
    )

    with pytest.raises(ValueError, match="source reference is not backed"):
        validate_event_sources(event, [known])


def test_editorial_output_rejects_related_reference_not_matching_candidate() -> None:
    known = article("a", "official", SourceGroup.OFFICIAL, "official")
    event = NewsEvent(
        id="event-forged-related",
        candidate_ids=[known.id],
        category="models",
        title_zh="模型发布",
        summary_zh="摘要",
        why_it_matters_zh="重要性",
        importance_score=90,
        confirmation_status=ConfirmationStatus.PRIMARY_CONFIRMED,
        primary_source=SourceRef(
            source_id=known.source_id,
            source_name=known.source_name,
            title=known.title,
            url=known.url,
            published_at=known.published_at,
        ),
        related_sources=[
            SourceRef(
                source_id=known.source_id,
                source_name=known.source_name,
                title=known.title,
                url="https://official.example/forged",
                published_at=known.published_at,
            )
        ],
    )

    with pytest.raises(ValueError, match="source reference is not backed"):
        validate_event_sources(event, [known])


def test_editorial_output_rejects_unverified_or_community_primary() -> None:
    official = article("a", "official", SourceGroup.OFFICIAL, "official")
    community = article("b", "hn", SourceGroup.COMMUNITY, "hn")
    media = article("c", "media", SourceGroup.MEDIA, "wire-a")

    unverified = NewsEvent(
        id="event-unverified",
        candidate_ids=[media.id],
        category="business",
        title_zh="未经确认",
        summary_zh="摘要",
        why_it_matters_zh="重要性",
        importance_score=80,
        confirmation_status=ConfirmationStatus.UNVERIFIED,
        primary_source=SourceRef(
            source_id=media.source_id,
            source_name=media.source_name,
            title=media.title,
            url=media.url,
            published_at=media.published_at,
        ),
    )
    with pytest.raises(ValueError, match="unverified"):
        validate_event_sources(unverified, [media])

    community_primary = NewsEvent(
        id="event-community-primary",
        candidate_ids=[official.id, community.id],
        category="models",
        title_zh="已有官方确认",
        summary_zh="摘要",
        why_it_matters_zh="重要性",
        importance_score=90,
        confirmation_status=ConfirmationStatus.PRIMARY_CONFIRMED,
        primary_source=SourceRef(
            source_id=community.source_id,
            source_name=community.source_name,
            title=community.title,
            url=community.url,
            published_at=community.published_at,
        ),
    )
    with pytest.raises(ValueError, match="community source"):
        validate_event_sources(community_primary, [official, community])
