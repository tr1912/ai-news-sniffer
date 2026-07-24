from datetime import datetime
from typing import Protocol

import httpx

from ai_news_sniffer.models import RawArticle, SourceConfig, SourceKind


class SourceFetchError(RuntimeError):
    pass


class SourceParseError(RuntimeError):
    pass


class SourceAdapter(Protocol):
    def fetch(
        self,
        source: SourceConfig,
        since: datetime,
        until: datetime,
    ) -> list[RawArticle]: ...


def build_source_adapter(
    source: SourceConfig,
    client: httpx.Client,
) -> SourceAdapter:
    if source.kind == SourceKind.RSS:
        from ai_news_sniffer.sources.rss import RssAdapter

        return RssAdapter(client)
    if source.kind == SourceKind.ARXIV:
        from ai_news_sniffer.sources.arxiv import ArxivAdapter

        return ArxivAdapter(client)
    if source.kind == SourceKind.GITHUB_RELEASES:
        from ai_news_sniffer.sources.github import GitHubReleasesAdapter

        return GitHubReleasesAdapter(client)
    if source.kind == SourceKind.HACKER_NEWS:
        from ai_news_sniffer.sources.hacker_news import HackerNewsAdapter

        return HackerNewsAdapter(client)
    if source.kind == SourceKind.HTML_WHITELIST:
        from ai_news_sniffer.sources.html import HtmlWhitelistAdapter

        return HtmlWhitelistAdapter(client)
    raise ValueError(f"Unsupported source kind: {source.kind}")
