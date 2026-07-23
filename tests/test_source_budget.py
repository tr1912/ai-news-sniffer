from datetime import UTC, datetime

from ai_news_sniffer.models import Article, EditorialBudget, SourceGroup
from ai_news_sniffer.source_budget import apply_source_budget

NOW = datetime(2026, 7, 23, tzinfo=UTC)


def article(number: int, score: float, excerpt: str) -> Article:
    return Article(
        id=str(number),
        source_id=f"source-{number}",
        source_name=f"Source {number}",
        source_group=SourceGroup.OFFICIAL,
        independence_group=f"source-{number}",
        title=f"Title {number}",
        url=f"https://example.com/{number}",
        canonical_url=f"https://example.com/{number}",
        normalized_title=f"title {number}",
        fingerprint=str(number) * 64,
        published_at=NOW,
        fetched_at=NOW,
        excerpt=excerpt,
        rule_score=score,
    )


def test_budget_enforces_count_item_and_total_character_caps() -> None:
    result = apply_source_budget(
        [
            article(1, 90, "a" * 1000),
            article(2, 80, "b" * 1000),
            article(3, 70, "c" * 1000),
        ],
        EditorialBudget(
            max_candidates=3,
            max_excerpt_chars_per_item=200,
            max_total_prompt_chars=450,
        ),
    )

    assert [item.id for item in result.articles] == ["1", "2"]
    assert all(len(item.excerpt) <= 200 for item in result.articles)
    assert result.prompt_chars <= 450
    assert result.estimated_input_tokens == max(1, result.prompt_chars // 4)


def test_one_run_candidate_override_can_raise_or_lower_profile_default() -> None:
    articles = [article(number, 100 - number, "short") for number in range(50)]
    budget = EditorialBudget(
        max_candidates=30,
        max_excerpt_chars_per_item=200,
        max_total_prompt_chars=60000,
    )

    assert len(apply_source_budget(articles, budget, 20).articles) == 20
    assert len(apply_source_budget(articles, budget, 40).articles) == 40
