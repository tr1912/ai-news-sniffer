import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from selectolax.lexbor import LexborHTMLParser

from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.sources.base import SourceFetchError, SourceParseError

_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y/%m/%d",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d %Y",
    "%b %d %Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y年%m月%d日",
    "%Y年%m月%d日 %H:%M",
]


def _try_parse_partial_date(value: str, ref_year: int) -> datetime | None:
    value = value.strip()
    for fmt in ("%b %d", "%B %d", "%b %d,", "%B %d,"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.replace(year=ref_year, tzinfo=UTC)
        except ValueError:
            pass
    month_day = value.split()
    if len(month_day) == 2:
        try:
            import calendar
            month_names = {m[:3].lower(): i for i, m in enumerate(calendar.month_abbr) if m}
            month_names.update({m.lower(): i for i, m in enumerate(calendar.month_name) if m})
            month_str, day_str = month_day[0].lower(), month_day[1].rstrip(",")
            if month_str in month_names:
                month = month_names[month_str]
                day = int(day_str)
                return datetime(ref_year, month, day, tzinfo=UTC)
        except (ValueError, KeyError):
            pass
    return None

# CSS selectors that are commonly used for article cards on news/blog sites.
_GENERIC_ITEM_SELECTORS = [
    "article",
    '[class*="post"]',
    '[class*="card"]',
    '[class*="article"]',
    '[class*="blog"]',
    '[class*="news"]',
    '[class*="list-item"]',
    '[class*="listItem"]',
    ".item",
    "main li",
    '[role="main"] li',
    ".content li",
    '[class*="content"] li',
]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()

    # ISO 8601 / Python datetime strings (including naive ones).
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        pass

    # Common human-readable formats found on news sites.
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass

    # RSS-style RFC 2822 dates, e.g., "Tue, 25 Jul 2026 09:00:00 GMT".
    try:
        return parsedate_to_datetime(value).astimezone(UTC)
    except (ValueError, TypeError, AttributeError):
        return None


def _record_types(record: dict[str, Any]) -> set[str]:
    raw = record.get("@type")
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {item for item in raw if isinstance(item, str)}
    return set()


def _collect_jsonld_records(
    value: Any,
    records: list[dict[str, Any]],
) -> None:
    if not isinstance(value, dict):
        return
    if _record_types(value) & {
        "Article",
        "BlogPosting",
        "NewsArticle",
        "Blog",
        "ScholarlyArticle",
        "TechArticle",
    }:
        records.append(value)
    graph = value.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            _collect_jsonld_records(item, records)
    if "ItemList" in _record_types(value):
        items = value.get("itemListElement", [])
        if isinstance(items, list):
            for item in items:
                _collect_jsonld_records(item, records)


def _jsonld_records(tree: LexborHTMLParser) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for node in tree.css('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.text())
        except (json.JSONDecodeError, TypeError):
            continue
        values = payload if isinstance(payload, list) else [payload]
        for value in values:
            _collect_jsonld_records(value, records)
    return records


def _extract_date(node, ref_year: int | None = None) -> datetime | None:
    """Try to extract a date from a node using common patterns."""
    if node is None:
        return None
    if ref_year is None:
        ref_year = datetime.now(UTC).year
    # Look for time child first
    time_node = node.css_first("time")
    if time_node is not None:
        date_value = time_node.attributes.get("datetime")
        if date_value:
            parsed = _parse_datetime(date_value)
            if parsed:
                return parsed
        text = time_node.text(strip=True)
        parsed = _parse_datetime(text)
        if parsed:
            return parsed
        parsed = _try_parse_partial_date(text, ref_year)
        if parsed:
            return parsed
    # Try common date attributes
    for attr in ("datetime", "data-date", "data-published", "data-timestamp"):
        value = node.attributes.get(attr)
        if value:
            parsed = _parse_datetime(value)
            if parsed:
                return parsed
    # Try common date classes/text
    for sel in (
        '[class*="date"]',
        '[class*="time"]',
        '[class*="published"]',
    ):
        child = node.css_first(sel)
        if child is not None:
            text = child.text(strip=True)
            parsed = _parse_datetime(text)
            if parsed:
                return parsed
            parsed = _try_parse_partial_date(text, ref_year)
            if parsed:
                return parsed
    # Last resort: scan text snippets for anything date-like.
    text = node.text(strip=True)
    if text:
        # Try the whole text first, then split by common delimiters.
        parsed = _parse_datetime(text)
        if parsed:
            return parsed
        for part in text.replace("|", "\n").replace("—", "\n").split("\n"):
            part = part.strip()
            if len(part) < 30:
                parsed = _parse_datetime(part)
                if parsed:
                    return parsed
                parsed = _try_parse_partial_date(part, ref_year)
                if parsed:
                    return parsed
    return None


def _extract_title(item) -> str | None:
    if item is None:
        return None
    for sel in (
        "h1", "h2", "h3", "h4", "h5",
        ".title", "[class*=\"title\"]",
        "[class*=\"heading\"]",
        "a[title]",
    ):
        node = item.css_first(sel)
        if node is not None:
            text = node.text(strip=True)
            if not text and sel == "a[title]":
                text = node.attributes.get("title", "")
            if text and len(text) > 5:
                return text
    return None


def _extract_link(item, base_url: str) -> str | None:
    if item is None:
        return None
    href = None
    if item.tag == "a":
        href = item.attributes.get("href")
    if not href:
        link_node = item.css_first("a")
        if link_node is not None:
            href = link_node.attributes.get("href")
    if not href:
        return None
    return urljoin(base_url, href)


def _extract_excerpt(item) -> str:
    if item is None:
        return ""
    for sel in (
        "p", ".summary", ".excerpt", ".description",
        '[class*="summary"]', '[class*="excerpt"]', '[class*="description"]',
    ):
        node = item.css_first(sel)
        if node is not None:
            text = node.text(strip=True)
            if text and len(text) > 20:
                return text
    return ""


def _articles_from_jsonld(
    records: list[dict[str, Any]],
    base_url: str,
) -> list[tuple[str, str, datetime, str]]:
    parsed: list[tuple[str, str, datetime, str]] = []
    for record in records:
        published = _parse_datetime(
            record.get("datePublished") or record.get("dateModified")
        )
        title = record.get("headline") or record.get("name")
        url = record.get("url")
        if title and url and published:
            parsed.append(
                (
                    str(title),
                    urljoin(base_url, str(url)),
                    published,
                    str(record.get("description") or ""),
                )
            )
    return parsed


def _articles_from_explicit_selectors(
    tree: LexborHTMLParser,
    source: SourceConfig,
    ref_year: int | None = None,
) -> list[tuple[str, str, datetime, str]]:
    """Use explicit source selectors if available, otherwise try generic article patterns."""
    selectors = source.selectors
    if selectors is None:
        return _articles_from_generic_selectors(tree, str(source.url), ref_year=ref_year)
    if ref_year is None:
        ref_year = datetime.now(UTC).year
    page_date = _extract_page_level_date(tree, ref_year)

    parsed: list[tuple[str, str, datetime, str]] = []
    for item in tree.css(selectors.item):
        title_node = item.css_first(selectors.title)
        link_node = item.css_first(selectors.link)
        date_node = item.css_first(selectors.date) if selectors.date else None
        excerpt_node = item.css_first(selectors.excerpt)
        published: datetime | None = None
        date_value = None
        if date_node is not None:
            date_value = date_node.attributes.get("datetime")
            if not date_value:
                date_value = date_node.text(strip=True)
            published = _parse_datetime(date_value)
            if not published and date_value:
                published = _try_parse_partial_date(date_value, ref_year)
        if published is None:
            published = _extract_date(item, ref_year=ref_year)
        if published is None:
            published = page_date
        href: str | None = None
        if link_node is not None:
            href = link_node.attributes.get("href")
        if not href and item.tag == "a":
            href = item.attributes.get("href")
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
    return parsed


def _extract_page_level_date(tree: LexborHTMLParser, ref_year: int) -> datetime | None:
    """Try to extract a date from the page header/title area for pages like hf-daily-papers
    where dates are not inside individual article cards."""
    for sel in ("h1", "h2", "[class*=\"date\"]", "[class*=\"Day\"]", "button[role=\"tab\"][aria-selected*=\"true\"]"):
        for node in tree.css(sel):
            text = node.text(strip=True)
            if not text:
                continue
            parsed = _parse_datetime(text)
            if parsed:
                return parsed
            parsed = _try_parse_partial_date(text, ref_year)
            if parsed:
                return parsed
    return None


def _articles_from_generic_selectors(
    tree: LexborHTMLParser,
    base_url: str,
    ref_year: int | None = None,
) -> list[tuple[str, str, datetime, str]]:
    """Fallback extraction for common news/blog list layouts.

    Collects dated articles from all generic selectors, deduplicating by URL.
    """
    if ref_year is None:
        ref_year = datetime.now(UTC).year
    seen_urls: set[str] = set()
    parsed: list[tuple[str, str, datetime, str]] = []
    page_date = _extract_page_level_date(tree, ref_year)

    for item_selector in _GENERIC_ITEM_SELECTORS:
        for item in tree.css(item_selector):
            title = _extract_title(item)
            if not title:
                continue
            link = _extract_link(item, base_url)
            if not link or link in seen_urls:
                continue
            published = _extract_date(item, ref_year=ref_year)
            if not published:
                published = page_date
            if not published:
                continue
            excerpt = _extract_excerpt(item)
            seen_urls.add(link)
            parsed.append((title, link, published, excerpt))

    return parsed


class HtmlWhitelistAdapter:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def fetch(
        self,
        source: SourceConfig,
        since: datetime,
        until: datetime,
    ) -> list[RawArticle]:
        ref_year = until.year
        request_headers = {
            "User-Agent": _BROWSER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        try:
            response = self.client.get(
                str(source.url),
                headers=request_headers,
                timeout=30,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"{source.id}: HTML fetch failed") from exc

        tree = LexborHTMLParser(response.text)
        parsed = _articles_from_jsonld(_jsonld_records(tree), str(source.url))

        if not parsed:
            if source.selectors is not None:
                parsed = _articles_from_explicit_selectors(tree, source, ref_year=ref_year)
            if not parsed:
                parsed = _articles_from_generic_selectors(tree, str(source.url), ref_year=ref_year)

        if not parsed:
            raise SourceParseError(f"{source.id}: no dated article records found")

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
        return articles
