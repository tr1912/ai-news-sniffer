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
    assert workflow["on"]["schedule"][0]["cron"] == "0 11 * * *"
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
