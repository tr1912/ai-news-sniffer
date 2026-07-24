from calendar import timegm
from datetime import UTC, datetime

import feedparser
import httpx

from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.sources.base import SourceFetchError


def entry_datetime(entry: object) -> datetime:
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry,
        "updated_parsed",
        None,
    )
    if parsed is None:
        return datetime.now(UTC)
    return datetime.fromtimestamp(timegm(parsed), tz=UTC)


class RssAdapter:
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
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"{source.id}: RSS fetch failed") from exc

        feed = feedparser.parse(response.content)
        articles: list[RawArticle] = []
        for entry in feed.entries:
            published_at = entry_datetime(entry)
            link = getattr(entry, "link", None) or getattr(entry, "id", None)
            if not link or not since <= published_at <= until:
                continue
            articles.append(
                RawArticle(
                    source_id=source.id,
                    source_name=source.name,
                    source_group=source.group,
                    independence_group=source.independence_group or source.id,
                    title=str(getattr(entry, "title", "")).strip(),
                    url=link,
                    published_at=published_at,
                    fetched_at=datetime.now(UTC),
                    excerpt=str(
                        getattr(entry, "summary", getattr(entry, "description", ""))
                    ).strip(),
                    author=getattr(entry, "author", None),
                    categories=source.categories,
                )
            )
        return articles
