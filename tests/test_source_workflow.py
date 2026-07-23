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


def test_source_audit_workflow_retains_artifact_without_publish_or_notify() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/source-audit.yml").read_text(encoding="utf-8")
    )
    steps = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]

    assert any(
        step.get("uses", "").startswith("actions/upload-artifact@")
        and step.get("with", {}).get("name") == "source-audit"
        and step.get("with", {}).get("path") == "runtime-data/"
        for step in steps
    )

    step_commands = [
        str(step.get(field, "")).casefold()
        for step in steps
        for field in ("uses", "run")
    ]
    forbidden = (
        "deploy-pages",
        "upload-pages-artifact",
        "notify",
        "notification",
        "meow",
        "wecom",
        "webhook",
    )
    for value in step_commands:
        assert not any(token in value for token in forbidden)
