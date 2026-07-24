import json
from datetime import UTC, date, datetime

import httpx
import respx

from ai_news_sniffer.models import (
    ChannelConfig,
    NotificationPayload,
    RunStatus,
)
from ai_news_sniffer.notifications.base import build_channels, send_all


def payload() -> NotificationPayload:
    return NotificationPayload(
        run_id="run-1",
        date=date(2026, 7, 23),
        status=RunStatus.PUBLISHED,
        title="AI 日报 · 2026-07-23",
        daily_summary="今日摘要",
        top_items=[],
        report_url="https://ai.example.com/2026/07/23/",
        generated_at=datetime(2026, 7, 23, 13, tzinfo=UTC),
    )


def test_send_all_isolates_failed_channel(monkeypatch) -> None:
    monkeypatch.setenv("MEOW_NICKNAME", "reader")
    monkeypatch.setenv("WECOM_WEBHOOK_URL", "https://wecom.test/send")
    configs = [
        ChannelConfig(id="meow", kind="meow", enabled=True, nickname_env="MEOW_NICKNAME"),
        ChannelConfig(
            id="wecom",
            kind="wecom",
            enabled=True,
            endpoint_env="WECOM_WEBHOOK_URL",
        ),
    ]
    with respx.mock:
        meow_route = respx.post("https://api.chuckfang.com/reader").mock(
            return_value=httpx.Response(500)
        )
        wecom_route = respx.post("https://wecom.test/send").mock(
            return_value=httpx.Response(200, json={"errcode": 0})
        )
        results = send_all(
            build_channels(configs, httpx.Client()),
            payload(),
            "message",
        )

    assert [result.success for result in results] == [False, True]
    assert json.loads(meow_route.calls[0].request.content)["title"].startswith("AI")
    assert json.loads(wecom_route.calls[0].request.content)["msgtype"] == "markdown"
    assert "reader" not in (results[0].error or "")


def test_generic_webhook_sends_standard_json(monkeypatch) -> None:
    monkeypatch.setenv("GENERIC_WEBHOOK_URL", "https://hook.test/digest")
    config = ChannelConfig(
        id="webhook",
        kind="webhook",
        enabled=True,
        endpoint_env="GENERIC_WEBHOOK_URL",
    )
    with respx.mock:
        route = respx.post("https://hook.test/digest").mock(
            return_value=httpx.Response(200)
        )
        result = build_channels([config], httpx.Client())[0].send(payload(), "message")

    assert result.success is True
    body = json.loads(route.calls[0].request.content)
    assert body["report_url"] == "https://ai.example.com/2026/07/23/"
    assert body["rendered_message"] == "message"
