from copy import deepcopy

import pytest
from wsi_viewer.assessment_branching import (
    active_responses,
    deterministic_order,
    reachable_section_ids,
)
from wsi_viewer.assessment_contract import AssessmentContractError
from wsi_viewer.assessment_contract_v2 import (
    V2_SCHEMA,
    compile_assessment_v2,
    document_schema,
    flatten_v2_items,
)


def v2_document() -> dict[str, object]:
    return {
        "schema": V2_SCHEMA,
        "title": "Thoracic pathology",
        "description": "A bounded synthetic assessment.",
        "presentation": {"preset": "standard", "showProgress": True},
        "sections": [
            {
                "id": "section-intro",
                "title": "Screening",
                "items": [
                    {
                        "id": "item-pattern",
                        "type": "dropdown",
                        "prompt": "Select the growth pattern",
                        "points": "1",
                        "required": True,
                        "options": [
                            {"id": "option-lepidic", "label": "Lepidic"},
                            {"id": "option-solid", "label": "Solid"},
                        ],
                        "answerKey": {"optionIds": ["option-lepidic"]},
                        "feedback": {
                            "correct": "The pattern is preserved.",
                            "incorrect": "Review the alveolar architecture.",
                        },
                        "routing": {
                            "rules": [
                                {
                                    "when": {
                                        "operator": "equals",
                                        "optionId": "option-solid",
                                    },
                                    "goToSectionId": "section-remediation",
                                }
                            ],
                            "defaultSectionId": "section-rating",
                        },
                    }
                ],
            },
            {
                "id": "section-remediation",
                "title": "Review",
                "items": [
                    {
                        "id": "item-help",
                        "type": "section-information",
                        "prompt": "Review the architecture before continuing.",
                    }
                ],
            },
            {
                "id": "section-rating",
                "title": "Confidence",
                "items": [
                    {
                        "id": "item-confidence",
                        "type": "rating",
                        "prompt": "How confident are you?",
                        "points": "0",
                        "required": True,
                        "rating": {"min": 1, "max": 5, "style": "stars"},
                        "validation": {
                            "required": True,
                            "message": "Choose a confidence rating.",
                        },
                    }
                ],
            },
        ],
        "settings": {"mode": "formative", "shuffleQuestions": True},
    }


def test_schema_detection_never_infers_v2_from_sections() -> None:
    assert document_schema({"title": "Legacy", "items": []}) == "pathlab.assessment/1"
    assert document_schema({"title": "Ambiguous", "sections": []}) == "pathlab.assessment/1"
    assert document_schema(v2_document()) == V2_SCHEMA


def test_v2_compile_is_deterministic_bounded_and_privacy_stripped() -> None:
    first = compile_assessment_v2(v2_document())
    second = compile_assessment_v2(deepcopy(v2_document()))

    assert first.checksum == second.checksum
    assert [item["position"] for item in flatten_v2_items(first.definition)] == [0, 1, 2]
    learner = repr(first.learner_manifest)
    for forbidden in ("answerKey", "feedback", "routing", "teacherNotes"):
        assert forbidden not in learner


@pytest.mark.parametrize("style", ["numbers", "stars", "hearts", "thumbs-up"])
def test_v2_rating_contract_accepts_approved_styles(style: str) -> None:
    document = v2_document()
    document["sections"][2]["items"][0]["rating"] = {  # type: ignore[index]
        "min": 1,
        "max": 10,
        "style": style,
    }
    compile_assessment_v2(document)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("sections", [], "ASSESSMENT_SECTIONS_REQUIRED"),
        ("title", "x" * 201, "ASSESSMENT_TITLE_LIMIT"),
    ],
)
def test_v2_contract_rejects_required_and_bounded_fields(
    field: str, value: object, code: str
) -> None:
    document = v2_document()
    document[field] = value
    with pytest.raises(AssessmentContractError, match=code):
        compile_assessment_v2(document)


def test_v2_contract_rejects_invalid_rating_and_dangling_route() -> None:
    document = v2_document()
    document["sections"][2]["items"][0]["rating"] = {  # type: ignore[index]
        "min": 0,
        "max": 11,
        "style": "emoji",
    }
    with pytest.raises(AssessmentContractError, match="ASSESSMENT_RATING_INVALID"):
        compile_assessment_v2(document)

    document = v2_document()
    document["sections"][0]["items"][0]["routing"]["defaultSectionId"] = (  # type: ignore[index]
        "missing"
    )
    with pytest.raises(AssessmentContractError, match="ASSESSMENT_ROUTE_INVALID"):
        compile_assessment_v2(document)


def test_branching_and_order_are_stable_and_remove_unreachable_responses() -> None:
    document = compile_assessment_v2(v2_document()).definition
    responses = {"item-pattern": {"optionId": "option-lepidic"}, "item-help": {"seen": True}}

    assert reachable_section_ids(document, responses) == ["section-intro", "section-rating"]
    assert active_responses(document, responses) == {"item-pattern": {"optionId": "option-lepidic"}}
    assert deterministic_order(["b", "a", "c"], "stable-seed") == deterministic_order(
        ["c", "b", "a"], "stable-seed"
    )
