from __future__ import annotations

import threading
from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from wsi_viewer import identity_routes
from wsi_viewer.cli import main as cli_main
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.identity import ROLE_CAPABILITIES
from wsi_viewer.main import create_app
from wsi_viewer.models import (
    AuditEvent,
    Organization,
    OrganizationMembership,
    User,
)
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password


def _settings(tmp_path: Path, *, enabled: bool = True) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'identity.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="identity-test-secret-that-is-long-enough",
        secure_cookies=False,
        identity_governance_enabled=enabled,
    )


def _client(tmp_path: Path, *, enabled: bool = True) -> tuple[TestClient, Settings, str]:
    settings = _settings(tmp_path, enabled=enabled)
    create_schema(settings)
    with session_factory(settings)() as database:
        database.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        database.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
            {"head": ALEMBIC_HEAD},
        )
        owner = User(username="owner", password_hash=hash_password("correct horse battery"))
        database.add(owner)
        database.flush()
        organization = Organization(slug="default", display_name="PathLab")
        database.add(organization)
        database.flush()
        database.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=owner.id,
                role="owner",
                created_by_user_id=owner.id,
            )
        )
        database.commit()
        organization_id = organization.id
    return TestClient(create_app(settings)), settings, organization_id


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/session",
        json={"username": "owner", "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return str(response.json()["csrfToken"])


def test_identity_routes_are_disabled_by_default(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path, enabled=False)
    _login(client)

    response = client.get("/api/v2/admin/identity/context")

    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "IDENTITY_DISABLED"}}


def test_owner_context_exposes_only_staff_organization_capabilities(tmp_path: Path) -> None:
    client, _, organization_id = _client(tmp_path)
    _login(client)

    response = client.get("/api/v2/admin/identity/context")

    assert response.status_code == 200
    payload = response.json()
    assert payload["activeOrganizationId"] == organization_id
    assert payload["organizations"][0]["membership"]["role"] == "owner"
    assert payload["organizations"][0]["capabilities"] == sorted(ROLE_CAPABILITIES["owner"])
    serialized = response.text.casefold()
    assert "learner" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized


def test_create_organization_is_audited_and_owner_scoped(tmp_path: Path) -> None:
    client, settings, source_organization_id = _client(tmp_path)
    csrf = _login(client)

    response = client.post(
        "/api/v2/admin/identity/organizations",
        headers={
            "X-CSRF-Token": csrf,
            "X-PathLab-Organization": source_organization_id,
        },
        json={"slug": "medical-school", "displayName": "Medical School"},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["organization"]["slug"] == "medical-school"
    assert created["membership"]["role"] == "owner"
    with session_factory(settings)() as database:
        organization = database.scalar(
            select(Organization).where(Organization.slug == "medical-school")
        )
        assert organization is not None and organization.audit_event_id is not None
        audit = database.get(AuditEvent, organization.audit_event_id)
        assert audit is not None
        assert audit.action == "identity.organization_created"
        assert audit.detail == {"sourceOrganizationId": source_organization_id}


def test_membership_mutations_fail_closed_across_organizations(tmp_path: Path) -> None:
    client, settings, source_organization_id = _client(tmp_path)
    csrf = _login(client)
    with session_factory(settings)() as database:
        second = Organization(slug="other", display_name="Other")
        target = User(username="instructor", password_hash=hash_password("unused password"))
        researcher = User(
            username="researcher", password_hash=hash_password("unused researcher password")
        )
        database.add_all([second, target, researcher])
        database.commit()
        second_id = second.id

    response = client.post(
        f"/api/v2/admin/identity/organizations/{second_id}/memberships",
        headers={"X-CSRF-Token": csrf},
        json={"username": "instructor", "role": "instructor"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "ORGANIZATION_FORBIDDEN"}}
    allowed = client.post(
        f"/api/v2/admin/identity/organizations/{source_organization_id}/memberships",
        headers={"X-CSRF-Token": csrf},
        json={"username": "instructor", "role": "instructor"},
    )
    assert allowed.status_code == 201
    assert allowed.json()["role"] == "instructor"
    assert "username" not in allowed.text.casefold()
    researcher_allowed = client.post(
        f"/api/v2/admin/identity/organizations/{source_organization_id}/memberships",
        headers={"X-CSRF-Token": csrf},
        json={"username": "researcher", "role": "researcher"},
    )
    assert researcher_allowed.status_code == 201
    assert researcher_allowed.json()["role"] == "researcher"


def test_admin_cannot_grant_owner_or_unheld_capabilities(tmp_path: Path) -> None:
    client, settings, organization_id = _client(tmp_path)
    with session_factory(settings)() as database:
        existing_owner = database.scalar(select(User).where(User.username == "owner"))
        assert existing_owner is not None
        admin = User(
            username="restricted-admin",
            password_hash=hash_password("restricted admin password"),
        )
        second_owner = User(
            username="second-owner",
            password_hash=hash_password("unused second owner password"),
        )
        candidate = User(
            username="owner-candidate",
            password_hash=hash_password("unused owner candidate password"),
        )
        researcher = User(
            username="researcher-candidate",
            password_hash=hash_password("unused researcher password"),
        )
        instructor = User(
            username="instructor-candidate",
            password_hash=hash_password("unused instructor password"),
        )
        auditor = User(
            username="auditor-candidate",
            password_hash=hash_password("unused auditor password"),
        )
        database.add_all([admin, second_owner, candidate, researcher, instructor, auditor])
        database.flush()
        database.add_all(
            [
                OrganizationMembership(
                    organization_id=organization_id,
                    user_id=admin.id,
                    role="admin",
                    created_by_user_id=existing_owner.id,
                ),
                OrganizationMembership(
                    organization_id=organization_id,
                    user_id=second_owner.id,
                    role="owner",
                    created_by_user_id=existing_owner.id,
                ),
            ]
        )
        database.commit()
        second_owner_membership = database.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == second_owner.id,
            )
        )
        assert second_owner_membership is not None
        second_owner_membership_id = second_owner_membership.id

    login = client.post(
        "/api/v1/auth/session",
        json={
            "username": "restricted-admin",
            "password": "restricted admin password",
        },
    )
    assert login.status_code == 201
    csrf = str(login.json()["csrfToken"])

    grant = client.post(
        f"/api/v2/admin/identity/organizations/{organization_id}/memberships",
        headers={"X-CSRF-Token": csrf},
        json={"username": "owner-candidate", "role": "owner"},
    )
    researcher_grant = client.post(
        f"/api/v2/admin/identity/organizations/{organization_id}/memberships",
        headers={"X-CSRF-Token": csrf},
        json={"username": "researcher-candidate", "role": "researcher"},
    )
    instructor_grant = client.post(
        f"/api/v2/admin/identity/organizations/{organization_id}/memberships",
        headers={"X-CSRF-Token": csrf},
        json={"username": "instructor-candidate", "role": "instructor"},
    )
    auditor_grant = client.post(
        f"/api/v2/admin/identity/organizations/{organization_id}/memberships",
        headers={"X-CSRF-Token": csrf},
        json={"username": "auditor-candidate", "role": "auditor"},
    )
    disable = client.delete(
        f"/api/v2/admin/identity/organizations/{organization_id}/memberships/"
        f"{second_owner_membership_id}",
        headers={"X-CSRF-Token": csrf},
    )

    assert grant.status_code == 403
    assert grant.json() == {"detail": {"code": "OWNER_ROLE_REQUIRED"}}
    for forbidden in (researcher_grant, instructor_grant):
        assert forbidden.status_code == 403
        assert forbidden.json() == {"detail": {"code": "ROLE_GRANT_FORBIDDEN"}}
    assert auditor_grant.status_code == 201
    assert auditor_grant.json()["role"] == "auditor"
    assert disable.status_code == 403
    assert disable.json() == {"detail": {"code": "OWNER_ROLE_REQUIRED"}}
    with session_factory(settings)() as database:
        owners = list(
            database.scalars(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.role == "owner",
                    OrganizationMembership.status == "active",
                )
            )
        )
        assert len(owners) == 2


def test_owner_can_manage_owner_memberships_but_cannot_remove_last_owner(
    tmp_path: Path,
) -> None:
    client, settings, organization_id = _client(tmp_path)
    csrf = _login(client)
    with session_factory(settings)() as database:
        existing_owner = database.scalar(select(User).where(User.username == "owner"))
        assert existing_owner is not None
        second_owner = User(
            username="second-owner",
            password_hash=hash_password("unused second owner password"),
        )
        candidate = User(
            username="owner-candidate",
            password_hash=hash_password("unused owner candidate password"),
        )
        database.add_all([second_owner, candidate])
        database.flush()
        second_membership = OrganizationMembership(
            organization_id=organization_id,
            user_id=second_owner.id,
            role="owner",
            created_by_user_id=existing_owner.id,
        )
        database.add(second_membership)
        database.commit()
        second_membership_id = second_membership.id

    grant = client.post(
        f"/api/v2/admin/identity/organizations/{organization_id}/memberships",
        headers={"X-CSRF-Token": csrf},
        json={"username": "owner-candidate", "role": "owner"},
    )
    assert grant.status_code == 201
    candidate_membership_id = str(grant.json()["id"])

    for membership_id in (candidate_membership_id, second_membership_id):
        response = client.delete(
            f"/api/v2/admin/identity/organizations/{organization_id}/memberships/{membership_id}",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 204

    with session_factory(settings)() as database:
        last_owner = database.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == "owner",
                OrganizationMembership.status == "active",
            )
        )
        assert last_owner is not None
        last_owner_id = last_owner.id
    response = client.delete(
        f"/api/v2/admin/identity/organizations/{organization_id}/memberships/{last_owner_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "LAST_OWNER_REQUIRED"}}


def test_concurrent_owner_disable_routes_leave_one_active_owner(
    tmp_path: Path, monkeypatch
) -> None:
    first_client, settings, organization_id = _client(tmp_path)
    with session_factory(settings)() as database:
        first_owner = database.scalar(select(User).where(User.username == "owner"))
        assert first_owner is not None
        second_owner = User(
            username="second-owner",
            password_hash=hash_password("second owner password"),
        )
        database.add(second_owner)
        database.flush()
        second_membership = OrganizationMembership(
            organization_id=organization_id,
            user_id=second_owner.id,
            role="owner",
            created_by_user_id=first_owner.id,
        )
        database.add(second_membership)
        database.commit()
        first_membership = database.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == first_owner.id,
            )
        )
        assert first_membership is not None
        first_membership_id = first_membership.id
        second_membership_id = second_membership.id

    barrier = threading.Barrier(2)
    actual_lock = identity_routes.lock_organization_mutation

    def simultaneous_lock(database, target_organization_id: str) -> None:
        barrier.wait(timeout=5)
        actual_lock(database, target_organization_id)

    monkeypatch.setattr(identity_routes, "lock_organization_mutation", simultaneous_lock)
    responses = []
    response_lock = threading.Lock()

    with first_client, TestClient(create_app(settings)) as second_client:
        first_csrf = _login(first_client)
        second_login = second_client.post(
            "/api/v1/auth/session",
            json={"username": "second-owner", "password": "second owner password"},
        )
        assert second_login.status_code == 201
        second_csrf = str(second_login.json()["csrfToken"])

        def disable_other(client: TestClient, csrf: str, membership_id: str) -> None:
            response = client.delete(
                f"/api/v2/admin/identity/organizations/{organization_id}/memberships/"
                f"{membership_id}",
                headers={"X-CSRF-Token": csrf},
            )
            with response_lock:
                responses.append(response)

        threads = [
            threading.Thread(
                target=disable_other,
                args=(first_client, first_csrf, second_membership_id),
            ),
            threading.Thread(
                target=disable_other,
                args=(second_client, second_csrf, first_membership_id),
            ),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=8)
            assert not thread.is_alive()

    assert len(responses) == 2
    assert [response.status_code for response in responses].count(204) == 1
    rejected = next(response for response in responses if response.status_code != 204)
    assert rejected.status_code in {403, 409}
    assert rejected.json()["detail"]["code"] in {
        "LAST_OWNER_REQUIRED",
        "ORGANIZATION_FORBIDDEN",
        "ORGANIZATION_MUTATION_BUSY",
    }
    with session_factory(settings)() as database:
        active_owner_count = database.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == "owner",
                OrganizationMembership.status == "active",
            )
        )
        assert active_owner_count == 1


def test_restricted_staff_keep_account_and_identity_access_but_not_legacy_admin(
    tmp_path: Path,
) -> None:
    client, settings, organization_id = _client(tmp_path)
    with session_factory(settings)() as database:
        owner = database.scalar(select(User).where(User.username == "owner"))
        assert owner is not None
        auditor = User(
            username="restricted-auditor",
            password_hash=hash_password("restricted auditor password"),
        )
        database.add(auditor)
        database.flush()
        database.add(
            OrganizationMembership(
                organization_id=organization_id,
                user_id=auditor.id,
                role="auditor",
                created_by_user_id=owner.id,
            )
        )
        database.commit()

    login = client.post(
        "/api/v1/auth/session",
        json={
            "username": "restricted-auditor",
            "password": "restricted auditor password",
        },
    )
    assert login.status_code == 201
    csrf = str(login.json()["csrfToken"])
    refresh = client.get("/api/v1/auth/session")
    context = client.get("/api/v2/admin/identity/context")
    legacy_read = client.get("/api/v1/admin/slides")
    legacy_write = client.post(
        "/api/v1/admin/slides",
        headers={"X-CSRF-Token": csrf},
        json={"displayName": "Denied", "filename": "denied.svs", "length": 1},
    )

    assert refresh.status_code == 200
    assert context.status_code == 200
    assert context.json()["organizations"][0]["capabilities"] == ["audit.read"]
    for response in (legacy_read, legacy_write):
        assert response.status_code == 403
        assert response.json() == {"detail": {"code": "LEGACY_ADMIN_FORBIDDEN"}}
    logout = client.delete(
        "/api/v1/auth/session",
        headers={"X-CSRF-Token": csrf},
    )
    assert logout.status_code == 204


def test_identity_migration_backfills_existing_user_as_default_owner(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "identity-migration.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")
    command.upgrade(config, "20260822_0024")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        database.execute(
            text(
                "INSERT INTO users "
                "(id, username, password_hash, credential_generation, created_at) "
                "VALUES ('11111111-1111-4111-8111-111111111111', 'existing', "
                "'hash', 1, CURRENT_TIMESTAMP)"
            )
        )
        database.commit()

    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        tables = set(inspect(database.connection()).get_table_names())
        assert {
            "organizations",
            "organization_memberships",
            "staff_invitations",
            "learner_profiles",
            "cohorts",
            "cohort_enrollments",
            "learner_credentials",
            "research_pseudonyms",
            "oidc_identity_links",
        } <= tables
        row = database.execute(
            text(
                "SELECT o.slug, m.role, m.status FROM organization_memberships m "
                "JOIN organizations o ON o.id = m.organization_id "
                "WHERE m.user_id = '11111111-1111-4111-8111-111111111111'"
            )
        ).one()
        assert row == ("default", "owner", "active")

    command.downgrade(config, "20260822_0024")
    with session_factory(settings)() as database:
        assert "organizations" not in inspect(database.connection()).get_table_names()


def test_create_admin_bootstraps_default_owner_on_a_fresh_schema(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "fresh-admin.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    settings = Settings()
    create_schema(settings)
    monkeypatch.setattr("sys.stdin", StringIO("correct horse battery\n"))
    monkeypatch.setattr("sys.argv", ["pathlab-admin", "create-admin", "--password-stdin"])

    cli_main()

    with session_factory(settings)() as database:
        row = database.execute(
            text(
                "SELECT o.slug, m.role, m.status FROM organization_memberships m "
                "JOIN organizations o ON o.id = m.organization_id "
                "JOIN users u ON u.id = m.user_id WHERE u.username = 'admin'"
            )
        ).one()
        assert row == ("default", "owner", "active")
