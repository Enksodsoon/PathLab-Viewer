import re
from collections.abc import Callable, Iterator
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from .identity import (
    ROLE_CAPABILITIES,
    StaffOrganizationContext,
    has_capability,
    staff_organization_context,
    staff_organization_contexts,
)
from .identity_mutation_lock import lock_organization_mutation
from .models import AuditEvent, Organization, OrganizationMembership, Session, User

SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slug: str = Field(min_length=2, max_length=80)
    display_name: str = Field(alias="displayName", min_length=1, max_length=160)


class MembershipCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    role: str


def _organization_json(organization: Organization) -> dict[str, Any]:
    return {
        "id": organization.id,
        "slug": organization.slug,
        "displayName": organization.display_name,
        "status": organization.status,
        "schemaVersion": organization.schema_version,
        "createdAt": organization.created_at.isoformat(),
        "updatedAt": organization.updated_at.isoformat(),
    }


def _context_json(context: StaffOrganizationContext) -> dict[str, Any]:
    return {
        "organization": _organization_json(context.organization),
        "membership": {
            "id": context.membership.id,
            "role": context.membership.role,
            "status": context.membership.status,
        },
        "capabilities": sorted(context.capabilities),
    }


def register_identity_routes(
    app: FastAPI,
    *,
    database_dependency: Callable[..., Iterator[OrmSession]],
    admin_dependency: Callable[..., Session],
    csrf_dependency: Callable[..., Session],
    enabled: bool,
) -> None:
    Database = Annotated[OrmSession, Depends(database_dependency)]
    AdminSession = Annotated[Session, Depends(admin_dependency)]
    CsrfSession = Annotated[Session, Depends(csrf_dependency)]
    ActiveOrganization = Annotated[str | None, Header(alias="X-PathLab-Organization")]

    def require_enabled() -> None:
        if not enabled:
            raise HTTPException(status_code=404, detail={"code": "IDENTITY_DISABLED"})

    def context_for(
        authenticated: Session,
        database: OrmSession,
        organization_id: str | None,
        capability: str | None = None,
    ) -> StaffOrganizationContext:
        context = staff_organization_context(database, authenticated.user_id, organization_id)
        if context is None:
            raise HTTPException(status_code=403, detail={"code": "ORGANIZATION_FORBIDDEN"})
        if capability is not None and not has_capability(context, capability):
            raise HTTPException(status_code=403, detail={"code": "CAPABILITY_REQUIRED"})
        return context

    @app.get("/api/v2/admin/identity/context", dependencies=[Depends(require_enabled)])
    def identity_context(
        authenticated: AdminSession,
        database: Database,
        organization_id: ActiveOrganization = None,
    ) -> dict[str, Any]:
        contexts = staff_organization_contexts(database, authenticated.user_id)
        active = context_for(authenticated, database, organization_id)
        return {
            "staffSubject": {"type": "staff", "id": authenticated.user_id},
            "activeOrganizationId": active.organization.id,
            "organizations": [_context_json(item) for item in contexts],
        }

    @app.post(
        "/api/v2/admin/identity/organizations",
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_enabled)],
    )
    def create_organization(
        payload: OrganizationCreate,
        authenticated: CsrfSession,
        database: Database,
        organization_id: ActiveOrganization = None,
    ) -> dict[str, Any]:
        source = context_for(authenticated, database, organization_id, "identity.manage")
        slug = payload.slug.strip().casefold()
        if SLUG_PATTERN.fullmatch(slug) is None:
            raise HTTPException(status_code=400, detail={"code": "ORGANIZATION_SLUG_INVALID"})
        audit = AuditEvent(
            actor_user_id=authenticated.user_id,
            action="identity.organization_created",
            detail={"sourceOrganizationId": source.organization.id},
        )
        database.add(audit)
        database.flush()
        organization = Organization(
            slug=slug,
            display_name=payload.display_name.strip(),
            created_by_user_id=authenticated.user_id,
            audit_event_id=audit.id,
        )
        database.add(organization)
        database.flush()
        membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=authenticated.user_id,
            role="owner",
            created_by_user_id=authenticated.user_id,
            audit_event_id=audit.id,
        )
        database.add(membership)
        audit.target_id = organization.id
        try:
            database.commit()
        except IntegrityError as error:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "ORGANIZATION_SLUG_CONFLICT"}
            ) from error
        database.refresh(organization)
        return _context_json(
            StaffOrganizationContext(
                organization=organization,
                membership=membership,
                capabilities=ROLE_CAPABILITIES["owner"],
            )
        )

    @app.post(
        "/api/v2/admin/identity/organizations/{target_organization_id}/memberships",
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_enabled)],
    )
    def create_membership(
        target_organization_id: str,
        payload: MembershipCreate,
        authenticated: CsrfSession,
        database: Database,
    ) -> dict[str, Any]:
        if payload.role not in ROLE_CAPABILITIES:
            raise HTTPException(status_code=400, detail={"code": "ROLE_INVALID"})
        lock_organization_mutation(database, target_organization_id)
        actor = context_for(authenticated, database, target_organization_id, "identity.manage")
        if actor.membership.role != "owner":
            if payload.role == "owner":
                raise HTTPException(status_code=403, detail={"code": "OWNER_ROLE_REQUIRED"})
            if not ROLE_CAPABILITIES[payload.role].issubset(actor.capabilities):
                raise HTTPException(status_code=403, detail={"code": "ROLE_GRANT_FORBIDDEN"})
        user = database.scalar(select(User).where(User.username == payload.username))
        if user is None:
            raise HTTPException(status_code=404, detail={"code": "STAFF_USER_NOT_FOUND"})
        audit = AuditEvent(
            actor_user_id=authenticated.user_id,
            action="identity.membership_created",
            target_id=target_organization_id,
            detail={"role": payload.role},
        )
        database.add(audit)
        database.flush()
        membership = OrganizationMembership(
            organization_id=target_organization_id,
            user_id=user.id,
            role=payload.role,
            created_by_user_id=authenticated.user_id,
            audit_event_id=audit.id,
        )
        database.add(membership)
        try:
            database.commit()
        except IntegrityError as error:
            database.rollback()
            raise HTTPException(status_code=409, detail={"code": "MEMBERSHIP_CONFLICT"}) from error
        database.refresh(membership)
        return {
            "id": membership.id,
            "organizationId": membership.organization_id,
            "staffSubject": {"type": "staff", "id": user.id},
            "role": membership.role,
            "status": membership.status,
        }

    @app.delete(
        "/api/v2/admin/identity/organizations/{target_organization_id}/memberships/{membership_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_enabled)],
    )
    def disable_membership(
        target_organization_id: str,
        membership_id: str,
        authenticated: CsrfSession,
        database: Database,
    ) -> None:
        lock_organization_mutation(database, target_organization_id)
        actor = context_for(authenticated, database, target_organization_id, "identity.manage")
        membership = database.get(OrganizationMembership, membership_id)
        if membership is None or membership.organization_id != target_organization_id:
            raise HTTPException(status_code=404, detail={"code": "MEMBERSHIP_NOT_FOUND"})
        if membership.role == "owner":
            if actor.membership.role != "owner":
                raise HTTPException(status_code=403, detail={"code": "OWNER_ROLE_REQUIRED"})
            owners = database.scalar(
                select(func.count())
                .select_from(OrganizationMembership)
                .where(
                    OrganizationMembership.organization_id == target_organization_id,
                    OrganizationMembership.role == "owner",
                    OrganizationMembership.status == "active",
                )
            )
            if int(owners or 0) <= 1:
                raise HTTPException(status_code=409, detail={"code": "LAST_OWNER_REQUIRED"})
        membership.status = "disabled"
        membership.disabled_at = func.now()
        audit = AuditEvent(
            actor_user_id=authenticated.user_id,
            action="identity.membership_disabled",
            target_id=membership.id,
            detail={"organizationId": target_organization_id},
        )
        database.add(audit)
        database.flush()
        membership.audit_event_id = audit.id
        database.commit()
