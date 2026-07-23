from ai_news_sniffer.models import Article, BudgetedCandidates, EditorialBudget


def _prompt_chars(article: Article) -> int:
    return len(article.title) + len(article.source_name) + len(article.excerpt) + 16


def apply_source_budget(
    articles: list[Article],
    budget: EditorialBudget,
    max_candidates_override: int | None = None,
) -> BudgetedCandidates:
    limit = budget.max_candidates
    if max_candidates_override is not None:
        limit = max(1, min(100, max_candidates_override))

    selected: list[Article] = []
    total_chars = 0
    for article in sorted(articles, key=lambda item: item.rule_score, reverse=True):
        remaining_chars = budget.max_total_prompt_chars - total_chars
        fixed_size = _prompt_chars(article.model_copy(update={"excerpt": ""}))
        if fixed_size > remaining_chars:
            continue

        excerpt_limit = min(
            budget.max_excerpt_chars_per_item,
            remaining_chars - fixed_size,
        )
        clipped = article.model_copy(update={"excerpt": article.excerpt[:excerpt_limit]})
        size = _prompt_chars(clipped)
        selected.append(clipped)
        total_chars += size
        if len(selected) == limit:
            break

    return BudgetedCandidates(
        articles=selected,
        prompt_chars=total_chars,
        estimated_input_tokens=max(1, total_chars // 4),
    )
