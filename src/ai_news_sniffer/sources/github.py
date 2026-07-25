from datetime import UTC, datetime

import httpx

from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.sources.base import SourceFetchError


class GitHubReleasesAdapter:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def fetch(
        self,
        source: SourceConfig,
        since: datetime,
        until: datetime,
    ) -> list[RawArticle]:
        try:
            response = self.client.get(
                str(source.url),
                headers={"Accept": "application/vnd.github+json"},
                timeout=20,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"{source.id}: GitHub fetch failed") from exc

        articles: list[RawArticle] = []
        for release in response.json():
            if not release.get("published_at") or release.get("draft"):
                continue
            published_at = datetime.fromisoformat(
                release["published_at"]
            )
            if not since <= published_at <= until:
                continue
            title = release.get("name") or release["tag_name"]
            articles.append(
                RawArticle(
                    source_id=source.id,
                    source_name=source.name,
                    source_group=source.group,
                    independence_group=source.independence_group or source.id,
                    title=f"{source.name}: {title}",
                    url=release["html_url"],
                    published_at=published_at,
                    fetched_at=datetime.now(UTC),
                    excerpt=(release.get("body") or "")[:2000],
                    author=(release.get("author") or {}).get("login"),
                    categories=source.categories,
                    raw_metadata={"release_id": release["id"]},
                )
            )
        return articles
