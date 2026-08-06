from datetime import date
from pathlib import Path

import httpx
import pytest
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
        ["notify", "--run-id", "run-1", "--force"],
        ["notify-failure", "--message", "deploy failed"],
    ):
        assert parser.parse_args(argv).command == argv[0]


def test_verify_report_url_logs_status_and_final_url(
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_url = "https://example.com/report/"
    final_url = "https://cdn.example.com/report/"
    with respx.mock:
        respx.get(request_url).mock(
            return_value=httpx.Response(302, headers={"Location": final_url})
        )
        respx.get(final_url).mock(
            return_value=httpx.Response(200, text="<h1>AI 每日情报</h1>")
        )
        with httpx.Client() as client:
            verify_report_url(request_url, client)

    log = capsys.readouterr().err
    assert "attempt=1" in log
    assert "classification=success" in log
    assert "status=200" in log
    assert f"request_url={request_url}" in log
    assert f"final_url={final_url}" in log


@pytest.mark.parametrize("url", ["ftp://example.com/report/", "/relative/report/"])
def test_verify_report_url_rejects_invalid_configuration(
    url: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ai_news_sniffer.cli.time.sleep", lambda _: None)
    with httpx.Client() as client:
        with pytest.raises(RuntimeError, match="invalid published report URL"):
            verify_report_url(url, client)

    log = capsys.readouterr().err
    assert "attempt=0" in log
    assert "classification=permanent" in log
    assert f"request_url={url}" in log
    assert "final_url=unavailable" in log


def test_verify_report_url_fails_fast_for_permanent_http_status(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_url = "https://example.com/report/"
    monkeypatch.setattr("ai_news_sniffer.cli.time.sleep", lambda _: None)
    with respx.mock:
        route = respx.get(request_url).mock(return_value=httpx.Response(403))
        with httpx.Client() as client:
            with pytest.raises(RuntimeError, match="permanent configuration error"):
                verify_report_url(request_url, client)

    assert route.call_count == 1
    log = capsys.readouterr().err
    assert "classification=permanent" in log
    assert "status=403" in log
    assert f"request_url={request_url}" in log
    assert f"final_url={request_url}" in log


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
