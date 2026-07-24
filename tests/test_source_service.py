from datetime import UTC, datetime
from pathlib import Path

import httpx

from ai_news_sniffer.config import load_settings
from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.source_health import SourceHealthStore
from ai_news_sniffer.source_service import collect_source_candidates

ROOT = Path(__file__).parents[1]
SINCE = datetime(2026, 7, 22, tzinfo=UTC)
UNTIL = datetime(2026, 7, 24, tzinfo=UTC)


class FakeAdapter:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def fetch(
        self,
        source: SourceConfig,
        since: datetime,
        until: datetime,
    ) -> list[RawArticle]:
        if self.should_fail:
            raise RuntimeError("fixture failure")
        return [
            RawArticle(
                source_id=source.id,
                source_name=source.name,
                source_group=source.group,
                independence_group=source.id,
                title=f"{source.name} model release",
                url=f"https://example.com/{source.id}",
                published_at=UNTIL,
                fetched_at=UNTIL,
                excerpt="A reasoning model release.",
                categories=["models"],
            )
        ]


def test_collection_isolates_failure_and_applies_budget(tmp_path: Path) -> None:
    settings = load_settings(ROOT / "config")
    health_store = SourceHealthStore(tmp_path)
    for number in range(6):
        health_store.record_failure(
            "anthropic-news",
            f"prior failure {number}",
            UNTIL,
        )

    def factory(source: SourceConfig, client: httpx.Client) -> FakeAdapter:
        return FakeAdapter(should_fail=source.id == "anthropic-news")

    result = collect_source_candidates(
        settings=settings,
        runtime_root=tmp_path,
        since=SINCE,
        until=UNTIL,
        profile="light",
        client=httpx.Client(),
        adapter_factory=factory,
    )

    assert len(result.enabled_source_ids) == 12
    assert "anthropic-news" in result.failures
    assert result.fetched_count == 11
    assert len(result.budgeted.articles) <= 20
    assert result.budgeted.prompt_chars <= 60000
    assert result.newly_auto_paused_source_ids == ["anthropic-news"]
    assert (tmp_path / "source-runs" / "2026-07-24.json").exists()


def test_zero_candidate_override_uses_profile_default(tmp_path: Path) -> None:
    settings = load_settings(ROOT / "config")

    def factory(source: SourceConfig, client: httpx.Client) -> FakeAdapter:
        return FakeAdapter()

    result = collect_source_candidates(
        settings=settings,
        runtime_root=tmp_path,
        since=SINCE,
        until=UNTIL,
        profile="full",
        max_ai_candidates=0,
        client=httpx.Client(),
        adapter_factory=factory,
    )

    assert len(result.budgeted.articles) == result.filtered_count
