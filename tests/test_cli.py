from datetime import date
from pathlib import Path

import httpx
import respx

from ai_news_sniffer.cli import build_parser, verify_report_url


def test_cli_exposes_required_stage_commands() -> None:
    parser = build_parser()
    for argv in (
        ["sources", "list", "--profile", "light"],
        ["build", "--dry-run"],
        ["verify-url", "https://example.com/report/"],
        ["mark-published", "--run-id", "run-1", "--report-url", "https://example.com/r/"],
        ["notify", "--run-id", "run-1"],
        ["notify-failure", "--message", "deploy failed"],
    ):
        assert parser.parse_args(argv).command == argv[0]


def test_verify_report_url_accepts_expected_page_marker() -> None:
    with respx.mock:
        respx.get("https://example.com/report/").mock(
            return_value=httpx.Response(200, text="<h1>AI 每日情报</h1>")
        )
        verify_report_url("https://example.com/report/", httpx.Client())


def test_cli_accepts_workflow_build_argument_order() -> None:
    args = build_parser().parse_args(
        [
            "--runtime-dir",
            "runtime-data",
            "--output-dir",
            "build/site",
            "build",
            "--source-profile",
            "balanced",
            "--include-sources",
            "openai-news,anthropic-news",
            "--exclude-sources",
            "hacker-news",
            "--max-ai-candidates",
            "0",
            "--target-date",
            "2026-07-23",
            "--dry-run",
        ]
    )
    assert args.runtime_dir == Path("runtime-data")
    assert args.output_dir == Path("build/site")
    assert args.target_date == date(2026, 7, 23)
    assert args.dry_run is True
    assert args.source_profile == "balanced"
    assert args.include_sources == "openai-news,anthropic-news"
    assert args.exclude_sources == "hacker-news"
    assert args.max_ai_candidates == 0
