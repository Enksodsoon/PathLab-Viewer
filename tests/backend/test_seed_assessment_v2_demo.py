from pathlib import Path
from runpy import run_path

from wsi_viewer.assessment_contract_v2 import compile_assessment_v2, flatten_v2_items

DEMO_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_assessment_v2_demo.py"


def test_teacher_studio_demo_exercises_v2_contract() -> None:
    demo_document = run_path(str(DEMO_SCRIPT))["demo_document"]
    compiled = compile_assessment_v2(demo_document("privacy-passed-slide"))
    items = flatten_v2_items(compiled.definition)
    assert len(compiled.definition["sections"]) == 4
    assert {item["type"] for item in items} >= {
        "multiple-choice",
        "checkboxes",
        "dropdown",
        "rating",
        "short-answer",
        "paragraph",
        "diagnostic-field",
        "section-information",
    }
    assert {item["rating"]["style"] for item in items if item["type"] == "rating"} == {
        "numbers",
        "stars",
        "hearts",
        "thumbs-up",
    }
    assert items[0]["routing"]["defaultSectionId"] == "section-application"
