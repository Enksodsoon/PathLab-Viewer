"""Persistent slide-stack membership and registration admission."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .alignment_policy import VALIDATION_POLICY, current_registration
from .domain import SlideState
from .models import ComparisonSet, ComparisonSetMember, Job, Slide

READY_STATES = {SlideState.READY_PRIVATE, SlideState.PUBLISHED}
ACTIVE_JOB_STATES = {"queued", "leased", "running", "retry_wait"}


def membership_rows(database: OrmSession, item: ComparisonSet) -> list[ComparisonSetMember]:
    rows = list(
        database.scalars(
            select(ComparisonSetMember)
            .where(ComparisonSetMember.comparison_set_id == item.id)
            .order_by(ComparisonSetMember.position, ComparisonSetMember.created_at)
        )
    )
    if rows or not item.member_slide_ids:
        return rows
    anchors = (item.alignment_config or {}).get("anchors", {})
    for position, slide_id in enumerate(item.member_slide_ids):
        database.add(
            ComparisonSetMember(
                comparison_set_id=item.id,
                slide_id=slide_id,
                anchor_slide_id=None
                if slide_id == item.reference_slide_id
                else anchors.get(slide_id, item.reference_slide_id),
                position=position,
            )
        )
    database.flush()
    return membership_rows(database, item)


def sync_membership_mirror(database: OrmSession, item: ComparisonSet) -> None:
    rows = membership_rows(database, item)
    item.member_slide_ids = [row.slide_id for row in rows]
    anchors = {
        row.slide_id: row.anchor_slide_id or item.reference_slide_id
        for row in rows
        if row.slide_id != item.reference_slide_id
    }
    item.alignment_config = {**(item.alignment_config or {}), "anchors": anchors}


def cancel_stack_jobs(database: OrmSession, comparison_set_id: str) -> None:
    now = datetime.now(UTC)
    for job in database.scalars(
        select(Job).where(
            Job.kind.in_(["align", "align_benchmark"]), Job.status.in_(ACTIVE_JOB_STATES)
        )
    ):
        if (job.checkpoint or {}).get("comparisonSetId") == comparison_set_id:
            job.cancellation_requested_at = now


def queue_ready_registrations(
    database: OrmSession,
    item: ComparisonSet,
    *,
    force: bool = False,
    preserve_existing: bool = False,
) -> int:
    rows = membership_rows(database, item)
    ids = [row.slide_id for row in rows]
    slides = {slide.id: slide for slide in database.scalars(select(Slide).where(Slide.id.in_(ids)))}
    queued = 0
    foreground_deadline = (datetime.now(UTC) + timedelta(seconds=10)).isoformat()
    for row in rows:
        if row.slide_id == item.reference_slide_id:
            continue
        slide = slides.get(row.slide_id)
        anchor_id = row.anchor_slide_id or item.reference_slide_id
        anchor = slides.get(anchor_id)
        if (
            slide is None
            or anchor is None
            or slide.trashed_at is not None
            or anchor.trashed_at is not None
            or slide.state not in READY_STATES
            or anchor.state not in READY_STATES
            or not slide.sha256
            or not anchor.sha256
        ):
            continue
        saved = current_registration(
            item.registrations.get(row.slide_id),
            source_version=slide.sha256,
            anchor_version=anchor.sha256,
        )
        if saved and saved.get("status") != "stale" and not force:
            continue
        versions = dict(item.source_versions or {})
        versions[slide.id] = slide.sha256
        versions[anchor.id] = anchor.sha256
        reference = slides.get(item.reference_slide_id)
        if reference and reference.sha256:
            versions[reference.id] = reference.sha256
        item.source_versions = versions
        key = hashlib.sha256(
            f"{item.id}:{item.version}:{slide.id}:{slide.sha256}:{anchor.id}:{anchor.sha256}:{VALIDATION_POLICY}".encode()
        ).hexdigest()
        if (
            database.scalar(
                select(Job.id).where(Job.kind == "align", Job.idempotency_key_hash == key)
            )
            is not None
        ):
            continue
        database.add(
            Job(
                slide_id=slide.id,
                kind="align",
                resource_class="isolated",
                idempotency_key_hash=key,
                checkpoint={
                    "comparisonSetId": item.id,
                    "memberId": slide.id,
                    "anchorSlideId": anchor.id,
                    "sourceVersion": slide.sha256,
                    "anchorVersion": anchor.sha256,
                    "setVersion": item.version,
                    "progress": 0,
                    "phase": "preview",
                    "foregroundDeadlineAt": foreground_deadline,
                    "preserveExisting": preserve_existing,
                },
                resource_limits={
                    "cpuThreads": 1,
                    "memoryBytes": 512 * 1024**2,
                    "timeoutSeconds": 10,
                },
            )
        )
        queued += 1
    if queued:
        item.status = "queued"
    elif len(rows) <= 1:
        item.status = "draft"
    return queued


def activate_ready_slide_memberships(database: OrmSession, slide: Slide) -> int:
    if slide.state not in READY_STATES or not slide.sha256:
        return 0
    set_ids = list(
        database.scalars(
            select(ComparisonSetMember.comparison_set_id).where(
                ComparisonSetMember.slide_id == slide.id
            )
        )
    )
    queued = 0
    for set_id in set_ids:
        item = database.get(ComparisonSet, set_id)
        if item is None:
            continue
        item.source_versions = {**(item.source_versions or {}), slide.id: slide.sha256}
        queued += queue_ready_registrations(database, item)
    return queued


def remove_slide_from_stacks(database: OrmSession, slide_id: str) -> None:
    """Apply stack deletion semantics before the slide row is removed."""
    rows = list(
        database.scalars(
            select(ComparisonSetMember).where(ComparisonSetMember.slide_id == slide_id)
        )
    )
    for row in rows:
        item = database.get(ComparisonSet, row.comparison_set_id)
        if item is None:
            continue
        if item.reference_slide_id == slide_id:
            database.delete(item)
            continue
        database.delete(row)
        database.flush()
        registrations = dict(item.registrations or {})
        registrations.pop(slide_id, None)
        for member_id, registration in list(registrations.items()):
            if registration.get("anchorSlideId") == slide_id:
                registrations.pop(member_id, None)
        item.registrations = registrations
        item.source_versions = {
            member_id: digest
            for member_id, digest in (item.source_versions or {}).items()
            if member_id != slide_id
        }
        item.version += 1
        item.status = "draft"
        cancel_stack_jobs(database, item.id)
        sync_membership_mirror(database, item)
