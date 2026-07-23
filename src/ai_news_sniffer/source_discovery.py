import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from ai_news_sniffer.models import Article, CandidateSource, SourceGroup, SourceKind


def discover_candidate_sources(
    articles: list[Article],
    known_domains: set[str],
    output_path: Path,
    now: datetime,
) -> list[CandidateSource]:
    existing: dict[str, CandidateSource] = {}
    if output_path.exists():
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                existing = {
                    item["domain"]: CandidateSource.model_validate(item)
                    for item in payload
                }
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError):
            existing = {}

    normalized_known_domains = {domain.casefold() for domain in known_domains}
    for article in articles:
        for upstream in article.upstream_urls:
            domain = (urlsplit(str(upstream)).hostname or "").casefold()
            if not domain or domain in normalized_known_domains:
                continue
            previous = existing.get(domain)
            referring = previous.referring_source_ids.copy() if previous else set()
            referring.add(article.source_id)
            existing[domain] = CandidateSource(
                domain=domain,
                sample_url=upstream,
                sample_title=article.title,
                first_seen_at=previous.first_seen_at if previous else now,
                last_seen_at=now,
                referring_source_ids=referring,
                suggested_group=SourceGroup.OFFICIAL,
                suggested_kind=SourceKind.HTML_WHITELIST,
                reason="Referenced by an enabled media or community source",
                risk="Requires ownership, access-policy, and parser review",
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(existing.values(), key=lambda item: item.domain)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(
            [item.model_dump(mode="json") for item in ordered],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)
    return ordered
