import json

from pydantic import BaseModel, Field

from ai_news_sniffer.models import Article, NewsEvent, SourceRef
from ai_news_sniffer.providers.base import StructuredProvider
from ai_news_sniffer.source_verification import (
    confirmation_status,
    validate_event_sources,
)


class EditorialEvent(BaseModel):
    id: str
    candidate_ids: list[str]
    category: str
    title_zh: str
    summary_zh: str
    why_it_matters_zh: str
    importance_score: float = Field(ge=0, le=100)
    primary_candidate_id: str
    related_candidate_ids: list[str]


class EditorialOutput(BaseModel):
    daily_summary_zh: str
    events: list[EditorialEvent]


class EditorialService:
    def __init__(self, provider: StructuredProvider, system_prompt: str) -> None:
        self.provider = provider
        self.system_prompt = system_prompt

    def edit(
        self,
        candidates: list[Article],
        min_items: int,
        max_items: int,
    ) -> tuple[str, list[NewsEvent]]:
        by_id = {item.id: item for item in candidates}
        user_prompt = json.dumps(
            {
                "instruction": (
                    f"Select at most {max_items} events. Use fewer than {min_items} "
                    "when quality is insufficient. Return JSON only."
                ),
                "candidates": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "excerpt": item.excerpt[:1500],
                        "source": item.source_name,
                        "source_group": item.source_group.value,
                        "independence_group": item.independence_group,
                        "url": str(item.url),
                        "published_at": item.published_at.isoformat(),
                        "categories": item.categories,
                        "rule_score": item.rule_score,
                    }
                    for item in candidates
                ],
            },
            ensure_ascii=False,
        )
        output = EditorialOutput.model_validate(
            self.provider.generate_json(self.system_prompt, user_prompt)
        )
        events: list[NewsEvent] = []
        for event in output.events:
            evidence_ids = list(
                dict.fromkeys(
                    [
                        event.primary_candidate_id,
                        *event.candidate_ids,
                        *event.related_candidate_ids,
                    ]
                )
            )
            referenced_ids = set(evidence_ids)
            unknown = referenced_ids.difference(by_id)
            if unknown:
                # Drop hallucinated candidate references instead of failing the whole
                # batch; the model may still return other valid events.
                continue
            primary = by_id[event.primary_candidate_id]
            related = [
                by_id[item_id]
                for item_id in event.related_candidate_ids
                if item_id != event.primary_candidate_id
            ]
            try:
                news_event = NewsEvent(
                    id=event.id,
                    candidate_ids=evidence_ids,
                    category=event.category,
                    title_zh=event.title_zh,
                    summary_zh=event.summary_zh,
                    why_it_matters_zh=event.why_it_matters_zh,
                    importance_score=event.importance_score,
                    confirmation_status=confirmation_status(
                        [by_id[item_id] for item_id in evidence_ids]
                    ),
                    primary_source=SourceRef(
                        source_id=primary.source_id,
                        source_name=primary.source_name,
                        title=primary.title,
                        url=primary.url,
                        published_at=primary.published_at,
                    ),
                    related_sources=[
                        SourceRef(
                            source_id=item.source_id,
                            source_name=item.source_name,
                            title=item.title,
                            url=item.url,
                            published_at=item.published_at,
                        )
                        for item in related
                    ],
                )
                validate_event_sources(news_event, candidates)
            except ValueError:
                # Skip individual events that violate source/verification rules.
                continue
            events.append(news_event)
        if not events:
            raise ValueError("no verified events after editorial validation")
        return output.daily_summary_zh, events
