from datetime import datetime

from rapidfuzz.fuzz import token_set_ratio

from ai_news_sniffer.models import Article, InterestsConfig

IMPACT_TERMS = {
    "release",
    "launch",
    "open-source",
    "breakthrough",
    "acquire",
    "funding",
    "regulation",
    "发布",
    "开源",
    "突破",
    "融资",
    "收购",
    "监管",
}
TECH_CATEGORIES = {
    "models",
    "products",
    "research",
    "open-source",
    "developer-tools",
}


def _contains(text: str, terms: list[str] | set[str]) -> int:
    folded = text.casefold()
    return sum(1 for term in terms if term.casefold() in folded)


def score_articles(
    articles: list[Article],
    interests: InterestsConfig,
    source_weights: dict[str, float],
    now: datetime,
) -> list[Article]:
    ranked: list[Article] = []
    for article in articles:
        text = f"{article.title} {article.excerpt}"
        if _contains(text, interests.exclude_terms):
            continue
        source_score = source_weights.get(article.source_id, 0)
        impact_score = min(25, _contains(text, IMPACT_TERMS) * 8)
        relevance_score = min(
            20,
            (
                _contains(text, interests.include_terms)
                + _contains(text, interests.entities)
                + _contains(" ".join(article.categories), interests.topics)
            )
            * 4,
        )
        technical_score = (
            15 if TECH_CATEGORIES.intersection(article.categories) else 8
        )
        corroboration_score = min(
            10,
            sum(
                5
                for other in articles
                if other.id != article.id
                and other.independence_group != article.independence_group
                and token_set_ratio(
                    article.normalized_title,
                    other.normalized_title,
                )
                >= 70
            ),
        )
        age_hours = max(
            0,
            (now - article.published_at).total_seconds() / 3600,
        )
        recency_score = max(0, 5 - age_hours / 10)
        article.rule_score = min(
            100,
            source_score
            + impact_score
            + relevance_score
            + technical_score
            + corroboration_score
            + recency_score,
        )
        ranked.append(article)
    return sorted(ranked, key=lambda item: item.rule_score, reverse=True)
