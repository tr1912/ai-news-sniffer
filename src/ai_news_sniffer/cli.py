import argparse
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from ai_news_sniffer.config import load_settings
from ai_news_sniffer.models import NotificationPayload, RunStatus
from ai_news_sniffer.notifications.base import build_channels, send_all
from ai_news_sniffer.providers.base import ProviderChain
from ai_news_sniffer.providers.editorial import EditorialService
from ai_news_sniffer.providers.openai_compatible import OpenAICompatibleProvider
from ai_news_sniffer.rendering.site import SiteRenderer
from ai_news_sniffer.source_cli import add_source_commands, run_source_command
from ai_news_sniffer.state import RuntimeStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-news-sniffer")
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--runtime-dir", type=Path, default=Path("runtime-data"))
    parser.add_argument("--output-dir", type=Path, default=Path("build/site"))
    parser.add_argument("--templates-dir", type=Path, default=Path("templates"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_source_commands(subparsers)
    build = subparsers.add_parser("build")
    build.add_argument("--target-date", type=date.fromisoformat)
    build.add_argument("--dry-run", action="store_true")
    build.add_argument(
        "--source-profile",
        choices=["light", "balanced", "full"],
    )
    build.add_argument("--include-sources", default="")
    build.add_argument("--exclude-sources", default="")
    build.add_argument("--max-ai-candidates", type=int)
    verify = subparsers.add_parser("verify-url")
    verify.add_argument("url")
    published = subparsers.add_parser("mark-published")
    published.add_argument("--run-id", required=True)
    published.add_argument("--report-url", required=True)
    notify = subparsers.add_parser("notify")
    notify.add_argument("--run-id", required=True)
    failure = subparsers.add_parser("notify-failure")
    failure.add_argument("--message", required=True)
    return parser


def verify_report_url(url: str, client: httpx.Client) -> None:
    last_error: Exception | None = None
    for attempt in range(1, 7):
        try:
            response = client.get(url, follow_redirects=True, timeout=30)
            response.raise_for_status()
            if "AI 每日情报" not in response.text:
                raise RuntimeError(
                    "published page does not contain the expected marker"
                )
            return
        except (httpx.HTTPError, RuntimeError) as error:
            last_error = error
            if attempt < 6:
                time.sleep(10)
    raise RuntimeError(
        f"published report was not reachable: {type(last_error).__name__}"
    )


def _provider_chain(settings) -> ProviderChain:
    by_id = {item.id: item for item in settings.providers.providers}
    return ProviderChain(
        [
            OpenAICompatibleProvider(by_id[provider_id])
            for provider_id in settings.providers.fallback_order
        ]
    )


def _source_ids(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "sources":
        return run_source_command(args)
    settings = load_settings(args.config_dir)
    store = RuntimeStore(args.runtime_dir)
    if args.command == "verify-url":
        with httpx.Client() as client:
            verify_report_url(args.url, client)
        return 0
    if args.command == "mark-published":
        with httpx.Client() as client:
            verify_report_url(args.report_url, client)
        store.mark_published(args.run_id, args.report_url)
        return 0
    if args.command == "build":
        from ai_news_sniffer.pipeline import Pipeline

        target_date = args.target_date or datetime.now(
            ZoneInfo(settings.app.timezone)
        ).date()
        prompt = Path("prompts/editorial.md").read_text(encoding="utf-8")
        pipeline = Pipeline(
            settings=settings,
            runtime_dir=args.runtime_dir,
            output_dir=args.output_dir,
            templates_root=args.templates_dir,
            editorial_service=EditorialService(
                _provider_chain(settings), prompt
            ),
        )
        print(
            pipeline.build(
                target_date,
                args.dry_run,
                source_profile=args.source_profile,
                include_sources=_source_ids(args.include_sources),
                exclude_sources=_source_ids(args.exclude_sources),
                max_ai_candidates=args.max_ai_candidates or None,
            ).model_dump_json()
        )
        return 0
    if args.command == "notify-failure":
        payload = NotificationPayload(
            run_id=f"failure-{datetime.now(ZoneInfo(settings.app.timezone)):%Y%m%d%H%M%S}",
            date=datetime.now(ZoneInfo(settings.app.timezone)).date(),
            status=RunStatus.FAILED,
            title="AI 日报运行失败",
            daily_summary=args.message,
            top_items=[],
            report_url=settings.app.public_base_url,
            generated_at=datetime.now(ZoneInfo("UTC")),
        )
        with httpx.Client() as client:
            results = send_all(
                build_channels(settings.channels.channels, client),
                payload,
                args.message,
            )
        return 0 if any(result.success for result in results) else 2
    if args.command == "notify":
        record = store.load_run(args.run_id)
        if record.status is RunStatus.NOTIFIED:
            return 0
        if record.status not in {
            RunStatus.PUBLISHED,
            RunStatus.PARTIALLY_NOTIFIED,
        } or not record.report_url:
            raise RuntimeError("run must be published before notification")
        report = next(
            item for item in store.load_reports() if item.run_id == args.run_id
        )
        report.report_url = record.report_url
        payload = NotificationPayload(
            run_id=report.run_id,
            date=report.date,
            status=record.status,
            title=f"AI 日报 · {report.date}",
            daily_summary=report.daily_summary_zh,
            top_items=report.events[:3],
            report_url=record.report_url,
            generated_at=report.generated_at,
        )
        message = SiteRenderer(args.templates_dir).render_notification(
            report,
            settings.app.template,
        )
        previous_successes = [
            result for result in record.channel_results if result.success
        ]
        failed_ids = {
            result.channel_id
            for result in record.channel_results
            if not result.success
        }
        channel_configs = settings.channels.channels
        if failed_ids:
            channel_configs = [
                config
                for config in channel_configs
                if config.id in failed_ids
            ]
        with httpx.Client() as client:
            results = previous_successes + send_all(
                build_channels(channel_configs, client),
                payload,
                message,
            )
        store.mark_notified(args.run_id, results)
        return 0 if all(result.success for result in results) else 2
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
