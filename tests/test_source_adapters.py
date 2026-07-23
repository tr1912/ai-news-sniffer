import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from ai_news_sniffer.models import SourceConfig, SourceGroup, SourceKind
from ai_news_sniffer.normalization import normalize_article
from ai_news_sniffer.sources.base import build_source_adapter

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
