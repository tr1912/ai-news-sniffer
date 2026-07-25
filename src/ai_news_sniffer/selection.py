import re
from collections import Counter

from ai_news_sniffer.models import (
    Article,
    ConfirmationStatus,
    NewsEvent,
    SourceGroup,
    SourceRef,
)


def _clean_degraded_excerpt(text: str, max_chars: int = 350) -> str:
    stripped = re.sub(r"<[^>]+>", "", text)
    stripped = re.sub(r"\*\*([^*]+)\*\*", r"\1", stripped)
    stripped = re.sub(r"\*([^*]+)\*", r"\1", stripped)
    stripped = re.sub(r"__([^_]+)__", r"\1", stripped)
    stripped = re.sub(r"_([^_]+)_", r"\1", stripped)
    stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
    stripped = re.sub(r"`([^`]+)`", r"\1", stripped)
    stripped = re.sub(r"^#{1,6}\s+", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^[-*+]\s+", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"---+", "", stripped)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    stripped = " ".join(stripped.split())
    return stripped[:max_chars].strip()


def select_diverse_events(
    events: list[NewsEvent],
    max_items: int,
    max_per_category: int = 3,
    max_per_source: int = 2,
) -> list[NewsEvent]:
    category_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    selected: list[NewsEvent] = []
    for event in sorted(events, key=lambda item: item.importance_score, reverse=True):
        if event.confirmation_status == ConfirmationStatus.UNVERIFIED:
            continue
        source_id = event.primary_source.source_id
        if category_counts[event.category] >= max_per_category:
            continue
        if source_counts[source_id] >= max_per_source:
            continue
        selected.append(event)
        category_counts[event.category] += 1
        source_counts[source_id] += 1
        if len(selected) == max_items:
            break
    return selected


def build_degraded_events(
    articles: list[Article],
    max_items: int,
) -> list[NewsEvent]:
    events: list[NewsEvent] = []
    for article in articles[:max_items]:
        if article.source_group not in {
            SourceGroup.OFFICIAL,
            SourceGroup.RESEARCH,
        }:
            continue
        events.append(
            NewsEvent(
                id=f"degraded-{article.id}",
                candidate_ids=[article.id],
                category=article.categories[0] if article.categories else "other",
                title_zh=article.title,
                summary_zh=_clean_degraded_excerpt(article.excerpt),
                why_it_matters_zh="",
                importance_score=article.rule_score,
                confirmation_status=ConfirmationStatus.PRIMARY_CONFIRMED,
                primary_source=SourceRef(
                    source_id=article.source_id,
                    source_name=article.source_name,
                    title=article.title,
                    url=article.url,
                    published_at=article.published_at,
                ),
            )
        )
    return events
