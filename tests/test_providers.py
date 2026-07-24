from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_news_sniffer.models import Article, ConfirmationStatus, SourceGroup
from ai_news_sniffer.providers.base import ProviderChain
from ai_news_sniffer.providers.editorial import EditorialService

FIXTURES = Path(__file__).parent / "fixtures"


class FailingProvider:
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        raise RuntimeError("rate limited")


class FixtureProvider:
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        return json.loads(
            (FIXTURES / "editorial_response.json").read_text(encoding="utf-8")
        )


class ValidProvider:
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {
            "daily_summary_zh": "今日 AI 要闻",
            "events": [
                {
                    "id": "event-1",
                    "candidate_ids": [],
                    "category": "models",
                    "title_zh": "新模型发布",
                    "summary_zh": "某公司发布了新模型。",
                    "why_it_matters_zh": "它提高了推理能力。",
                    "importance_score": 90,
                    "primary_candidate_id": "a1",
                    "related_candidate_ids": [],
                }
            ],
        }


# ---------------------------------------------------------------------------
# ProviderChain tests
# ---------------------------------------------------------------------------


def test_provider_chain_uses_next_provider_after_failure() -> None:
    result = ProviderChain([FailingProvider(), FixtureProvider()]).generate_json("s", "u")
    assert result["daily_summary_zh"] == "今日 AI 要闻"


def test_provider_chain_raises_when_all_providers_fail() -> None:
    with pytest.raises(RuntimeError, match="all providers failed"):
        ProviderChain([FailingProvider(), FailingProvider()]).generate_json("s", "u")


def test_provider_chain_rejects_empty_provider_list() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ProviderChain([])


# ---------------------------------------------------------------------------
# EditorialService tests
# ---------------------------------------------------------------------------


def test_editorial_service_rejects_unknown_candidate_ids() -> None:
    service = EditorialService(FixtureProvider(), "Output JSON.")
    with pytest.raises(ValueError, match="unknown candidate"):
        service.edit([], min_items=1, max_items=15)


def test_editorial_service_builds_news_event() -> None:
    candidate = Article(
        id="a1",
        source_id="official",
        source_name="Official",
        source_group=SourceGroup.OFFICIAL,
        independence_group="official",
        title="New model",
        url="https://example.com/model",
        canonical_url="https://example.com/model",
        normalized_title="new model",
        fingerprint="a" * 64,
        published_at=datetime(2026, 7, 23, tzinfo=UTC),
        fetched_at=datetime(2026, 7, 23, tzinfo=UTC),
        excerpt="Release notes.",
        categories=["models"],
        rule_score=90,
    )
    service = EditorialService(ValidProvider(), "Output JSON.")

    summary, events = service.edit([candidate], min_items=1, max_items=15)

    assert summary == "今日 AI 要闻"
    assert len(events) == 1
    assert events[0].candidate_ids == ["a1"]
    assert events[0].confirmation_status == ConfirmationStatus.PRIMARY_CONFIRMED
    assert events[0].primary_source.source_id == "official"


def test_editorial_service_evidence_ids_deduplicated() -> None:
    candidate = Article(
        id="a1",
        source_id="official",
        source_name="Official",
        source_group=SourceGroup.OFFICIAL,
        independence_group="official",
        title="New model",
        url="https://example.com/model",
        canonical_url="https://example.com/model",
        normalized_title="new model",
        fingerprint="a" * 64,
        published_at=datetime(2026, 7, 23, tzinfo=UTC),
        fetched_at=datetime(2026, 7, 23, tzinfo=UTC),
        excerpt="Release notes.",
        categories=["models"],
        rule_score=90,
    )

    class DuplicateProvider:
        def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
            return {
                "daily_summary_zh": "摘要",
                "events": [
                    {
                        "id": "event-1",
                        "candidate_ids": ["a1"],
                        "category": "models",
                        "title_zh": "标题",
                        "summary_zh": "事实",
                        "why_it_matters_zh": "重要",
                        "importance_score": 90,
                        "primary_candidate_id": "a1",
                        "related_candidate_ids": ["a1"],
                    }
                ],
            }

    service = EditorialService(DuplicateProvider(), "Output JSON.")
    _, events = service.edit([candidate], min_items=1, max_items=15)
    # evidence_ids deduplicates: ["a1", "a1"] → ["a1"]
    assert events[0].candidate_ids == ["a1"]


def test_editorial_service_rejects_community_primary() -> None:
    community = Article(
        id="c1",
        source_id="community-blog",
        source_name="Community Blog",
        source_group=SourceGroup.COMMUNITY,
        independence_group="community-blog",
        title="Rumor",
        url="https://community.example.com/rumor",
        canonical_url="https://community.example.com/rumor",
        normalized_title="rumor",
        fingerprint="c" * 64,
        published_at=datetime(2026, 7, 23, tzinfo=UTC),
        fetched_at=datetime(2026, 7, 23, tzinfo=UTC),
        excerpt="Something.",
        categories=["models"],
        rule_score=40,
    )

    class CommunityPrimaryProvider:
        def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
            return {
                "daily_summary_zh": "摘要",
                "events": [
                    {
                        "id": "event-1",
                        "candidate_ids": [],
                        "category": "models",
                        "title_zh": "标题",
                        "summary_zh": "事实",
                        "why_it_matters_zh": "重要",
                        "importance_score": 90,
                        "primary_candidate_id": "c1",
                        "related_candidate_ids": [],
                    }
                ],
            }

    service = EditorialService(CommunityPrimaryProvider(), "Output JSON.")
    with pytest.raises(ValueError, match="community"):
        service.edit([community], min_items=1, max_items=15)


def test_editorial_service_rejects_unverified_event() -> None:
    community = Article(
        id="c1",
        source_id="community-blog",
        source_name="Community Blog",
        source_group=SourceGroup.COMMUNITY,
        independence_group="community-blog-a",
        title="Rumor",
        url="https://community.example.com/rumor",
        canonical_url="https://community.example.com/rumor",
        normalized_title="rumor",
        fingerprint="c" * 64,
        published_at=datetime(2026, 7, 23, tzinfo=UTC),
        fetched_at=datetime(2026, 7, 23, tzinfo=UTC),
        excerpt="Something.",
        categories=["models"],
        rule_score=40,
    )

    class UnverifiedProvider:
        def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
            return {
                "daily_summary_zh": "摘要",
                "events": [
                    {
                        "id": "event-1",
                        "candidate_ids": [],
                        "category": "models",
                        "title_zh": "标题",
                        "summary_zh": "事实",
                        "why_it_matters_zh": "重要",
                        "importance_score": 90,
                        "primary_candidate_id": "c1",
                        "related_candidate_ids": [],
                    }
                ],
            }

    service = EditorialService(UnverifiedProvider(), "Output JSON.")
    # First fails on community primary, not unverified
    with pytest.raises(ValueError):
        service.edit([community], min_items=1, max_items=15)
