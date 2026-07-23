import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from selectolax.lexbor import LexborHTMLParser

from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.sources.base import SourceFetchError, SourceParseError


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _jsonld_records(tree: LexborHTMLParser) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for node in tree.css('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.text())
        except (json.JSONDecodeError, TypeError):
            continue
        values = payload if isinstance(payload, list) else [payload]
        for value in values:
            if not isinstance(value, dict):
                continue
            graph = value.get("@graph", [])
            candidates = graph if isinstance(graph, list) else []
            if value.get("@type") == "ItemList":
                candidates.extend(value.get("itemListElement", []))
            else:
                candidates.append(value)
            for candidate in candidates:
                if isinstance(candidate, dict) and candidate.get("@type") in {
                    "Article",
                    "BlogPosting",
                    "NewsArticle",
                }:
                    records.append(candidate)
    return records


class HtmlWhitelistAdapter:
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
                headers={"User-Agent": "ai-news-sniffer/0.1 (+source audit)"},
                timeout=20,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"{source.id}: HTML fetch failed") from exc

        tree = LexborHTMLParser(response.text)
        records = _jsonld_records(tree)
        parsed: list[tuple[str, str, datetime, str]] = []
        for record in records:
            published = _datetime(
                record.get("datePublished") or record.get("dateModified")
            )
            title = record.get("headline") or record.get("name")
            url = record.get("url")
            if title and url and published:
                parsed.append(
                    (
                        str(title),
                        urljoin(str(source.url), str(url)),
                        published,
                        str(record.get("description") or ""),
                    )
                )

        if not parsed and source.selectors:
            for item in tree.css(source.selectors.item):
                title_node = item.css_first(source.selectors.title)
                link_node = item.css_first(source.selectors.link)
                date_node = item.css_first(source.selectors.date)
                excerpt_node = item.css_first(source.selectors.excerpt)
                date_value = (
                    date_node.attributes.get("datetime") if date_node else None
                )
                published = _datetime(date_value)
                href = link_node.attributes.get("href") if link_node else None
                if not title_node or not href or not published:
                    continue
                parsed.append(
                    (
                        title_node.text(strip=True),
                        urljoin(str(source.url), href),
                        published,
                        excerpt_node.text(strip=True) if excerpt_node else "",
                    )
                )

        articles = [
            RawArticle(
                source_id=source.id,
                source_name=source.name,
                source_group=source.group,
                independence_group=source.independence_group or source.id,
                title=title,
                url=url,
                published_at=published,
                fetched_at=datetime.now(UTC),
                excerpt=excerpt,
                categories=source.categories,
            )
            for title, url, published, excerpt in parsed
            if since <= published <= until
        ]
        if not articles:
            raise SourceParseError(f"{source.id}: no dated article records found")
        return articles
