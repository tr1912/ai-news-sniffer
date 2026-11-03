from datetime import UTC, datetime

import httpx
from pydantic import ValidationError

from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.sources.base import SourceFetchError, SourceParseError


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class HfDailyPapersAdapter:
    """调用 Hugging Face 官方 JSON 接口 /api/daily_papers，不依赖第三方 RSS。"""

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
            raise SourceFetchError(f"{source.id}: daily papers fetch failed") from exc

        payload = response.json()
        if not isinstance(payload, list):
            raise SourceParseError(f"{source.id}: unexpected payload shape")

        articles: list[RawArticle] = []
        for item in payload:
            paper = item.get("paper") or {}
            title = item.get("title") or paper.get("title")
            paper_id = paper.get("id")
            published = _parse_iso(item.get("publishedAt")) or _parse_iso(
                paper.get("publishedAt")
            )
            if not title or not paper_id or published is None:
                continue
            if not since <= published <= until:
                continue
            summary = item.get("summary") or paper.get("summary") or ""
            try:
                articles.append(
                    RawArticle(
                        source_id=source.id,
                        source_name=source.name,
                        source_group=source.group,
                        independence_group=source.independence_group or source.id,
                        title=str(title).strip(),
                        url=f"https://huggingface.co/papers/{paper_id}",
                        published_at=published,
                        fetched_at=datetime.now(UTC),
                        excerpt=str(summary).strip(),
                        categories=source.categories,
                    )
                )
            except ValidationError:
                continue

        # 窗口内无文章是正常的（返回空），但「接口有数据却一条都解析不出」说明
        # 接口结构已变，必须 fail-closed 以触发健康告警，而非静默记为成功。
        windowed = any(
            _parse_iso(item.get("publishedAt")) or _parse_iso((item.get("paper") or {}).get("publishedAt"))
            for item in payload
            if (item.get("title") or (item.get("paper") or {}).get("title"))
            and (item.get("paper") or {}).get("id")
        )
        if not articles and not windowed:
            raise SourceParseError(f"{source.id}: no dated article records found")
        return articles
