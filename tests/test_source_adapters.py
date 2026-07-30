import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from ai_news_sniffer.models import HtmlSelectors, SourceConfig, SourceGroup, SourceKind
from ai_news_sniffer.normalization import normalize_article
from ai_news_sniffer.sources.base import SourceParseError, build_source_adapter

FIXTURES = Path(__file__).parent / "fixtures"
SINCE = datetime(2026, 7, 22, tzinfo=UTC)
UNTIL = datetime(2026, 7, 24, tzinfo=UTC)


def source(kind: SourceKind, url: str, **options: object) -> SourceConfig:
    return SourceConfig(
        id=kind.value.replace("_", "-"),
        name=kind.value,
        kind=kind,
        group=SourceGroup.RESEARCH,
        profiles={"full"},
        url=url,
        categories=["research"],
        options=options,
    )


@respx.mock
def test_rss_and_arxiv_adapters_return_windowed_items() -> None:
    rss = source(SourceKind.RSS, "https://example.com/feed.xml")
    arxiv = source(
        SourceKind.ARXIV,
        "https://export.arxiv.org/api/query",
        query="cat:cs.AI",
        max_results=30,
    )
    respx.get(str(rss.url)).mock(
        return_value=httpx.Response(
            200,
            text=(FIXTURES / "rss.xml").read_text(encoding="utf-8"),
        )
    )
    respx.get(str(arxiv.url)).mock(
        return_value=httpx.Response(
            200,
            text=(FIXTURES / "arxiv.xml").read_text(encoding="utf-8"),
        )
    )
    client = httpx.Client()

    assert len(build_source_adapter(rss, client).fetch(rss, SINCE, UNTIL)) == 1
    assert len(build_source_adapter(arxiv, client).fetch(arxiv, SINCE, UNTIL)) == 1


@respx.mock
def test_github_and_hacker_news_adapters_return_items() -> None:
    github = source(
        SourceKind.GITHUB_RELEASES,
        "https://api.github.com/repos/example/repo/releases",
        repository="example/repo",
    )
    hacker_news = source(
        SourceKind.HACKER_NEWS,
        "https://hacker-news.firebaseio.com/v0/topstories.json",
        item_limit=1,
    )
    respx.get(str(github.url)).mock(
        return_value=httpx.Response(
            200,
            json=json.loads(
                (FIXTURES / "github_releases.json").read_text(encoding="utf-8")
            ),
        )
    )
    respx.get(str(hacker_news.url)).mock(
        return_value=httpx.Response(
            200,
            json=json.loads(
                (FIXTURES / "hn_topstories.json").read_text(encoding="utf-8")
            ),
        )
    )
    respx.get("https://hacker-news.firebaseio.com/v0/item/42.json").mock(
        return_value=httpx.Response(
            200,
            json=json.loads((FIXTURES / "hn_item.json").read_text(encoding="utf-8")),
        )
    )
    client = httpx.Client()

    assert len(build_source_adapter(github, client).fetch(github, SINCE, UNTIL)) == 1
    assert len(
        build_source_adapter(hacker_news, client).fetch(
            hacker_news,
            SINCE,
            UNTIL,
        )
    ) == 1


def test_normalization_removes_tracking_and_preserves_source_group() -> None:
    rss = source(SourceKind.RSS, "https://example.com/feed.xml")
    raw = build_source_adapter(
        rss,
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    text=(FIXTURES / "rss.xml").read_text(encoding="utf-8"),
                )
            )
        ),
    ).fetch(rss, SINCE, UNTIL)[0]
    raw.url = "https://example.com/post?id=7&utm_source=rss"

    article = normalize_article(raw)

    assert str(article.canonical_url) == "https://example.com/post?id=7"
    assert article.source_group == SourceGroup.RESEARCH
    assert len(article.fingerprint) == 64


@respx.mock
def test_html_adapter_prefers_jsonld_and_resolves_relative_urls() -> None:
    html_source = SourceConfig(
        id="official-html",
        name="Official HTML",
        kind=SourceKind.HTML_WHITELIST,
        group=SourceGroup.OFFICIAL,
        profiles={"full"},
        url="https://official.example/news",
        categories=["models"],
    )
    respx.get(str(html_source.url)).mock(
        return_value=httpx.Response(
            200,
            text=(FIXTURES / "html_jsonld.html").read_text(encoding="utf-8"),
        )
    )

    articles = build_source_adapter(
        html_source,
        httpx.Client(),
    ).fetch(html_source, SINCE, UNTIL)

    assert [item.title for item in articles] == ["Official model launch"]
    assert str(articles[0].url) == "https://official.example/model"


@respx.mock
def test_html_adapter_uses_explicit_selectors_and_skips_missing_date() -> None:
    html_source = SourceConfig(
        id="selector-html",
        name="Selector HTML",
        kind=SourceKind.HTML_WHITELIST,
        group=SourceGroup.MEDIA,
        profiles={"full"},
        url="https://media.example/ai",
        categories=["products"],
        selectors=HtmlSelectors(
            item=".story",
            title=".title",
            link="a",
            date="time",
            excerpt=".summary",
        ),
    )
    respx.get(str(html_source.url)).mock(
        return_value=httpx.Response(
            200,
            text=(FIXTURES / "html_selectors.html").read_text(encoding="utf-8"),
        )
    )

    articles = build_source_adapter(
        html_source,
        httpx.Client(),
    ).fetch(html_source, SINCE, UNTIL)

    assert [item.title for item in articles] == ["Selector story"]


@respx.mock
def test_html_adapter_fails_closed_on_unparseable_page() -> None:
    html_source = SourceConfig(
        id="empty-html",
        name="Empty HTML",
        kind=SourceKind.HTML_WHITELIST,
        group=SourceGroup.OFFICIAL,
        profiles={"full"},
        url="https://empty.example/news",
    )
    respx.get(str(html_source.url)).mock(
        return_value=httpx.Response(200, text="<html><body>app shell</body></html>")
    )

    with pytest.raises(SourceParseError):
        build_source_adapter(
            html_source,
            httpx.Client(),
        ).fetch(html_source, SINCE, UNTIL)


@respx.mock
def test_html_adapter_accepts_naive_jsonld_date_as_utc() -> None:
    html_source = SourceConfig(
        id="naive-date-html",
        name="Naive date HTML",
        kind=SourceKind.HTML_WHITELIST,
        group=SourceGroup.OFFICIAL,
        profiles={"full"},
        url="https://official.example/news",
    )
    respx.get(str(html_source.url)).mock(
        return_value=httpx.Response(
            200,
            text="""
                <script type="application/ld+json">
                  {
                    "@type": "NewsArticle",
                    "headline": "Missing timezone",
                    "url": "/model",
                    "datePublished": "2026-07-23T09:00:00"
                  }
                </script>
            """,
        )
    )

    articles = build_source_adapter(
        html_source,
        httpx.Client(),
    ).fetch(html_source, SINCE, UNTIL)

    assert len(articles) == 1
    assert articles[0].title == "Missing timezone"
    assert articles[0].published_at.tzinfo is UTC


@respx.mock
@respx.mock
def test_html_adapter_falls_back_to_generic_article_selectors() -> None:
    html_source = SourceConfig(
        id="generic-html",
        name="Generic HTML",
        kind=SourceKind.HTML_WHITELIST,
        group=SourceGroup.OFFICIAL,
        profiles={"full"},
        url="https://generic.example/news",
        categories=["models"],
    )
    respx.get(str(html_source.url)).mock(
        return_value=httpx.Response(
            200,
            text="""
                <html><body>
                  <article>
                    <h2><a href="/first">First article</a></h2>
                    <time>Jul 23, 2026</time>
                    <p>First summary.</p>
                  </article>
                  <article>
                    <h2><a href="/second">Second article</a></h2>
                    <span class="date">Jul 22, 2026</span>
                    <p>Second summary.</p>
                  </article>
                </body></html>
            """,
        )
    )

    articles = build_source_adapter(
        html_source,
        httpx.Client(),
    ).fetch(html_source, SINCE, UNTIL)

    assert [item.title for item in articles] == ["First article"]


@respx.mock
def test_html_adapter_returns_empty_when_records_exist_outside_window() -> None:
    html_source = SourceConfig(
        id="old-html",
        name="Old HTML",
        kind=SourceKind.HTML_WHITELIST,
        group=SourceGroup.OFFICIAL,
        profiles={"full"},
        url="https://old.example/news",
        categories=["models"],
    )
    respx.get(str(html_source.url)).mock(
        return_value=httpx.Response(
            200,
            text="""
                <html><body>
                  <article>
                    <h2><a href="/old">Old article</a></h2>
                    <time>Jul 1, 2026</time>
                    <p>Old summary.</p>
                  </article>
                </body></html>
            """,
        )
    )

    articles = build_source_adapter(
        html_source,
        httpx.Client(),
    ).fetch(html_source, SINCE, UNTIL)

    assert articles == []


@respx.mock
def test_html_adapter_uses_browser_user_agent() -> None:
    html_source = SourceConfig(
        id="ua-html",
        name="UA HTML",
        kind=SourceKind.HTML_WHITELIST,
        group=SourceGroup.OFFICIAL,
        profiles={"full"},
        url="https://ua.example/news",
        categories=["models"],
    )
    request_headers: dict[str, str] | None = None

    def capture_request(request: httpx.Request) -> httpx.Response:
        nonlocal request_headers
        request_headers = dict(request.headers)
        return httpx.Response(
            200,
            text="""
                <html><body>
                  <article>
                    <h2><a href="/a">A</a></h2>
                    <time>Jul 23, 2026</time>
                  </article>
                </body></html>
            """,
        )

    respx.get(str(html_source.url)).mock(side_effect=capture_request)
    build_source_adapter(html_source, httpx.Client()).fetch(html_source, SINCE, UNTIL)

    assert request_headers is not None
    assert "Chrome" in request_headers.get("user-agent", "")


@respx.mock
def test_html_adapter_selector_item_can_be_the_link() -> None:
    html_source = SourceConfig(
        id="link-item-html",
        name="Link Item HTML",
        kind=SourceKind.HTML_WHITELIST,
        group=SourceGroup.OFFICIAL,
        profiles={"full"},
        url="https://link-item.example/news",
        categories=["models"],
        selectors=HtmlSelectors(
            item="[class*=\"item-row\"]",
            title=".title",
            link="a",
            date="time",
            excerpt="p",
        ),
    )
    respx.get(str(html_source.url)).mock(
        return_value=httpx.Response(
            200,
            text="""
                <html><body>
                  <a class="item-row" href="/row1">
                    <span class="title">Row one</span>
                    <time>Jul 23, 2026</time>
                    <p>Summary.</p>
                  </a>
                </body></html>
            """,
        )
    )

    articles = build_source_adapter(
        html_source,
        httpx.Client(),
    ).fetch(html_source, SINCE, UNTIL)

    assert [item.title for item in articles] == ["Row one"]
    assert str(articles[0].url) == "https://link-item.example/row1"
