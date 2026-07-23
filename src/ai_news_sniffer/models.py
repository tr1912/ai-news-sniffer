from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

ProfileName = Literal["light", "balanced", "full"]


class SourceKind(StrEnum):
    RSS = "rss"
    ARXIV = "arxiv"
    GITHUB_RELEASES = "github_releases"
    HACKER_NEWS = "hacker_news"
    HTML_WHITELIST = "html_whitelist"


class SourceGroup(StrEnum):
    OFFICIAL = "official"
    RESEARCH = "research"
    MEDIA = "media"
    COMMUNITY = "community"


class ConfirmationStatus(StrEnum):
    PRIMARY_CONFIRMED = "primary_confirmed"
    CROSS_CONFIRMED = "cross_confirmed"
    UNVERIFIED = "unverified"


class RunStatus(StrEnum):
    PREPARED = "prepared"
    PUBLISHED = "published"
    NOTIFIED = "notified"
    PARTIALLY_NOTIFIED = "partially_notified"
    DEGRADED = "degraded"
    FAILED = "failed"


class HtmlSelectors(BaseModel):
    item: str = "article"
    title: str = "h2, h3"
    link: str = "a"
    date: str = "time"
    excerpt: str = "p"


class SourceConfig(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    kind: SourceKind
    group: SourceGroup
    enabled: bool = True
    profiles: set[ProfileName]
    url: HttpUrl
    categories: list[str] = Field(default_factory=list)
    weight: float = Field(default=0, ge=0, le=25)
    independence_group: str | None = None
    selectors: HtmlSelectors | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("source URL must use HTTPS")
        return value


class SourceGroupConfig(BaseModel):
    enabled: bool = True


class SourcesConfig(BaseModel):
    active_profile: ProfileName = "balanced"
    profile_candidate_limits: dict[ProfileName, int]
    source_groups: dict[SourceGroup, SourceGroupConfig]
    sources: list[SourceConfig]

    @model_validator(mode="after")
    def unique_source_ids(self) -> SourcesConfig:
        ids = [item.id for item in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source ids must be unique")
        return self


class EditorialBudget(BaseModel):
    max_candidates: int = Field(default=30, ge=1, le=100)
    max_excerpt_chars_per_item: int = Field(default=1200, ge=100, le=5000)
    max_total_prompt_chars: int = Field(default=60000, ge=100, le=200000)


class AppConfig(BaseModel):
    timezone: str = "Asia/Shanghai"
    lookback_hours: int = Field(default=48, ge=1, le=168)
    min_items: int = Field(default=8, ge=1, le=15)
    max_items: int = Field(default=15, ge=1, le=30)
    template: str = "default"
    public_base_url: HttpUrl
    editorial: EditorialBudget


class InterestsConfig(BaseModel):
    topics: list[str]
    entities: list[str]
    include_terms: list[str]
    exclude_terms: list[str]


class ProviderConfig(BaseModel):
    id: str
    api_style: str
    base_url: HttpUrl
    model: str
    api_key_env: str
    timeout_seconds: int = 60
    max_retries: int = 3


class ProvidersConfig(BaseModel):
    providers: list[ProviderConfig]
    fallback_order: list[str]


class ChannelConfig(BaseModel):
    id: str
    kind: str
    enabled: bool = False
    endpoint_env: str | None = None
    nickname_env: str | None = None
    timeout_seconds: int = 15
    max_retries: int = 3


class ChannelsConfig(BaseModel):
    channels: list[ChannelConfig]


class Settings(BaseModel):
    app: AppConfig
    sources: SourcesConfig
    interests: InterestsConfig
    providers: ProvidersConfig
    channels: ChannelsConfig


class RawArticle(BaseModel):
    source_id: str
    source_name: str
    source_group: SourceGroup
    independence_group: str
    title: str
    url: HttpUrl
    published_at: datetime
    fetched_at: datetime
    language: str = "unknown"
    excerpt: str = ""
    categories: list[str] = Field(default_factory=list)
    author: str | None = None
    upstream_urls: list[HttpUrl] = Field(default_factory=list)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class Article(RawArticle):
    id: str
    canonical_url: HttpUrl
    normalized_title: str
    fingerprint: str
    rule_score: float = Field(default=0, ge=0, le=100)


class SourceRef(BaseModel):
    source_id: str
    source_name: str
    title: str
    url: HttpUrl
    published_at: datetime


class NewsEvent(BaseModel):
    id: str
    candidate_ids: list[str]
    category: str
    title_zh: str
    summary_zh: str
    why_it_matters_zh: str
    importance_score: float = Field(ge=0, le=100)
    confirmation_status: ConfirmationStatus
    primary_source: SourceRef
    related_sources: list[SourceRef] = Field(default_factory=list)


class DailyReport(BaseModel):
    date: date
    generated_at: datetime
    run_id: str
    daily_summary_zh: str
    events: list[NewsEvent]
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)
    report_url: str | None = None
    source_coverage: dict[str, Any] = Field(default_factory=dict)


class ChannelResult(BaseModel):
    channel_id: str
    success: bool
    attempts: int
    error: str | None = None


class NotificationPayload(BaseModel):
    run_id: str
    date: date
    status: RunStatus
    title: str
    daily_summary: str
    top_items: list[NewsEvent]
    report_url: HttpUrl
    generated_at: datetime


class RunRecord(BaseModel):
    run_id: str
    target_date: date
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    report_path: str
    report_url: str | None = None
    pending_fingerprints: list[str] = Field(default_factory=list)
    channel_results: list[ChannelResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BudgetedCandidates(BaseModel):
    articles: list[Article]
    prompt_chars: int
    estimated_input_tokens: int


class SourceHealth(BaseModel):
    source_id: str
    consecutive_failures: int = 0
    degraded: bool = False
    auto_paused: bool = False
    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_error: str | None = None


class CandidateSource(BaseModel):
    domain: str
    sample_url: HttpUrl
    sample_title: str
    first_seen_at: datetime
    last_seen_at: datetime
    referring_source_ids: set[str]
    suggested_group: SourceGroup
    suggested_kind: SourceKind
    reason: str
    risk: str
    enabled: Literal[False] = False


class SourceCollection(BaseModel):
    enabled_source_ids: list[str]
    fetched_count: int
    normalized_count: int
    filtered_count: int
    budgeted: BudgetedCandidates
    failures: dict[str, str]
    newly_auto_paused_source_ids: list[str] = Field(default_factory=list)
