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
