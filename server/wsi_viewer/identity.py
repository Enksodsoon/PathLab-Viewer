from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .models import AuditEvent, Organization, OrganizationMembership, User

DEFAULT_ORGANIZATION_ID = "00000000-0000-4000-8000-000000000001"

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "owner": frozenset(
        {
            "identity.manage",
            "library.manage",
            "classroom.manage",
            "education.manage",
            "research.manage",
            "audit.read",
        }
    ),
    "admin": frozenset(
        {
            "identity.manage",
            "library.manage",
            "classroom.manage",
            "education.manage",
            "audit.read",
        }
    ),
    "instructor": frozenset({"classroom.manage", "education.manage", "learners.read"}),
    "teaching_assistant": frozenset({"classroom.manage", "learners.read"}),
    "researcher": frozenset({"research.manage", "learners.read"}),
    "auditor": frozenset({"audit.read"}),
}


@dataclass(frozen=True)
class StaffOrganizationContext:
    organization: Organization
    membership: OrganizationMembership
    capabilities: frozenset[str]


def staff_organization_contexts(
    database: OrmSession, user_id: str
) -> list[StaffOrganizationContext]:
    rows = database.execute(
        select(OrganizationMembership, Organization)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
            Organization.status == "active",
        )
        .order_by(Organization.created_at, Organization.id)
    ).all()
    return [
        StaffOrganizationContext(
            organization=organization,
            membership=membership,
            capabilities=ROLE_CAPABILITIES[membership.role],
        )
        for membership, organization in rows
    ]


def staff_organization_context(
    database: OrmSession,
    user_id: str,
    organization_id: str | None,
) -> StaffOrganizationContext | None:
    contexts = staff_organization_contexts(database, user_id)
    if organization_id is None:
        return contexts[0] if contexts else None
    return next(
        (item for item in contexts if item.organization.id == organization_id),
        None,
    )


def has_capability(context: StaffOrganizationContext, capability: str) -> bool:
    return capability in context.capabilities


def is_default_legacy_owner(database: OrmSession, user_id: str) -> bool:
    membership_id = database.scalar(
        select(OrganizationMembership.id)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == DEFAULT_ORGANIZATION_ID,
            OrganizationMembership.role == "owner",
            OrganizationMembership.status == "active",
            Organization.status == "active",
        )
        .limit(1)
    )
    return membership_id is not None


def ensure_default_owner_membership(database: OrmSession, user: User) -> OrganizationMembership:
    membership = database.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == DEFAULT_ORGANIZATION_ID,
        )
    )
    if membership is not None:
        return membership
    organization = database.get(Organization, DEFAULT_ORGANIZATION_ID)
    audit = AuditEvent(
        actor_user_id=user.id,
        action="identity.default_organization_bootstrapped",
        target_id=DEFAULT_ORGANIZATION_ID,
    )
    database.add(audit)
    database.flush()
    if organization is None:
        organization = Organization(
            id=DEFAULT_ORGANIZATION_ID,
            slug="default",
            display_name="PathLab",
            created_by_user_id=user.id,
            audit_event_id=audit.id,
        )
        database.add(organization)
        database.flush()
    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        role="owner",
        created_by_user_id=user.id,
        audit_event_id=audit.id,
    )
    database.add(membership)
    database.flush()
    return membership
