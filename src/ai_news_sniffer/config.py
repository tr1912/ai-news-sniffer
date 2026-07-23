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
