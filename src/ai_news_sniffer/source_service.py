import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from ai_news_sniffer.dedup import deduplicate_articles
from ai_news_sniffer.models import Settings, SourceCollection, SourceConfig
from ai_news_sniffer.normalization import normalize_article
from ai_news_sniffer.scoring import score_articles
from ai_news_sniffer.source_budget import apply_source_budget
from ai_news_sniffer.source_discovery import discover_candidate_sources
from ai_news_sniffer.source_health import SourceHealthStore
from ai_news_sniffer.source_registry import resolve_sources
from ai_news_sniffer.sources.base import SourceAdapter, build_source_adapter

AdapterFactory = Callable[[SourceConfig, httpx.Client], SourceAdapter]


def collect_source_candidates(
    settings: Settings,
    runtime_root: Path,
    since: datetime,
    until: datetime,
    profile: str | None = None,
    include_sources: set[str] | None = None,
    exclude_sources: set[str] | None = None,
    max_ai_candidates: int | None = None,
    seen_fingerprints: set[str] | None = None,
    client: httpx.Client | None = None,
    adapter_factory: AdapterFactory = build_source_adapter,
    live_audit: bool = False,
) -> SourceCollection:
    health_store = SourceHealthStore(runtime_root)
    auto_paused_before = health_store.auto_paused_ids()
    selected = resolve_sources(
        settings.sources,
        profile_override=profile,
        include_sources=include_sources,
        exclude_sources=exclude_sources,
        auto_paused=set() if live_audit else health_store.auto_paused_ids(),
    )
    owned_client = client is None
    http_client = client or httpx.Client(follow_redirects=True)
    raw_articles = []
    failures: dict[str, str] = {}
    newly_auto_paused_source_ids: list[str] = []
    try:
        for source in selected:
            try:
                fetched = adapter_factory(source, http_client).fetch(source, since, until)
                raw_articles.extend(fetched)
                if live_audit:
                    health_store.clear_pause_after_audit(source.id, until)
                else:
                    health_store.record_success(source.id, until)
            except Exception as exc:  # noqa: BLE001 — per-source isolation: one bad adapter must not kill the full collection run
                message = f"{type(exc).__name__}: {str(exc)[:200]}"
                failures[source.id] = message
                health = health_store.record_failure(source.id, message, until)
                if health.auto_paused and source.id not in auto_paused_before:
                    newly_auto_paused_source_ids.append(source.id)
    finally:
        if owned_client:
            http_client.close()

    normalized = [normalize_article(item) for item in raw_articles]
    deduplicated = deduplicate_articles(normalized, seen_fingerprints or set())
    source_weights = {item.id: item.weight for item in selected}
    scored = score_articles(deduplicated, settings.interests, source_weights, until)
    resolved_profile = profile or settings.sources.active_profile
    candidate_limit = settings.sources.profile_candidate_limits[resolved_profile]
    if max_ai_candidates not in (None, 0):
        candidate_limit = max_ai_candidates
    budgeted = apply_source_budget(
        scored,
        settings.app.editorial,
        max_candidates_override=candidate_limit,
    )
    known_domains = {
        (urlsplit(str(item.url)).hostname or "").casefold()
        for item in settings.sources.sources
    }
    discover_candidate_sources(
        normalized,
        known_domains,
        runtime_root / "candidate-sources.json",
        until,
    )
    result = SourceCollection(
        enabled_source_ids=[item.id for item in selected],
        fetched_count=len(raw_articles),
        normalized_count=len(normalized),
        filtered_count=len(scored),
        budgeted=budgeted,
        failures=failures,
        newly_auto_paused_source_ids=sorted(newly_auto_paused_source_ids),
    )
    run_path = runtime_root / "source-runs" / f"{until.date().isoformat()}.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result
