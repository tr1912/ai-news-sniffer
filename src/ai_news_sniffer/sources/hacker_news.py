from datetime import UTC, datetime

import httpx

from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.sources.base import SourceFetchError


class HackerNewsAdapter:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def fetch(
        self,
        source: SourceConfig,
        since: datetime,
        until: datetime,
    ) -> list[RawArticle]:
        try:
            response = self.client.get(str(source.url), timeout=20)
            response.raise_for_status()
            ids = response.json()[: int(source.options.get("item_limit", 100))]
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"{source.id}: HN index fetch failed") from exc

        articles: list[RawArticle] = []
        for item_id in ids:
            item_url = f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
            try:
                item_response = self.client.get(item_url, timeout=10)
                item_response.raise_for_status()
            except httpx.HTTPError:
                continue
            item = item_response.json()
            if item.get("type") != "story" or not item.get("url"):
                continue
            published_at = datetime.fromtimestamp(item["time"], tz=UTC)
            if not since <= published_at <= until:
                continue
            articles.append(
                RawArticle(
                    source_id=source.id,
                    source_name=source.name,
                    source_group=source.group,
                    independence_group=source.independence_group or source.id,
                    title=item["title"],
                    url=item["url"],
                    published_at=published_at,
                    fetched_at=datetime.now(UTC),
                    author=item.get("by"),
                    categories=source.categories,
                    upstream_urls=[item["url"]],
                    raw_metadata={
                        "hn_id": item_id,
                        "score": item.get("score", 0),
                    },
                )
            )
        return articles
