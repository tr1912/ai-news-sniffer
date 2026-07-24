import time
from typing import Protocol

import httpx

from ai_news_sniffer.models import (
    ChannelConfig,
    ChannelResult,
    NotificationPayload,
)


class NotificationChannel(Protocol):
    def send(self, payload: NotificationPayload, message: str) -> ChannelResult: ...


class RetryingChannel:
    def __init__(self, channel_id: str, max_retries: int) -> None:
        self.channel_id = channel_id
        self.max_retries = max_retries

    def _request(self, payload: NotificationPayload, message: str) -> None:
        raise NotImplementedError

    def send(self, payload: NotificationPayload, message: str) -> ChannelResult:
        last_error: httpx.HTTPError | RuntimeError | ValueError | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._request(payload, message)
                return ChannelResult(
                    channel_id=self.channel_id,
                    success=True,
                    attempts=attempt,
                )
            except (httpx.HTTPError, RuntimeError, ValueError) as error:
                last_error = error
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))
        return ChannelResult(
            channel_id=self.channel_id,
            success=False,
            attempts=self.max_retries,
            error=self._safe_error(last_error),
        )

    @staticmethod
    def _safe_error(error: httpx.HTTPError | RuntimeError | ValueError | None) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            return f"HTTP {error.response.status_code}"
        return type(error).__name__ if error else "UnknownError"


def build_channels(
    configs: list[ChannelConfig],
    client: httpx.Client,
) -> list[NotificationChannel]:
    channels: list[NotificationChannel] = []
    for config in configs:
        if not config.enabled:
            continue
        if config.kind == "meow":
            from ai_news_sniffer.notifications.meow import MeowChannel

            channels.append(MeowChannel(config, client))
        elif config.kind == "wecom":
            from ai_news_sniffer.notifications.wecom import WeComChannel

            channels.append(WeComChannel(config, client))
        elif config.kind == "webhook":
            from ai_news_sniffer.notifications.webhook import WebhookChannel

            channels.append(WebhookChannel(config, client))
    return channels


def send_all(
    channels: list[NotificationChannel],
    payload: NotificationPayload,
    message: str,
) -> list[ChannelResult]:
    return [channel.send(payload, message) for channel in channels]
