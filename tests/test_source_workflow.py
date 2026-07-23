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
