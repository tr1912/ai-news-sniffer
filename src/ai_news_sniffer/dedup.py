from rapidfuzz.fuzz import token_set_ratio

from ai_news_sniffer.models import Article


def deduplicate_articles(
    articles: list[Article],
    seen_fingerprints: set[str],
    title_threshold: float = 92,
) -> list[Article]:
    kept: list[Article] = []
    seen_urls: set[str] = set()
    for candidate in sorted(
        articles,
        key=lambda item: item.published_at,
        reverse=True,
    ):
        if candidate.fingerprint in seen_fingerprints:
            continue
        if str(candidate.canonical_url) in seen_urls:
            continue
        if any(
            token_set_ratio(
                candidate.normalized_title,
                item.normalized_title,
            )
            >= title_threshold
            for item in kept
        ):
            continue
        kept.append(candidate)
        seen_urls.add(str(candidate.canonical_url))
    return kept
