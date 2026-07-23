from ai_news_sniffer.models import (
    Article,
    ConfirmationStatus,
    NewsEvent,
    SourceGroup,
    SourceRef,
)

PRIMARY_GROUPS = {SourceGroup.OFFICIAL, SourceGroup.RESEARCH}


def _matching_candidate(
    source_ref: SourceRef,
    candidates: list[Article],
) -> Article | None:
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.source_id == source_ref.source_id
            and candidate.source_name == source_ref.source_name
            and candidate.title == source_ref.title
            and str(candidate.url) == str(source_ref.url)
            and candidate.published_at == source_ref.published_at
        ),
        None,
    )


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
    candidates = [by_id[item_id] for item_id in event.candidate_ids]
    primary_candidate = _matching_candidate(event.primary_source, candidates)
    if primary_candidate is None:
        raise ValueError("source reference is not backed by a candidate")
    if any(
        _matching_candidate(source_ref, candidates) is None
        for source_ref in event.related_sources
    ):
        raise ValueError("source reference is not backed by a candidate")
    expected = confirmation_status(candidates)
    if primary_candidate.source_group == SourceGroup.COMMUNITY:
        raise ValueError("community source cannot be primary")
    if expected == ConfirmationStatus.UNVERIFIED:
        raise ValueError("unverified event cannot be published")
    if event.confirmation_status != expected:
        raise ValueError("confirmation status does not match candidate evidence")
