import httpx

from ai_news_sniffer.config import resolve_secret
from ai_news_sniffer.models import ChannelConfig, NotificationPayload
from ai_news_sniffer.notifications.base import RetryingChannel


class WeComChannel(RetryingChannel):
    def __init__(self, config: ChannelConfig, client: httpx.Client) -> None:
        super().__init__(config.id, config.max_retries)
        if not config.endpoint_env:
            raise ValueError("WeCom channel requires endpoint_env")
        self.endpoint = resolve_secret(config.endpoint_env)
        self.client = client
        self.timeout = config.timeout_seconds

    def _request(self, payload: NotificationPayload, message: str) -> None:
        response = self.client.post(
            self.endpoint,
            json={"msgtype": "markdown", "markdown": {"content": message}},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"WeCom rejected message: {data}")
