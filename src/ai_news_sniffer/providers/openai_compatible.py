import json
import time

from openai import OpenAI

from ai_news_sniffer.config import resolve_secret
from ai_news_sniffer.models import ProviderConfig


class OpenAICompatibleProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.client = OpenAI(
            api_key=resolve_secret(config.api_key_env),
            base_url=str(config.base_url).rstrip("/"),
            timeout=config.timeout_seconds,
        )

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    stream=False,
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("provider returned empty content")
                return json.loads(content)
            except Exception as error:  # noqa: BLE001
                last_error = error
                if attempt < self.config.max_retries:
                    time.sleep(2 ** (attempt - 1))
        raise RuntimeError(
            f"provider {self.config.id} failed after "
            f"{self.config.max_retries} attempts: {last_error}"
        )
