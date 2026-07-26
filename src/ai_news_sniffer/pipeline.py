import hashlib
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from ai_news_sniffer.models import (
    DailyReport,
    RunRecord,
    RunStatus,
    Settings,
    SourceConfig,
)
from ai_news_sniffer.providers.editorial import EditorialService
from ai_news_sniffer.rendering.site import SiteRenderer
from ai_news_sniffer.selection import build_degraded_events, select_diverse_events
from ai_news_sniffer.source_service import collect_source_candidates
from ai_news_sniffer.sources.base import SourceAdapter, build_source_adapter
from ai_news_sniffer.state import RuntimeStore


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        runtime_dir: Path,
        output_dir: Path,
        templates_root: Path,
        editorial_service: EditorialService,
        adapter_factory: Callable[
            [SourceConfig, httpx.Client],
            SourceAdapter,
        ] = build_source_adapter,
    ) -> None:
        self.settings = settings
        self.runtime_dir = runtime_dir
        self.store = RuntimeStore(runtime_dir)
        self.output_dir = output_dir
        url_path = urlparse(str(settings.app.public_base_url)).path.rstrip("/")
        base_path = url_path if url_path else "/"
        self.renderer = SiteRenderer(templates_root, base_path=base_path)
        self.editorial_service = editorial_service
        self.adapter_factory = adapter_factory

    def build(
        self,
        target_date: date,
        dry_run: bool,
        source_profile: str | None = None,
        include_sources: set[str] | None = None,
        exclude_sources: set[str] | None = None,
        max_ai_candidates: int | None = None,
    ) -> RunRecord:
        now = datetime.now(UTC)
        timezone = ZoneInfo(self.settings.app.timezone)
        local_start = datetime.combine(target_date, time.min, tzinfo=timezone)
        until = (local_start + timedelta(days=1)).astimezone(UTC)
        since = until - timedelta(hours=self.settings.app.lookback_hours)
        seen_fingerprints = self.store.load_seen_fingerprints(
            excluding_date=target_date
        )
        with httpx.Client(
            headers={"User-Agent": "ai-news-sniffer/0.1"},
            follow_redirects=True,
        ) as client:
            collection = collect_source_candidates(
                settings=self.settings,
                runtime_root=self.runtime_dir,
                since=since,
                until=until,
                profile=source_profile,
                include_sources=include_sources,
                exclude_sources=exclude_sources,
                max_ai_candidates=max_ai_candidates,
                seen_fingerprints=seen_fingerprints,
                client=client,
                adapter_factory=self.adapter_factory,
            )
        ranked = collection.budgeted.articles
        warnings = [
            f"source {source_id} failed: {error}"
            for source_id, error in sorted(collection.failures.items())
        ]
        warnings.extend(
            f"maintenance required: source {source_id} auto-paused after 7 failures"
            for source_id in collection.newly_auto_paused_source_ids
        )
        degraded = False
        try:
            summary, events = self.editorial_service.edit(
                ranked,
                self.settings.app.min_items,
                self.settings.app.max_items,
            )
        except (RuntimeError, ValueError) as error:
            degraded = True
            warnings.append(
                f"model chain failed: {error}. "
                f"Falling back to degraded mode with {len(ranked)} raw candidates."
            )
            summary = "模型暂不可用，本期仅展示来源标题与摘要。"
            events = build_degraded_events(ranked, self.settings.app.max_items)
        events = select_diverse_events(events, self.settings.app.max_items)
        if degraded and not events:
            summary = (
                "今日未找到符合发布标准的已验证事件。"
                "多数高质量源处于暂停/解析失败状态，已自动尝试恢复。"
            )
        event_key = "|".join(
            sorted(candidate_id for event in events for candidate_id in event.candidate_ids)
        )
        run_hash = hashlib.sha256(event_key.encode()).hexdigest()[:8]
        run_id = f"{target_date.isoformat()}-{run_hash}"
        report = DailyReport(
            date=target_date,
            generated_at=now,
            run_id=run_id,
            daily_summary_zh=summary,
            events=events,
            degraded=degraded,
            warnings=warnings,
            source_coverage={
                "enabled": len(collection.enabled_source_ids),
                "fetched": collection.fetched_count,
                "normalized": collection.normalized_count,
                "filtered": collection.filtered_count,
                "ai_candidates": len(collection.budgeted.articles),
                "prompt_chars": collection.budgeted.prompt_chars,
                "estimated_input_tokens": (
                    collection.budgeted.estimated_input_tokens
                ),
                "failed_source_ids": sorted(collection.failures),
                "newly_auto_paused_source_ids": (
                    collection.newly_auto_paused_source_ids
                ),
            },
        )
        for warning in report.warnings:
            print(f"[warning] {warning}", file=sys.stderr)
        print(
            f"[summary] events={len(report.events)} "
            f"degraded={report.degraded} "
            f"coverage={report.source_coverage}",
            file=sys.stderr,
        )
        if dry_run:
            reports_for_render = self.store.load_reports() + [report]
            self.renderer.render(
                reports_for_render,
                self.settings.app.template,
                self.output_dir,
            )
            return RunRecord(
                run_id=run_id,
                target_date=target_date,
                status=RunStatus.PREPARED,
                created_at=now,
                updated_at=now,
                report_path=f"reports/{target_date.isoformat()}.json",
                pending_fingerprints=sorted(
                    {item.fingerprint for item in ranked}
                ),
            )
        record = self.store.save_prepared(
            report,
            {item.fingerprint for item in ranked},
        )
        reports = self.store.load_reports()
        self.renderer.render(
            reports,
            self.settings.app.template,
            self.output_dir,
        )
        return record
