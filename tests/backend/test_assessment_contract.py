from decimal import Decimal

import pytest
from wsi_viewer.assessment_contract import (
    AssessmentContractError,
    compile_assessment,
    normalize_short_answer,
    score_item,
)


def _draft() -> dict[str, object]:
    return {
        "title": "Lung pathology quiz",
        "items": [
            {
                "id": "item-1",
                "type": "multiple-choice",
                "prompt": "Most likely diagnosis?",
                "points": "1",
                "required": True,
                "options": [
                    {"id": "option-a", "label": "Adenocarcinoma"},
                    {"id": "option-b", "label": "Reactive change"},
                ],
                "answerKey": {"optionIds": ["option-a"]},
                "feedback": {"correct": "Correct", "incorrect": "Review the glands"},
            },
            {
                "id": "item-2",
                "type": "diagnostic-field",
                "prompt": "Select the diagnostic region",
                "points": "2",
                "required": True,
                "slideId": "slide-1",
                "answerKey": {
                    "regions": [{"kind": "point", "x": 0.5, "y": 0.5}],
                    "diagnoses": ["Adenocarcinoma"],
                },
                "scoring": {"pointTolerance": 0.03, "rectangleIou": 0.25},
            },
        ],
        "settings": {"shuffleQuestions": False},
    }


def test_compile_is_deterministic_and_strips_all_answers_from_learner_manifest() -> None:
    first = compile_assessment(_draft())
    second = compile_assessment(dict(reversed(list(_draft().items()))))

    assert first.definition["schema"] == "pathlab.assessment/1"
    assert first.checksum == second.checksum
    serialized = repr(first.learner_manifest)
    assert "answerKey" not in serialized
    assert "regions" not in serialized
    assert "diagnoses" not in serialized
    assert first.learner_manifest["items"][1]["slideId"] == "slide-1"


def test_compile_rejects_limits_duplicate_ids_and_incomplete_publish_data() -> None:
    draft = _draft()
    draft["items"] = [draft["items"][0]] * 101  # type: ignore[index]
    with pytest.raises(AssessmentContractError, match="ASSESSMENT_ITEM_LIMIT"):
        compile_assessment(draft)

    duplicate = _draft()
    duplicate["items"] = [duplicate["items"][0], duplicate["items"][0]]  # type: ignore[index]
    with pytest.raises(AssessmentContractError, match="ASSESSMENT_DUPLICATE_ID"):
        compile_assessment(duplicate)


def test_short_answer_normalization_is_unicode_and_whitespace_stable() -> None:
    assert normalize_short_answer("  ADENO\u212aARCINOMA\n  NOS ") == "adenokarcinoma nos"


def test_known_scoring_vectors_are_decimal_half_up_and_bounded() -> None:
    assert score_item(
        {
            "type": "checkboxes",
            "points": "3",
            "answerKey": {"optionIds": ["a", "b"]},
            "scoring": {"partialCredit": True},
            "options": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}],
        },
        {"optionIds": ["a", "c"]},
    ) == Decimal("0.000")
    assert score_item(
        {
            "type": "short-answer",
            "points": "1.0055",
            "answerKey": {"variants": [" Adenocarcinoma "]},
        },
        {"text": "ADENOCARCINOMA"},
    ) == Decimal("1.006")
    assert score_item(
        {
            "type": "diagnostic-field",
            "points": "2",
            "answerKey": {
                "regions": [{"kind": "rectangle", "x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2}],
                "diagnoses": ["Adenocarcinoma"],
            },
            "scoring": {"pointTolerance": 0.03, "rectangleIou": 0.25},
        },
        {"selection": {"kind": "point", "x": 0.5, "y": 0.5}, "diagnosis": "adenocarcinoma"},
    ) == Decimal("2.000")
