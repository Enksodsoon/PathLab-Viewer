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
    for forbidden in ("answerKey", "feedback", "teacherNotes"):
        assert forbidden not in learner
    assert first.learner_manifest["sections"][0]["items"][0]["routing"]


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


def test_v2_contract_accepts_bounded_question_media_and_rejects_unsafe_sources() -> None:
    document = v2_document()
    item = document["sections"][0]["items"][0]  # type: ignore[index]
    item["media"] = {
        "kind": "uploaded-image",
        "assetPath": "data:image/png;base64,aW1hZ2U=",
        "fileName": "teaching-image.png",
        "alt": "Teaching image",
    }
    item["mediaItems"] = [
        {
            "kind": "uploaded-image",
            "assetPath": "data:image/webp;base64,UklGRg==",
            "fileName": "second-field.webp",
            "alt": "Second teaching field",
        }
    ]
    compiled = compile_assessment_v2(document)
    assert compiled.learner_manifest["sections"][0]["items"][0]["media"][  # type: ignore[index]
        "assetPath"
    ].startswith("data:image/png;base64,")
    assert compiled.learner_manifest["sections"][0]["items"][0]["mediaItems"][0][  # type: ignore[index]
        "fileName"
    ] == "second-field.webp"

    item["media"] = {
        "kind": "uploaded-image",
        "assetPath": "file:///private/teaching-image.png",
    }
    with pytest.raises(AssessmentContractError, match="ASSESSMENT_MEDIA_INVALID"):
        compile_assessment_v2(document)


def test_v2_contract_accepts_ten_media_items_and_rejects_an_eleventh() -> None:
    document = v2_document()
    item = document["sections"][0]["items"][0]  # type: ignore[index]

    def image(index: int) -> dict[str, str]:
        return {
            "kind": "uploaded-image",
            "assetPath": "data:image/png;base64,aW1hZ2U=",
            "fileName": f"teaching-image-{index}.png",
            "alt": f"Teaching image {index}",
        }

    item["media"] = image(1)
    item["mediaItems"] = [image(index) for index in range(2, 11)]
    compiled = compile_assessment_v2(document)
    compiled_item = compiled.learner_manifest["sections"][0]["items"][0]  # type: ignore[index]
    assert len(compiled_item["mediaItems"]) == 9

    item["mediaItems"].append(image(11))
    with pytest.raises(AssessmentContractError, match="ASSESSMENT_MEDIA_LIMIT"):
        compile_assessment_v2(document)


def test_v2_contract_accepts_bounded_answer_choice_media() -> None:
    document = v2_document()
    item = document["sections"][0]["items"][0]  # type: ignore[index]
    item["options"][0]["media"] = {
        "kind": "slide-thumbnail",
        "slideId": "slide-a",
        "assetPath": "/tiles/public-slide-a/v1/thumbnail.jpg?assessment-preview=1",
        "alt": "Representative gland pattern",
    }
    item["options"][0]["mediaItems"] = [
        {
            "kind": "uploaded-image",
            "assetPath": "data:image/png;base64,aW1hZ2Uy",
            "fileName": "detail.png",
        },
        {
            "kind": "uploaded-image",
            "assetPath": "data:image/webp;base64,aW1hZ2Uz",
            "fileName": "overview.webp",
        },
    ]
    item["options"][1]["media"] = {
        "kind": "uploaded-image",
        "assetPath": "data:image/png;base64,aW1hZ2U=",
        "fileName": "reactive.png",
    }

    compiled = compile_assessment_v2(document)
    compiled_options = compiled.learner_manifest["sections"][0]["items"][0]["options"]  # type: ignore[index]
    assert compiled_options[0]["media"]["slideId"] == "slide-a"
    assert len(compiled_options[0]["mediaItems"]) == 2
    assert compiled_options[1]["media"]["fileName"] == "reactive.png"

    item["options"][0]["media"]["assetPath"] = "/tiles/../private/thumbnail.jpg"
    with pytest.raises(AssessmentContractError, match="ASSESSMENT_MEDIA_INVALID"):
        compile_assessment_v2(document)

    item["options"][0]["media"]["assetPath"] = "/tiles/public-slide-a/v1/thumbnail.jpg"
    item["options"][0]["mediaItems"].append(item["options"][0]["mediaItems"][0])
    with pytest.raises(AssessmentContractError, match="ASSESSMENT_MEDIA_LIMIT"):
        compile_assessment_v2(document)


def test_v2_contract_accepts_bounded_wsi_capture_and_annotations() -> None:
    document = v2_document()
    item = document["sections"][0]["items"][0]  # type: ignore[index]
    item["media"] = {
        "kind": "slide-thumbnail",
        "slideId": "slide-a",
        "capture": {
            "kind": "rectangle",
            "x": 0.15,
            "y": 0.2,
            "width": 0.4,
            "height": 0.3,
        },
        "capturedImage": {
            "assetPath": "data:image/webp;base64,UklGRg==",
            "width": 1200,
            "height": 800,
            "bytes": 256000,
        },
        "marks": [
            {"kind": "point", "x": 0.25, "y": 0.35, "label": "Tumour focus"},
            {
                "kind": "rectangle",
                "x": 0.3,
                "y": 0.3,
                "width": 0.1,
                "height": 0.1,
            },
            {
                "kind": "freehand",
                "points": [
                    {"x": 0.22, "y": 0.25},
                    {"x": 0.28, "y": 0.3},
                    {"x": 0.32, "y": 0.27},
                ],
                "label": "Irregular boundary",
            },
        ],
    }

    compiled = compile_assessment_v2(document)
    media = compiled.learner_manifest["sections"][0]["items"][0]["media"]  # type: ignore[index]
    assert media["capture"]["width"] == 0.4
    assert media["capturedImage"]["width"] == 1200
    assert len(media["marks"]) == 3
    assert media["marks"][0]["label"] == "Tumour focus"
    assert media["marks"][2]["points"][1]["x"] == 0.28

    item["media"]["capture"]["width"] = 0.95
    with pytest.raises(AssessmentContractError, match="ASSESSMENT_MEDIA_INVALID"):
        compile_assessment_v2(document)

    item["media"]["marks"][2]["points"] = [
        {"x": 0.22, "y": 0.25},
        {"x": 0.28, "y": 0.3},
    ]
    item["media"]["capturedImage"]["width"] = 1800
    with pytest.raises(AssessmentContractError, match="ASSESSMENT_MEDIA_INVALID"):
        compile_assessment_v2(document)

    item["media"]["capture"]["width"] = 0.4
    item["media"]["marks"][2]["points"] = [{"x": 0.2, "y": 0.2}]
    with pytest.raises(AssessmentContractError, match="ASSESSMENT_MEDIA_INVALID"):
        compile_assessment_v2(document)


def test_branching_and_order_are_stable_and_remove_unreachable_responses() -> None:
    document = compile_assessment_v2(v2_document()).definition
    responses = {"item-pattern": {"optionId": "option-lepidic"}, "item-help": {"seen": True}}

    assert reachable_section_ids(document, responses) == ["section-intro", "section-rating"]
    assert active_responses(document, responses) == {"item-pattern": {"optionId": "option-lepidic"}}
    assert deterministic_order(["b", "a", "c"], "stable-seed") == deterministic_order(
        ["c", "b", "a"], "stable-seed"
    )
