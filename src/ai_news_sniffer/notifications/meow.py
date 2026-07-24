from urllib.parse import quote

import httpx

from ai_news_sniffer.config import resolve_secret
from ai_news_sniffer.models import ChannelConfig, NotificationPayload
from ai_news_sniffer.notifications.base import RetryingChannel


class MeowChannel(RetryingChannel):
    def __init__(self, config: ChannelConfig, client: httpx.Client) -> None:
        super().__init__(config.id, config.max_retries)
        if not config.nickname_env:
            raise ValueError("MeoW channel requires nickname_env")
        nickname = quote(resolve_secret(config.nickname_env), safe="")
        self.endpoint = f"https://api.chuckfang.com/{nickname}"
        self.client = client
        self.timeout = config.timeout_seconds

    def _request(self, payload: NotificationPayload, message: str) -> None:
        response = self.client.post(
            self.endpoint,
            params={"msgType": "markdown"},
            json={
                "title": payload.title,
                "msg": message,
                "url": str(payload.report_url),
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") != 200:
            raise RuntimeError(f"MeoW rejected message with status {data.get('status')}")
