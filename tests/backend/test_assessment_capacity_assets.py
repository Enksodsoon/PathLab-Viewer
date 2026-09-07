import json
from pathlib import Path


def test_assessment_capacity_workflow_is_manual_protected_and_default_off() -> None:
    workflow = Path(".github/workflows/assessment-capacity.yml").read_text(encoding="utf-8")
    script = Path("tests/load/assessment-500.js").read_text(encoding="utf-8")
    config = Path("server/wsi_viewer/config.py").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "environment: assessment-capacity" in workflow
    assert "assessment_enabled: bool = False" in config
    assert "PATHLAB_ASSESSMENT_ENABLED" not in workflow
    assert "matrix:" in workflow and "shard: [1, 2, 3, 4, 5]" in workflow
    assert "executor: 'per-vu-iterations'" in script
    assert "vus: 100" in script and "iterations: 1" in script
    assert "HOLD_SECONDS = 60 * 60" in script
    assert "AUTOSAVES_PER_STUDENT = 20" in script
    assert "fail(" in script


def test_assessment_evidence_schema_keeps_certification_states_distinct() -> None:
    schema = json.loads(
        Path("tests/load/assessment-evidence.schema.json").read_text(encoding="utf-8")
    )
    assert schema["properties"]["status"]["enum"] == [
        "SUCCESS",
        "PARTIAL",
        "NEGATIVE",
        "NOT_EVALUABLE",
    ]
    assert "releaseSha" in schema["required"]
    assert "database" in schema["required"]
    assert "cleanup" in schema["required"]
