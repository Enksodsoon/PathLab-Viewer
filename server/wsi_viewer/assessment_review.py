from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _items(definition: dict[str, Any]) -> list[tuple[str | None, dict[str, Any]]]:
    if definition.get("schema") == "pathlab.assessment/2":
        return [
            (section.get("id"), item)
            for section in definition.get("sections", [])
            for item in section.get("items", [])
        ]
    return [(None, item) for item in definition.get("items", [])]


def _safe_correct_answer(item: dict[str, Any]) -> dict[str, Any] | None:
    answer = item.get("answerKey")
    if not isinstance(answer, dict):
        return None
    safe: dict[str, Any] = {}
    if isinstance(answer.get("optionIds"), list):
        safe["optionIds"] = [str(value) for value in answer["optionIds"]]
    if isinstance(answer.get("variants"), list):
        safe["acceptedAnswers"] = [str(value) for value in answer["variants"]]
    if isinstance(answer.get("diagnoses"), list):
        safe["diagnoses"] = [str(value) for value in answer["diagnoses"]]
    if isinstance(answer.get("regions"), list):
        safe["regions"] = [
            {
                key: region[key]
                for key in ("kind", "x", "y", "width", "height")
                if key in region
            }
            for region in answer["regions"]
            if isinstance(region, dict)
        ]
    if "value" in answer:
        safe["value"] = answer["value"]
    return safe or None


def _earned(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def build_learner_review(
    *,
    definition: dict[str, Any],
    responses: dict[str, dict[str, Any]],
    breakdown: dict[str, Any],
    manual_feedback: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    show_score = bool(policy.get("showScore", False))
    show_answers = bool(policy.get("showAnswers", False))
    show_authored = bool(
        policy.get("showAuthoredFeedback", policy.get("showFeedback", False))
    )
    show_manual = bool(policy.get("showManualFeedback", False))
    show_annotations = bool(policy.get("showAnnotations", False)) and show_answers
    review_items: list[dict[str, Any]] = []
    for section_id, item in _items(definition):
        item_id = str(item["id"])
        review: dict[str, Any] = {
            "itemId": item_id,
            "sectionId": section_id,
            "type": item.get("type"),
            "prompt": item.get("prompt", ""),
            "response": responses.get(item_id),
        }
        if show_score:
            review["points"] = breakdown.get(item_id)
            review["maximumPoints"] = str(item.get("points", "0"))
        if show_answers:
            answer = _safe_correct_answer(item)
            if answer is not None:
                review["correctAnswer"] = answer
        if show_authored and isinstance(item.get("feedback"), dict):
            feedback_key = "correct" if _earned(breakdown.get(item_id)) > 0 else "incorrect"
            authored = item["feedback"].get(feedback_key)
            if authored:
                review["authoredFeedback"] = str(authored)
        if show_manual and manual_feedback.get(item_id):
            review["manualFeedback"] = str(manual_feedback[item_id])
        if show_annotations and isinstance(item.get("annotations"), list):
            review["annotations"] = [
                {
                    key: annotation[key]
                    for key in ("kind", "x", "y", "width", "height", "label")
                    if key in annotation
                }
                for annotation in item["annotations"]
                if isinstance(annotation, dict)
            ]
        media_values = [item.get("media")]
        additional_media = item.get("mediaItems", [])
        if isinstance(additional_media, list):
            media_values.extend(additional_media)
        review_media = [
            {
                "kind": "slide-thumbnail",
                "assetPath": media["assetPath"],
                "alt": str(media.get("alt", "")),
            }
            for media in media_values
            if isinstance(media, dict)
            and str(media.get("assetPath", "")).startswith("/assessment-assets/")
        ]
        if review_media:
            review["media"] = review_media[0]
            if len(review_media) > 1:
                review["mediaItems"] = review_media[1:]
        review_items.append(review)
    return {"items": review_items}
