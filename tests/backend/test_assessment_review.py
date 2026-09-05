from wsi_viewer.assessment_review import build_learner_review


def _definition() -> dict[str, object]:
    return {
        "schema": "pathlab.assessment/2",
        "sections": [
            {
                "id": "section-1",
                "items": [
                    {
                        "id": "item-1",
                        "type": "diagnostic-field",
                        "prompt": "Make a diagnosis",
                        "points": "2",
                        "answerKey": {
                            "diagnoses": ["Adenocarcinoma"],
                            "regions": [{"kind": "point", "x": 0.2, "y": 0.3}],
                        },
                        "feedback": {"correct": "Well localized."},
                        "teacherNotes": "Never show this",
                        "adminUrl": "/admin/slides/private",
                        "annotations": [
                            {
                                "kind": "rectangle",
                                "x": 0.1,
                                "y": 0.2,
                                "width": 0.3,
                                "height": 0.4,
                                "filesystemPath": "C:/private/source.svs",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_review_is_field_allowlisted_before_answer_release() -> None:
    review = build_learner_review(
        definition=_definition(),
        responses={"item-1": {"diagnosis": "Adenocarcinoma"}},
        breakdown={"item-1": "2.000"},
        manual_feedback={"item-1": "Good work"},
        policy={"showScore": True},
    )
    serialized = repr(review)
    assert review["items"][0]["points"] == "2.000"
    for private_value in (
        "answerKey",
        "regions",
        "teacherNotes",
        "Good work",
        "source.svs",
        "/admin/",
    ):
        assert private_value not in serialized


def test_review_reveals_only_sanitized_permitted_feedback_and_overlays() -> None:
    review = build_learner_review(
        definition=_definition(),
        responses={"item-1": {"diagnosis": "Adenocarcinoma"}},
        breakdown={"item-1": "2.000"},
        manual_feedback={"item-1": "Good work"},
        policy={
            "showScore": True,
            "showAnswers": True,
            "showAuthoredFeedback": True,
            "showManualFeedback": True,
            "showAnnotations": True,
        },
    )
    item = review["items"][0]
    assert item["correctAnswer"]["diagnoses"] == ["Adenocarcinoma"]
    assert item["authoredFeedback"] == "Well localized."
    assert item["manualFeedback"] == "Good work"
    assert item["annotations"] == [
        {"kind": "rectangle", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
    ]
    assert "filesystemPath" not in repr(item)
