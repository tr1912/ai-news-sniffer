from ai_news_sniffer.models import (
    Article,
    ConfirmationStatus,
    NewsEvent,
    SourceGroup,
)

PRIMARY_GROUPS = {SourceGroup.OFFICIAL, SourceGroup.RESEARCH}


def confirmation_status(
    cluster: list[Article],
) -> ConfirmationStatus:
    if any(item.source_group in PRIMARY_GROUPS for item in cluster):
        return ConfirmationStatus.PRIMARY_CONFIRMED
    independent_media = {
        item.independence_group
        for item in cluster
        if item.source_group == SourceGroup.MEDIA
    }
    if len(independent_media) >= 2:
        return ConfirmationStatus.CROSS_CONFIRMED
    return ConfirmationStatus.UNVERIFIED


def validate_event_sources(
    event: NewsEvent,
    articles: list[Article],
) -> None:
    by_id = {item.id: item for item in articles}
    unknown = set(event.candidate_ids) - by_id.keys()
    if unknown:
        raise ValueError(f"unknown candidate ids: {sorted(unknown)}")
    source_ids = {by_id[item_id].source_id for item_id in event.candidate_ids}
    if event.primary_source.source_id not in source_ids:
        raise ValueError("primary source is not backed by a candidate")
    expected = confirmation_status([by_id[item_id] for item_id in event.candidate_ids])
    primary_candidate = next(
        item
        for item in by_id.values()
        if item.source_id == event.primary_source.source_id
        and item.id in event.candidate_ids
    )
    if primary_candidate.source_group == SourceGroup.COMMUNITY:
        raise ValueError("community source cannot be primary")
    if expected == ConfirmationStatus.UNVERIFIED:
        raise ValueError("unverified event cannot be published")
    if event.confirmation_status != expected:
        raise ValueError("confirmation status does not match candidate evidence")
