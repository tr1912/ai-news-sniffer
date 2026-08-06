import argparse
import sys
import time
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
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
    notify.add_argument("--force", action="store_true")
    failure = subparsers.add_parser("notify-failure")
    failure.add_argument("--message", required=True)
    return parser


def _extract_path(public_base_url: str) -> str:
    url_path = urlparse(str(public_base_url)).path.rstrip("/")
    return url_path if url_path else "/"


_REPORT_MARKER = "AI 每日情报"
_VERIFY_BUDGET_SECONDS = 480.0
_REQUEST_TIMEOUT_SECONDS = 30.0
_TRANSIENT_STATUS_CODES = {404, 408, 425, 429}


def _validated_report_url(url: str) -> httpx.URL:
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, ValueError) as error:
        raise ValueError(str(error)) from error
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise ValueError("URL must use http or https and include a host")
    return parsed


def _is_transient_status(status_code: int) -> bool:
    return status_code in _TRANSIENT_STATUS_CODES or 500 <= status_code <= 599


def _log_url_verification(
    *,
    attempt: int,
    classification: str,
    request_url: str,
    final_url: str | None,
    status_code: int | None,
    error: str | None = None,
    next_delay_seconds: float | None = None,
    remaining_seconds: float | None = None,
) -> None:
    fields = [
        "[verify-url]",
        f"attempt={attempt}",
        f"classification={classification}",
        f"status={status_code if status_code is not None else 'unavailable'}",
        f"request_url={request_url}",
        f"final_url={final_url or 'unavailable'}",
    ]
    if error is not None:
        fields.append(f"error={error}")
    if next_delay_seconds is not None:
        fields.append(f"next_delay_seconds={next_delay_seconds:.1f}")
    if remaining_seconds is not None:
        fields.append(f"remaining_seconds={remaining_seconds:.1f}")
    print(" ".join(fields), file=sys.stderr)


def verify_report_url(
    url: str,
    client: httpx.Client,
    *,
    max_wait_seconds: float = _VERIFY_BUDGET_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    if max_wait_seconds <= 0:
        raise ValueError("max_wait_seconds must be positive")
    try:
        request_url = str(_validated_report_url(url))
    except ValueError as error:
        _log_url_verification(
            attempt=0,
            classification="permanent",
            request_url=url,
            final_url=None,
            status_code=None,
            error="invalid-url",
        )
        raise RuntimeError(f"invalid published report URL: {error}") from error

    deadline = monotonic() + max_wait_seconds
    previous_delay = 0.0
    next_delay = 1.0
    attempt = 0
    last_detail = "no response"

    while True:
        attempt += 1
        remaining_before_request = max(0.0, deadline - monotonic())
        request_timeout = min(
            _REQUEST_TIMEOUT_SECONDS,
            max(0.001, remaining_before_request),
        )
        try:
            response = client.get(
                request_url,
                follow_redirects=True,
                timeout=request_timeout,
            )
        except (
            httpx.InvalidURL,
            httpx.UnsupportedProtocol,
            httpx.TooManyRedirects,
        ) as error:
            error_name = type(error).__name__
            _log_url_verification(
                attempt=attempt,
                classification="permanent",
                request_url=request_url,
                final_url=None,
                status_code=None,
                error=error_name,
            )
            raise RuntimeError(
                "published report URL has a permanent configuration error: "
                f"error={error_name} request_url={request_url}"
            ) from error
        except httpx.TransportError as error:
            error_name = type(error).__name__
            final_url = None
            status_code = None
            transient_error = error_name
            last_detail = f"error={error_name} request_url={request_url}"
        else:
            final_url = str(response.url)
            status_code = response.status_code
            if 200 <= status_code <= 299 and _REPORT_MARKER in response.text:
                _log_url_verification(
                    attempt=attempt,
                    classification="success",
                    request_url=request_url,
                    final_url=final_url,
                    status_code=status_code,
                )
                return
            if _is_transient_status(status_code) or 200 <= status_code <= 299:
                transient_error = (
                    "missing-marker"
                    if 200 <= status_code <= 299
                    else f"http-{status_code}"
                )
                last_detail = f"status={status_code} final_url={final_url}"
            else:
                _log_url_verification(
                    attempt=attempt,
                    classification="permanent",
                    request_url=request_url,
                    final_url=final_url,
                    status_code=status_code,
                    error=f"http-{status_code}",
                )
                raise RuntimeError(
                    "published report URL has a permanent configuration error: "
                    f"status={status_code} request_url={request_url} "
                    f"final_url={final_url}"
                )

        remaining_seconds = max(0.0, deadline - monotonic())
        retry_wait_budget = max(
            0.0,
            remaining_seconds - min(_REQUEST_TIMEOUT_SECONDS, remaining_seconds),
        )
        delay_seconds = min(next_delay, retry_wait_budget)
        _log_url_verification(
            attempt=attempt,
            classification="transient",
            request_url=request_url,
            final_url=final_url,
            status_code=status_code,
            error=transient_error,
            next_delay_seconds=delay_seconds,
            remaining_seconds=remaining_seconds,
        )
        if delay_seconds <= 0:
            break

        sleep(delay_seconds)
        previous_delay, next_delay = next_delay, previous_delay + next_delay

    raise RuntimeError(
        f"published report was not reachable within {max_wait_seconds:g}s: "
        f"{last_detail}"
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


def handle_verify_url_command(
    args: argparse.Namespace, settings, store: RuntimeStore
) -> int:
    with httpx.Client() as client:
        verify_report_url(args.url, client)
    return 0


def handle_mark_published_command(
    args: argparse.Namespace, settings, store: RuntimeStore
) -> int:
    record = store.load_run(args.run_id)
    if record.status in {
        RunStatus.PUBLISHED,
        RunStatus.NOTIFIED,
        RunStatus.PARTIALLY_NOTIFIED,
    }:
        print(
            f"[skip] run {args.run_id} is already published/notified, "
            f"updating fingerprints only",
            file=sys.stderr,
        )
    with httpx.Client() as client:
        verify_report_url(args.report_url, client)
    store.mark_published(args.run_id, args.report_url)
    return 0


def handle_build_command(
    args: argparse.Namespace, settings, store: RuntimeStore
) -> int:
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


def handle_notify_failure_command(
    args: argparse.Namespace, settings, store: RuntimeStore
) -> int:
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


def handle_notify_command(
    args: argparse.Namespace, settings, store: RuntimeStore
) -> int:
    record = store.load_run(args.run_id)
    if record.status is RunStatus.NOTIFIED and not args.force:
        print(
            f"[skip] run {args.run_id} was already notified — no duplicate "
            f"notification will be sent",
            file=sys.stderr,
        )
        return 0
    allowed_for_notify = {
        RunStatus.PUBLISHED,
        RunStatus.PARTIALLY_NOTIFIED,
    }
    if args.force:
        allowed_for_notify.add(RunStatus.NOTIFIED)
    if record.status not in allowed_for_notify or not record.report_url:
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
    message = SiteRenderer(
        args.templates_dir,
        base_path=_extract_path(settings.app.public_base_url),
    ).render_notification(
        report,
        settings.app.template,
        report_url=str(record.report_url),
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "sources":
        return run_source_command(args)
    settings = load_settings(args.config_dir)
    store = RuntimeStore(args.runtime_dir)

    command_handlers = {
        "verify-url": handle_verify_url_command,
        "mark-published": handle_mark_published_command,
        "build": handle_build_command,
        "notify-failure": handle_notify_failure_command,
        "notify": handle_notify_command,
    }

    handler = command_handlers.get(args.command)
    if handler:
        return handler(args, settings, store)

    raise AssertionError(f"unreachable command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
