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
