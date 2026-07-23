# AI News Source Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the configurable 35-source collection subsystem that feeds only verified, budget-bounded AI-news candidates into the existing daily-report pipeline.

**Architecture:** A typed source registry resolves profile, group, per-source, and one-run overrides before any network call. Focused RSS, API, GitHub Releases, and HTML-whitelist adapters normalize records into one article model; deterministic filtering, confirmation, health, discovery, and prompt-budget components run before the editorial model. This plan replaces Tasks 1–3 of `docs/superpowers/plans/2026-07-23-ai-news-sniffer.md`; after it passes, continue that plan at Task 4.

**Tech Stack:** Python 3.12, Pydantic 2.13, PyYAML 6, HTTPX 0.28, feedparser 6.0, selectolax 0.4, RapidFuzz 3, pytest 9, respx, Ruff, GitHub Actions.

## Global Constraints

- Use only the 35 configured sources in `docs/superpowers/specs/2026-07-23-ai-news-source-strategy-design.md`; AI cannot add or enable sources.
- `light`, `balanced`, and `full` must resolve to exactly 12, 25, and 35 sources before explicit user exclusions or runtime auto-pauses.
- `enabled: false` and a disabled source group are hard stops; `include_sources` can only narrow the already eligible set.
- RSS, Atom, public APIs, and GitHub Releases are preferred; HTML parsing is allowed only for explicit HTTPS whitelist entries.
- Do not add browser automation, paid search APIs, paywall bypasses, full-article storage, or automatic commits to `main`.
- Normal collection does not call a model. The later editorial call receives at most `max_candidates`, `max_excerpt_chars_per_item`, and `max_total_prompt_chars`.
- Official announcements, papers, and repositories can be `primary_confirmed`; media claims require two independent origins; community-only claims remain `unverified`.
- An `unverified` event cannot enter a published report, and a community source cannot be its primary source.
- Source failures are isolated. Three consecutive failures mark degradation; seven auto-pause the source in runtime state without editing configuration.
- Regular tests use fixtures and mocked HTTP. Only `sources audit` performs intentional live-network checks.
- Use TDD for every task: prove a focused failure, implement the smallest complete behavior, run focused and regression checks, then commit.

---

## File Structure

```text
.
├── .github/workflows/
│   └── source-audit.yml                 # Manual live source audit with profile overrides
├── config/
│   ├── app.yaml                         # Editorial candidate and prompt-character budgets
│   ├── channels.yaml                    # Downstream notification configuration
│   ├── interests.yaml                   # Interest and exclusion terms
│   ├── providers.yaml                   # Downstream model configuration
│   └── sources.yaml                     # 35-source registry, groups, profiles, selectors
├── src/ai_news_sniffer/
│   ├── __init__.py                      # Package metadata
│   ├── models.py                        # Shared Pydantic domain/config models
│   ├── config.py                        # YAML loading and validation
│   ├── normalization.py                 # Canonical URLs, normalized titles, fingerprints
│   ├── dedup.py                         # Deterministic URL/title/history deduplication
│   ├── scoring.py                       # Configurable 100-point rule scoring
│   ├── source_budget.py                 # Candidate count and prompt-character hard limits
│   ├── source_registry.py               # Profile/group/source/runtime resolution
│   ├── source_verification.py           # Primary/cross/unverified classification
│   ├── source_health.py                 # Runtime health, degradation, auto-pause
│   ├── source_discovery.py              # Candidate-domain records without auto-enable
│   ├── source_service.py                # Collection orchestration and isolation
│   ├── source_cli.py                    # Reusable `sources` parser and command handler
│   ├── cli.py                           # Initial executable CLI; later extended by main plan
│   └── sources/
│       ├── __init__.py                  # Source adapter package
│       ├── base.py                      # Adapter protocol, errors, factory
│       ├── rss.py                       # RSS/Atom adapter
│       ├── arxiv.py                     # arXiv Atom API adapter
│       ├── github.py                    # GitHub Releases adapter
│       ├── hacker_news.py               # Hacker News API adapter
│       └── html.py                      # JSON-LD and CSS whitelist adapter
├── tests/
│   ├── fixtures/
│   │   ├── arxiv.xml
│   │   ├── github_releases.json
│   │   ├── hn_item.json
│   │   ├── hn_topstories.json
│   │   ├── html_jsonld.html
│   │   ├── html_selectors.html
│   │   └── rss.xml
│   ├── test_config.py
│   ├── test_source_adapters.py
│   ├── test_source_budget.py
│   ├── test_source_cli.py
│   ├── test_source_health_discovery.py
│   ├── test_source_registry.py
│   ├── test_source_service.py
│   ├── test_source_verification.py
│   └── test_source_workflow.py
├── README.md
└── pyproject.toml
```

---

### Task 1: Shared Models, Configuration Loader, and the 35-Source Registry

**Files:**
- Create: `pyproject.toml`
- Create: `src/ai_news_sniffer/__init__.py`
- Create: `src/ai_news_sniffer/models.py`
- Create: `src/ai_news_sniffer/config.py`
- Create: `config/app.yaml`
- Create: `config/sources.yaml`
- Create: `config/interests.yaml`
- Create: `config/providers.yaml`
- Create: `config/channels.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `load_settings(config_dir: Path) -> Settings`.
- Produces: `SourceConfig`, `SourcesConfig`, `EditorialBudget`, `RawArticle`, `Article`, `SourceRef`, `NewsEvent`, `DailyReport`, and downstream provider/channel models.
- Consumes: YAML files containing no secrets.

- [ ] **Step 1: Write failing configuration tests**

Create `tests/test_config.py`:

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_news_sniffer.config import load_settings
from ai_news_sniffer.models import SourceConfig, SourceKind

ROOT = Path(__file__).parents[1]


def test_committed_registry_has_exact_profile_counts() -> None:
    settings = load_settings(ROOT / "config")

    assert len(settings.sources.sources) == 35
    assert sum("light" in item.profiles for item in settings.sources.sources) == 12
    assert sum("balanced" in item.profiles for item in settings.sources.sources) == 25
    assert sum("full" in item.profiles for item in settings.sources.sources) == 35
    assert len({item.id for item in settings.sources.sources}) == 35


def test_source_rejects_non_https_url() -> None:
    with pytest.raises(ValidationError):
        SourceConfig(
            id="bad",
            name="Bad",
            kind=SourceKind.RSS,
            group="media",
            url="http://example.com/feed",
            profiles={"full"},
        )


def test_editorial_budget_is_loaded() -> None:
    settings = load_settings(ROOT / "config")

    assert settings.app.editorial.max_candidates == 30
    assert settings.app.editorial.max_excerpt_chars_per_item == 1200
    assert settings.app.editorial.max_total_prompt_chars == 60000
    assert settings.sources.profile_candidate_limits == {
        "light": 20,
        "balanced": 30,
        "full": 40,
    }
```

- [ ] **Step 2: Run the focused test and prove the package is missing**

Run:

```bash
pytest tests/test_config.py -v
```

Expected: test collection fails with `ModuleNotFoundError: No module named 'ai_news_sniffer'`.

- [ ] **Step 3: Add the package and dependency configuration**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[project]
name = "ai-news-sniffer"
version = "0.1.0"
requires-python = ">=3.12,<3.15"
dependencies = [
  "feedparser>=6.0.12,<7",
  "httpx>=0.28.1,<1",
  "jinja2>=3.1.6,<4",
  "openai>=2.47,<3",
  "pydantic>=2.13.4,<3",
  "pyyaml>=6.0.2,<7",
  "rapidfuzz>=3.13,<4",
  "selectolax>=0.4.11,<1",
]

[project.optional-dependencies]
dev = [
  "pytest>=9.1,<10",
  "pytest-cov>=7,<8",
  "respx>=0.22,<1",
  "ruff>=0.14,<1",
]

[project.scripts]
ai-news-sniffer = "ai_news_sniffer.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/ai_news_sniffer"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
```

Create `src/ai_news_sniffer/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Define complete shared models**

Create `src/ai_news_sniffer/models.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


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
    max_total_prompt_chars: int = Field(default=60000, ge=1000, le=200000)


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
```

- [ ] **Step 5: Implement YAML loading**

Create `src/ai_news_sniffer/config.py`:

```python
import os
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from ai_news_sniffer.models import (
    AppConfig,
    ChannelsConfig,
    InterestsConfig,
    ProvidersConfig,
    Settings,
    SourcesConfig,
)

ConfigModel = TypeVar("ConfigModel", bound=BaseModel)


def _load_yaml(path: Path, model: type[ConfigModel]) -> ConfigModel:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return model.model_validate(payload)


def load_settings(config_dir: Path) -> Settings:
    app = _load_yaml(config_dir / "app.yaml", AppConfig)
    if public_base_url := os.getenv("PUBLIC_BASE_URL"):
        app.public_base_url = public_base_url
    return Settings(
        app=app,
        sources=_load_yaml(config_dir / "sources.yaml", SourcesConfig),
        interests=_load_yaml(config_dir / "interests.yaml", InterestsConfig),
        providers=_load_yaml(config_dir / "providers.yaml", ProvidersConfig),
        channels=_load_yaml(config_dir / "channels.yaml", ChannelsConfig),
    )


def resolve_secret(env_name: str) -> str:
    value = os.getenv(env_name)
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {env_name}")
    return value
```

- [ ] **Step 6: Add non-source configuration**

Create `config/app.yaml`:

```yaml
timezone: Asia/Shanghai
lookback_hours: 48
min_items: 8
max_items: 15
template: default
public_base_url: https://example.github.io/ai-news-sniffer
editorial:
  max_candidates: 30
  max_excerpt_chars_per_item: 1200
  max_total_prompt_chars: 60000
```

Create `config/interests.yaml`:

```yaml
topics: [models, products, research, open-source, developer-tools, business, policy]
entities: [OpenAI, Anthropic, Google DeepMind, Meta AI, DeepSeek, Kimi, MiniMax]
include_terms: [AI, LLM, agent, multimodal, inference, reasoning, open-source]
exclude_terms: [sponsored, giveaway, 招聘, 赞助]
```

Create `config/providers.yaml`:

```yaml
providers:
  - id: deepseek
    api_style: openai_chat_completions
    base_url: https://api.deepseek.com
    model: deepseek-v4-flash
    api_key_env: DEEPSEEK_API_KEY
    timeout_seconds: 60
    max_retries: 3
fallback_order: [deepseek]
```

Create `config/channels.yaml`:

```yaml
channels:
  - id: meow
    kind: meow
    enabled: true
    nickname_env: MEOW_NICKNAME
    timeout_seconds: 15
    max_retries: 3
  - id: wecom
    kind: wecom
    enabled: false
    endpoint_env: WECOM_WEBHOOK_URL
    timeout_seconds: 15
    max_retries: 3
  - id: webhook
    kind: webhook
    enabled: false
    endpoint_env: GENERIC_WEBHOOK_URL
    timeout_seconds: 15
    max_retries: 3
```

- [ ] **Step 7: Add the exact 35-source configuration**

Create `config/sources.yaml`:

```yaml
active_profile: balanced
profile_candidate_limits:
  light: 20
  balanced: 30
  full: 40
source_groups:
  official: {enabled: true}
  research: {enabled: true}
  media: {enabled: true}
  community: {enabled: true}
sources:
  - {id: openai-news, name: OpenAI Newsroom, kind: html_whitelist, group: official, enabled: true, profiles: [light, balanced, full], url: "https://openai.com/news/", categories: [models, products, company], weight: 25}
  - {id: anthropic-news, name: Anthropic Newsroom, kind: html_whitelist, group: official, enabled: true, profiles: [light, balanced, full], url: "https://www.anthropic.com/news", categories: [models, products, safety], weight: 25}
  - {id: deepmind-news, name: Google DeepMind News, kind: html_whitelist, group: official, enabled: true, profiles: [light, balanced, full], url: "https://deepmind.google/discover/blog/", categories: [models, research], weight: 25}
  - {id: google-research, name: Google Research Blog, kind: html_whitelist, group: official, enabled: true, profiles: [balanced, full], url: "https://research.google/blog/", categories: [research], weight: 24}
  - {id: meta-ai-blog, name: Meta AI Blog, kind: html_whitelist, group: official, enabled: true, profiles: [light, balanced, full], url: "https://ai.meta.com/blog", categories: [models, research, open-source], weight: 25}
  - {id: microsoft-research, name: Microsoft Research Blog, kind: html_whitelist, group: official, enabled: true, profiles: [balanced, full], url: "https://www.microsoft.com/en-us/research/blog/", categories: [research, products], weight: 23}
  - {id: nvidia-genai, name: NVIDIA Generative AI Blog, kind: rss, group: official, enabled: true, profiles: [balanced, full], url: "https://developer.nvidia.com/blog/blog/category/generative-ai/feed/", categories: [infrastructure, products], weight: 23}
  - {id: aws-ai-blog, name: AWS AI and ML Blog, kind: rss, group: official, enabled: true, profiles: [full], url: "https://aws.amazon.com/blogs/machine-learning/feed/", categories: [products, developer-tools], weight: 21}
  - {id: huggingface-blog, name: Hugging Face Blog, kind: rss, group: official, enabled: true, profiles: [light, balanced, full], url: "https://huggingface.co/blog/feed.xml", categories: [models, research, open-source], weight: 25}
  - {id: deepseek-updates, name: DeepSeek API Updates, kind: html_whitelist, group: official, enabled: true, profiles: [light, balanced, full], url: "https://api-docs.deepseek.com/updates/", categories: [models, products], weight: 25}
  - {id: kimi-platform-blog, name: Kimi Platform Blog, kind: html_whitelist, group: official, enabled: true, profiles: [light, balanced, full], url: "https://platform.kimi.com/blog", categories: [models, products], weight: 25}
  - {id: qwen-blog, name: Qwen Blog, kind: html_whitelist, group: official, enabled: true, profiles: [light, balanced, full], url: "https://qwenlm.github.io/blog/", categories: [models, open-source], weight: 25}
  - {id: minimax-news, name: MiniMax News, kind: html_whitelist, group: official, enabled: true, profiles: [light, balanced, full], url: "https://www.minimaxi.com/news", categories: [models, products], weight: 25}
  - {id: zhipu-research, name: Zhipu GLM Research, kind: html_whitelist, group: official, enabled: true, profiles: [light, balanced, full], url: "https://www.zhipuai.cn/zh/research", categories: [models, research, open-source], weight: 25}
  - {id: mistral-news, name: Mistral News, kind: html_whitelist, group: official, enabled: true, profiles: [balanced, full], url: "https://mistral.ai/news/", categories: [models, products, open-source], weight: 24}
  - {id: cohere-blog, name: Cohere Blog, kind: html_whitelist, group: official, enabled: true, profiles: [balanced, full], url: "https://cohere.com/blog", categories: [models, products, research], weight: 23}
  - {id: apple-ml, name: Apple Machine Learning Research, kind: html_whitelist, group: official, enabled: true, profiles: [full], url: "https://machinelearning.apple.com/", categories: [research, products], weight: 23}
  - {id: arxiv-ai, name: arXiv AI, kind: arxiv, group: research, enabled: true, profiles: [light, balanced, full], url: "https://export.arxiv.org/api/query", categories: [research], weight: 22, options: {query: "cat:cs.AI OR cat:cs.CL OR cat:cs.LG", max_results: 30}}
  - {id: hf-daily-papers, name: Hugging Face Daily Papers, kind: html_whitelist, group: research, enabled: true, profiles: [light, balanced, full], url: "https://huggingface.co/papers", categories: [research], weight: 22}
  - {id: vllm-releases, name: vLLM Releases, kind: github_releases, group: research, enabled: true, profiles: [balanced, full], url: "https://api.github.com/repos/vllm-project/vllm/releases", categories: [open-source, inference], weight: 22, options: {repository: "vllm-project/vllm"}}
  - {id: transformers-releases, name: Transformers Releases, kind: github_releases, group: research, enabled: true, profiles: [balanced, full], url: "https://api.github.com/repos/huggingface/transformers/releases", categories: [open-source, developer-tools], weight: 22, options: {repository: "huggingface/transformers"}}
  - {id: llama-cpp-releases, name: llama.cpp Releases, kind: github_releases, group: research, enabled: true, profiles: [balanced, full], url: "https://api.github.com/repos/ggml-org/llama.cpp/releases", categories: [open-source, inference], weight: 21, options: {repository: "ggml-org/llama.cpp"}}
  - {id: ollama-releases, name: Ollama Releases, kind: github_releases, group: research, enabled: true, profiles: [full], url: "https://api.github.com/repos/ollama/ollama/releases", categories: [open-source, products], weight: 20, options: {repository: "ollama/ollama"}}
  - {id: langchain-releases, name: LangChain Releases, kind: github_releases, group: research, enabled: true, profiles: [full], url: "https://api.github.com/repos/langchain-ai/langchain/releases", categories: [open-source, developer-tools], weight: 19, options: {repository: "langchain-ai/langchain"}}
  - {id: llama-index-releases, name: LlamaIndex Releases, kind: github_releases, group: research, enabled: true, profiles: [full], url: "https://api.github.com/repos/run-llama/llama_index/releases", categories: [open-source, developer-tools], weight: 19, options: {repository: "run-llama/llama_index"}}
  - {id: 36kr, name: 36Kr, kind: rss, group: media, enabled: true, profiles: [balanced, full], url: "https://36kr.com/feed", categories: [business, products], weight: 17}
  - {id: jiqizhixin, name: 机器之心, kind: html_whitelist, group: media, enabled: true, profiles: [balanced, full], url: "https://www.jiqizhixin.com/", categories: [models, research, products], weight: 18}
  - {id: qbitai, name: 量子位, kind: html_whitelist, group: media, enabled: true, profiles: [balanced, full], url: "https://www.qbitai.com/", categories: [models, products, business], weight: 18}
  - {id: techcrunch-ai, name: TechCrunch AI, kind: rss, group: media, enabled: true, profiles: [balanced, full], url: "https://techcrunch.com/category/artificial-intelligence/feed/", categories: [business, products], weight: 17}
  - {id: venturebeat-ai, name: VentureBeat AI, kind: rss, group: media, enabled: true, profiles: [full], url: "https://venturebeat.com/category/ai/feed/", categories: [business, products], weight: 16}
  - {id: the-verge-ai, name: The Verge AI, kind: rss, group: media, enabled: true, profiles: [full], url: "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", categories: [products, policy], weight: 16}
  - {id: ars-ai, name: Ars Technica AI, kind: rss, group: media, enabled: true, profiles: [full], url: "https://feeds.arstechnica.com/arstechnica/technology-lab", categories: [technology, policy], weight: 16}
  - {id: hacker-news, name: Hacker News, kind: hacker_news, group: community, enabled: true, profiles: [balanced, full], url: "https://hacker-news.firebaseio.com/v0/topstories.json", categories: [products, developer-tools], weight: 10, options: {item_limit: 100}}
  - {id: github-trending, name: GitHub Trending, kind: html_whitelist, group: community, enabled: true, profiles: [full], url: "https://github.com/trending", categories: [open-source, developer-tools], weight: 9}
  - {id: hf-trending-models, name: Hugging Face Trending Models, kind: html_whitelist, group: community, enabled: true, profiles: [full], url: "https://huggingface.co/models?sort=trending", categories: [models, open-source], weight: 9}
```

- [ ] **Step 8: Run configuration tests and commit**

Run:

```bash
pytest tests/test_config.py -v
ruff check src tests
```

Expected: `3 passed`; Ruff exits 0.

Commit:

```bash
git add pyproject.toml src/ai_news_sniffer config tests/test_config.py
git commit -m "feat: add configurable 35-source registry"
```

---

### Task 2: Profile Resolution and AI Input Budget

**Files:**
- Create: `src/ai_news_sniffer/source_registry.py`
- Create: `src/ai_news_sniffer/source_budget.py`
- Test: `tests/test_source_registry.py`
- Test: `tests/test_source_budget.py`

**Interfaces:**
- Consumes: `SourcesConfig`, `EditorialBudget`, `Article`.
- Produces: `resolve_sources(config, profile_override, include_sources, exclude_sources, auto_paused) -> list[SourceConfig]`.
- Produces: `apply_source_budget(articles, budget, max_candidates_override=None) -> BudgetedCandidates`.

- [ ] **Step 1: Write failing profile-resolution tests**

Create `tests/test_source_registry.py`:

```python
from pathlib import Path

from ai_news_sniffer.config import load_settings
from ai_news_sniffer.source_registry import resolve_sources

ROOT = Path(__file__).parents[1]


def ids(profile: str, **kwargs: object) -> set[str]:
    settings = load_settings(ROOT / "config")
    return {
        item.id
        for item in resolve_sources(
            settings.sources,
            profile_override=profile,
            **kwargs,
        )
    }


def test_profiles_resolve_exact_counts() -> None:
    assert len(ids("light")) == 12
    assert len(ids("balanced")) == 25
    assert len(ids("full")) == 35


def test_include_only_narrows_and_exclude_wins() -> None:
    selected = ids(
        "balanced",
        include_sources={"openai-news", "github-trending"},
        exclude_sources={"openai-news"},
    )
    assert selected == set()


def test_runtime_auto_pause_removes_source() -> None:
    assert "openai-news" not in ids("light", auto_paused={"openai-news"})
```

- [ ] **Step 2: Write failing prompt-budget tests**

Create `tests/test_source_budget.py`:

```python
from datetime import UTC, datetime

from ai_news_sniffer.models import Article, EditorialBudget, SourceGroup
from ai_news_sniffer.source_budget import apply_source_budget

NOW = datetime(2026, 7, 23, tzinfo=UTC)


def article(number: int, score: float, excerpt: str) -> Article:
    return Article(
        id=str(number),
        source_id=f"source-{number}",
        source_name=f"Source {number}",
        source_group=SourceGroup.OFFICIAL,
        independence_group=f"source-{number}",
        title=f"Title {number}",
        url=f"https://example.com/{number}",
        canonical_url=f"https://example.com/{number}",
        normalized_title=f"title {number}",
        fingerprint=str(number) * 64,
        published_at=NOW,
        fetched_at=NOW,
        excerpt=excerpt,
        rule_score=score,
    )


def test_budget_enforces_count_item_and_total_character_caps() -> None:
    result = apply_source_budget(
        [
            article(1, 90, "a" * 1000),
            article(2, 80, "b" * 1000),
            article(3, 70, "c" * 1000),
        ],
        EditorialBudget(
            max_candidates=3,
            max_excerpt_chars_per_item=200,
            max_total_prompt_chars=450,
        ),
    )

    assert [item.id for item in result.articles] == ["1", "2"]
    assert all(len(item.excerpt) <= 200 for item in result.articles)
    assert result.prompt_chars <= 450
    assert result.estimated_input_tokens == max(1, result.prompt_chars // 4)


def test_one_run_candidate_override_can_raise_or_lower_profile_default() -> None:
    articles = [article(number, 100 - number, "short") for number in range(50)]
    budget = EditorialBudget(
        max_candidates=30,
        max_excerpt_chars_per_item=200,
        max_total_prompt_chars=60000,
    )

    assert len(apply_source_budget(articles, budget, 20).articles) == 20
    assert len(apply_source_budget(articles, budget, 40).articles) == 40
```

- [ ] **Step 3: Run both tests and prove the modules are missing**

Run:

```bash
pytest tests/test_source_registry.py tests/test_source_budget.py -v
```

Expected: collection fails because `source_registry` and `source_budget` do not exist.

- [ ] **Step 4: Implement deterministic source resolution**

Create `src/ai_news_sniffer/source_registry.py`:

```python
from ai_news_sniffer.models import ProfileName, SourceConfig, SourcesConfig


def resolve_sources(
    config: SourcesConfig,
    profile_override: ProfileName | None = None,
    include_sources: set[str] | None = None,
    exclude_sources: set[str] | None = None,
    auto_paused: set[str] | None = None,
) -> list[SourceConfig]:
    profile = profile_override or config.active_profile
    included = include_sources or set()
    excluded = exclude_sources or set()
    paused = auto_paused or set()
    selected: list[SourceConfig] = []

    for source in config.sources:
        if not source.enabled:
            continue
        if not config.source_groups[source.group].enabled:
            continue
        if profile not in source.profiles:
            continue
        if included and source.id not in included:
            continue
        if source.id in excluded or source.id in paused:
            continue
        selected.append(source)
    return selected
```

- [ ] **Step 5: Implement hard prompt-budget enforcement**

Create `src/ai_news_sniffer/source_budget.py`:

```python
from ai_news_sniffer.models import (
    Article,
    BudgetedCandidates,
    EditorialBudget,
)


def _prompt_chars(article: Article) -> int:
    return len(article.title) + len(article.source_name) + len(article.excerpt) + 16


def apply_source_budget(
    articles: list[Article],
    budget: EditorialBudget,
    max_candidates_override: int | None = None,
) -> BudgetedCandidates:
    limit = budget.max_candidates
    if max_candidates_override is not None:
        limit = max(1, min(100, max_candidates_override))

    selected: list[Article] = []
    total_chars = 0
    for article in sorted(articles, key=lambda item: item.rule_score, reverse=True):
        clipped = article.model_copy(
            update={"excerpt": article.excerpt[: budget.max_excerpt_chars_per_item]}
        )
        size = _prompt_chars(clipped)
        if size > budget.max_total_prompt_chars:
            continue
        if total_chars + size > budget.max_total_prompt_chars:
            continue
        selected.append(clipped)
        total_chars += size
        if len(selected) == limit:
            break

    return BudgetedCandidates(
        articles=selected,
        prompt_chars=total_chars,
        estimated_input_tokens=max(1, total_chars // 4),
    )
```

- [ ] **Step 6: Run focused and regression tests, then commit**

Run:

```bash
pytest tests/test_source_registry.py tests/test_source_budget.py -v
pytest -q
ruff check src tests
```

Expected: focused tests report `5 passed`; full suite and Ruff exit 0.

Commit:

```bash
git add src/ai_news_sniffer/source_registry.py src/ai_news_sniffer/source_budget.py tests/test_source_registry.py tests/test_source_budget.py
git commit -m "feat: add source profiles and AI input budgets"
```

---

### Task 3: RSS, arXiv, GitHub Releases, Hacker News, and Normalization

**Files:**
- Create: `src/ai_news_sniffer/sources/__init__.py`
- Create: `src/ai_news_sniffer/sources/base.py`
- Create: `src/ai_news_sniffer/sources/rss.py`
- Create: `src/ai_news_sniffer/sources/arxiv.py`
- Create: `src/ai_news_sniffer/sources/github.py`
- Create: `src/ai_news_sniffer/sources/hacker_news.py`
- Create: `src/ai_news_sniffer/normalization.py`
- Create: `tests/fixtures/rss.xml`
- Create: `tests/fixtures/arxiv.xml`
- Create: `tests/fixtures/github_releases.json`
- Create: `tests/fixtures/hn_topstories.json`
- Create: `tests/fixtures/hn_item.json`
- Test: `tests/test_source_adapters.py`

**Interfaces:**
- Consumes: `SourceConfig`, `RawArticle`, a shared `httpx.Client`, `since`, and `until`.
- Produces: `SourceAdapter.fetch(source, since, until) -> list[RawArticle]`.
- Produces: `build_source_adapter(source, client) -> SourceAdapter`.
- Produces: `normalize_article(raw) -> Article`.

- [ ] **Step 1: Write failing adapter and normalization tests**

Create `tests/test_source_adapters.py`:

```python
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
        id=kind.value,
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
```

- [ ] **Step 2: Add deterministic fixtures**

Create `tests/fixtures/rss.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example</title>
    <item>
      <title>New model released</title>
      <link>https://example.com/post</link>
      <description>A factual description.</description>
      <pubDate>Thu, 23 Jul 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
```

Create `tests/fixtures/arxiv.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>arXiv Query</title>
  <entry>
    <id>https://arxiv.org/abs/2607.00001</id>
    <updated>2026-07-23T10:00:00Z</updated>
    <published>2026-07-23T09:00:00Z</published>
    <title>Reliable Agent Evaluation</title>
    <summary>A controlled evaluation of agents.</summary>
    <author><name>Example Author</name></author>
    <link href="https://arxiv.org/abs/2607.00001" rel="alternate"/>
  </entry>
</feed>
```

Create `tests/fixtures/github_releases.json`:

```json
[
  {
    "id": 7,
    "name": "v1.2.0",
    "tag_name": "v1.2.0",
    "html_url": "https://github.com/example/repo/releases/tag/v1.2.0",
    "published_at": "2026-07-23T08:00:00Z",
    "body": "Adds a new inference engine.",
    "author": {"login": "maintainer"}
  }
]
```

Create `tests/fixtures/hn_topstories.json`:

```json
[42]
```

Create `tests/fixtures/hn_item.json`:

```json
{
  "id": 42,
  "type": "story",
  "title": "New open model",
  "url": "https://primary.example/model",
  "by": "submitter",
  "time": 1784793600,
  "score": 250
}
```

- [ ] **Step 3: Run tests and prove adapter modules are missing**

Run:

```bash
pytest tests/test_source_adapters.py -v
```

Expected: collection fails because `ai_news_sniffer.normalization` and `ai_news_sniffer.sources` do not exist.

- [ ] **Step 4: Define adapter errors, protocol, and factory**

Create empty `src/ai_news_sniffer/sources/__init__.py`.

Create `src/ai_news_sniffer/sources/base.py`:

```python
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
```

- [ ] **Step 5: Implement RSS and arXiv adapters**

Create `src/ai_news_sniffer/sources/rss.py`:

```python
from calendar import timegm
from datetime import UTC, datetime

import feedparser
import httpx

from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.sources.base import SourceFetchError


def entry_datetime(entry: object) -> datetime:
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry,
        "updated_parsed",
        None,
    )
    if parsed is None:
        return datetime.now(UTC)
    return datetime.fromtimestamp(timegm(parsed), tz=UTC)


class RssAdapter:
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
            raise SourceFetchError(f"{source.id}: RSS fetch failed") from exc

        feed = feedparser.parse(response.content)
        articles: list[RawArticle] = []
        for entry in feed.entries:
            published_at = entry_datetime(entry)
            link = getattr(entry, "link", None) or getattr(entry, "id", None)
            if not link or not since <= published_at <= until:
                continue
            articles.append(
                RawArticle(
                    source_id=source.id,
                    source_name=source.name,
                    source_group=source.group,
                    independence_group=source.independence_group or source.id,
                    title=str(getattr(entry, "title", "")).strip(),
                    url=link,
                    published_at=published_at,
                    fetched_at=datetime.now(UTC),
                    excerpt=str(
                        getattr(entry, "summary", getattr(entry, "description", ""))
                    ).strip(),
                    author=getattr(entry, "author", None),
                    categories=source.categories,
                )
            )
        return articles
```

Create `src/ai_news_sniffer/sources/arxiv.py`:

```python
from urllib.parse import urlencode

from ai_news_sniffer.models import SourceConfig
from ai_news_sniffer.sources.rss import RssAdapter


class ArxivAdapter(RssAdapter):
    def fetch(self, source: SourceConfig, since, until):  # type: ignore[no-untyped-def]
        query = str(source.options["query"])
        max_results = int(source.options.get("max_results", 30))
        url = f"{source.url}?{urlencode({
            'search_query': query,
            'sortBy': 'submittedDate',
            'sortOrder': 'descending',
            'max_results': max_results,
        })}"
        arxiv_source = source.model_copy(update={"url": url})
        return super().fetch(arxiv_source, since, until)
```

- [ ] **Step 6: Implement GitHub Releases and Hacker News adapters**

Create `src/ai_news_sniffer/sources/github.py`:

```python
from datetime import UTC, datetime

import httpx

from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.sources.base import SourceFetchError


class GitHubReleasesAdapter:
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
                headers={"Accept": "application/vnd.github+json"},
                timeout=20,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"{source.id}: GitHub fetch failed") from exc

        articles: list[RawArticle] = []
        for release in response.json():
            if not release.get("published_at") or release.get("draft"):
                continue
            published_at = datetime.fromisoformat(
                release["published_at"].replace("Z", "+00:00")
            )
            if not since <= published_at <= until:
                continue
            title = release.get("name") or release["tag_name"]
            articles.append(
                RawArticle(
                    source_id=source.id,
                    source_name=source.name,
                    source_group=source.group,
                    independence_group=source.independence_group or source.id,
                    title=f"{source.name}: {title}",
                    url=release["html_url"],
                    published_at=published_at,
                    fetched_at=datetime.now(UTC),
                    excerpt=(release.get("body") or "")[:2000],
                    author=(release.get("author") or {}).get("login"),
                    categories=source.categories,
                    raw_metadata={"release_id": release["id"]},
                )
            )
        return articles
```

Create `src/ai_news_sniffer/sources/hacker_news.py`:

```python
from datetime import UTC, datetime

import httpx

from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.sources.base import SourceFetchError


class HackerNewsAdapter:
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
            ids = response.json()[: int(source.options.get("item_limit", 100))]
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"{source.id}: HN index fetch failed") from exc

        articles: list[RawArticle] = []
        for item_id in ids:
            item_url = f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
            try:
                item_response = self.client.get(item_url, timeout=10)
                item_response.raise_for_status()
            except httpx.HTTPError:
                continue
            item = item_response.json()
            if item.get("type") != "story" or not item.get("url"):
                continue
            published_at = datetime.fromtimestamp(item["time"], tz=UTC)
            if not since <= published_at <= until:
                continue
            articles.append(
                RawArticle(
                    source_id=source.id,
                    source_name=source.name,
                    source_group=source.group,
                    independence_group=source.independence_group or source.id,
                    title=item["title"],
                    url=item["url"],
                    published_at=published_at,
                    fetched_at=datetime.now(UTC),
                    author=item.get("by"),
                    categories=source.categories,
                    upstream_urls=[item["url"]],
                    raw_metadata={
                        "hn_id": item_id,
                        "score": item.get("score", 0),
                    },
                )
            )
        return articles
```

- [ ] **Step 7: Implement normalization**

Create `src/ai_news_sniffer/normalization.py`:

```python
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ai_news_sniffer.models import Article, RawArticle

TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "ref", "source"}


def canonicalize_url(url: str) -> str:
    split = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(split.query, keep_blank_values=True)
        if key.casefold() not in TRACKING_KEYS
        and not key.casefold().startswith(TRACKING_PREFIXES)
    ]
    return urlunsplit(
        (
            split.scheme.casefold(),
            split.netloc.casefold(),
            split.path.rstrip("/") or "/",
            urlencode(query),
            "",
        )
    )


def normalize_title(title: str) -> str:
    return " ".join(re.findall(r"[\w\u4e00-\u9fff]+", title.casefold()))


def normalize_article(raw: RawArticle) -> Article:
    canonical_url = canonicalize_url(str(raw.url))
    normalized_title = normalize_title(raw.title)
    fingerprint = hashlib.sha256(
        f"{canonical_url}|{normalized_title}".encode()
    ).hexdigest()
    return Article(
        **raw.model_dump(),
        id=fingerprint[:16],
        canonical_url=canonical_url,
        normalized_title=normalized_title,
        fingerprint=fingerprint,
    )
```

- [ ] **Step 8: Run adapter tests and commit**

Run:

```bash
pytest tests/test_source_adapters.py -v
pytest -q
ruff check src tests
```

Expected: adapter tests report `3 passed`; full suite and Ruff exit 0.

Commit:

```bash
git add src/ai_news_sniffer/sources src/ai_news_sniffer/normalization.py tests/fixtures tests/test_source_adapters.py
git commit -m "feat: add public feed and API source adapters"
```

---

### Task 4: HTML Whitelist Parsing

**Files:**
- Create: `src/ai_news_sniffer/sources/html.py`
- Create: `tests/fixtures/html_jsonld.html`
- Create: `tests/fixtures/html_selectors.html`
- Modify: `tests/test_source_adapters.py`

**Interfaces:**
- Consumes: a `SourceConfig` whose `kind` is `html_whitelist`.
- Produces: `HtmlWhitelistAdapter.fetch(...) -> list[RawArticle]`.
- Raises: `SourceFetchError` for HTTP failure and `SourceParseError` when neither JSON-LD nor configured selectors yield valid dated links.

- [ ] **Step 1: Add failing JSON-LD and selector tests**

Append to `tests/test_source_adapters.py`:

```python
from ai_news_sniffer.models import HtmlSelectors
from ai_news_sniffer.sources.base import SourceParseError


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
```

Add `import pytest` to the existing test imports.

- [ ] **Step 2: Add HTML fixtures**

Create `tests/fixtures/html_jsonld.html`:

```html
<!doctype html>
<html>
  <head>
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
          {
            "@type": "NewsArticle",
            "headline": "Official model launch",
            "url": "/model",
            "datePublished": "2026-07-23T09:00:00Z",
            "description": "The company released a model."
          }
        ]
      }
    </script>
  </head>
</html>
```

Create `tests/fixtures/html_selectors.html`:

```html
<!doctype html>
<html>
  <body>
    <article class="story">
      <h2 class="title"><a href="/story">Selector story</a></h2>
      <time datetime="2026-07-23T08:00:00Z"></time>
      <p class="summary">A sourced summary.</p>
    </article>
    <article class="story">
      <h2 class="title"><a href="/missing-date">Missing date</a></h2>
      <p class="summary">This item is skipped.</p>
    </article>
  </body>
</html>
```

- [ ] **Step 3: Run focused tests and prove the HTML adapter is missing**

Run:

```bash
pytest tests/test_source_adapters.py -v
```

Expected: HTML tests fail because `ai_news_sniffer.sources.html` does not exist.

- [ ] **Step 4: Implement JSON-LD and selector parsing**

Create `src/ai_news_sniffer/sources/html.py`:

```python
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
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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
                    date_node.attributes.get("datetime")
                    if date_node
                    else None
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
```

- [ ] **Step 5: Run HTML and regression tests, then commit**

Run:

```bash
pytest tests/test_source_adapters.py -v
pytest -q
ruff check src tests
```

Expected: adapter tests report `6 passed`; full suite and Ruff exit 0.

Commit:

```bash
git add src/ai_news_sniffer/sources/html.py tests/fixtures/html_jsonld.html tests/fixtures/html_selectors.html tests/test_source_adapters.py
git commit -m "feat: add fail-closed HTML whitelist adapter"
```

---

### Task 5: Deduplication, Rule Scoring, and Fact Confirmation

**Files:**
- Create: `src/ai_news_sniffer/dedup.py`
- Create: `src/ai_news_sniffer/scoring.py`
- Create: `src/ai_news_sniffer/source_verification.py`
- Test: `tests/test_source_verification.py`

**Interfaces:**
- Consumes: normalized `Article` objects and configured source weights.
- Produces: `deduplicate_articles(...) -> list[Article]`.
- Produces: `score_articles(...) -> list[Article]`.
- Produces: `confirmation_status(cluster) -> ConfirmationStatus`.
- Produces: `validate_event_sources(event, articles) -> None`.

- [ ] **Step 1: Write failing deduplication, scoring, and confirmation tests**

Create `tests/test_source_verification.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from ai_news_sniffer.dedup import deduplicate_articles
from ai_news_sniffer.models import (
    Article,
    ConfirmationStatus,
    InterestsConfig,
    NewsEvent,
    SourceGroup,
    SourceRef,
)
from ai_news_sniffer.scoring import score_articles
from ai_news_sniffer.source_verification import (
    confirmation_status,
    validate_event_sources,
)

NOW = datetime(2026, 7, 23, 13, tzinfo=UTC)


def article(
    article_id: str,
    source_id: str,
    group: SourceGroup,
    independence_group: str,
    title: str = "New reasoning model released",
) -> Article:
    return Article(
        id=article_id,
        source_id=source_id,
        source_name=source_id,
        source_group=group,
        independence_group=independence_group,
        title=title,
        url=f"https://{source_id}.example/{article_id}",
        canonical_url=f"https://{source_id}.example/{article_id}",
        normalized_title=title.casefold(),
        fingerprint=(article_id * 64)[:64],
        published_at=NOW - timedelta(hours=1),
        fetched_at=NOW,
        excerpt="An open-source reasoning model was released.",
        categories=["models", "open-source"],
    )


def test_dedup_and_score_prioritize_verified_relevant_sources() -> None:
    official = article("a", "official", SourceGroup.OFFICIAL, "official")
    duplicate = article(
        "b",
        "media",
        SourceGroup.MEDIA,
        "wire-a",
        "New reasoning model is released",
    )
    unique = deduplicate_articles([official, duplicate], set())
    ranked = score_articles(
        unique,
        InterestsConfig(
            topics=["models", "open-source"],
            entities=[],
            include_terms=["reasoning", "model"],
            exclude_terms=["sponsored"],
        ),
        {"official": 25, "media": 10},
        NOW,
    )

    assert ranked[0].source_id == "official"
    assert 0 <= ranked[0].rule_score <= 100


def test_confirmation_requires_primary_or_two_independent_media_origins() -> None:
    official = article("a", "official", SourceGroup.OFFICIAL, "official")
    first = article("b", "media-a", SourceGroup.MEDIA, "wire-a")
    syndication = article("c", "media-b", SourceGroup.MEDIA, "wire-a")
    independent = article("d", "media-c", SourceGroup.MEDIA, "wire-b")
    community = article("e", "hn", SourceGroup.COMMUNITY, "hn")

    assert confirmation_status([official]) == ConfirmationStatus.PRIMARY_CONFIRMED
    assert confirmation_status([first, syndication]) == ConfirmationStatus.UNVERIFIED
    assert (
        confirmation_status([first, independent])
        == ConfirmationStatus.CROSS_CONFIRMED
    )
    assert confirmation_status([community]) == ConfirmationStatus.UNVERIFIED


def test_editorial_output_cannot_reference_unknown_candidate() -> None:
    known = article("a", "official", SourceGroup.OFFICIAL, "official")
    event = NewsEvent(
        id="event-1",
        candidate_ids=["missing"],
        category="models",
        title_zh="模型发布",
        summary_zh="摘要",
        why_it_matters_zh="重要性",
        importance_score=90,
        confirmation_status=ConfirmationStatus.PRIMARY_CONFIRMED,
        primary_source=SourceRef(
            source_id=known.source_id,
            source_name=known.source_name,
            title=known.title,
            url=known.url,
            published_at=known.published_at,
        ),
    )

    with pytest.raises(ValueError, match="unknown candidate ids"):
        validate_event_sources(event, [known])


def test_editorial_output_rejects_unverified_or_community_primary() -> None:
    official = article("a", "official", SourceGroup.OFFICIAL, "official")
    community = article("b", "hn", SourceGroup.COMMUNITY, "hn")
    media = article("c", "media", SourceGroup.MEDIA, "wire-a")

    unverified = NewsEvent(
        id="event-unverified",
        candidate_ids=[media.id],
        category="business",
        title_zh="未经确认",
        summary_zh="摘要",
        why_it_matters_zh="重要性",
        importance_score=80,
        confirmation_status=ConfirmationStatus.UNVERIFIED,
        primary_source=SourceRef(
            source_id=media.source_id,
            source_name=media.source_name,
            title=media.title,
            url=media.url,
            published_at=media.published_at,
        ),
    )
    with pytest.raises(ValueError, match="unverified"):
        validate_event_sources(unverified, [media])

    community_primary = NewsEvent(
        id="event-community-primary",
        candidate_ids=[official.id, community.id],
        category="models",
        title_zh="已有官方确认",
        summary_zh="摘要",
        why_it_matters_zh="重要性",
        importance_score=90,
        confirmation_status=ConfirmationStatus.PRIMARY_CONFIRMED,
        primary_source=SourceRef(
            source_id=community.source_id,
            source_name=community.source_name,
            title=community.title,
            url=community.url,
            published_at=community.published_at,
        ),
    )
    with pytest.raises(ValueError, match="community source"):
        validate_event_sources(community_primary, [official, community])
```

- [ ] **Step 2: Run tests and prove ranking modules are missing**

Run:

```bash
pytest tests/test_source_verification.py -v
```

Expected: collection fails because `dedup`, `scoring`, and `source_verification` do not exist.

- [ ] **Step 3: Implement deterministic deduplication**

Create `src/ai_news_sniffer/dedup.py`:

```python
from rapidfuzz.fuzz import token_set_ratio

from ai_news_sniffer.models import Article


def deduplicate_articles(
    articles: list[Article],
    seen_fingerprints: set[str],
    title_threshold: float = 92,
) -> list[Article]:
    kept: list[Article] = []
    seen_urls: set[str] = set()
    for candidate in sorted(
        articles,
        key=lambda item: item.published_at,
        reverse=True,
    ):
        if candidate.fingerprint in seen_fingerprints:
            continue
        if str(candidate.canonical_url) in seen_urls:
            continue
        if any(
            token_set_ratio(
                candidate.normalized_title,
                item.normalized_title,
            )
            >= title_threshold
            for item in kept
        ):
            continue
        kept.append(candidate)
        seen_urls.add(str(candidate.canonical_url))
    return kept
```

- [ ] **Step 4: Implement the 100-point rule scorer**

Create `src/ai_news_sniffer/scoring.py`:

```python
from datetime import datetime

from rapidfuzz.fuzz import token_set_ratio

from ai_news_sniffer.models import Article, InterestsConfig

IMPACT_TERMS = {
    "release",
    "launch",
    "open-source",
    "breakthrough",
    "acquire",
    "funding",
    "regulation",
    "发布",
    "开源",
    "突破",
    "融资",
    "收购",
    "监管",
}
TECH_CATEGORIES = {
    "models",
    "products",
    "research",
    "open-source",
    "developer-tools",
}


def _contains(text: str, terms: list[str] | set[str]) -> int:
    folded = text.casefold()
    return sum(1 for term in terms if term.casefold() in folded)


def score_articles(
    articles: list[Article],
    interests: InterestsConfig,
    source_weights: dict[str, float],
    now: datetime,
) -> list[Article]:
    ranked: list[Article] = []
    for article in articles:
        text = f"{article.title} {article.excerpt}"
        if _contains(text, interests.exclude_terms):
            continue
        source_score = source_weights.get(article.source_id, 0)
        impact_score = min(25, _contains(text, IMPACT_TERMS) * 8)
        relevance_score = min(
            20,
            (
                _contains(text, interests.include_terms)
                + _contains(text, interests.entities)
                + _contains(" ".join(article.categories), interests.topics)
            )
            * 4,
        )
        technical_score = (
            15 if TECH_CATEGORIES.intersection(article.categories) else 8
        )
        corroboration_score = min(
            10,
            sum(
                5
                for other in articles
                if other.id != article.id
                and other.independence_group != article.independence_group
                and token_set_ratio(
                    article.normalized_title,
                    other.normalized_title,
                )
                >= 70
            ),
        )
        age_hours = max(
            0,
            (now - article.published_at).total_seconds() / 3600,
        )
        recency_score = max(0, 5 - age_hours / 10)
        article.rule_score = min(
            100,
            source_score
            + impact_score
            + relevance_score
            + technical_score
            + corroboration_score
            + recency_score,
        )
        ranked.append(article)
    return sorted(ranked, key=lambda item: item.rule_score, reverse=True)
```

- [ ] **Step 5: Implement fact confirmation and editorial-source validation**

Create `src/ai_news_sniffer/source_verification.py`:

```python
from ai_news_sniffer.models import (
    Article,
    ConfirmationStatus,
    NewsEvent,
    SourceGroup,
)

PRIMARY_GROUPS = {SourceGroup.OFFICIAL, SourceGroup.RESEARCH}


def confirmation_status(
    cluster: list[Article],
) -> ConfirmationStatus:
    if any(item.source_group in PRIMARY_GROUPS for item in cluster):
        return ConfirmationStatus.PRIMARY_CONFIRMED
    independent_media = {
        item.independence_group
        for item in cluster
        if item.source_group == SourceGroup.MEDIA
    }
    if len(independent_media) >= 2:
        return ConfirmationStatus.CROSS_CONFIRMED
    return ConfirmationStatus.UNVERIFIED


def validate_event_sources(
    event: NewsEvent,
    articles: list[Article],
) -> None:
    by_id = {item.id: item for item in articles}
    unknown = set(event.candidate_ids) - by_id.keys()
    if unknown:
        raise ValueError(f"unknown candidate ids: {sorted(unknown)}")
    source_ids = {by_id[item_id].source_id for item_id in event.candidate_ids}
    if event.primary_source.source_id not in source_ids:
        raise ValueError("primary source is not backed by a candidate")
    expected = confirmation_status([by_id[item_id] for item_id in event.candidate_ids])
    primary_candidate = next(
        item
        for item in by_id.values()
        if item.source_id == event.primary_source.source_id
        and item.id in event.candidate_ids
    )
    if primary_candidate.source_group == SourceGroup.COMMUNITY:
        raise ValueError("community source cannot be primary")
    if expected == ConfirmationStatus.UNVERIFIED:
        raise ValueError("unverified event cannot be published")
    if event.confirmation_status != expected:
        raise ValueError("confirmation status does not match candidate evidence")
```

- [ ] **Step 6: Run verification tests and commit**

Run:

```bash
pytest tests/test_source_verification.py -v
pytest -q
ruff check src tests
```

Expected: verification tests report `4 passed`; full suite and Ruff exit 0.

Commit:

```bash
git add src/ai_news_sniffer/dedup.py src/ai_news_sniffer/scoring.py src/ai_news_sniffer/source_verification.py tests/test_source_verification.py
git commit -m "feat: verify and rank source-backed candidates"
```

---

### Task 6: Source Health, Auto-Pause, and Candidate-Source Discovery

**Files:**
- Create: `src/ai_news_sniffer/source_health.py`
- Create: `src/ai_news_sniffer/source_discovery.py`
- Test: `tests/test_source_health_discovery.py`

**Interfaces:**
- Consumes: runtime root `Path`, source result data, normalized articles, and known source domains.
- Produces: `SourceHealthStore.load_all()`, `record_success()`, `record_failure()`, `clear_pause_after_audit()`, `auto_paused_ids()`.
- Produces: `discover_candidate_sources(...) -> list[CandidateSource]`.
- Persists only `runtime-data/source-health.json` and `runtime-data/candidate-sources.json`.

- [ ] **Step 1: Write failing health and discovery tests**

Create `tests/test_source_health_discovery.py`:

```python
from datetime import UTC, datetime
from pathlib import Path

from ai_news_sniffer.models import Article, SourceGroup
from ai_news_sniffer.source_discovery import discover_candidate_sources
from ai_news_sniffer.source_health import SourceHealthStore

NOW = datetime(2026, 7, 23, tzinfo=UTC)


def article_with_upstream(url: str) -> Article:
    return Article(
        id="a1",
        source_id="hacker-news",
        source_name="Hacker News",
        source_group=SourceGroup.COMMUNITY,
        independence_group="hacker-news",
        title="A discovered official source",
        url="https://news.ycombinator.com/item?id=1",
        canonical_url="https://news.ycombinator.com/item?id=1",
        normalized_title="a discovered official source",
        fingerprint="a" * 64,
        published_at=NOW,
        fetched_at=NOW,
        upstream_urls=[url],
    )


def test_health_degrades_at_three_and_auto_pauses_at_seven(tmp_path: Path) -> None:
    store = SourceHealthStore(tmp_path)

    for number in range(7):
        health = store.record_failure(
            "broken-source",
            f"failure {number}",
            NOW,
        )

    assert health.degraded is True
    assert health.auto_paused is True
    assert store.auto_paused_ids() == {"broken-source"}

    cleared = store.clear_pause_after_audit("broken-source", NOW)
    assert cleared.auto_paused is False
    assert cleared.consecutive_failures == 0


def test_discovery_records_unknown_domain_without_enabling_it(tmp_path: Path) -> None:
    candidates = discover_candidate_sources(
        [article_with_upstream("https://new-lab.example/releases/model")],
        known_domains={"news.ycombinator.com"},
        output_path=tmp_path / "candidate-sources.json",
        now=NOW,
    )

    assert candidates[0].domain == "new-lab.example"
    assert candidates[0].enabled is False
    assert candidates[0].referring_source_ids == {"hacker-news"}
    assert (tmp_path / "candidate-sources.json").exists()
```

- [ ] **Step 2: Run tests and prove state modules are missing**

Run:

```bash
pytest tests/test_source_health_discovery.py -v
```

Expected: collection fails because `source_health` and `source_discovery` do not exist.

- [ ] **Step 3: Implement source health persistence**

Create `src/ai_news_sniffer/source_health.py`:

```python
import json
from datetime import datetime
from pathlib import Path

from ai_news_sniffer.models import SourceHealth


class SourceHealthStore:
    def __init__(self, runtime_root: Path) -> None:
        self.path = runtime_root / "source-health.json"

    def load_all(self) -> dict[str, SourceHealth]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            source_id: SourceHealth.model_validate(value)
            for source_id, value in payload.items()
        }

    def _save(self, health: dict[str, SourceHealth]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            source_id: value.model_dump(mode="json")
            for source_id, value in sorted(health.items())
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def record_success(
        self,
        source_id: str,
        at: datetime,
    ) -> SourceHealth:
        values = self.load_all()
        previous = values.get(source_id, SourceHealth(source_id=source_id))
        current = previous.model_copy(
            update={
                "consecutive_failures": 0,
                "degraded": False,
                "last_success_at": at,
                "last_attempt_at": at,
                "last_error": None,
            }
        )
        values[source_id] = current
        self._save(values)
        return current

    def record_failure(
        self,
        source_id: str,
        error: str,
        at: datetime,
    ) -> SourceHealth:
        values = self.load_all()
        previous = values.get(source_id, SourceHealth(source_id=source_id))
        failures = previous.consecutive_failures + 1
        current = previous.model_copy(
            update={
                "consecutive_failures": failures,
                "degraded": failures >= 3,
                "auto_paused": failures >= 7,
                "last_attempt_at": at,
                "last_error": error[:300],
            }
        )
        values[source_id] = current
        self._save(values)
        return current

    def clear_pause_after_audit(
        self,
        source_id: str,
        at: datetime,
    ) -> SourceHealth:
        values = self.load_all()
        current = SourceHealth(
            source_id=source_id,
            consecutive_failures=0,
            degraded=False,
            auto_paused=False,
            last_success_at=at,
            last_attempt_at=at,
        )
        values[source_id] = current
        self._save(values)
        return current

    def auto_paused_ids(self) -> set[str]:
        return {
            source_id
            for source_id, health in self.load_all().items()
            if health.auto_paused
        }
```

- [ ] **Step 4: Implement candidate-source discovery**

Create `src/ai_news_sniffer/source_discovery.py`:

```python
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from ai_news_sniffer.models import (
    Article,
    CandidateSource,
    SourceGroup,
    SourceKind,
)


def discover_candidate_sources(
    articles: list[Article],
    known_domains: set[str],
    output_path: Path,
    now: datetime,
) -> list[CandidateSource]:
    existing: dict[str, CandidateSource] = {}
    if output_path.exists():
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        existing = {
            item["domain"]: CandidateSource.model_validate(item)
            for item in payload
        }

    for article in articles:
        for upstream in article.upstream_urls:
            domain = (urlsplit(str(upstream)).hostname or "").casefold()
            if not domain or domain in known_domains:
                continue
            previous = existing.get(domain)
            referring = (
                previous.referring_source_ids.copy() if previous else set()
            )
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
    output_path.write_text(
        json.dumps(
            [item.model_dump(mode="json") for item in ordered],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ordered
```

- [ ] **Step 5: Run health/discovery tests and commit**

Run:

```bash
pytest tests/test_source_health_discovery.py -v
pytest -q
ruff check src tests
```

Expected: focused tests report `2 passed`; full suite and Ruff exit 0.

Commit:

```bash
git add src/ai_news_sniffer/source_health.py src/ai_news_sniffer/source_discovery.py tests/test_source_health_discovery.py
git commit -m "feat: track source health and discovery candidates"
```

---

### Task 7: Collection Service, Source CLI, Manual Audit Workflow, and Operations

**Files:**
- Create: `src/ai_news_sniffer/source_service.py`
- Create: `src/ai_news_sniffer/source_cli.py`
- Create: `src/ai_news_sniffer/cli.py`
- Create: `tests/test_source_service.py`
- Create: `tests/test_source_cli.py`
- Create: `tests/test_source_workflow.py`
- Create: `.github/workflows/source-audit.yml`
- Create: `README.md`

**Interfaces:**
- Consumes: `Settings`, runtime root, date window, profile/include/exclude/budget overrides, HTTP client, optional adapter factory.
- Produces: `collect_source_candidates(...) -> SourceCollection`.
- Produces CLI commands: `sources list`, `sources test SOURCE_ID`, `sources audit`, `sources candidates`.
- Produces a manually dispatched source-audit workflow; it does not publish a report or send notifications.

- [ ] **Step 1: Write failing isolated-service tests**

Create `tests/test_source_service.py`:

```python
from datetime import UTC, datetime
from pathlib import Path

import httpx

from ai_news_sniffer.config import load_settings
from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.source_health import SourceHealthStore
from ai_news_sniffer.source_service import collect_source_candidates

ROOT = Path(__file__).parents[1]
SINCE = datetime(2026, 7, 22, tzinfo=UTC)
UNTIL = datetime(2026, 7, 24, tzinfo=UTC)


class FakeAdapter:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def fetch(
        self,
        source: SourceConfig,
        since: datetime,
        until: datetime,
    ) -> list[RawArticle]:
        if self.should_fail:
            raise RuntimeError("fixture failure")
        return [
            RawArticle(
                source_id=source.id,
                source_name=source.name,
                source_group=source.group,
                independence_group=source.id,
                title=f"{source.name} model release",
                url=f"https://example.com/{source.id}",
                published_at=UNTIL,
                fetched_at=UNTIL,
                excerpt="A reasoning model release.",
                categories=["models"],
            )
        ]


def test_collection_isolates_failure_and_applies_budget(tmp_path: Path) -> None:
    settings = load_settings(ROOT / "config")
    health_store = SourceHealthStore(tmp_path)
    for number in range(6):
        health_store.record_failure(
            "anthropic-news",
            f"prior failure {number}",
            UNTIL,
        )

    def factory(source: SourceConfig, client: httpx.Client) -> FakeAdapter:
        return FakeAdapter(should_fail=source.id == "anthropic-news")

    result = collect_source_candidates(
        settings=settings,
        runtime_root=tmp_path,
        since=SINCE,
        until=UNTIL,
        profile="light",
        client=httpx.Client(),
        adapter_factory=factory,
    )

    assert len(result.enabled_source_ids) == 12
    assert "anthropic-news" in result.failures
    assert result.fetched_count == 11
    assert len(result.budgeted.articles) <= 20
    assert result.budgeted.prompt_chars <= 60000
    assert result.newly_auto_paused_source_ids == ["anthropic-news"]
    assert (tmp_path / "source-runs" / "2026-07-24.json").exists()
```

- [ ] **Step 2: Write failing CLI and workflow-contract tests**

Create `tests/test_source_cli.py`:

```python
from pathlib import Path

from ai_news_sniffer.cli import main

ROOT = Path(__file__).parents[1]


def test_sources_list_prints_resolved_json(capsys) -> None:
    exit_code = main(
        [
            "--config-dir",
            str(ROOT / "config"),
            "sources",
            "list",
            "--profile",
            "light",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"count": 12' in output
    assert '"openai-news"' in output
```

Create `tests/test_source_workflow.py`:

```python
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_source_audit_workflow_exposes_safe_manual_inputs() -> None:
    text = (ROOT / ".github/workflows/source-audit.yml").read_text(
        encoding="utf-8"
    )
    workflow = yaml.safe_load(text)
    trigger = workflow.get("on") or workflow.get(True)
    inputs = trigger["workflow_dispatch"]["inputs"]

    assert set(inputs) == {
        "source_profile",
        "include_sources",
        "exclude_sources",
        "max_ai_candidates",
    }
    assert inputs["source_profile"]["default"] == "balanced"
    assert inputs["max_ai_candidates"]["default"] == "0"
    assert "schedule" not in trigger
```

- [ ] **Step 3: Run tests and prove orchestration is missing**

Run:

```bash
pytest tests/test_source_service.py tests/test_source_cli.py tests/test_source_workflow.py -v
```

Expected: collection fails because `source_service`, `cli`, and the workflow do not exist.

- [ ] **Step 4: Implement isolated source collection**

Create `src/ai_news_sniffer/source_service.py`:

```python
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from ai_news_sniffer.dedup import deduplicate_articles
from ai_news_sniffer.models import (
    Settings,
    SourceCollection,
    SourceConfig,
)
from ai_news_sniffer.normalization import normalize_article
from ai_news_sniffer.scoring import score_articles
from ai_news_sniffer.source_budget import apply_source_budget
from ai_news_sniffer.source_discovery import discover_candidate_sources
from ai_news_sniffer.source_health import SourceHealthStore
from ai_news_sniffer.source_registry import resolve_sources
from ai_news_sniffer.sources.base import SourceAdapter, build_source_adapter

AdapterFactory = Callable[[SourceConfig, httpx.Client], SourceAdapter]


def collect_source_candidates(
    settings: Settings,
    runtime_root: Path,
    since: datetime,
    until: datetime,
    profile: str | None = None,
    include_sources: set[str] | None = None,
    exclude_sources: set[str] | None = None,
    max_ai_candidates: int | None = None,
    seen_fingerprints: set[str] | None = None,
    client: httpx.Client | None = None,
    adapter_factory: AdapterFactory = build_source_adapter,
    live_audit: bool = False,
) -> SourceCollection:
    health_store = SourceHealthStore(runtime_root)
    auto_paused_before = health_store.auto_paused_ids()
    selected = resolve_sources(
        settings.sources,
        profile_override=profile,
        include_sources=include_sources,
        exclude_sources=exclude_sources,
        auto_paused=set() if live_audit else health_store.auto_paused_ids(),
    )
    owned_client = client is None
    http_client = client or httpx.Client(follow_redirects=True)
    raw_articles = []
    failures: dict[str, str] = {}
    newly_auto_paused_source_ids: list[str] = []
    try:
        for source in selected:
            try:
                fetched = adapter_factory(source, http_client).fetch(
                    source,
                    since,
                    until,
                )
                raw_articles.extend(fetched)
                if live_audit:
                    health_store.clear_pause_after_audit(source.id, until)
                else:
                    health_store.record_success(source.id, until)
            except Exception as exc:
                message = f"{type(exc).__name__}: {str(exc)[:200]}"
                failures[source.id] = message
                health = health_store.record_failure(source.id, message, until)
                if health.auto_paused and source.id not in auto_paused_before:
                    newly_auto_paused_source_ids.append(source.id)
    finally:
        if owned_client:
            http_client.close()

    normalized = [normalize_article(item) for item in raw_articles]
    deduplicated = deduplicate_articles(
        normalized,
        seen_fingerprints or set(),
    )
    source_weights = {item.id: item.weight for item in selected}
    scored = score_articles(
        deduplicated,
        settings.interests,
        source_weights,
        until,
    )
    resolved_profile = profile or settings.sources.active_profile
    candidate_limit = (
        max_ai_candidates
        if max_ai_candidates is not None
        else settings.sources.profile_candidate_limits[resolved_profile]
    )
    budgeted = apply_source_budget(
        scored,
        settings.app.editorial,
        max_candidates_override=candidate_limit,
    )
    known_domains = {
        (urlsplit(str(item.url)).hostname or "").casefold()
        for item in settings.sources.sources
    }
    discover_candidate_sources(
        normalized,
        known_domains,
        runtime_root / "candidate-sources.json",
        until,
    )
    result = SourceCollection(
        enabled_source_ids=[item.id for item in selected],
        fetched_count=len(raw_articles),
        normalized_count=len(normalized),
        filtered_count=len(scored),
        budgeted=budgeted,
        failures=failures,
        newly_auto_paused_source_ids=sorted(newly_auto_paused_source_ids),
    )
    run_path = runtime_root / "source-runs" / f"{until.date().isoformat()}.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return result
```

- [ ] **Step 5: Implement reusable source commands and the initial CLI**

Create `src/ai_news_sniffer/source_cli.py`:

```python
import argparse
import json
from datetime import UTC, datetime, timedelta

from ai_news_sniffer.config import load_settings
from ai_news_sniffer.source_health import SourceHealthStore
from ai_news_sniffer.source_registry import resolve_sources
from ai_news_sniffer.source_service import collect_source_candidates


def _ids(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def add_source_commands(
    commands: argparse._SubParsersAction,
) -> None:
    sources = commands.add_parser("sources")
    actions = sources.add_subparsers(dest="source_command", required=True)

    listing = actions.add_parser("list")
    listing.add_argument("--profile", choices=["light", "balanced", "full"])

    testing = actions.add_parser("test")
    testing.add_argument("source_id")

    audit = actions.add_parser("audit")
    audit.add_argument(
        "--profile",
        choices=["light", "balanced", "full"],
        default="balanced",
    )
    audit.add_argument("--include-sources", default="")
    audit.add_argument("--exclude-sources", default="")
    audit.add_argument("--max-ai-candidates", type=int)

    actions.add_parser("candidates")


def run_source_command(args: argparse.Namespace) -> int:
    settings = load_settings(args.config_dir)

    if args.source_command == "list":
        sources = resolve_sources(
            settings.sources,
            profile_override=args.profile,
            auto_paused=SourceHealthStore(args.runtime_dir).auto_paused_ids(),
        )
        print(
            json.dumps(
                {"count": len(sources), "source_ids": [item.id for item in sources]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.source_command == "candidates":
        path = args.runtime_dir / "candidate-sources.json"
        print(path.read_text(encoding="utf-8") if path.exists() else "[]")
        return 0

    now = datetime.now(UTC)
    if args.source_command == "test":
        result = collect_source_candidates(
            settings=settings,
            runtime_root=args.runtime_dir,
            since=now - timedelta(hours=settings.app.lookback_hours),
            until=now,
            profile="full",
            include_sources={args.source_id},
            live_audit=True,
        )
    else:
        result = collect_source_candidates(
            settings=settings,
            runtime_root=args.runtime_dir,
            since=now - timedelta(hours=settings.app.lookback_hours),
            until=now,
            profile=args.profile,
            include_sources=_ids(args.include_sources),
            exclude_sources=_ids(args.exclude_sources),
            max_ai_candidates=args.max_ai_candidates or None,
            live_audit=True,
        )
    print(result.model_dump_json(indent=2))
    return 1 if result.failures else 0
```

Create `src/ai_news_sniffer/cli.py`:

```python
import argparse
from pathlib import Path

from ai_news_sniffer.source_cli import add_source_commands, run_source_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-news-sniffer")
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--runtime-dir", type=Path, default=Path("runtime-data"))
    commands = parser.add_subparsers(dest="command", required=True)
    add_source_commands(commands)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "sources":
        return run_source_command(args)
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Add the manual source-audit workflow**

Create `.github/workflows/source-audit.yml`:

```yaml
name: Source audit

on:
  workflow_dispatch:
    inputs:
      source_profile:
        description: Source profile
        required: true
        default: balanced
        type: choice
        options: [light, balanced, full]
      include_sources:
        description: Optional comma-separated allowlist
        required: false
        default: ""
        type: string
      exclude_sources:
        description: Optional comma-separated blocklist
        required: false
        default: ""
        type: string
      max_ai_candidates:
        description: Candidate cap; 0 uses the selected profile default
        required: false
        default: "0"
        type: string

permissions:
  contents: read

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
          cache: pip
      - name: Install
        run: python -m pip install -e .
      - name: Audit enabled sources
        run: >
          ai-news-sniffer
          --config-dir config
          --runtime-dir runtime-data
          sources audit
          --profile "${{ inputs.source_profile }}"
          --include-sources "${{ inputs.include_sources }}"
          --exclude-sources "${{ inputs.exclude_sources }}"
          --max-ai-candidates "${{ inputs.max_ai_candidates }}"
      - uses: actions/upload-artifact@v7
        if: always()
        with:
          name: source-audit
          path: runtime-data/
          if-no-files-found: warn
```

- [ ] **Step 7: Add exact operator documentation**

Create `README.md`:

```markdown
# AI News Sniffer

The source subsystem collects a curated, configurable set of public AI-news
sources. It does not ask a model to discover or enable production sources.

## Source modes

- `light`: 12 core official/research sources, at most 20 AI candidates.
- `balanced`: 25 sources, at most 30 candidates; this is the default.
- `full`: all 35 sources, at most 40 AI candidates by default.

Set the default with `active_profile` in `config/sources.yaml`. A source with
`enabled: false` or a disabled source group remains off in every mode.

## Local inspection

```bash
python -m pip install -e ".[dev]"
ai-news-sniffer sources list --profile light
ai-news-sniffer sources candidates
```

## Intentional live checks

The regular test suite does not access live websites. Use one of these commands
when you intentionally want network access:

```bash
ai-news-sniffer sources test openai-news
ai-news-sniffer sources audit --profile balanced
```

A successful live audit clears a runtime auto-pause; it never changes
`config/sources.yaml` or commits to `main`.

## One-run overrides

```bash
ai-news-sniffer sources audit \
  --profile full \
  --include-sources openai-news,anthropic-news \
  --exclude-sources anthropic-news \
  --max-ai-candidates 10
```

`include_sources` only narrows sources that are already enabled and belong to
the selected profile. `exclude_sources` is applied last.

The manual workflow uses `0` for `max_ai_candidates` to select the profile
default: 20 for `light`, 30 for `balanced`, and 40 for `full`.

## Cost controls

RSS/API/HTML collection itself consumes no model tokens. Before a later
editorial call, `config/app.yaml` limits candidate count, excerpt characters per
item, and total prompt characters. The recorded token value is an estimate;
character limits are the hard enforcement mechanism.

## Candidate sources

Unknown upstream domains are written to
`runtime-data/candidate-sources.json` with `enabled: false`. Approve one only by
reviewing its ownership and access policy, adding a complete entry to
`config/sources.yaml`, and committing that change.
```

- [ ] **Step 8: Run the complete source-subsystem verification**

Run:

```bash
pytest -v
ruff check src tests
python -m ai_news_sniffer.cli --config-dir config sources list --profile light
python -m ai_news_sniffer.cli --config-dir config sources list --profile balanced
python -m ai_news_sniffer.cli --config-dir config sources list --profile full
```

Expected:

- All tests pass.
- Ruff exits 0.
- The three CLI results report counts `12`, `25`, and `35`.
- No command performs a live network request.

- [ ] **Step 9: Commit**

```bash
git add src/ai_news_sniffer/source_service.py src/ai_news_sniffer/source_cli.py src/ai_news_sniffer/cli.py tests/test_source_service.py tests/test_source_cli.py tests/test_source_workflow.py .github/workflows/source-audit.yml README.md
git commit -m "feat: orchestrate and audit configured news sources"
```

---

## Integration With the Main Implementation Plan

After all seven tasks pass:

1. Do not execute Tasks 1–3 in `docs/superpowers/plans/2026-07-23-ai-news-sniffer.md`; this plan provides their compatible models, configuration, adapters, normalization, deduplication, and scoring.
2. Continue the main plan at Task 4, preserving the public interfaces defined here.
3. In main-plan Task 5, validate every AI-produced event with `validate_event_sources`.
4. In main-plan Task 6, reject `ConfirmationStatus.UNVERIFIED` and prevent community sources from becoming primary.
5. In main-plan Task 7, render `source_coverage`, degraded source IDs, candidate counts, and estimated input tokens.
6. In main-plan Task 9, extend the existing `cli.py`; do not replace the `sources` command tree.
7. In main-plan Task 10, copy the four manual source inputs from `source-audit.yml` into the daily workflow, persist `source-health.json`, `candidate-sources.json`, and `source-runs/<date>.json` on `runtime-data`, and surface `newly_auto_paused_source_ids` in the next successful notification.

## Implementation Completion Gate

Run:

```bash
pytest -v
ruff check src tests
git diff --check
git status --short
```

Completion requires:

- All source-subsystem tests pass with no live-network dependency.
- Ruff and whitespace checks exit 0.
- The registry contains exactly 35 unique IDs.
- Profiles resolve to 12/25/35 before runtime exclusions.
- Model input is bounded by all three configured limits.
- Unknown AI source IDs and unverified/community-only events are rejected.
- Health state degrades at 3 failures and auto-pauses at 7.
- Candidate discovery never edits `config/sources.yaml`.
- The manual workflow has no schedule and sends no notifications.

## Primary References

- Source strategy specification: `docs/superpowers/specs/2026-07-23-ai-news-source-strategy-design.md`
- Main V2 specification: `docs/superpowers/specs/2026-07-23-ai-news-sniffer-design.md`
- [selectolax 0.4.11](https://pypi.org/project/selectolax/)
- [HTTPX 0.28.1](https://pypi.org/project/httpx/)
- [feedparser 6.0.12](https://pypi.org/project/feedparser/)
- [arXiv API](https://info.arxiv.org/help/api/)
- [Hacker News API](https://github.com/HackerNews/API)
- [GitHub REST releases](https://docs.github.com/en/rest/releases/releases)

## Specification Coverage Matrix

| Specification requirement | Plan task |
|---|---|
| 35 configured sources and exact profiles | Task 1 |
| Per-source, group, profile, include/exclude controls | Task 2 |
| Candidate count and prompt-character budgets | Task 2 |
| RSS, arXiv, GitHub Releases, and Hacker News | Task 3 |
| HTML whitelist with no browser bypass | Task 4 |
| Deterministic deduplication and 100-point scoring | Task 5 |
| Primary/cross/unverified confirmation | Task 5 |
| Unknown AI source rejection | Task 5 |
| Health degradation and auto-pause | Task 6 |
| Candidate-domain discovery without auto-enable | Task 6 |
| Failure isolation and source coverage result | Task 7 |
| Source list/test/audit/candidates CLI | Task 7 |
| Manual workflow controls and operator documentation | Task 7 |
