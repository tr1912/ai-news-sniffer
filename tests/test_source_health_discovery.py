from datetime import UTC, datetime
from pathlib import Path

from ai_news_sniffer.models import Article, SourceGroup
from ai_news_sniffer.source_discovery import discover_candidate_sources
from ai_news_sniffer.source_health import SourceHealthStore

NOW = datetime(2026, 7, 23, tzinfo=UTC)


def article_with_upstream(url: str, source_id: str = "hacker-news") -> Article:
    return Article(
        id="a1",
        source_id=source_id,
        source_name="Hacker News",
        source_group=SourceGroup.COMMUNITY,
        independence_group="hacker-news",
        title="A discovered official source",
        url="https://news.ycombinator.com/item?id=1",
        canonical_url="https://news.ycombinator.com/item?id=1",
        normalized_title="a discovered official source",
        fingerprint="a" * 64,
        published_at=NOW,
        fetched_at=NOW,
        upstream_urls=[url],
    )


def test_health_degrades_at_three_and_auto_pauses_at_seven(tmp_path: Path) -> None:
    store = SourceHealthStore(tmp_path)

    for number in range(7):
        health = store.record_failure("broken-source", f"failure {number}", NOW)

    assert health.degraded is True
    assert health.auto_paused is True
    assert store.auto_paused_ids() == {"broken-source"}

    cleared = store.clear_pause_after_audit("broken-source", NOW)
    assert cleared.auto_paused is False
    assert cleared.consecutive_failures == 0


def test_success_resets_degradation_without_clearing_auto_pause(tmp_path: Path) -> None:
    store = SourceHealthStore(tmp_path)
    for number in range(7):
        store.record_failure("broken-source", f"failure {number}", NOW)

    health = store.record_success("broken-source", NOW)

    assert health.consecutive_failures == 0
    assert health.degraded is False
    assert health.auto_paused is True
    assert health.last_error is None


def test_failure_after_pause_does_not_reactivate_source(tmp_path: Path) -> None:
    store = SourceHealthStore(tmp_path)
    for number in range(7):
        store.record_failure("broken-source", f"failure {number}", NOW)
    store.record_success("broken-source", NOW)

    health = store.record_failure("broken-source", "failure after success", NOW)

    assert health.auto_paused is True
    assert store.auto_paused_ids() == {"broken-source"}


def test_discovery_records_unknown_domain_without_enabling_it(tmp_path: Path) -> None:
    candidates = discover_candidate_sources(
        [article_with_upstream("https://new-lab.example/releases/model")],
        known_domains={"news.ycombinator.com"},
        output_path=tmp_path / "candidate-sources.json",
        now=NOW,
    )

    assert candidates[0].domain == "new-lab.example"
    assert candidates[0].enabled is False
    assert candidates[0].referring_source_ids == {"hacker-news"}
    assert (tmp_path / "candidate-sources.json").exists()


def test_discovery_merges_referrers_and_preserves_first_seen(tmp_path: Path) -> None:
    output_path = tmp_path / "candidate-sources.json"
    discover_candidate_sources(
        [article_with_upstream("https://new-lab.example/releases/model")],
        known_domains=set(),
        output_path=output_path,
        now=NOW,
    )
    later = datetime(2026, 7, 24, tzinfo=UTC)

    candidates = discover_candidate_sources(
        [article_with_upstream("https://new-lab.example/blog/update", "reddit")],
        known_domains=set(),
        output_path=output_path,
        now=later,
    )

    candidate = candidates[0]
    assert candidate.first_seen_at == NOW
    assert candidate.last_seen_at == later
    assert candidate.referring_source_ids == {"hacker-news", "reddit"}
    assert candidate.enabled is False
