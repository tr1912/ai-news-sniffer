# AI News Sniffer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an unattended daily AI-news pipeline that selects 8–15 high-value global stories, publishes a Chinese mobile-first HTML digest to GitHub Pages, and sends pluggable notifications at about 21:00 Asia/Shanghai.

**Architecture:** A deterministic Python pipeline owns collection, normalization, deduplication, scoring, persistence, rendering, and delivery. An OpenAI-compatible provider chain performs only semantic event clustering, editorial ranking, and Chinese summarization. GitHub Actions schedules and stages `prepared → published → notified` runs while a dedicated `runtime-data` branch preserves report JSON and fingerprints.

**Tech Stack:** Python 3.12, Pydantic 2, PyYAML, httpx, feedparser, RapidFuzz, Jinja2 sandbox, OpenAI Python SDK, pytest, respx, Ruff, GitHub Actions, GitHub Pages.

## Execution Prerequisite

Execute `docs/superpowers/plans/2026-07-23-ai-news-source-strategy.md` first. That focused plan implements the approved 35-source registry, source profiles and switches, AI input budget, RSS/API/GitHub/HTML adapters, fact confirmation, source health, discovery, and source CLI. It supersedes Tasks 1–3 below. After its completion gate passes, continue this plan at Task 4.

## Global Constraints

- Output 8–15 stories normally; publish fewer rather than padding with low-quality items.
- Collect global Chinese and English sources, but produce Chinese reports.
- Weight technical, model, open-source, and AI-product news slightly above business news while retaining truly important business and policy events.
- Use free public sources only in v1; paid search APIs remain outside implementation scope.
- Run at `0 13 * * *` UTC, accepting normal GitHub Actions scheduling delay.
- Support `dry_run`, `publish`, and `notify` manual controls plus an optional target date.
- Default to DeepSeek through an OpenAI-compatible interface; keep provider configuration portable to Kimi, MiniMax, and other compatible endpoints.
- Keep API keys, MeoW nickname, and webhook URLs in GitHub Secrets or environment variables, never committed YAML.
- Render public static pages with `noindex`; do not represent `noindex` as access control.
- Keep report content separate from `templates/<name>/`; switching templates must rebuild history without collecting or summarizing again.
- Persist runtime data only on `runtime-data`; daily automation must not commit to `main`.
- Isolate notification failures per channel and never send a success notification before the report URL is reachable.
- Preserve article copyright boundaries: store titles, excerpts, generated summaries, and source links, not copied full articles.
- Follow TDD: every task starts with a failing test, proves the failure, adds the smallest implementation, proves passing tests, then commits.

## File Structure

```text
.
├── .env.example                         # Non-secret environment variable names
├── .github/workflows/
│   ├── ci.yml                           # Lint and test on pushes/PRs
│   └── daily-digest.yml                 # Schedule, manual controls, Pages deploy, notify
├── config/
│   ├── app.yaml                         # Global report/render settings
│   ├── channels.yaml                    # Enabled channel types and env-var references
│   ├── interests.yaml                   # Topics, entities, include/exclude terms
│   ├── providers.yaml                   # Provider chain and model settings
│   └── sources.yaml                     # Source registry and source weights
├── prompts/
│   └── editorial.md                     # Versioned semantic-editor prompt
├── src/ai_news_sniffer/
│   ├── __init__.py                      # Package version
│   ├── __main__.py                      # `python -m ai_news_sniffer`
│   ├── cli.py                           # build/verify/mark-published/notify commands
│   ├── config.py                        # YAML loading and environment-secret resolution
│   ├── models.py                        # Shared Pydantic domain models
│   ├── normalization.py                 # URL/title/time normalization and fingerprints
│   ├── dedup.py                         # Exact and fuzzy deterministic deduplication
│   ├── scoring.py                       # Configurable 100-point deterministic scoring
│   ├── selection.py                     # Diversity caps and final count enforcement
│   ├── pipeline.py                      # Stage orchestration; no provider-specific logic
│   ├── state.py                         # JSON runtime store and stage transitions
│   ├── sources/
│   │   ├── base.py                      # SourceAdapter protocol and registry
│   │   ├── rss.py                       # RSS/Atom feeds, including arXiv queries
│   │   ├── github.py                    # GitHub Releases API adapter
│   │   └── hacker_news.py               # Official Hacker News API adapter
│   ├── providers/
│   │   ├── base.py                      # StructuredProvider protocol
│   │   ├── openai_compatible.py         # DeepSeek/Kimi/MiniMax-compatible client
│   │   └── editorial.py                 # Prompt construction and semantic validation
│   ├── rendering/
│   │   └── site.py                      # Sandboxed template loading and site generation
│   └── notifications/
│       ├── base.py                      # NotificationChannel protocol and fan-out
│       ├── meow.py                      # MeoW Push API adapter
│       ├── wecom.py                     # WeCom group-robot adapter
│       └── webhook.py                   # Generic JSON webhook adapter
├── templates/default/
│   ├── report.html.j2                   # Dated report page
│   ├── index.html.j2                    # Latest-report landing page
│   ├── archive.html.j2                  # Historical index
│   ├── notification.md.j2               # Short shared notification copy
│   └── static/style.css                 # Mobile-first styles
├── tests/
│   ├── fixtures/                        # Network/model fixtures and expected report JSON
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_dedup_scoring.py
│   ├── test_notifications.py
│   ├── test_pipeline.py
│   ├── test_providers.py
│   ├── test_rendering.py
│   ├── test_sources.py
│   └── test_state.py
├── pyproject.toml                       # Runtime/dev dependencies and tool config
└── README.md                            # Setup, secrets, manual run, DNS, operations
```

---

### Task 1: Core Domain Models and Configuration

> **Superseded — do not execute.** Execute Tasks 1–2 of `docs/superpowers/plans/2026-07-23-ai-news-source-strategy.md`; they provide compatible domain models and the approved 35-source configuration.

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
- Create: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: none.
- Produces: `load_settings(config_dir: Path) -> Settings`, `resolve_secret(env_name: str) -> str`, and shared models `RawArticle`, `Article`, `NewsEvent`, `DailyReport`, `RunRecord`, `NotificationPayload`, `ChannelResult`.

- [ ] **Step 1: Add the package metadata and dependency manifest**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[project]
name = "ai-news-sniffer"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "feedparser>=6.0.11,<7",
  "httpx>=0.28,<1",
  "jinja2>=3.1.6,<4",
  "openai>=2.47,<3",
  "pydantic>=2.13,<3",
  "pyyaml>=6.0.2,<7",
  "rapidfuzz>=3.13,<4",
]

[project.optional-dependencies]
dev = [
  "pytest>=9.1,<10",
  "pytest-cov>=6.2,<7",
  "respx>=0.22,<1",
  "ruff>=0.12,<1",
]

[project.scripts]
ai-news-sniffer = "ai_news_sniffer.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/ai_news_sniffer"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

Create `src/ai_news_sniffer/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 2: Write the failing configuration tests**

Create `tests/test_config.py`:

```python
from pathlib import Path

import pytest

from ai_news_sniffer.config import load_settings, resolve_secret


def test_load_settings_reads_all_config_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "app.yaml").write_text(
        "timezone: Asia/Shanghai\nlookback_hours: 48\nmin_items: 8\n"
        "max_items: 15\ncandidate_limit: 40\ntemplate: default\n"
        "public_base_url: https://ai.example.com\n",
        encoding="utf-8",
    )
    (tmp_path / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (tmp_path / "interests.yaml").write_text(
        "topics: [models]\nentities: []\ninclude_terms: []\nexclude_terms: []\n",
        encoding="utf-8",
    )
    (tmp_path / "providers.yaml").write_text(
        "providers:\n"
        "  - id: deepseek\n"
        "    api_style: openai_chat_completions\n"
        "    base_url: https://api.deepseek.com\n"
        "    model: deepseek-v4-flash\n"
        "    api_key_env: DEEPSEEK_API_KEY\n"
        "    timeout_seconds: 60\n"
        "    max_retries: 3\n"
        "fallback_order: [deepseek]\n",
        encoding="utf-8",
    )
    (tmp_path / "channels.yaml").write_text("channels: []\n", encoding="utf-8")

    settings = load_settings(tmp_path)

    assert settings.app.timezone == "Asia/Shanghai"
    assert settings.app.max_items == 15
    assert settings.providers.fallback_order == ["deepseek"]
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://ai.example.com")
    assert str(load_settings(tmp_path).app.public_base_url).rstrip("/") == (
        "https://ai.example.com"
    )


def test_resolve_secret_rejects_missing_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        resolve_secret("DEEPSEEK_API_KEY")
```

- [ ] **Step 3: Run the tests to prove the configuration layer is missing**

Run:

```bash
python -m pip install -e '.[dev]'
pytest tests/test_config.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'ai_news_sniffer.config'`.

- [ ] **Step 4: Implement the shared models**

Create `src/ai_news_sniffer/models.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class RunStatus(StrEnum):
    PREPARED = "prepared"
    PUBLISHED = "published"
    NOTIFIED = "notified"
    PARTIALLY_NOTIFIED = "partially_notified"
    DEGRADED = "degraded"
    FAILED = "failed"


class SourceRef(BaseModel):
    source_id: str
    source_name: str
    title: str
    url: HttpUrl
    published_at: datetime


class RawArticle(BaseModel):
    source_id: str
    source_name: str
    title: str
    url: HttpUrl
    published_at: datetime
    fetched_at: datetime
    language: str = "und"
    excerpt: str = ""
    categories: list[str] = Field(default_factory=list)
    author: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class Article(RawArticle):
    id: str
    canonical_url: str
    normalized_title: str
    fingerprint: str
    rule_score: float = 0


class NewsEvent(BaseModel):
    id: str
    candidate_ids: list[str]
    category: str
    title_zh: str
    summary_zh: str
    why_it_matters_zh: str
    importance_score: float = Field(ge=0, le=100)
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


class AppConfig(BaseModel):
    timezone: str = "Asia/Shanghai"
    lookback_hours: int = Field(default=48, ge=1, le=168)
    min_items: int = Field(default=8, ge=1)
    max_items: int = Field(default=15, ge=1)
    candidate_limit: int = Field(default=40, ge=8)
    template: str = "default"
    public_base_url: HttpUrl


class SourceConfig(BaseModel):
    id: str
    name: str
    kind: Literal["rss", "github_releases", "hacker_news"]
    enabled: bool = True
    url: str | None = None
    categories: list[str] = Field(default_factory=list)
    weight: float = Field(default=15, ge=0, le=25)
    options: dict[str, Any] = Field(default_factory=dict)


class InterestsConfig(BaseModel):
    topics: list[str]
    entities: list[str]
    include_terms: list[str]
    exclude_terms: list[str]


class ProviderConfig(BaseModel):
    id: str
    api_style: Literal["openai_chat_completions"]
    base_url: HttpUrl
    model: str
    api_key_env: str
    timeout_seconds: float = Field(default=60, gt=0)
    max_retries: int = Field(default=3, ge=1, le=5)


class ProvidersConfig(BaseModel):
    providers: list[ProviderConfig]
    fallback_order: list[str]


class ChannelConfig(BaseModel):
    id: str
    kind: Literal["meow", "wecom", "webhook"]
    enabled: bool = False
    endpoint_env: str | None = None
    nickname_env: str | None = None
    timeout_seconds: float = Field(default=15, gt=0)
    max_retries: int = Field(default=3, ge=1, le=5)


class ChannelsConfig(BaseModel):
    channels: list[ChannelConfig]


class SourcesConfig(BaseModel):
    sources: list[SourceConfig]


class Settings(BaseModel):
    app: AppConfig
    sources: SourcesConfig
    interests: InterestsConfig
    providers: ProvidersConfig
    channels: ChannelsConfig
```

- [ ] **Step 5: Implement YAML loading and secret resolution**

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

T = TypeVar("T", bound=BaseModel)


def _load_yaml(path: Path, model: type[T]) -> T:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return model.model_validate(data)


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

Create configuration files with these exact starting values:

```yaml
# config/app.yaml
timezone: Asia/Shanghai
lookback_hours: 48
min_items: 8
max_items: 15
candidate_limit: 40
template: default
public_base_url: https://example.github.io/ai-news-sniffer
```

```yaml
# config/sources.yaml
sources:
  - id: hugging-face-blog
    name: Hugging Face Blog
    kind: rss
    enabled: true
    url: https://huggingface.co/blog/feed.xml
    categories: [models, products, open-source]
    weight: 20
  - id: arxiv-ai
    name: arXiv AI
    kind: rss
    enabled: true
    url: https://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.LG&sortBy=submittedDate&sortOrder=descending&max_results=30
    categories: [research]
    weight: 18
  - id: tracked-releases
    name: Tracked GitHub Releases
    kind: github_releases
    enabled: true
    categories: [open-source, developer-tools]
    weight: 20
    options:
      repositories: [vllm-project/vllm, huggingface/transformers]
  - id: hacker-news
    name: Hacker News
    kind: hacker_news
    enabled: true
    categories: [products, developer-tools]
    weight: 12
    options:
      item_limit: 100
```

```yaml
# config/interests.yaml
topics: [models, products, research, open-source, developer-tools, business, policy]
entities: [OpenAI, Anthropic, Google DeepMind, Meta AI, DeepSeek, Kimi, MiniMax]
include_terms: [AI, LLM, agent, multimodal, inference, reasoning, open-source]
exclude_terms: [sponsored, giveaway]
```

```yaml
# config/providers.yaml
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

```yaml
# config/channels.yaml
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

Create `.env.example`:

```dotenv
DEEPSEEK_API_KEY=
MEOW_NICKNAME=
WECOM_WEBHOOK_URL=
GENERIC_WEBHOOK_URL=
```

- [ ] **Step 6: Run the configuration tests and static checks**

Run:

```bash
pytest tests/test_config.py -v
ruff check src tests
```

Expected: both commands exit 0; pytest reports `2 passed`.

- [ ] **Step 7: Commit the core contract**

```bash
git add pyproject.toml src/ai_news_sniffer config .env.example tests/test_config.py
git commit -m "feat: add core models and configuration"
```

---

### Task 2: Source Adapters and Normalization

> **Superseded — do not execute.** Execute Tasks 3–4 of `docs/superpowers/plans/2026-07-23-ai-news-source-strategy.md`; they add RSS, arXiv, GitHub Releases, Hacker News, and HTML-whitelist adapters plus normalization.

**Files:**
- Create: `src/ai_news_sniffer/sources/__init__.py`
- Create: `src/ai_news_sniffer/sources/base.py`
- Create: `src/ai_news_sniffer/sources/rss.py`
- Create: `src/ai_news_sniffer/sources/github.py`
- Create: `src/ai_news_sniffer/sources/hacker_news.py`
- Create: `src/ai_news_sniffer/normalization.py`
- Create: `tests/fixtures/rss.xml`
- Create: `tests/fixtures/github_releases.json`
- Create: `tests/fixtures/hn_topstories.json`
- Create: `tests/fixtures/hn_item.json`
- Test: `tests/test_sources.py`

**Interfaces:**
- Consumes: `RawArticle`, `Article`, `SourceConfig`.
- Produces: `SourceAdapter.fetch(source: SourceConfig, since: datetime, until: datetime) -> list[RawArticle]`, `build_source_adapter(source: SourceConfig, client: httpx.Client) -> SourceAdapter`, `normalize_article(raw: RawArticle) -> Article`.

- [ ] **Step 1: Write failing adapter and normalization tests**

Create `tests/test_sources.py`:

```python
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from ai_news_sniffer.models import RawArticle, SourceConfig
from ai_news_sniffer.normalization import normalize_article
from ai_news_sniffer.sources.base import build_source_adapter

FIXTURES = Path(__file__).parent / "fixtures"
SINCE = datetime(2026, 7, 22, tzinfo=UTC)
UNTIL = datetime(2026, 7, 24, tzinfo=UTC)


def test_rss_adapter_returns_articles() -> None:
    source = SourceConfig(
        id="example",
        name="Example",
        kind="rss",
        url="https://example.com/feed.xml",
        categories=["models"],
        weight=20,
    )
    with respx.mock:
        respx.get(source.url).mock(
            return_value=httpx.Response(
                200,
                text=(FIXTURES / "rss.xml").read_text(encoding="utf-8"),
            )
        )
        articles = build_source_adapter(source, httpx.Client()).fetch(source, SINCE, UNTIL)

    assert [article.title for article in articles] == ["New model released"]
    assert articles[0].categories == ["models"]


def test_normalize_article_removes_tracking_parameters() -> None:
    raw = RawArticle(
        source_id="example",
        source_name="Example",
        title="  New MODEL Released | Example  ",
        url="https://example.com/post?utm_source=rss&id=7",
        published_at=datetime(2026, 7, 23, tzinfo=UTC),
        fetched_at=datetime(2026, 7, 23, tzinfo=UTC),
    )

    article = normalize_article(raw)

    assert article.canonical_url == "https://example.com/post?id=7"
    assert article.normalized_title == "new model released example"
    assert len(article.fingerprint) == 64


def test_registry_builds_all_supported_adapter_types() -> None:
    client = httpx.Client()
    for kind in ("rss", "github_releases", "hacker_news"):
        source = SourceConfig(id=kind, name=kind, kind=kind, options={})
        assert build_source_adapter(source, client) is not None
```

Add a small RSS fixture:

```xml
<!-- tests/fixtures/rss.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example</title>
    <item>
      <title>New model released</title>
      <link>https://example.com/model</link>
      <description>A factual description.</description>
      <pubDate>Thu, 23 Jul 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
```

- [ ] **Step 2: Run the focused tests to prove adapters are missing**

Run:

```bash
pytest tests/test_sources.py -v
```

Expected: collection fails because `ai_news_sniffer.normalization` and `ai_news_sniffer.sources` do not exist.

- [ ] **Step 3: Define the adapter protocol and registry**

Create `src/ai_news_sniffer/sources/__init__.py` as an empty package marker.

Create `src/ai_news_sniffer/sources/base.py`:

```python
from datetime import datetime
from typing import Protocol

import httpx

from ai_news_sniffer.models import RawArticle, SourceConfig


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
    if source.kind == "rss":
        from ai_news_sniffer.sources.rss import RssAdapter

        return RssAdapter(client)
    if source.kind == "github_releases":
        from ai_news_sniffer.sources.github import GitHubReleasesAdapter

        return GitHubReleasesAdapter(client)
    if source.kind == "hacker_news":
        from ai_news_sniffer.sources.hacker_news import HackerNewsAdapter

        return HackerNewsAdapter(client)
    raise ValueError(f"Unsupported source kind: {source.kind}")
```

- [ ] **Step 4: Implement the RSS adapter**

Create `src/ai_news_sniffer/sources/rss.py`:

```python
from datetime import UTC, datetime
from time import struct_time

import feedparser
import httpx

from ai_news_sniffer.models import RawArticle, SourceConfig


def _as_datetime(value: struct_time | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return datetime(*value[:6], tzinfo=UTC)


class RssAdapter:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def fetch(
        self,
        source: SourceConfig,
        since: datetime,
        until: datetime,
    ) -> list[RawArticle]:
        if not source.url:
            raise ValueError(f"RSS source {source.id} requires url")
        response = self.client.get(source.url, timeout=30)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        fetched_at = datetime.now(UTC)
        articles: list[RawArticle] = []
        for entry in feed.entries:
            published_at = _as_datetime(
                entry.get("published_parsed") or entry.get("updated_parsed")
            )
            if not since <= published_at <= until:
                continue
            articles.append(
                RawArticle(
                    source_id=source.id,
                    source_name=source.name,
                    title=entry.get("title", "").strip(),
                    url=entry.get("link") or entry.get("id", ""),
                    published_at=published_at,
                    fetched_at=fetched_at,
                    excerpt=entry.get("summary", ""),
                    categories=source.categories,
                    author=entry.get("author"),
                )
            )
        return articles
```

- [ ] **Step 5: Implement GitHub Releases and Hacker News adapters**

Create `src/ai_news_sniffer/sources/github.py`:

```python
from datetime import UTC, datetime

import httpx

from ai_news_sniffer.models import RawArticle, SourceConfig


class GitHubReleasesAdapter:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def fetch(
        self,
        source: SourceConfig,
        since: datetime,
        until: datetime,
    ) -> list[RawArticle]:
        fetched_at = datetime.now(UTC)
        articles: list[RawArticle] = []
        for repository in source.options.get("repositories", []):
            response = self.client.get(
                f"https://api.github.com/repos/{repository}/releases",
                headers={"Accept": "application/vnd.github+json"},
                timeout=30,
            )
            response.raise_for_status()
            for release in response.json():
                published_at = datetime.fromisoformat(
                    release["published_at"].replace("Z", "+00:00")
                )
                if since <= published_at <= until:
                    articles.append(
                        RawArticle(
                            source_id=source.id,
                            source_name=f"{source.name}: {repository}",
                            title=f"{repository} {release['name'] or release['tag_name']}",
                            url=release["html_url"],
                            published_at=published_at,
                            fetched_at=fetched_at,
                            excerpt=release.get("body") or "",
                            categories=source.categories,
                            raw_metadata={"repository": repository},
                        )
                    )
        return articles
```

Create `src/ai_news_sniffer/sources/hacker_news.py`:

```python
from datetime import UTC, datetime

import httpx

from ai_news_sniffer.models import RawArticle, SourceConfig


class HackerNewsAdapter:
    BASE = "https://hacker-news.firebaseio.com/v0"

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def fetch(
        self,
        source: SourceConfig,
        since: datetime,
        until: datetime,
    ) -> list[RawArticle]:
        limit = int(source.options.get("item_limit", 100))
        ids = self.client.get(f"{self.BASE}/topstories.json", timeout=30).json()[:limit]
        fetched_at = datetime.now(UTC)
        include_terms = tuple(
            term.casefold()
            for term in source.options.get(
                "include_terms",
                ["ai", "llm", "model", "agent", "inference"],
            )
        )
        articles: list[RawArticle] = []
        for item_id in ids:
            response = self.client.get(f"{self.BASE}/item/{item_id}.json", timeout=15)
            response.raise_for_status()
            item = response.json()
            title = item.get("title", "")
            published_at = datetime.fromtimestamp(item["time"], tz=UTC)
            if (
                item.get("type") != "story"
                or not since <= published_at <= until
                or not any(term in title.casefold() for term in include_terms)
            ):
                continue
            articles.append(
                RawArticle(
                    source_id=source.id,
                    source_name=source.name,
                    title=title,
                    url=item.get("url") or f"https://news.ycombinator.com/item?id={item_id}",
                    published_at=published_at,
                    fetched_at=fetched_at,
                    excerpt=item.get("text") or "",
                    categories=source.categories,
                    raw_metadata={"hn_id": item_id, "score": item.get("score", 0)},
                )
            )
        return articles
```

- [ ] **Step 6: Implement normalization**

Create `src/ai_news_sniffer/normalization.py`:

```python
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ai_news_sniffer.models import Article, RawArticle

TRACKING_KEYS = {"fbclid", "gclid", "ref", "source"}
TRACKING_PREFIXES = ("utm_",)


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.casefold() not in TRACKING_KEYS
        and not key.casefold().startswith(TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.casefold(), parts.netloc.casefold(), path, urlencode(query), "")
    )


def normalize_title(title: str) -> str:
    return " ".join(re.findall(r"[\w\u4e00-\u9fff]+", title.casefold()))


def normalize_article(raw: RawArticle) -> Article:
    canonical_url = canonicalize_url(str(raw.url))
    normalized_title = normalize_title(raw.title)
    fingerprint = hashlib.sha256(
        f"{canonical_url}\n{normalized_title}".encode()
    ).hexdigest()
    return Article(
        **raw.model_dump(),
        id=fingerprint[:16],
        canonical_url=canonical_url,
        normalized_title=normalized_title,
        fingerprint=fingerprint,
    )
```

- [ ] **Step 7: Add complete public-API fixtures and coverage**

Create `tests/fixtures/github_releases.json`:

```json
[
  {
    "name": "v1.0",
    "tag_name": "v1.0",
    "published_at": "2026-07-23T09:00:00Z",
    "html_url": "https://github.com/acme/model/releases/tag/v1.0",
    "body": "First stable release."
  },
  {
    "name": "v0.1",
    "tag_name": "v0.1",
    "published_at": "2026-07-01T09:00:00Z",
    "html_url": "https://github.com/acme/model/releases/tag/v0.1",
    "body": "Old release outside the window."
  }
]
```

Create `tests/fixtures/hn_topstories.json`:

```json
[123]
```

Create `tests/fixtures/hn_item.json`:

```json
{
  "id": 123,
  "type": "story",
  "title": "New open-source AI inference engine",
  "url": "https://example.com/inference",
  "time": 1784811600,
  "score": 250
}
```

Append these tests to `tests/test_sources.py`:

```python
def test_github_releases_adapter_filters_old_releases() -> None:
    source = SourceConfig(
        id="releases",
        name="Releases",
        kind="github_releases",
        categories=["open-source"],
        options={"repositories": ["acme/model"]},
    )
    with respx.mock:
        respx.get("https://api.github.com/repos/acme/model/releases").mock(
            return_value=httpx.Response(
                200,
                json=json.loads(
                    (FIXTURES / "github_releases.json").read_text(encoding="utf-8")
                ),
            )
        )
        articles = build_source_adapter(source, httpx.Client()).fetch(
            source, SINCE, UNTIL
        )
    assert len(articles) == 1
    assert articles[0].title == "acme/model v1.0"


def test_hacker_news_adapter_filters_for_ai_terms() -> None:
    source = SourceConfig(
        id="hn",
        name="Hacker News",
        kind="hacker_news",
        categories=["developer-tools"],
        options={"item_limit": 10, "include_terms": ["AI"]},
    )
    with respx.mock:
        respx.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json"
        ).mock(
            return_value=httpx.Response(
                200,
                json=json.loads(
                    (FIXTURES / "hn_topstories.json").read_text(encoding="utf-8")
                ),
            )
        )
        respx.get("https://hacker-news.firebaseio.com/v0/item/123.json").mock(
            return_value=httpx.Response(
                200,
                json=json.loads(
                    (FIXTURES / "hn_item.json").read_text(encoding="utf-8")
                ),
            )
        )
        articles = build_source_adapter(source, httpx.Client()).fetch(
            source, SINCE, UNTIL
        )
    assert len(articles) == 1
    assert articles[0].raw_metadata["hn_id"] == 123
```

Add `import json` to the imports at the top of `tests/test_sources.py`.

- [ ] **Step 8: Run source tests and commit**

Run:

```bash
pytest tests/test_sources.py -v
ruff check src tests
```

Expected: all adapter and normalization tests pass; Ruff exits 0.

Commit:

```bash
git add src/ai_news_sniffer/sources src/ai_news_sniffer/normalization.py tests
git commit -m "feat: add free news source adapters"
```

---

### Task 3: Deterministic Deduplication and Scoring

> **Superseded — do not execute.** Execute Task 5 of `docs/superpowers/plans/2026-07-23-ai-news-source-strategy.md`; it adds compatible deduplication and scoring plus the required fact-confirmation gate.

**Files:**
- Create: `src/ai_news_sniffer/dedup.py`
- Create: `src/ai_news_sniffer/scoring.py`
- Test: `tests/test_dedup_scoring.py`

**Interfaces:**
- Consumes: `Article`, `InterestsConfig`, source weights from `dict[str, float]`.
- Produces: `deduplicate_articles(articles: list[Article], seen_fingerprints: set[str], title_threshold: float = 92) -> list[Article]`, `score_articles(articles: list[Article], interests: InterestsConfig, source_weights: dict[str, float], now: datetime) -> list[Article]`.

- [ ] **Step 1: Write failing deduplication and scoring tests**

Create `tests/test_dedup_scoring.py`:

```python
from datetime import UTC, datetime, timedelta

from ai_news_sniffer.dedup import deduplicate_articles
from ai_news_sniffer.models import Article, InterestsConfig
from ai_news_sniffer.scoring import score_articles

NOW = datetime(2026, 7, 23, 13, tzinfo=UTC)


def article(article_id: str, title: str, url: str, source_id: str = "official") -> Article:
    return Article(
        id=article_id,
        source_id=source_id,
        source_name=source_id,
        title=title,
        url=url,
        canonical_url=url,
        normalized_title=title.casefold(),
        fingerprint=article_id * 64,
        published_at=NOW - timedelta(hours=1),
        fetched_at=NOW,
        categories=["models"],
        excerpt="A new reasoning model is released.",
    )


def test_deduplicate_articles_removes_seen_url_and_near_duplicate_title() -> None:
    first = article("a", "Company releases Model X", "https://example.com/x")
    same_url = article("b", "Model X is here", "https://example.com/x")
    same_event_title = article(
        "c", "Company releases the Model X", "https://news.example.com/x"
    )

    result = deduplicate_articles([first, same_url, same_event_title], set())

    assert result == [first]


def test_score_articles_prioritizes_official_relevant_technical_news() -> None:
    technical = article("a", "New open-source reasoning model", "https://official.test/a")
    unrelated = article("b", "Celebrity interview", "https://other.test/b", "other")
    interests = InterestsConfig(
        topics=["models", "open-source"],
        entities=[],
        include_terms=["reasoning", "model"],
        exclude_terms=["sponsored"],
    )

    ranked = score_articles(
        [unrelated, technical],
        interests,
        {"official": 25, "other": 5},
        NOW,
    )

    assert ranked[0].id == "a"
    assert 0 <= ranked[0].rule_score <= 100
```

- [ ] **Step 2: Run the tests to prove ranking modules are missing**

Run:

```bash
pytest tests/test_dedup_scoring.py -v
```

Expected: collection fails because `ai_news_sniffer.dedup` is missing.

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
    for candidate in sorted(articles, key=lambda item: item.published_at, reverse=True):
        if candidate.fingerprint in seen_fingerprints:
            continue
        if candidate.canonical_url in seen_urls:
            continue
        if any(
            token_set_ratio(candidate.normalized_title, item.normalized_title)
            >= title_threshold
            for item in kept
        ):
            continue
        kept.append(candidate)
        seen_urls.add(candidate.canonical_url)
    return kept
```

- [ ] **Step 4: Implement the 100-point scoring function**

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
TECH_CATEGORIES = {"models", "products", "research", "open-source", "developer-tools"}


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
        technical_score = 15 if TECH_CATEGORIES.intersection(article.categories) else 8
        corroboration_score = min(
            10,
            sum(
                5
                for other in articles
                if other.id != article.id
                and other.source_id != article.source_id
                and token_set_ratio(
                    article.normalized_title,
                    other.normalized_title,
                )
                >= 70
            ),
        )
        age_hours = max(0, (now - article.published_at).total_seconds() / 3600)
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

- [ ] **Step 5: Prove tests and commit**

Run:

```bash
pytest tests/test_dedup_scoring.py -v
pytest -q
ruff check src tests
```

Expected: focused tests report `2 passed`; full suite and Ruff exit 0.

Commit:

```bash
git add src/ai_news_sniffer/dedup.py src/ai_news_sniffer/scoring.py tests/test_dedup_scoring.py
git commit -m "feat: add deterministic ranking pipeline"
```

---

### Task 4: Runtime State and Idempotent Stage Transitions

**Files:**
- Create: `src/ai_news_sniffer/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `DailyReport`, `RunRecord`, `RunStatus`, `ChannelResult`.
- Produces: `RuntimeStore(root: Path)`, `load_seen_fingerprints(excluding_date: date | None = None) -> set[str]`, `save_prepared(report: DailyReport, fingerprints: set[str]) -> RunRecord`, `load_run(run_id: str) -> RunRecord`, `mark_published(run_id: str, report_url: str) -> RunRecord`, `mark_notified(run_id: str, results: list[ChannelResult]) -> RunRecord`, `load_reports() -> list[DailyReport]`.

- [ ] **Step 1: Write failing state transition tests**

Create `tests/test_state.py`:

```python
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ai_news_sniffer.models import ChannelResult, DailyReport, RunStatus
from ai_news_sniffer.state import RuntimeStore


def report() -> DailyReport:
    return DailyReport(
        date=date(2026, 7, 23),
        generated_at=datetime(2026, 7, 23, 13, tzinfo=UTC),
        run_id="2026-07-23-a1b2c3",
        daily_summary_zh="今日摘要",
        events=[],
    )


def test_runtime_store_advances_prepared_published_notified(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path)
    prepared = store.save_prepared(report(), {"fingerprint-a"})
    assert prepared.status is RunStatus.PREPARED
    assert store.load_seen_fingerprints() == set()

    published = store.mark_published(prepared.run_id, "https://ai.example.com/2026/07/23/")
    assert published.status is RunStatus.PUBLISHED
    assert store.load_seen_fingerprints() == {"fingerprint-a"}

    notified = store.mark_notified(
        prepared.run_id,
        [ChannelResult(channel_id="meow", success=True, attempts=1)],
    )
    assert notified.status is RunStatus.NOTIFIED


def test_runtime_store_rejects_invalid_transition(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path)
    store.save_prepared(report(), set())

    with pytest.raises(ValueError, match="published"):
        store.mark_notified("2026-07-23-a1b2c3", [])
```

- [ ] **Step 2: Run the tests to prove the state store is missing**

Run:

```bash
pytest tests/test_state.py -v
```

Expected: collection fails because `ai_news_sniffer.state` does not exist.

- [ ] **Step 3: Implement atomic JSON persistence and transitions**

Create `src/ai_news_sniffer/state.py`:

```python
import json
from datetime import UTC, date, datetime
from pathlib import Path

from ai_news_sniffer.models import (
    ChannelResult,
    DailyReport,
    RunRecord,
    RunStatus,
)


class RuntimeStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.reports_dir = root / "reports"
        self.runs_dir = root / "runs"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: Path, value: dict) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _run_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def _load_run(self, run_id: str) -> RunRecord:
        return RunRecord.model_validate_json(
            self._run_path(run_id).read_text(encoding="utf-8")
        )

    def load_run(self, run_id: str) -> RunRecord:
        return self._load_run(run_id)

    def _fingerprint_index(self) -> dict[str, str]:
        path = self.root / "seen_fingerprints.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))["fingerprints"]

    def load_seen_fingerprints(
        self,
        excluding_date: date | None = None,
    ) -> set[str]:
        excluded = excluding_date.isoformat() if excluding_date else None
        return {
            fingerprint
            for fingerprint, report_date in self._fingerprint_index().items()
            if report_date != excluded
        }

    def save_seen_fingerprints(
        self,
        fingerprints: set[str],
        target_date: date,
    ) -> None:
        index = self._fingerprint_index()
        index.update(
            {fingerprint: target_date.isoformat() for fingerprint in fingerprints}
        )
        self._write_json(
            self.root / "seen_fingerprints.json",
            {"fingerprints": dict(sorted(index.items()))},
        )

    def save_prepared(
        self,
        report: DailyReport,
        fingerprints: set[str],
    ) -> RunRecord:
        now = datetime.now(UTC)
        report_path = self.reports_dir / f"{report.date.isoformat()}.json"
        self._write_json(report_path, report.model_dump(mode="json"))
        if self._run_path(report.run_id).exists():
            return self._load_run(report.run_id)
        record = RunRecord(
            run_id=report.run_id,
            target_date=report.date,
            status=RunStatus.PREPARED,
            created_at=now,
            updated_at=now,
            report_path=str(report_path.relative_to(self.root)),
            pending_fingerprints=sorted(fingerprints),
        )
        self._write_json(self._run_path(record.run_id), record.model_dump(mode="json"))
        return record

    def mark_published(self, run_id: str, report_url: str) -> RunRecord:
        record = self._load_run(run_id)
        if record.status in {
            RunStatus.PUBLISHED,
            RunStatus.NOTIFIED,
            RunStatus.PARTIALLY_NOTIFIED,
        }:
            return record
        if record.status not in {RunStatus.PREPARED, RunStatus.DEGRADED}:
            raise ValueError("run must be prepared before it can be published")
        record.status = RunStatus.PUBLISHED
        record.report_url = report_url
        record.updated_at = datetime.now(UTC)
        self.save_seen_fingerprints(
            set(record.pending_fingerprints),
            record.target_date,
        )
        self._write_json(self._run_path(run_id), record.model_dump(mode="json"))
        self._write_json(
            self.root / "latest.json",
            {"run_id": run_id, "report_url": report_url},
        )
        return record

    def mark_notified(
        self,
        run_id: str,
        results: list[ChannelResult],
    ) -> RunRecord:
        record = self._load_run(run_id)
        if record.status not in {RunStatus.PUBLISHED, RunStatus.PARTIALLY_NOTIFIED}:
            raise ValueError("run must be published before it can be notified")
        record.channel_results = results
        record.status = (
            RunStatus.NOTIFIED
            if all(result.success for result in results)
            else RunStatus.PARTIALLY_NOTIFIED
        )
        record.updated_at = datetime.now(UTC)
        self._write_json(self._run_path(run_id), record.model_dump(mode="json"))
        return record

    def load_reports(self) -> list[DailyReport]:
        return sorted(
            (
                DailyReport.model_validate_json(path.read_text(encoding="utf-8"))
                for path in self.reports_dir.glob("*.json")
            ),
            key=lambda item: item.date,
        )
```

- [ ] **Step 4: Add fingerprint round-trip and duplicate-run tests**

Append to `tests/test_state.py`:

```python
def test_seen_fingerprints_round_trip(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path)
    store.save_seen_fingerprints({"a", "b"}, date(2026, 7, 23))
    assert store.load_seen_fingerprints() == {"a", "b"}
    assert store.load_seen_fingerprints(excluding_date=date(2026, 7, 23)) == set()


def test_load_run_is_public(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path)
    saved = store.save_prepared(report(), set())
    assert store.load_run(saved.run_id) == saved


def test_partial_notification_can_advance_after_failed_channel_retry(
    tmp_path: Path,
) -> None:
    store = RuntimeStore(tmp_path)
    saved = store.save_prepared(report(), set())
    store.mark_published(saved.run_id, "https://ai.example.com/2026/07/23/")
    partial = store.mark_notified(
        saved.run_id,
        [
            ChannelResult(channel_id="meow", success=True, attempts=1),
            ChannelResult(channel_id="wecom", success=False, attempts=3),
        ],
    )
    completed = store.mark_notified(
        saved.run_id,
        [
            ChannelResult(channel_id="meow", success=True, attempts=1),
            ChannelResult(channel_id="wecom", success=True, attempts=1),
        ],
    )
    assert partial.status is RunStatus.PARTIALLY_NOTIFIED
    assert completed.status is RunStatus.NOTIFIED


def test_save_prepared_preserves_completed_run_idempotently(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path)
    first = store.save_prepared(report(), set())
    store.mark_published(first.run_id, "https://ai.example.com/2026/07/23/")
    completed = store.mark_notified(
        first.run_id,
        [ChannelResult(channel_id="meow", success=True, attempts=1)],
    )
    second = store.save_prepared(report(), set())
    assert first.run_id == second.run_id
    assert second.status is RunStatus.NOTIFIED
    assert second == completed
    assert len(store.load_reports()) == 1
```

- [ ] **Step 5: Run state tests and commit**

Run:

```bash
pytest tests/test_state.py -v
pytest -q
ruff check src tests
```

Expected: state tests report `6 passed`; full suite and Ruff exit 0.

Commit:

```bash
git add src/ai_news_sniffer/state.py tests/test_state.py
git commit -m "feat: add persistent runtime state"
```

---

### Task 5: Provider Chain and Semantic Editorial Pass

**Files:**
- Create: `src/ai_news_sniffer/providers/__init__.py`
- Create: `src/ai_news_sniffer/providers/base.py`
- Create: `src/ai_news_sniffer/providers/openai_compatible.py`
- Create: `src/ai_news_sniffer/providers/editorial.py`
- Create: `prompts/editorial.md`
- Create: `tests/fixtures/editorial_response.json`
- Test: `tests/test_providers.py`

**Interfaces:**
- Consumes: `Article`, `NewsEvent`, `ProviderConfig`, `resolve_secret`.
- Produces: `StructuredProvider.generate_json(system_prompt: str, user_prompt: str) -> dict`, `ProviderChain.generate_json(...) -> dict`, `EditorialService.edit(candidates: list[Article], min_items: int, max_items: int) -> tuple[str, list[NewsEvent]]`.

- [ ] **Step 1: Write failing provider fallback and validation tests**

Create `tests/test_providers.py`:

```python
import json
from pathlib import Path

import pytest

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


def test_provider_chain_uses_next_provider_after_failure() -> None:
    result = ProviderChain([FailingProvider(), FixtureProvider()]).generate_json("s", "u")
    assert result["daily_summary_zh"] == "今日 AI 要闻"


def test_editorial_service_rejects_unknown_candidate_ids() -> None:
    service = EditorialService(FixtureProvider(), "Output JSON.")
    with pytest.raises(ValueError, match="unknown candidate"):
        service.edit([], min_items=1, max_items=15)
```

Create `tests/fixtures/editorial_response.json`:

```json
{
  "daily_summary_zh": "今日 AI 要闻",
  "events": [
    {
      "id": "event-1",
      "candidate_ids": ["missing"],
      "category": "models",
      "title_zh": "新模型发布",
      "summary_zh": "某公司发布了新模型。",
      "why_it_matters_zh": "它提高了推理能力。",
      "importance_score": 90,
      "primary_candidate_id": "missing",
      "related_candidate_ids": []
    }
  ]
}
```

- [ ] **Step 2: Run tests to prove provider modules are missing**

Run:

```bash
pytest tests/test_providers.py -v
```

Expected: collection fails because `ai_news_sniffer.providers` does not exist.

- [ ] **Step 3: Define provider protocol and fallback chain**

Create an empty `src/ai_news_sniffer/providers/__init__.py`.

Create `src/ai_news_sniffer/providers/base.py`:

```python
from typing import Protocol


class StructuredProvider(Protocol):
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict: ...


class ProviderChain:
    def __init__(self, providers: list[StructuredProvider]) -> None:
        if not providers:
            raise ValueError("provider chain cannot be empty")
        self.providers = providers

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return provider.generate_json(system_prompt, user_prompt)
            except Exception as error:
                errors.append(f"{type(error).__name__}: {error}")
        raise RuntimeError("all providers failed: " + " | ".join(errors))
```

- [ ] **Step 4: Implement the OpenAI-compatible provider**

Create `src/ai_news_sniffer/providers/openai_compatible.py`:

```python
import json
import time

from openai import OpenAI

from ai_news_sniffer.config import resolve_secret
from ai_news_sniffer.models import ProviderConfig


class OpenAICompatibleProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.client = OpenAI(
            api_key=resolve_secret(config.api_key_env),
            base_url=str(config.base_url).rstrip("/"),
            timeout=config.timeout_seconds,
        )

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    stream=False,
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("provider returned empty content")
                return json.loads(content)
            except Exception as error:
                last_error = error
                if attempt < self.config.max_retries:
                    time.sleep(2 ** (attempt - 1))
        raise RuntimeError(
            f"provider {self.config.id} failed after "
            f"{self.config.max_retries} attempts: {last_error}"
        )
```

- [ ] **Step 5: Implement semantic output validation**

Create `src/ai_news_sniffer/providers/editorial.py`:

```python
import json

from pydantic import BaseModel, Field

from ai_news_sniffer.models import (
    Article,
    ConfirmationStatus,
    NewsEvent,
    SourceGroup,
    SourceRef,
)
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
                        "source_group": item.source_group,
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
                raise ValueError(f"unknown candidate ids: {sorted(unknown)}")
            primary = by_id[event.primary_candidate_id]
            related = [
                by_id[item_id]
                for item_id in event.related_candidate_ids
                if item_id != event.primary_candidate_id
            ]
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
            events.append(news_event)
        return output.daily_summary_zh, events
```

Create `prompts/editorial.md`:

```markdown
You are the editor of a high-signal Chinese AI daily digest.

Return one valid JSON object. Merge articles about the same real-world event.
Never invent facts, dates, organizations, metrics, or source URLs. Use candidate
IDs exactly as provided. Prefer official and primary sources. Rank model,
technical, open-source, developer-tool, and AI-product events slightly higher,
while retaining genuinely important business, financing, acquisition, and
policy events. Separate factual summary from why the event matters. Do not
select a community candidate as `primary_candidate_id`. Do not include an event
unless its candidates contain an official/research source or two independent
media origins.

The JSON object must have `daily_summary_zh` and `events`. Every event must have
`id`, `candidate_ids`, `category`, `title_zh`, `summary_zh`,
`why_it_matters_zh`, `importance_score`, `primary_candidate_id`, and
`related_candidate_ids`.

Example JSON shape:
{"daily_summary_zh":"今日摘要","events":[{"id":"event-1",
"candidate_ids":["a1"],"category":"models","title_zh":"标题",
"summary_zh":"事实摘要","why_it_matters_zh":"重要性说明",
"importance_score":90,"primary_candidate_id":"a1",
"related_candidate_ids":[]}]}
```

- [ ] **Step 6: Add a complete valid editorial conversion test**

Append to `tests/test_providers.py`:

```python
from datetime import UTC, datetime

from ai_news_sniffer.models import Article, ConfirmationStatus, SourceGroup


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
    assert events[0].candidate_ids == ["a1"]
    assert events[0].primary_source.source_id == candidate.source_id
    assert (
        events[0].confirmation_status
        == ConfirmationStatus.PRIMARY_CONFIRMED
    )
    assert events[0].title_zh == "新模型发布"
```

- [ ] **Step 7: Run provider tests and commit**

Run:

```bash
pytest tests/test_providers.py -v
pytest -q
ruff check src tests
```

Expected: fallback, validation, and conversion tests pass; full suite and Ruff exit 0.

Commit:

```bash
git add src/ai_news_sniffer/providers prompts tests/test_providers.py tests/fixtures
git commit -m "feat: add extensible editorial provider chain"
```

---

### Task 6: Diversity Selection and Degraded Reports

**Files:**
- Create: `src/ai_news_sniffer/selection.py`
- Test: `tests/test_selection.py`

**Interfaces:**
- Consumes: `Article`, `NewsEvent`, `SourceRef`.
- Produces: `select_diverse_events(events: list[NewsEvent], max_items: int, max_per_category: int = 3, max_per_source: int = 2) -> list[NewsEvent]`, `build_degraded_events(articles: list[Article], max_items: int) -> list[NewsEvent]`.

- [ ] **Step 1: Write failing diversity and degraded-mode tests**

Create `tests/test_selection.py`:

```python
from datetime import UTC, datetime

from ai_news_sniffer.models import (
    Article,
    ConfirmationStatus,
    NewsEvent,
    SourceGroup,
    SourceRef,
)
from ai_news_sniffer.selection import build_degraded_events, select_diverse_events

NOW = datetime(2026, 7, 23, 13, tzinfo=UTC)


def source(source_id: str, suffix: str) -> SourceRef:
    return SourceRef(
        source_id=source_id,
        source_name=source_id,
        title=f"Source title {suffix}",
        url=f"https://example.com/{suffix}",
        published_at=NOW,
    )


def event(number: int, category: str, source_id: str) -> NewsEvent:
    return NewsEvent(
        id=f"event-{number}",
        candidate_ids=[f"article-{number}"],
        category=category,
        title_zh=f"新闻 {number}",
        summary_zh="事实摘要",
        why_it_matters_zh="重要性说明",
        importance_score=100 - number,
        confirmation_status=ConfirmationStatus.PRIMARY_CONFIRMED,
        primary_source=source(source_id, str(number)),
    )


def test_select_diverse_events_enforces_source_and_category_caps() -> None:
    events = [
        event(1, "models", "same"),
        event(2, "models", "same"),
        event(3, "models", "same"),
        event(4, "models", "other"),
        event(5, "policy", "policy-source"),
    ]

    selected = select_diverse_events(
        events,
        max_items=5,
        max_per_category=3,
        max_per_source=2,
    )

    assert [item.id for item in selected] == ["event-1", "event-2", "event-4", "event-5"]


def test_build_degraded_events_does_not_invent_why_it_matters() -> None:
    article = Article(
        id="a1",
        source_id="official",
        source_name="Official",
        source_group=SourceGroup.OFFICIAL,
        independence_group="official",
        title="Original title",
        url="https://example.com/a1",
        canonical_url="https://example.com/a1",
        normalized_title="original title",
        fingerprint="a" * 64,
        published_at=NOW,
        fetched_at=NOW,
        excerpt="Original source excerpt.",
        categories=["models"],
        rule_score=88,
    )

    degraded = build_degraded_events([article], max_items=15)

    assert degraded[0].summary_zh == "Original source excerpt."
    assert degraded[0].why_it_matters_zh == ""
```

- [ ] **Step 2: Run tests to prove the selection module is missing**

Run:

```bash
pytest tests/test_selection.py -v
```

Expected: collection fails because `ai_news_sniffer.selection` does not exist.

- [ ] **Step 3: Implement diversity caps and source-only degradation**

Create `src/ai_news_sniffer/selection.py`:

```python
from collections import Counter

from ai_news_sniffer.models import (
    Article,
    ConfirmationStatus,
    NewsEvent,
    SourceGroup,
    SourceRef,
)


def select_diverse_events(
    events: list[NewsEvent],
    max_items: int,
    max_per_category: int = 3,
    max_per_source: int = 2,
) -> list[NewsEvent]:
    category_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    selected: list[NewsEvent] = []
    for event in sorted(events, key=lambda item: item.importance_score, reverse=True):
        if event.confirmation_status == ConfirmationStatus.UNVERIFIED:
            continue
        source_id = event.primary_source.source_id
        if category_counts[event.category] >= max_per_category:
            continue
        if source_counts[source_id] >= max_per_source:
            continue
        selected.append(event)
        category_counts[event.category] += 1
        source_counts[source_id] += 1
        if len(selected) == max_items:
            break
    return selected


def build_degraded_events(
    articles: list[Article],
    max_items: int,
) -> list[NewsEvent]:
    events: list[NewsEvent] = []
    for article in articles[:max_items]:
        if article.source_group not in {
            SourceGroup.OFFICIAL,
            SourceGroup.RESEARCH,
        }:
            continue
        events.append(
            NewsEvent(
                id=f"degraded-{article.id}",
                candidate_ids=[article.id],
                category=article.categories[0] if article.categories else "other",
                title_zh=article.title,
                summary_zh=article.excerpt[:500],
                why_it_matters_zh="",
                importance_score=article.rule_score,
                confirmation_status=ConfirmationStatus.PRIMARY_CONFIRMED,
                primary_source=SourceRef(
                    source_id=article.source_id,
                    source_name=article.source_name,
                    title=article.title,
                    url=article.url,
                    published_at=article.published_at,
                ),
            )
        )
    return events
```

- [ ] **Step 4: Run selection tests and commit**

Run:

```bash
pytest tests/test_selection.py -v
pytest -q
ruff check src tests
```

Expected: selection tests report `2 passed`; full suite and Ruff exit 0.

Commit:

```bash
git add src/ai_news_sniffer/selection.py tests/test_selection.py
git commit -m "feat: enforce editorial diversity and degradation"
```

---

### Task 7: Sandboxed Template Rendering and Historical Site

**Files:**
- Create: `src/ai_news_sniffer/rendering/__init__.py`
- Create: `src/ai_news_sniffer/rendering/site.py`
- Create: `templates/default/report.html.j2`
- Create: `templates/default/index.html.j2`
- Create: `templates/default/archive.html.j2`
- Create: `templates/default/notification.md.j2`
- Create: `templates/default/static/style.css`
- Test: `tests/test_rendering.py`

**Interfaces:**
- Consumes: `DailyReport`, a history list, template name, and public base URL.
- Produces: `SiteRenderer(templates_root: Path).render(reports: list[DailyReport], template_name: str, output_dir: Path) -> list[Path]`, `SiteRenderer.render_notification(report: DailyReport, template_name: str) -> str`.

- [ ] **Step 1: Write failing rendering tests**

Create `tests/test_rendering.py`:

```python
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ai_news_sniffer.models import (
    ConfirmationStatus,
    DailyReport,
    NewsEvent,
    SourceRef,
)
from ai_news_sniffer.rendering.site import SiteRenderer


def make_report() -> DailyReport:
    source = SourceRef(
        source_id="official",
        source_name="Official",
        title="Original title",
        url="https://example.com/original",
        published_at=datetime(2026, 7, 23, 10, tzinfo=UTC),
    )
    event = NewsEvent(
        id="event-1",
        candidate_ids=["a1"],
        category="models",
        title_zh="新模型发布",
        summary_zh="这是事实摘要。",
        why_it_matters_zh="这会影响开发者。",
        importance_score=95,
        confirmation_status=ConfirmationStatus.PRIMARY_CONFIRMED,
        primary_source=source,
    )
    return DailyReport(
        date=date(2026, 7, 23),
        generated_at=datetime(2026, 7, 23, 13, tzinfo=UTC),
        run_id="run-1",
        daily_summary_zh="今日共一条重要新闻。",
        events=[event],
        source_coverage={
            "enabled": 12,
            "ai_candidates": 20,
            "estimated_input_tokens": 8000,
            "failed_source_ids": [],
            "newly_auto_paused_source_ids": [],
        },
    )


def test_render_creates_latest_dated_archive_and_noindex(tmp_path: Path) -> None:
    renderer = SiteRenderer(Path("templates"))
    created = renderer.render([make_report()], "default", tmp_path)

    assert tmp_path / "index.html" in created
    assert (tmp_path / "2026/07/23/index.html").exists()
    assert (tmp_path / "archive/index.html").exists()
    html = (tmp_path / "2026/07/23/index.html").read_text(encoding="utf-8")
    assert '<meta name="robots" content="noindex,nofollow">' in html
    assert "为什么重要" in html
    assert "https://example.com/original" in html
    assert "来源覆盖" in html
    assert "启用 12" in html


def test_render_notification_includes_only_three_headlines() -> None:
    report = make_report()
    report.events = report.events * 4
    text = SiteRenderer(Path("templates")).render_notification(report, "default")
    assert text.count("阅读原文") == 3


def test_renderer_rejects_template_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="template name"):
        SiteRenderer(Path("templates")).render(
            [make_report()],
            "../outside",
            tmp_path,
        )
```

- [ ] **Step 2: Run tests to prove rendering is missing**

Run:

```bash
pytest tests/test_rendering.py -v
```

Expected: collection fails because `ai_news_sniffer.rendering` does not exist.

- [ ] **Step 3: Implement the sandboxed renderer**

Create an empty `src/ai_news_sniffer/rendering/__init__.py`.

Create `src/ai_news_sniffer/rendering/site.py`:

```python
from pathlib import Path
from shutil import copytree

from jinja2 import FileSystemLoader, StrictUndefined, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

from ai_news_sniffer.models import DailyReport


class SiteRenderer:
    def __init__(self, templates_root: Path) -> None:
        self.templates_root = templates_root

    def _environment(self, template_name: str) -> SandboxedEnvironment:
        root = self.templates_root.resolve()
        directory = (root / template_name).resolve()
        if root not in directory.parents:
            raise ValueError("template name must stay inside templates root")
        if not directory.is_dir():
            raise ValueError(f"template does not exist: {template_name}")
        environment = SandboxedEnvironment(
            loader=FileSystemLoader(directory),
            autoescape=select_autoescape(["html", "xml"]),
            undefined=StrictUndefined,
        )
        environment.filters["date_path"] = lambda value: value.strftime("%Y/%m/%d")
        return environment

    def render(
        self,
        reports: list[DailyReport],
        template_name: str,
        output_dir: Path,
    ) -> list[Path]:
        if not reports:
            raise ValueError("cannot render a site without reports")
        environment = self._environment(template_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        created: list[Path] = []
        ordered = sorted(reports, key=lambda item: item.date, reverse=True)
        report_template = environment.get_template("report.html.j2")
        for index, report in enumerate(ordered):
            destination = (
                output_dir
                / f"{report.date:%Y}"
                / f"{report.date:%m}"
                / f"{report.date:%d}"
                / "index.html"
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                report_template.render(
                    report=report,
                    previous=ordered[index + 1] if index + 1 < len(ordered) else None,
                    next=ordered[index - 1] if index > 0 else None,
                ),
                encoding="utf-8",
            )
            created.append(destination)
        latest = output_dir / "index.html"
        latest.write_text(
            environment.get_template("index.html.j2").render(report=ordered[0]),
            encoding="utf-8",
        )
        created.append(latest)
        archive = output_dir / "archive" / "index.html"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text(
            environment.get_template("archive.html.j2").render(reports=ordered),
            encoding="utf-8",
        )
        created.append(archive)
        static_source = self.templates_root / template_name / "static"
        if static_source.exists():
            copytree(static_source, output_dir / "static", dirs_exist_ok=True)
        return created

    def render_notification(
        self,
        report: DailyReport,
        template_name: str,
    ) -> str:
        return self._environment(template_name).get_template(
            "notification.md.j2"
        ).render(report=report, top_items=report.events[:3])
```

- [ ] **Step 4: Create the complete default templates**

Create `templates/default/report.html.j2`:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>AI 每日情报 · {{ report.date }}</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="hero">
    <p class="eyebrow">DAILY AI SIGNAL</p>
    <h1>AI 每日情报 · {{ report.date }}</h1>
    <p>{{ report.events|length }} 条精选 · 更新于 {{ report.generated_at }}</p>
  </header>
  <main>
    <section class="summary">
      <h2>今日速览</h2>
      <p>{{ report.daily_summary_zh }}</p>
      {% if report.degraded %}
      <p class="warning">模型不可用，本期为来源摘要降级版。</p>
      {% endif %}
    </section>
    <section class="coverage">
      <h2>来源覆盖</h2>
      <p>
        成功 {{ report.source_coverage.get("enabled", 0) - report.source_coverage.get("failed_source_ids", [])|length }}
        / 启用 {{ report.source_coverage.get("enabled", 0) }}；
        模型候选 {{ report.source_coverage.get("ai_candidates", 0) }} 条；
        估算输入 {{ report.source_coverage.get("estimated_input_tokens", 0) }} Token。
      </p>
      {% if report.source_coverage.get("failed_source_ids") %}
      <p class="warning">
        降级来源：{{ report.source_coverage["failed_source_ids"]|join("、") }}
      </p>
      {% endif %}
      {% if report.warnings %}
      <details><summary>运行提示</summary><ul>
        {% for warning in report.warnings %}<li>{{ warning }}</li>{% endfor %}
      </ul></details>
      {% endif %}
    </section>
    {% for event in report.events %}
    <article id="{{ event.id }}">
      <div class="meta">{{ event.category }} · {{ event.primary_source.source_name }}</div>
      <h2>{{ event.title_zh }}</h2>
      <p>{{ event.summary_zh }}</p>
      {% if event.why_it_matters_zh %}
      <aside><strong>为什么重要：</strong>{{ event.why_it_matters_zh }}</aside>
      {% endif %}
      <p><a href="{{ event.primary_source.url }}" rel="noopener noreferrer">阅读原文 ↗</a></p>
      {% if event.related_sources %}
      <details><summary>其他相关来源</summary>
        <ul>{% for source in event.related_sources %}
          <li><a href="{{ source.url }}">{{ source.source_name }}</a></li>
        {% endfor %}</ul>
      </details>
      {% endif %}
    </article>
    {% endfor %}
    <nav>
      {% if previous %}<a href="/{{ previous.date|date_path }}/">← 前一天</a>{% endif %}
      <a href="/archive/">历史归档</a>
      {% if next %}<a href="/{{ next.date|date_path }}/">后一天 →</a>{% endif %}
    </nav>
  </main>
</body>
</html>
```

Create `templates/default/index.html.j2`:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <meta http-equiv="refresh" content="0;url=/{{ report.date|date_path }}/">
  <title>AI 每日情报</title>
</head>
<body><a href="/{{ report.date|date_path }}/">查看最新日报</a></body>
</html>
```

Create `templates/default/archive.html.j2`:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>AI 日报归档</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body><main><h1>历史归档</h1><ul>
{% for report in reports %}
  <li><a href="/{{ report.date|date_path }}/">{{ report.date }} · {{ report.events|length }} 条</a></li>
{% endfor %}
</ul></main></body>
</html>
```

Create `templates/default/notification.md.j2`:

```markdown
{{ report.daily_summary_zh }}
{% if report.source_coverage.get("newly_auto_paused_source_ids") %}
⚠️ 来源维护提醒：已自动暂停
{{ report.source_coverage["newly_auto_paused_source_ids"]|join("、") }}
{% endif %}
{% for event in top_items %}
{{ loop.index }}. **{{ event.title_zh }}**
{{ event.summary_zh }}
[阅读原文]({{ event.primary_source.url }})
{% endfor %}
```

Create `templates/default/static/style.css`:

```css
:root{color-scheme:light;--ink:#0f172a;--muted:#64748b;--brand:#7c3aed}
*{box-sizing:border-box}
body{margin:0;background:#f8fafc;color:var(--ink);font:16px/1.65 system-ui,sans-serif}
.hero{padding:2rem 1.2rem;background:#111827;color:#fff}
.hero>*{max-width:760px;margin-left:auto;margin-right:auto}
.eyebrow{color:#c4b5fd;font-size:.75rem;letter-spacing:.12em}
main{max-width:760px;margin:auto;padding:1rem}
.summary,.coverage,article{background:#fff;border-radius:16px;padding:1.1rem;margin:1rem 0}
.summary{background:#f5f3ff;border:1px solid #ddd6fe}
.meta{color:var(--brand);font-size:.78rem;font-weight:700}
h1,h2{line-height:1.25}
article aside{border-left:3px solid var(--brand);background:#faf5ff;padding:.8rem}
a{color:var(--brand)}
nav{display:flex;justify-content:space-between;gap:1rem;padding:1rem 0}
.warning{color:#b45309;font-weight:700}
@media(max-width:520px){.hero{padding:1.5rem 1rem}main{padding:.7rem}.summary,article{border-radius:12px}}
```

- [ ] **Step 5: Run rendering tests and commit**

Run:

```bash
pytest tests/test_rendering.py -v
pytest -q
ruff check src tests
```

Expected: rendering tests report `3 passed`; full suite and Ruff exit 0.

Commit:

```bash
git add src/ai_news_sniffer/rendering templates tests/test_rendering.py
git commit -m "feat: render mobile-first historical digests"
```

---

### Task 8: Pluggable Notification Gateway

**Files:**
- Create: `src/ai_news_sniffer/notifications/__init__.py`
- Create: `src/ai_news_sniffer/notifications/base.py`
- Create: `src/ai_news_sniffer/notifications/meow.py`
- Create: `src/ai_news_sniffer/notifications/wecom.py`
- Create: `src/ai_news_sniffer/notifications/webhook.py`
- Test: `tests/test_notifications.py`

**Interfaces:**
- Consumes: `NotificationPayload`, `ChannelConfig`, secret environment names.
- Produces: `NotificationChannel.send(payload: NotificationPayload, message: str) -> ChannelResult`, `build_channels(configs: list[ChannelConfig], client: httpx.Client) -> list[NotificationChannel]`, `send_all(channels, payload, message) -> list[ChannelResult]`.

- [ ] **Step 1: Write failing channel-isolation and request-shape tests**

Create `tests/test_notifications.py`:

```python
import json
from datetime import UTC, date, datetime

import httpx
import respx

from ai_news_sniffer.models import (
    ChannelConfig,
    NotificationPayload,
    RunStatus,
)
from ai_news_sniffer.notifications.base import build_channels, send_all


def payload() -> NotificationPayload:
    return NotificationPayload(
        run_id="run-1",
        date=date(2026, 7, 23),
        status=RunStatus.PUBLISHED,
        title="AI 日报 · 2026-07-23",
        daily_summary="今日摘要",
        top_items=[],
        report_url="https://ai.example.com/2026/07/23/",
        generated_at=datetime(2026, 7, 23, 13, tzinfo=UTC),
    )


def test_send_all_isolates_failed_channel(monkeypatch) -> None:
    monkeypatch.setenv("MEOW_NICKNAME", "reader")
    monkeypatch.setenv("WECOM_WEBHOOK_URL", "https://wecom.test/send")
    configs = [
        ChannelConfig(id="meow", kind="meow", enabled=True, nickname_env="MEOW_NICKNAME"),
        ChannelConfig(
            id="wecom",
            kind="wecom",
            enabled=True,
            endpoint_env="WECOM_WEBHOOK_URL",
        ),
    ]
    with respx.mock:
        meow_route = respx.post("https://api.chuckfang.com/reader").mock(
            return_value=httpx.Response(500)
        )
        wecom_route = respx.post("https://wecom.test/send").mock(
            return_value=httpx.Response(200, json={"errcode": 0})
        )
        results = send_all(
            build_channels(configs, httpx.Client()),
            payload(),
            "message",
        )

    assert [result.success for result in results] == [False, True]
    assert json.loads(meow_route.calls[0].request.content)["title"].startswith("AI")
    assert json.loads(wecom_route.calls[0].request.content)["msgtype"] == "markdown"
    assert "reader" not in (results[0].error or "")


def test_generic_webhook_sends_standard_json(monkeypatch) -> None:
    monkeypatch.setenv("GENERIC_WEBHOOK_URL", "https://hook.test/digest")
    config = ChannelConfig(
        id="webhook",
        kind="webhook",
        enabled=True,
        endpoint_env="GENERIC_WEBHOOK_URL",
    )
    with respx.mock:
        route = respx.post("https://hook.test/digest").mock(
            return_value=httpx.Response(200)
        )
        result = build_channels([config], httpx.Client())[0].send(payload(), "message")

    assert result.success is True
    body = json.loads(route.calls[0].request.content)
    assert body["report_url"] == "https://ai.example.com/2026/07/23/"
    assert body["rendered_message"] == "message"
```

- [ ] **Step 2: Run tests to prove notification modules are missing**

Run:

```bash
pytest tests/test_notifications.py -v
```

Expected: collection fails because `ai_news_sniffer.notifications` does not exist.

- [ ] **Step 3: Define channel protocol, registry, retries, and isolation**

Create an empty `src/ai_news_sniffer/notifications/__init__.py`.

Create `src/ai_news_sniffer/notifications/base.py`:

```python
import time
from typing import Protocol

import httpx

from ai_news_sniffer.models import (
    ChannelConfig,
    ChannelResult,
    NotificationPayload,
)


class NotificationChannel(Protocol):
    def send(self, payload: NotificationPayload, message: str) -> ChannelResult: ...


class RetryingChannel:
    def __init__(self, channel_id: str, max_retries: int) -> None:
        self.channel_id = channel_id
        self.max_retries = max_retries

    def _request(self, payload: NotificationPayload, message: str) -> None:
        raise NotImplementedError

    def send(self, payload: NotificationPayload, message: str) -> ChannelResult:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._request(payload, message)
                return ChannelResult(
                    channel_id=self.channel_id,
                    success=True,
                    attempts=attempt,
                )
            except Exception as error:
                last_error = error
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))
        return ChannelResult(
            channel_id=self.channel_id,
            success=False,
            attempts=self.max_retries,
            error=self._safe_error(last_error),
        )

    @staticmethod
    def _safe_error(error: Exception | None) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            return f"HTTP {error.response.status_code}"
        return type(error).__name__ if error else "UnknownError"


def build_channels(
    configs: list[ChannelConfig],
    client: httpx.Client,
) -> list[NotificationChannel]:
    channels: list[NotificationChannel] = []
    for config in configs:
        if not config.enabled:
            continue
        if config.kind == "meow":
            from ai_news_sniffer.notifications.meow import MeowChannel

            channels.append(MeowChannel(config, client))
        elif config.kind == "wecom":
            from ai_news_sniffer.notifications.wecom import WeComChannel

            channels.append(WeComChannel(config, client))
        elif config.kind == "webhook":
            from ai_news_sniffer.notifications.webhook import WebhookChannel

            channels.append(WebhookChannel(config, client))
    return channels


def send_all(
    channels: list[NotificationChannel],
    payload: NotificationPayload,
    message: str,
) -> list[ChannelResult]:
    return [channel.send(payload, message) for channel in channels]
```

- [ ] **Step 4: Implement MeoW, WeCom, and generic webhook adapters**

Create `src/ai_news_sniffer/notifications/meow.py`:

```python
from urllib.parse import quote

import httpx

from ai_news_sniffer.config import resolve_secret
from ai_news_sniffer.models import ChannelConfig, NotificationPayload
from ai_news_sniffer.notifications.base import RetryingChannel


class MeowChannel(RetryingChannel):
    def __init__(self, config: ChannelConfig, client: httpx.Client) -> None:
        super().__init__(config.id, config.max_retries)
        if not config.nickname_env:
            raise ValueError("MeoW channel requires nickname_env")
        nickname = quote(resolve_secret(config.nickname_env), safe="")
        self.endpoint = f"https://api.chuckfang.com/{nickname}"
        self.client = client
        self.timeout = config.timeout_seconds

    def _request(self, payload: NotificationPayload, message: str) -> None:
        response = self.client.post(
            self.endpoint,
            params={"msgType": "markdown"},
            json={
                "title": payload.title,
                "msg": message,
                "url": str(payload.report_url),
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") != 200:
            raise RuntimeError(f"MeoW rejected message with status {data.get('status')}")
```

Create `src/ai_news_sniffer/notifications/wecom.py`:

```python
import httpx

from ai_news_sniffer.config import resolve_secret
from ai_news_sniffer.models import ChannelConfig, NotificationPayload
from ai_news_sniffer.notifications.base import RetryingChannel


class WeComChannel(RetryingChannel):
    def __init__(self, config: ChannelConfig, client: httpx.Client) -> None:
        super().__init__(config.id, config.max_retries)
        if not config.endpoint_env:
            raise ValueError("WeCom channel requires endpoint_env")
        self.endpoint = resolve_secret(config.endpoint_env)
        self.client = client
        self.timeout = config.timeout_seconds

    def _request(self, payload: NotificationPayload, message: str) -> None:
        response = self.client.post(
            self.endpoint,
            json={"msgtype": "markdown", "markdown": {"content": message}},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"WeCom rejected message: {data}")
```

Create `src/ai_news_sniffer/notifications/webhook.py`:

```python
import httpx

from ai_news_sniffer.config import resolve_secret
from ai_news_sniffer.models import ChannelConfig, NotificationPayload
from ai_news_sniffer.notifications.base import RetryingChannel


class WebhookChannel(RetryingChannel):
    def __init__(self, config: ChannelConfig, client: httpx.Client) -> None:
        super().__init__(config.id, config.max_retries)
        if not config.endpoint_env:
            raise ValueError("webhook channel requires endpoint_env")
        self.endpoint = resolve_secret(config.endpoint_env)
        self.client = client
        self.timeout = config.timeout_seconds

    def _request(self, payload: NotificationPayload, message: str) -> None:
        body = payload.model_dump(mode="json")
        body["rendered_message"] = message
        response = self.client.post(self.endpoint, json=body, timeout=self.timeout)
        response.raise_for_status()
```

- [ ] **Step 5: Verify request details and commit**

Run:

```bash
pytest tests/test_notifications.py -v
pytest -q
ruff check src tests
```

Expected: channel isolation and request-shape tests pass; full suite and Ruff exit 0.

Commit:

```bash
git add src/ai_news_sniffer/notifications tests/test_notifications.py
git commit -m "feat: add pluggable notification channels"
```

---

### Task 9: End-to-End Pipeline and CLI Stage Commands

> Extend the `src/ai_news_sniffer/cli.py` created by the source-strategy plan. Preserve its `sources list`, `sources test`, `sources audit`, and `sources candidates` command tree.

**Files:**
- Create: `src/ai_news_sniffer/pipeline.py`
- Modify: `src/ai_news_sniffer/cli.py`
- Create: `src/ai_news_sniffer/__main__.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: all prior task interfaces.
- Produces: `Pipeline.build(target_date: date, dry_run: bool) -> RunRecord`, `verify_report_url(url: str, client: httpx.Client) -> None`, CLI commands `build`, `verify-url`, `mark-published`, and `notify`.

- [ ] **Step 1: Write a failing offline pipeline test**

Create `tests/test_pipeline.py`:

```python
from datetime import UTC, date, datetime
from pathlib import Path

from ai_news_sniffer.models import RawArticle, RunStatus
from ai_news_sniffer.pipeline import Pipeline


class FixtureAdapter:
    def fetch(self, source, since, until):
        return [
            RawArticle(
                source_id=source.id,
                source_name=source.name,
                source_group=source.group,
                independence_group=source.independence_group or source.id,
                title="Official AI model release",
                url="https://example.com/model",
                published_at=datetime(2026, 7, 23, 10, tzinfo=UTC),
                fetched_at=datetime(2026, 7, 23, 13, tzinfo=UTC),
                excerpt="The official release notes.",
                categories=["models"],
            )
        ]


class FixtureEditorial:
    def edit(self, candidates, min_items, max_items):
        from ai_news_sniffer.selection import build_degraded_events

        return "今日 AI 要闻", build_degraded_events(candidates, max_items)


def test_pipeline_builds_prepared_report_without_network(
    tmp_path: Path,
    settings,
) -> None:
    pipeline = Pipeline(
        settings=settings,
        runtime_dir=tmp_path / "runtime",
        output_dir=tmp_path / "site",
        templates_root=Path("templates"),
        adapter_factory=lambda source, client: FixtureAdapter(),
        editorial_service=FixtureEditorial(),
    )

    record = pipeline.build(date(2026, 7, 23), dry_run=False)

    assert record.status is RunStatus.PREPARED
    assert (tmp_path / "site/2026/07/23/index.html").exists()


def test_pipeline_dry_run_does_not_write_fingerprints(
    tmp_path: Path,
    settings,
) -> None:
    runtime_dir = tmp_path / "runtime"
    pipeline = Pipeline(
        settings=settings,
        runtime_dir=runtime_dir,
        output_dir=tmp_path / "site",
        templates_root=Path("templates"),
        adapter_factory=lambda source, client: FixtureAdapter(),
        editorial_service=FixtureEditorial(),
    )

    pipeline.build(date(2026, 7, 23), dry_run=True)

    assert not (runtime_dir / "seen_fingerprints.json").exists()
```

Create `tests/conftest.py`:

```python
from pathlib import Path
from shutil import copytree

import pytest
import yaml

from ai_news_sniffer.config import load_settings


@pytest.fixture
def settings(tmp_path: Path):
    config_dir = tmp_path / "config"
    copytree("config", config_dir)
    app_path = config_dir / "app.yaml"
    app = yaml.safe_load(app_path.read_text(encoding="utf-8"))
    app["public_base_url"] = "https://ai.example.com"
    app_path.write_text(
        yaml.safe_dump(app, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return load_settings(config_dir)
```

- [ ] **Step 2: Run pipeline tests to prove orchestration is missing**

Run:

```bash
pytest tests/test_pipeline.py -v
```

Expected: collection fails because `ai_news_sniffer.pipeline` does not exist.

- [ ] **Step 3: Implement the pipeline**

Create `src/ai_news_sniffer/pipeline.py`:

```python
import hashlib
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from ai_news_sniffer.models import (
    DailyReport,
    RunRecord,
    Settings,
    SourceConfig,
)
from ai_news_sniffer.providers.editorial import EditorialService
from ai_news_sniffer.rendering.site import SiteRenderer
from ai_news_sniffer.selection import build_degraded_events, select_diverse_events
from ai_news_sniffer.source_service import collect_source_candidates
from ai_news_sniffer.sources.base import SourceAdapter, build_source_adapter
from ai_news_sniffer.state import RuntimeStore


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        runtime_dir: Path,
        output_dir: Path,
        templates_root: Path,
        editorial_service: EditorialService,
        adapter_factory: Callable[
            [SourceConfig, httpx.Client],
            SourceAdapter,
        ] = build_source_adapter,
    ) -> None:
        self.settings = settings
        self.runtime_dir = runtime_dir
        self.store = RuntimeStore(runtime_dir)
        self.output_dir = output_dir
        self.renderer = SiteRenderer(templates_root)
        self.editorial_service = editorial_service
        self.adapter_factory = adapter_factory

    def build(
        self,
        target_date: date,
        dry_run: bool,
        source_profile: str | None = None,
        include_sources: set[str] | None = None,
        exclude_sources: set[str] | None = None,
        max_ai_candidates: int | None = None,
    ) -> RunRecord:
        now = datetime.now(UTC)
        timezone = ZoneInfo(self.settings.app.timezone)
        local_start = datetime.combine(target_date, time.min, tzinfo=timezone)
        until = (local_start + timedelta(days=1)).astimezone(UTC)
        since = until - timedelta(hours=self.settings.app.lookback_hours)
        seen_fingerprints = self.store.load_seen_fingerprints(
            excluding_date=target_date
        )
        with httpx.Client(
            headers={"User-Agent": "ai-news-sniffer/0.1"},
            follow_redirects=True,
        ) as client:
            collection = collect_source_candidates(
                settings=self.settings,
                runtime_root=self.runtime_dir,
                since=since,
                until=until,
                profile=source_profile,
                include_sources=include_sources,
                exclude_sources=exclude_sources,
                max_ai_candidates=max_ai_candidates,
                seen_fingerprints=seen_fingerprints,
                client=client,
                adapter_factory=self.adapter_factory,
            )
        ranked = collection.budgeted.articles
        warnings = [
            f"source {source_id} failed: {error}"
            for source_id, error in sorted(collection.failures.items())
        ]
        warnings.extend(
            f"maintenance required: source {source_id} auto-paused after 7 failures"
            for source_id in collection.newly_auto_paused_source_ids
        )
        degraded = False
        try:
            summary, events = self.editorial_service.edit(
                ranked,
                self.settings.app.min_items,
                self.settings.app.max_items,
            )
        except Exception as error:
            degraded = True
            warnings.append(f"model chain failed: {error}")
            summary = "模型暂不可用，本期仅展示来源标题与摘要。"
            events = build_degraded_events(ranked, self.settings.app.max_items)
        events = select_diverse_events(events, self.settings.app.max_items)
        event_key = "|".join(
            sorted(candidate_id for event in events for candidate_id in event.candidate_ids)
        )
        run_hash = hashlib.sha256(event_key.encode()).hexdigest()[:8]
        run_id = f"{target_date.isoformat()}-{run_hash}"
        report = DailyReport(
            date=target_date,
            generated_at=now,
            run_id=run_id,
            daily_summary_zh=summary,
            events=events,
            degraded=degraded,
            warnings=warnings,
            source_coverage={
                "enabled": len(collection.enabled_source_ids),
                "fetched": collection.fetched_count,
                "normalized": collection.normalized_count,
                "filtered": collection.filtered_count,
                "ai_candidates": len(collection.budgeted.articles),
                "prompt_chars": collection.budgeted.prompt_chars,
                "estimated_input_tokens": (
                    collection.budgeted.estimated_input_tokens
                ),
                "failed_source_ids": sorted(collection.failures),
                "newly_auto_paused_source_ids": (
                    collection.newly_auto_paused_source_ids
                ),
            },
        )
        record = self.store.save_prepared(
            report,
            {item.fingerprint for item in ranked},
        )
        reports = self.store.load_reports()
        self.renderer.render(
            reports,
            self.settings.app.template,
            self.output_dir,
        )
        return record
```

- [ ] **Step 4: Write failing CLI tests**

Create `tests/test_cli.py`:

```python
import httpx
import respx

from ai_news_sniffer.cli import build_parser, verify_report_url


def test_cli_exposes_required_stage_commands() -> None:
    parser = build_parser()
    for argv in (
        ["sources", "list", "--profile", "light"],
        ["build", "--dry-run"],
        ["verify-url", "https://example.com/report/"],
        ["mark-published", "--run-id", "run-1", "--report-url", "https://example.com/r/"],
        ["notify", "--run-id", "run-1"],
        ["notify-failure", "--message", "deploy failed"],
    ):
        assert parser.parse_args(argv).command == argv[0]


def test_verify_report_url_accepts_expected_page_marker() -> None:
    with respx.mock:
        respx.get("https://example.com/report/").mock(
            return_value=httpx.Response(200, text="<h1>AI 每日情报</h1>")
        )
        verify_report_url("https://example.com/report/", httpx.Client())
```

Run:

```bash
pytest tests/test_cli.py -v
```

Expected: collection fails because `ai_news_sniffer.cli` does not exist.

- [ ] **Step 5: Implement CLI parsing and stage commands**

Create `src/ai_news_sniffer/cli.py`:

```python
import argparse
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from ai_news_sniffer.config import load_settings
from ai_news_sniffer.models import NotificationPayload, RunStatus
from ai_news_sniffer.notifications.base import build_channels, send_all
from ai_news_sniffer.providers.base import ProviderChain
from ai_news_sniffer.providers.editorial import EditorialService
from ai_news_sniffer.providers.openai_compatible import OpenAICompatibleProvider
from ai_news_sniffer.rendering.site import SiteRenderer
from ai_news_sniffer.source_cli import add_source_commands, run_source_command
from ai_news_sniffer.state import RuntimeStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-news-sniffer")
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--runtime-dir", type=Path, default=Path("runtime-data"))
    parser.add_argument("--output-dir", type=Path, default=Path("build/site"))
    parser.add_argument("--templates-dir", type=Path, default=Path("templates"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_source_commands(subparsers)
    build = subparsers.add_parser("build")
    build.add_argument("--target-date", type=date.fromisoformat)
    build.add_argument("--dry-run", action="store_true")
    build.add_argument(
        "--source-profile",
        choices=["light", "balanced", "full"],
    )
    build.add_argument("--include-sources", default="")
    build.add_argument("--exclude-sources", default="")
    build.add_argument("--max-ai-candidates", type=int)
    verify = subparsers.add_parser("verify-url")
    verify.add_argument("url")
    published = subparsers.add_parser("mark-published")
    published.add_argument("--run-id", required=True)
    published.add_argument("--report-url", required=True)
    notify = subparsers.add_parser("notify")
    notify.add_argument("--run-id", required=True)
    failure = subparsers.add_parser("notify-failure")
    failure.add_argument("--message", required=True)
    return parser


def verify_report_url(url: str, client: httpx.Client) -> None:
    last_error: Exception | None = None
    for attempt in range(1, 7):
        try:
            response = client.get(url, follow_redirects=True, timeout=30)
            response.raise_for_status()
            if "AI 每日情报" not in response.text:
                raise RuntimeError(
                    "published page does not contain the expected marker"
                )
            return
        except Exception as error:
            last_error = error
            if attempt < 6:
                time.sleep(10)
    raise RuntimeError(f"published report was not reachable: {type(last_error).__name__}")


def _provider_chain(settings) -> ProviderChain:
    by_id = {item.id: item for item in settings.providers.providers}
    return ProviderChain(
        [
            OpenAICompatibleProvider(by_id[provider_id])
            for provider_id in settings.providers.fallback_order
        ]
    )


def _source_ids(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "sources":
        return run_source_command(args)
    settings = load_settings(args.config_dir)
    store = RuntimeStore(args.runtime_dir)
    if args.command == "verify-url":
        with httpx.Client() as client:
            verify_report_url(args.url, client)
        return 0
    if args.command == "mark-published":
        with httpx.Client() as client:
            verify_report_url(args.report_url, client)
        store.mark_published(args.run_id, args.report_url)
        return 0
    if args.command == "build":
        from ai_news_sniffer.pipeline import Pipeline

        target_date = args.target_date or datetime.now(
            ZoneInfo(settings.app.timezone)
        ).date()
        prompt = Path("prompts/editorial.md").read_text(encoding="utf-8")
        pipeline = Pipeline(
            settings=settings,
            runtime_dir=args.runtime_dir,
            output_dir=args.output_dir,
            templates_root=args.templates_dir,
            editorial_service=EditorialService(_provider_chain(settings), prompt),
        )
        print(
            pipeline.build(
                target_date,
                args.dry_run,
                source_profile=args.source_profile,
                include_sources=_source_ids(args.include_sources),
                exclude_sources=_source_ids(args.exclude_sources),
                max_ai_candidates=args.max_ai_candidates or None,
            ).model_dump_json()
        )
        return 0
    if args.command == "notify-failure":
        payload = NotificationPayload(
            run_id=f"failure-{datetime.now(ZoneInfo(settings.app.timezone)):%Y%m%d%H%M%S}",
            date=datetime.now(ZoneInfo(settings.app.timezone)).date(),
            status=RunStatus.FAILED,
            title="AI 日报运行失败",
            daily_summary=args.message,
            top_items=[],
            report_url=settings.app.public_base_url,
            generated_at=datetime.now(ZoneInfo("UTC")),
        )
        with httpx.Client() as client:
            results = send_all(
                build_channels(settings.channels.channels, client),
                payload,
                args.message,
            )
        return 0 if any(result.success for result in results) else 2
    if args.command == "notify":
        record = store.load_run(args.run_id)
        if record.status is RunStatus.NOTIFIED:
            return 0
        if record.status not in {
            RunStatus.PUBLISHED,
            RunStatus.PARTIALLY_NOTIFIED,
        } or not record.report_url:
            raise RuntimeError("run must be published before notification")
        report = next(
            item for item in store.load_reports() if item.run_id == args.run_id
        )
        report.report_url = record.report_url
        payload = NotificationPayload(
            run_id=report.run_id,
            date=report.date,
            status=record.status,
            title=f"AI 日报 · {report.date}",
            daily_summary=report.daily_summary_zh,
            top_items=report.events[:3],
            report_url=record.report_url,
            generated_at=report.generated_at,
        )
        message = SiteRenderer(args.templates_dir).render_notification(
            report,
            settings.app.template,
        )
        previous_successes = [
            result for result in record.channel_results if result.success
        ]
        failed_ids = {
            result.channel_id for result in record.channel_results if not result.success
        }
        channel_configs = settings.channels.channels
        if failed_ids:
            channel_configs = [
                config for config in channel_configs if config.id in failed_ids
            ]
        with httpx.Client() as client:
            results = previous_successes + send_all(
                build_channels(channel_configs, client),
                payload,
                message,
            )
        store.mark_notified(args.run_id, results)
        return 0 if all(result.success for result in results) else 2
    raise AssertionError("unreachable command")
```

Create `src/ai_news_sniffer/__main__.py`:

```python
from ai_news_sniffer.cli import main

raise SystemExit(main())
```

- [ ] **Step 6: Run pipeline and CLI tests, then commit**

Run:

```bash
pytest tests/test_pipeline.py tests/test_cli.py -v
pytest -q
ruff check src tests
```

Expected: both offline pipeline tests and all CLI parsing tests pass; full suite and Ruff exit 0.

Commit:

```bash
git add src/ai_news_sniffer tests/test_pipeline.py tests/test_cli.py tests/conftest.py
git commit -m "feat: orchestrate digest stages through cli"
```

---

### Task 10: GitHub Actions, Pages, Runtime Branch, and Operator Documentation

> Reuse the source-strategy plan's `source_profile`, `include_sources`, `exclude_sources`, and `max_ai_candidates` inputs. Persist source health, source-run summaries, and candidate-source records on `runtime-data`.

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/daily-digest.yml`
- Modify: `README.md`
- Modify: `.gitignore`
- Test: `tests/test_workflow_contract.py`

**Interfaces:**
- Consumes: CLI commands from Task 9 and repository secrets.
- Produces: CI checks, scheduled/manual daily workflow, `runtime-data` persistence, Pages deployment, notification stage, and operator setup/runbook.

- [ ] **Step 1: Write a failing workflow contract test**

Create `tests/test_workflow_contract.py`:

```python
import re
from pathlib import Path

import yaml


class GithubActionsLoader(yaml.SafeLoader):
    pass


for first_character, resolvers in GithubActionsLoader.yaml_implicit_resolvers.items():
    GithubActionsLoader.yaml_implicit_resolvers[first_character] = [
        resolver
        for resolver in resolvers
        if resolver[0] != "tag:yaml.org,2002:bool"
    ]
GithubActionsLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


def load_workflow(name: str) -> dict:
    path = Path(".github/workflows") / name
    return yaml.load(path.read_text(encoding="utf-8"), Loader=GithubActionsLoader)


def test_daily_workflow_has_schedule_manual_inputs_and_concurrency() -> None:
    workflow = load_workflow("daily-digest.yml")
    assert workflow["on"]["schedule"][0]["cron"] == "0 13 * * *"
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {
        "dry_run",
        "publish",
        "notify",
        "target_date",
        "source_profile",
        "include_sources",
        "exclude_sources",
        "max_ai_candidates",
    }
    assert inputs["source_profile"]["default"] == "balanced"
    assert inputs["max_ai_candidates"]["default"] == "0"
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_pages_job_has_required_permissions() -> None:
    workflow = load_workflow("daily-digest.yml")
    permissions = workflow["jobs"]["deploy"]["permissions"]
    assert permissions["pages"] == "write"
    assert permissions["id-token"] == "write"
```

- [ ] **Step 2: Run the contract test to prove workflows are missing**

Run:

```bash
pytest tests/test_workflow_contract.py -v
```

Expected: fails with `FileNotFoundError` for `.github/workflows/daily-digest.yml`.

- [ ] **Step 3: Create continuous integration**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
          cache: pip
      - run: python -m pip install -e '.[dev]'
      - run: ruff check src tests
      - run: pytest --cov=ai_news_sniffer --cov-report=term-missing
```

- [ ] **Step 4: Create the scheduled/manual build and Pages workflow**

Create `.github/workflows/daily-digest.yml`:

```yaml
name: Daily AI Digest

on:
  schedule:
    - cron: "0 13 * * *"
  workflow_dispatch:
    inputs:
      dry_run:
        description: Generate preview only
        type: boolean
        default: true
      publish:
        description: Deploy to GitHub Pages
        type: boolean
        default: false
      notify:
        description: Send enabled notifications after publish
        type: boolean
        default: false
      target_date:
        description: Optional YYYY-MM-DD date
        type: string
        default: ""
      source_profile:
        description: Source coverage profile
        type: choice
        options: [light, balanced, full]
        default: balanced
      include_sources:
        description: Optional comma-separated allowlist
        type: string
        default: ""
      exclude_sources:
        description: Optional comma-separated blocklist
        type: string
        default: ""
      max_ai_candidates:
        description: Candidate cap; 0 uses the selected profile default
        type: string
        default: "0"

concurrency:
  group: daily-ai-digest
  cancel-in-progress: false

env:
  PYTHON_VERSION: "3.12"
  PUBLIC_BASE_URL: ${{ vars.PUBLIC_BASE_URL }}

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    outputs:
      run_id: ${{ steps.build.outputs.run_id }}
      report_url: ${{ steps.build.outputs.report_url }}
      should_publish: ${{ steps.mode.outputs.should_publish }}
      should_notify: ${{ steps.mode.outputs.should_notify }}
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip
      - run: python -m pip install -e .
      - name: Resolve mode
        id: mode
        shell: bash
        run: |
          if [[ "${{ github.event_name }}" == "schedule" ]]; then
            echo "dry_run=false" >> "$GITHUB_OUTPUT"
            echo "should_publish=true" >> "$GITHUB_OUTPUT"
            echo "should_notify=true" >> "$GITHUB_OUTPUT"
          else
            if [[ "${{ inputs.notify }}" == "true" && "${{ inputs.publish }}" != "true" ]]; then
              echo "notify requires publish" >&2
              exit 2
            fi
            if [[ "${{ inputs.dry_run }}" == "true" && ( "${{ inputs.publish }}" == "true" || "${{ inputs.notify }}" == "true" ) ]]; then
              echo "dry_run cannot publish or notify" >&2
              exit 2
            fi
            echo "dry_run=${{ inputs.dry_run }}" >> "$GITHUB_OUTPUT"
            echo "should_publish=${{ inputs.publish }}" >> "$GITHUB_OUTPUT"
            echo "should_notify=${{ inputs.notify }}" >> "$GITHUB_OUTPUT"
          fi
      - name: Check out runtime data
        shell: bash
        run: |
          git fetch origin runtime-data || true
          if git show-ref --verify --quiet refs/remotes/origin/runtime-data; then
            git worktree add runtime-data origin/runtime-data
          else
            git worktree add --detach runtime-data
            cd runtime-data
            git switch --orphan runtime-data
            git rm -rf .
            mkdir -p reports runs
          fi
      - name: Build digest
        id: build
        shell: bash
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
        run: |
          TARGET_DATE="${{ inputs.target_date }}"
          DATE_ARGS=()
          if [[ -n "$TARGET_DATE" ]]; then DATE_ARGS=(--target-date "$TARGET_DATE"); fi
          DRY_ARGS=()
          if [[ "${{ steps.mode.outputs.dry_run }}" == "true" ]]; then DRY_ARGS=(--dry-run); fi
          SOURCE_PROFILE="${{ inputs.source_profile || 'balanced' }}"
          INCLUDE_SOURCES="${{ inputs.include_sources }}"
          EXCLUDE_SOURCES="${{ inputs.exclude_sources }}"
          MAX_AI_CANDIDATES="${{ inputs.max_ai_candidates || '0' }}"
          OUTPUT_FILE="$RUNNER_TEMP/build-output.json"
          python -m ai_news_sniffer \
            --runtime-dir runtime-data \
            --output-dir build/site \
            build \
            --source-profile "$SOURCE_PROFILE" \
            --include-sources "$INCLUDE_SOURCES" \
            --exclude-sources "$EXCLUDE_SOURCES" \
            --max-ai-candidates "$MAX_AI_CANDIDATES" \
            "${DATE_ARGS[@]}" "${DRY_ARGS[@]}" | tee "$OUTPUT_FILE"
          RUN_ID="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_id"])' "$OUTPUT_FILE")"
          REPORT_DATE="${RUN_ID:0:10}"
          REPORT_PATH="${REPORT_DATE:0:4}/${REPORT_DATE:5:2}/${REPORT_DATE:8:2}"
          REPORT_URL="${{ vars.PUBLIC_BASE_URL }}/$REPORT_PATH/"
          echo "run_id=$RUN_ID" >> "$GITHUB_OUTPUT"
          echo "report_url=$REPORT_URL" >> "$GITHUB_OUTPUT"
      - name: Persist prepared runtime state
        if: steps.mode.outputs.dry_run != 'true'
        working-directory: runtime-data
        shell: bash
        run: |
          git config user.name github-actions[bot]
          git config user.email 41898282+github-actions[bot]@users.noreply.github.com
          git add reports runs source-health.json source-runs candidate-sources.json
          git commit -m "data: prepare ${{ steps.build.outputs.run_id }}" || true
          git push origin HEAD:runtime-data
      - name: Upload dry-run preview
        if: steps.mode.outputs.dry_run == 'true'
        uses: actions/upload-artifact@v7
        with:
          name: ai-digest-preview-${{ steps.build.outputs.run_id }}
          path: build/site
          retention-days: 7
      - name: Upload Pages artifact
        if: steps.mode.outputs.should_publish == 'true'
        uses: actions/upload-pages-artifact@v4
        with:
          path: build/site

  deploy:
    if: needs.build.outputs.should_publish == 'true'
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy Pages artifact
        id: deployment
        uses: actions/deploy-pages@v4

  finalize:
    if: needs.build.outputs.should_publish == 'true'
    needs: [build, deploy]
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip
      - run: python -m pip install -e .
      - name: Check out runtime data
        run: |
          git fetch origin runtime-data
          git worktree add runtime-data origin/runtime-data
      - name: Verify published URL and mark published
        run: |
          python -m ai_news_sniffer \
            --runtime-dir runtime-data \
            mark-published \
            --run-id "${{ needs.build.outputs.run_id }}" \
            --report-url "${{ needs.build.outputs.report_url }}"
      - name: Persist published state
        working-directory: runtime-data
        run: |
          git config user.name github-actions[bot]
          git config user.email 41898282+github-actions[bot]@users.noreply.github.com
          git add latest.json runs seen_fingerprints.json
          git commit -m "data: publish ${{ needs.build.outputs.run_id }}" || true
          git push origin HEAD:runtime-data
      - name: Send notifications
        id: notify
        if: needs.build.outputs.should_notify == 'true'
        continue-on-error: true
        env:
          MEOW_NICKNAME: ${{ secrets.MEOW_NICKNAME }}
          WECOM_WEBHOOK_URL: ${{ secrets.WECOM_WEBHOOK_URL }}
          GENERIC_WEBHOOK_URL: ${{ secrets.GENERIC_WEBHOOK_URL }}
        run: |
          python -m ai_news_sniffer \
            --runtime-dir runtime-data \
            notify --run-id "${{ needs.build.outputs.run_id }}"
      - name: Persist notification results
        if: always() && needs.build.outputs.should_notify == 'true'
        working-directory: runtime-data
        run: |
          git add runs
          git commit -m "data: notify ${{ needs.build.outputs.run_id }}" || true
          git push origin HEAD:runtime-data
      - name: Fail after persisting partial notification status
        if: steps.notify.outcome == 'failure'
        run: exit 2

  failure-alert:
    if: ${{ always() && (needs.build.result == 'failure' || needs.deploy.result == 'failure' || needs.finalize.result == 'failure') }}
    needs: [build, deploy, finalize]
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip
      - run: python -m pip install -e .
      - name: Send failure alert through available channels
        env:
          MEOW_NICKNAME: ${{ secrets.MEOW_NICKNAME }}
          WECOM_WEBHOOK_URL: ${{ secrets.WECOM_WEBHOOK_URL }}
          GENERIC_WEBHOOK_URL: ${{ secrets.GENERIC_WEBHOOK_URL }}
        run: |
          python -m ai_news_sniffer notify-failure \
            --message "Daily AI Digest workflow failed: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
```

- [ ] **Step 5: Verify the exact CLI/workflow argument contract**

Append to `tests/test_cli.py`:

```python
from datetime import date
from pathlib import Path


def test_cli_accepts_workflow_build_argument_order() -> None:
    args = build_parser().parse_args(
        [
            "--runtime-dir",
            "runtime-data",
            "--output-dir",
            "build/site",
            "build",
            "--source-profile",
            "balanced",
            "--include-sources",
            "openai-news,anthropic-news",
            "--exclude-sources",
            "hacker-news",
            "--max-ai-candidates",
            "0",
            "--target-date",
            "2026-07-23",
            "--dry-run",
        ]
    )
    assert args.runtime_dir == Path("runtime-data")
    assert args.output_dir == Path("build/site")
    assert args.target_date == date(2026, 7, 23)
    assert args.dry_run is True
    assert args.source_profile == "balanced"
    assert args.include_sources == "openai-news,anthropic-news"
    assert args.exclude_sources == "hacker-news"
    assert args.max_ai_candidates == 0
```

Run:

```bash
pytest tests/test_cli.py::test_cli_accepts_workflow_build_argument_order -v
```

Expected: PASS.

- [ ] **Step 6: Write the operator runbook**

Create `README.md` with these exact sections and commands:

````markdown
# AI News Sniffer

Daily Chinese AI-news digest generated from free public sources.

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Export the required values from `.env` in your shell; the application does not
load `.env` automatically in production.

## Test

```bash
ruff check src tests
pytest
```

## Dry run

```bash
python -m ai_news_sniffer \
  --runtime-dir .local/runtime-data \
  --output-dir build/site \
  build --target-date 2026-07-23 --dry-run
```

Open `build/site/index.html` locally. A dry run does not update fingerprints,
publish Pages, or send notifications.

## Source configuration

`config/sources.yaml` contains the reviewed 35-source whitelist and all
source/group switches. `light`, `balanced`, and `full` resolve to 12, 25, and
35 sources with default AI candidate caps of 20, 30, and 40. Inspect effective
selection without network access:

```bash
ai-news-sniffer sources list --profile balanced
ai-news-sniffer sources candidates
```

For an intentional live check, use `ai-news-sniffer sources test SOURCE_ID` or
run the manual Source audit workflow. A successful audit clears runtime
auto-pause state but never changes `config/sources.yaml`.

## GitHub configuration

Create repository secrets `DEEPSEEK_API_KEY` and `MEOW_NICKNAME`. Add
`WECOM_WEBHOOK_URL` and `GENERIC_WEBHOOK_URL` only when those channels are
enabled. Create repository variable `PUBLIC_BASE_URL` without a trailing slash.
Enable GitHub Pages with GitHub Actions as its source.

The first successful non-dry run creates the `runtime-data` branch. Protect
`main`; allow the workflow token to write repository contents and Pages.

## Manual run

Open Actions → Daily AI Digest → Run workflow. Keep `dry_run=true` for preview.
For a real run set `dry_run=false`, `publish=true`, and set `notify=true` only
when notifications should be sent. `source_profile` defaults to `balanced`;
`include_sources` and `exclude_sources` accept comma-separated source IDs.
`max_ai_candidates=0` uses the selected profile's default budget.

## Custom domain

Verify the domain in GitHub, configure it in repository Pages settings, and use
a subdomain CNAME pointing to `<account>.github.io` or the documented apex
records. Do not use wildcard DNS. Set `PUBLIC_BASE_URL` to the final HTTPS URL.

## Templates

Copy `templates/default` to `templates/<new-name>`, edit the Jinja2/CSS files,
then set `template: <new-name>` in `config/app.yaml`. A later run rebuilds all
stored report JSON through the selected template.

## Provider extension

Add an entry to `config/providers.yaml`, put its key in a new GitHub Secret,
and add the provider ID to `fallback_order`. Use
`api_style: openai_chat_completions` for compatible DeepSeek, Kimi, MiniMax,
or other endpoints.

## Failure behavior

Source failures are logged and isolated. Provider failure uses the configured
fallback order, then creates a clearly labeled source-summary digest. Pages are
verified before notification. Channel failures are recorded independently in
`runtime-data/runs/`. A source is marked degraded after three consecutive
failures and auto-paused after seven; the next successful notification includes
a maintenance reminder. Use the manual Source audit workflow to test and clear
an auto-pause only after a real network audit succeeds.
````

Add these lines to `.gitignore`:

```gitignore
.venv/
.local/
build/
runtime-data/
```

- [ ] **Step 7: Run full verification**

Run:

```bash
pytest tests/test_workflow_contract.py -v
ruff check src tests
pytest --cov=ai_news_sniffer --cov-report=term-missing
python -m ai_news_sniffer --help
```

Expected:

- Workflow tests pass.
- Ruff exits 0.
- Full pytest suite has zero failures.
- CLI help lists `build`, `verify-url`, `mark-published`, `notify`, and
  `notify-failure`.

- [ ] **Step 8: Perform a fixture-backed end-to-end dry run**

Run the pipeline test that replaces source/model network access with fixtures:

```bash
pytest tests/test_pipeline.py -v
```

Expected: both tests pass; together they assert dated HTML exists, runtime status is
`prepared`, fixture adapters avoid network access, and dry-run does not create the
fingerprint file.

- [ ] **Step 9: Commit the automation and runbook**

```bash
git add .github README.md .gitignore tests/test_workflow_contract.py
git commit -m "ci: schedule publish and notify daily digest"
```

---

## Spec Coverage Matrix

| Design specification area | Implementation tasks |
|---|---|
| Goals, daily cadence, manual trigger | Tasks 9–10 |
| Free source collection, source switches, profiles, and normalization | Source-strategy Tasks 1–4 |
| Deterministic deduplication, 100-point scoring, and confirmation | Source-strategy Task 5 |
| Source health, auto-pause, discovery, audit, and AI budgets | Source-strategy Tasks 2, 6–7 |
| Runtime data, 48-hour window, idempotent reruns | Tasks 4 and 9–10 |
| Provider fallback, semantic grouping, Chinese editorial output | Tasks 5–6 |
| Mobile HTML, history, `noindex`, repository templates | Task 7 |
| MeoW, WeCom, generic webhook, channel isolation | Task 8 |
| Failure degradation, publish verification, failure alert | Tasks 5–6 and 8–10 |
| Secrets, URL/error redaction, template sandbox | Source-strategy Task 1 and main Tasks 7–8 and 10 |
| Unit, fixture, integration, workflow, and visual checks | Every task; final gate below |
| GitHub Pages and custom-domain operations | Task 10 |
| Explicit v1 non-goals | Global Constraints and the absence of admin, auth, paid search, realtime, and native-app tasks |

## Implementation Completion Gate

Before calling the feature complete:

1. Run `ruff check src tests`.
2. Run `pytest --cov=ai_news_sniffer --cov-report=term-missing`.
3. Run one fixture-backed `dry-run` and visually inspect `build/site/index.html` at a mobile viewport.
4. Run the GitHub workflow manually with `dry_run=true`; download and inspect its preview artifact.
5. Add real repository secrets and `PUBLIC_BASE_URL`, then run with `publish=true`, `notify=false`.
6. Verify the dated custom-domain URL returns the expected report marker.
7. Run with `publish=true`, `notify=true`; confirm MeoW receives the title, summary, three headlines, and working link.
8. Enable WeCom and generic webhook one at a time and confirm a failure in either does not suppress MeoW.
9. Confirm `runtime-data` contains report JSON, fingerprints, a `published`/`notified` run record, and no secret values.

## Primary References

- Design specification: `docs/superpowers/specs/2026-07-23-ai-news-sniffer-design.md`
- DeepSeek OpenAI-compatible API and current model names: https://api-docs.deepseek.com/quick_start/pricing-details-usd/
- DeepSeek JSON output requirements: https://api-docs.deepseek.com/guides/json_mode/
- OpenAI-compatible Python client package: https://pypi.org/project/openai/
- GitHub Pages custom workflow: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- GitHub Actions workflow triggers: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
- GitHub Pages custom domains: https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/about-custom-domains-and-github-pages
