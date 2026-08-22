from __future__ import annotations

from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
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
        database.add_all([second, target])
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
