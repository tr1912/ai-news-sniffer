from datetime import UTC, date, datetime
from pathlib import Path

from ai_news_sniffer.models import RawArticle, RunStatus
from ai_news_sniffer.pipeline import Pipeline


class FixtureAdapter:
    def fetch(self, source, since, until):
        return [
            RawArticle(
                source_id=source.id,
                source_name=source.name,
                source_group=source.group,
                independence_group=source.independence_group or source.id,
                title="Official AI model release",
                url="https://example.com/model",
                published_at=datetime(2026, 7, 23, 10, tzinfo=UTC),
                fetched_at=datetime(2026, 7, 23, 13, tzinfo=UTC),
                excerpt="The official release notes.",
                categories=["models"],
            )
        ]


class FixtureEditorial:
    def edit(self, candidates, min_items, max_items):
        from ai_news_sniffer.selection import build_degraded_events

        return "今日 AI 要闻", build_degraded_events(candidates, max_items)


def test_pipeline_builds_prepared_report_without_network(
    tmp_path: Path,
    settings,
) -> None:
    pipeline = Pipeline(
        settings=settings,
        runtime_dir=tmp_path / "runtime",
        output_dir=tmp_path / "site",
        templates_root=Path("templates"),
        adapter_factory=lambda source, client: FixtureAdapter(),
        editorial_service=FixtureEditorial(),
    )

    record = pipeline.build(date(2026, 7, 23), dry_run=False)

    assert record.status is RunStatus.PREPARED
    assert (tmp_path / "site/2026/07/23/index.html").exists()


def test_pipeline_dry_run_does_not_write_fingerprints(
    tmp_path: Path,
    settings,
) -> None:
    runtime_dir = tmp_path / "runtime"
    pipeline = Pipeline(
        settings=settings,
        runtime_dir=runtime_dir,
        output_dir=tmp_path / "site",
        templates_root=Path("templates"),
        adapter_factory=lambda source, client: FixtureAdapter(),
        editorial_service=FixtureEditorial(),
    )

    pipeline.build(date(2026, 7, 23), dry_run=True)

    assert not (runtime_dir / "seen_fingerprints.json").exists()
