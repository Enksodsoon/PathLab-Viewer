from __future__ import annotations

from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from .assessment_branching import reachable_section_ids
from .models import (
    AssessmentAdministration,
    AssessmentAggregateSnapshot,
    AssessmentAttempt,
    AssessmentGradebookRow,
    AssessmentParticipant,
    AssessmentResponse,
    AssessmentRosterSnapshot,
    AssessmentScoreVersion,
    AssessmentVersion,
)

HEATMAP_SIZE = 20


def _latest_scores(
    database: OrmSession, administration_id: str
) -> dict[str, AssessmentScoreVersion]:
    rows = database.scalars(
        select(AssessmentScoreVersion)
        .join(AssessmentAttempt, AssessmentAttempt.id == AssessmentScoreVersion.attempt_id)
        .where(AssessmentAttempt.administration_id == administration_id)
        .order_by(AssessmentScoreVersion.attempt_id, AssessmentScoreVersion.version.desc())
    )
    latest: dict[str, AssessmentScoreVersion] = {}
    for row in rows:
        latest.setdefault(row.attempt_id, row)
    return latest


def _selection_center(response: dict[str, Any]) -> tuple[float, float] | None:
    selection = response.get("selection", response)
    if not isinstance(selection, dict):
        return None
    try:
        x = float(selection["x"])
        y = float(selection["y"])
        if selection.get("kind") == "rectangle":
            x += float(selection["width"]) / 2
            y += float(selection["height"]) / 2
    except (KeyError, TypeError, ValueError):
        return None
    if not 0 <= x <= 1 or not 0 <= y <= 1:
        return None
    return x, y


def build_aggregate(
    database: OrmSession, administration: AssessmentAdministration
) -> dict[str, Any]:
    attempts = database.scalars(
        select(AssessmentAttempt).where(
            AssessmentAttempt.administration_id == administration.id,
            AssessmentAttempt.status.in_(("submitted", "auto_submitted")),
        )
    ).all()
    scores = _latest_scores(database, administration.id)
    score_values = [Decimal(str(scores[item.id].points)) for item in attempts if item.id in scores]
    roster_size = int(
        database.scalar(
            select(func.count(AssessmentRosterSnapshot.id)).where(
                AssessmentRosterSnapshot.administration_id == administration.id,
                AssessmentRosterSnapshot.status == "active",
            )
        )
        or 0
    )
    participant_size = int(
        database.scalar(
            select(func.count(AssessmentParticipant.id)).where(
                AssessmentParticipant.administration_id == administration.id
            )
        )
        or 0
    )
    denominator = roster_size or participant_size
    version = database.get(AssessmentVersion, administration.version_id)
    definition = version.definition if version is not None else {}
    sections = definition.get("sections", []) if isinstance(definition, dict) else []
    items = (
        [
            item
            for section in sections
            if isinstance(section, dict)
            for item in section.get("items", [])
        ]
        if sections
        else definition.get("items", [])
    )
    attempt_responses: dict[str, dict[str, dict[str, Any]]] = {
        attempt.id: {} for attempt in attempts
    }
    if attempts:
        for response in database.scalars(
            select(AssessmentResponse).where(AssessmentResponse.attempt_id.in_(attempt_responses))
        ):
            attempt_responses[response.attempt_id][response.item_id] = response.response
    item_sections = {
        item.get("id"): section.get("id")
        for section in sections
        if isinstance(section, dict)
        for item in section.get("items", [])
        if isinstance(item, dict)
    }
    questions: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        item_id = item["id"]
        values = [
            Decimal(str(score.breakdown[item_id]))
            for score in scores.values()
            if score.breakdown.get(item_id) is not None
        ]
        item_responses = [
            responses[item_id] for responses in attempt_responses.values() if item_id in responses
        ]
        reachable_count = sum(
            1
            for responses in attempt_responses.values()
            if not sections
            or item_sections.get(item_id) in reachable_section_ids(definition, responses)
        )
        question: dict[str, Any] = {
            "responseCount": len(item_responses),
            "reachableCount": reachable_count,
            "scoredCount": len(values),
            "averagePoints": (
                f"{sum(values, start=Decimal('0')) / len(values):.3f}" if values else "0.000"
            ),
        }
        if item.get("type") in {"multiple-choice", "checkboxes", "dropdown"}:
            option_labels = {
                option.get("id"): option.get("label", "")
                for option in item.get("options", [])
                if isinstance(option, dict)
            }
            distribution = {label: 0 for label in option_labels.values()}
            other: dict[str, int] = {}
            for response_data in item_responses:
                option_ids = response_data.get("optionIds", [response_data.get("optionId")])
                for option_id in option_ids:
                    if option_id in option_labels:
                        distribution[option_labels[option_id]] += 1
                if response_data.get("other"):
                    rendered = str(response_data["other"])
                    other[rendered] = other.get(rendered, 0) + 1
            question["optionDistribution"] = distribution
            question["otherDistribution"] = other
        if item.get("type") == "rating":
            ratings = [
                float(response["value"])
                for response in item_responses
                if isinstance(response.get("value"), (int, float))
            ]
            question["ratingDistribution"] = {
                str(value): ratings.count(float(value))
                for value in range(1, int(item.get("rating", {}).get("max", 5)) + 1)
            }
            question["ratingMean"] = round(sum(ratings) / len(ratings), 3) if ratings else None
            question["ratingMedian"] = median(ratings) if ratings else None
        if item.get("type") == "diagnostic-field":
            diagnostic_labels: dict[str, int] = {}
            for response_data in item_responses:
                if response_data.get("diagnosis"):
                    label = str(response_data["diagnosis"])
                    diagnostic_labels[label] = diagnostic_labels.get(label, 0) + 1
            question["diagnosticLabels"] = diagnostic_labels
        if item.get("type") == "diagnostic-field":
            grid = [[0 for _ in range(HEATMAP_SIZE)] for _ in range(HEATMAP_SIZE)]
            response_rows = database.scalars(
                select(AssessmentResponse)
                .join(AssessmentAttempt, AssessmentAttempt.id == AssessmentResponse.attempt_id)
                .where(
                    AssessmentAttempt.administration_id == administration.id,
                    AssessmentResponse.item_id == item_id,
                )
            )
            for response_row in response_rows:
                center = _selection_center(response_row.response)
                if center is None:
                    continue
                x, y = center
                grid[min(HEATMAP_SIZE - 1, int(y * HEATMAP_SIZE))][
                    min(HEATMAP_SIZE - 1, int(x * HEATMAP_SIZE))
                ] += 1
            question["spatialHeatmap"] = {
                "width": HEATMAP_SIZE,
                "height": HEATMAP_SIZE,
                "counts": grid,
            }
        questions[item_id] = question
    section_metrics = []
    for section in sections:
        section_items = [
            item for item in section.get("items", []) if item.get("type") != "section-information"
        ]
        reachable = 0
        completed = 0
        for response_map in attempt_responses.values():
            if section.get("id") not in reachable_section_ids(definition, response_map):
                continue
            reachable += 1
            if all(
                not item.get("required") or item.get("id") in response_map for item in section_items
            ):
                completed += 1
        section_metrics.append(
            {
                "sectionId": section.get("id"),
                "title": section.get("title", ""),
                "reachable": reachable,
                "completed": completed,
                "dropOff": max(0, reachable - completed),
            }
        )
    return {
        "responses": len(attempts),
        "averagePoints": (
            f"{sum(score_values, start=Decimal('0')) / len(score_values):.3f}"
            if score_values
            else "0.000"
        ),
        "completionRate": (
            f"{Decimal(len({item.participant_id for item in attempts})) / denominator:.3f}"
            if denominator
            else "0.000"
        ),
        "needsGrading": int(
            database.scalar(
                select(func.count(AssessmentGradebookRow.id)).where(
                    AssessmentGradebookRow.administration_id == administration.id,
                    AssessmentGradebookRow.status == "needs_grading",
                )
            )
            or 0
        ),
        "questions": questions,
        "sections": section_metrics,
    }


def snapshot_aggregate(
    database: OrmSession, administration: AssessmentAdministration
) -> AssessmentAggregateSnapshot:
    next_version = (
        int(
            database.scalar(
                select(func.coalesce(func.max(AssessmentAggregateSnapshot.version), 0)).where(
                    AssessmentAggregateSnapshot.administration_id == administration.id
                )
            )
            or 0
        )
        + 1
    )
    snapshot = AssessmentAggregateSnapshot(
        administration_id=administration.id,
        version=next_version,
        aggregate=build_aggregate(database, administration),
    )
    database.add(snapshot)
    database.flush()
    return snapshot


def latest_aggregate(
    database: OrmSession, administration_id: str
) -> AssessmentAggregateSnapshot | None:
    return database.scalar(
        select(AssessmentAggregateSnapshot)
        .where(AssessmentAggregateSnapshot.administration_id == administration_id)
        .order_by(AssessmentAggregateSnapshot.version.desc())
    )
