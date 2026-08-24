from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

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
    items = version.definition.get("items", []) if version is not None else []
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
        question: dict[str, Any] = {
            "responseCount": int(
                database.scalar(
                    select(func.count(AssessmentResponse.id))
                    .join(AssessmentAttempt, AssessmentAttempt.id == AssessmentResponse.attempt_id)
                    .where(
                        AssessmentAttempt.administration_id == administration.id,
                        AssessmentResponse.item_id == item_id,
                    )
                )
                or 0
            ),
            "scoredCount": len(values),
            "averagePoints": (
                f"{sum(values, start=Decimal('0')) / len(values):.3f}" if values else "0.000"
            ),
        }
        if item.get("type") == "diagnostic-field":
            grid = [[0 for _ in range(HEATMAP_SIZE)] for _ in range(HEATMAP_SIZE)]
            responses = database.scalars(
                select(AssessmentResponse)
                .join(AssessmentAttempt, AssessmentAttempt.id == AssessmentResponse.attempt_id)
                .where(
                    AssessmentAttempt.administration_id == administration.id,
                    AssessmentResponse.item_id == item_id,
                )
            )
            for response in responses:
                center = _selection_center(response.response)
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
