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
