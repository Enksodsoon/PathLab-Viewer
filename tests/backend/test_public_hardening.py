from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.main import create_app
from wsi_viewer.models import Slide, User
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password

STRONG_SECRET = "test-only-strong-secret-material-1234567890"


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key=STRONG_SECRET,
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / "tus",
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        database.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        database.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
            {"head": ALEMBIC_HEAD},
        )
        database.add(User(username="admin", password_hash=hash_password("correct horse battery")))
        database.commit()
    return TestClient(create_app(settings))


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/session",
        json={"username": "admin", "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return str(response.json()["csrfToken"])


def _ready_slide(client: TestClient) -> tuple[str, str]:
    settings = client.app.state.settings
    with session_factory(settings)() as database:
        slide = Slide(
            display_name="Deidentified teaching slide",
            original_filename="private-source-name.ome.tif",
            source_bytes=100,
            state=SlideState.READY_PRIVATE,
            slide_metadata={
                "width": 48,
                "height": 32,
                "physicalSizeX": 0.25,
                "physicalSizeY": 0.25,
                "physicalSizeUnit": "micrometer",
                "bitsPerSample": 8,
                "hasIccProfile": False,
                "futurePrivateField": "must-not-be-public",
            },
        )
        database.add(slide)
        database.commit()
        slide_id, public_id = slide.id, slide.public_id
    derivative = settings.data_root / "private" / slide_id
    (derivative / "slide_files" / "0").mkdir(parents=True)
    (derivative / "slide.dzi").write_text("<Image />", encoding="utf-8")
    (derivative / "slide_files" / "0" / "0_0.jpeg").write_bytes(b"jpeg")
    return slide_id, public_id


def test_production_settings_fail_closed() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production")
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="replace-with-at-least-32-random-bytes",
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            secret_key=STRONG_SECRET,
            secure_cookies=False,
        )

    settings = Settings(
        _env_file=None,
        environment="production",
        secret_key=STRONG_SECRET,
        secure_cookies=True,
    )
    assert settings.environment == "production"


def test_single_slide_publish_requires_explicit_deidentification_and_minimizes_metadata(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        csrf = _login(client)
        slide_id, public_id = _ready_slide(client)
        headers = {"X-CSRF-Token": csrf}

        missing = client.post(f"/api/v1/admin/slides/{slide_id}/publish", headers=headers)
        assert missing.status_code == 422
        assert missing.json() == {"detail": {"code": "DEIDENTIFICATION_CONFIRMATION_REQUIRED"}}

        denied = client.post(
            f"/api/v1/admin/slides/{slide_id}/publish",
            headers=headers,
            json={"deidentifiedConfirmed": False},
        )
        assert denied.status_code == 422
        assert denied.json() == {"detail": {"code": "DEIDENTIFICATION_CONFIRMATION_REQUIRED"}}

        published = client.post(
            f"/api/v1/admin/slides/{slide_id}/publish",
            headers=headers,
            json={"deidentifiedConfirmed": True},
        )
        assert published.status_code == 200

        public = client.get(f"/api/v1/public/slides/{public_id}")
        assert public.status_code == 200
        body = public.json()
        assert set(body) == {"publicId", "displayName", "state", "metadata", "tileSource"}
        assert body["metadata"] == {
            "width": 48,
            "height": 32,
            "physicalSizeX": 0.25,
        }

        settings = client.app.state.settings
        with session_factory(settings)() as database:
            slide = database.get(Slide, slide_id)
            assert slide is not None
            assert slide.privacy_status == "passed"
            assert slide.privacy_scanned_at is not None


def test_public_fields_cannot_change_while_shared_and_private_edits_reset_review(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        csrf = _login(client)
        slide_id, _ = _ready_slide(client)
        headers = {"X-CSRF-Token": csrf}
        assert (
            client.post(
                f"/api/v1/admin/slides/{slide_id}/publish",
                headers=headers,
                json={"deidentifiedConfirmed": True},
            ).status_code
            == 200
        )

        blocked = client.post(
            "/api/v2/admin/slides/batch-metadata",
            headers=headers,
            json={"slideIds": [slide_id], "displayName": "Changed while public"},
        )
        assert blocked.status_code == 409
        assert blocked.json() == {"detail": {"code": "SLIDE_PUBLIC"}}

        private_note = client.post(
            "/api/v2/admin/slides/batch-metadata",
            headers=headers,
            json={"slideIds": [slide_id], "adminNotes": "Private administrator note"},
        )
        assert private_note.status_code == 200

        assert (
            client.post(f"/api/v1/admin/slides/{slide_id}/unpublish", headers=headers).status_code
            == 200
        )
        changed = client.post(
            "/api/v2/admin/slides/batch-metadata",
            headers=headers,
            json={"slideIds": [slide_id], "displayName": "Reviewed again"},
        )
        assert changed.status_code == 200

        settings = client.app.state.settings
        with session_factory(settings)() as database:
            slide = database.scalar(select(Slide).where(Slide.id == slide_id))
            assert slide is not None
            assert slide.display_name == "Reviewed again"
            assert slide.admin_notes == "Private administrator note"
            assert slide.privacy_status == "pending"
            assert slide.privacy_scanned_at is None


def test_public_proxy_and_deployment_configuration_disclose_no_live_target() -> None:
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")
    release = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")

    assert "@internal_api path /api/v1/internal/*" in caddyfile
    assert "respond @internal_api 404" in caddyfile
    assert caddyfile.index("respond @internal_api 404") < caddyfile.index("handle @backend")
    assert 'Content-Security-Policy "' in caddyfile
    assert 'Strict-Transport-Security "' in caddyfile
    assert 'X-Robots-Tag "noindex, nofollow, noarchive"' in caddyfile

    public_text = "\n".join((release, workflow))
    assert "sslip.io" not in public_text
    assert "140-245-126-212" not in public_text
    assert 'HEALTH_URL="https://${DOMAIN}/readyz"' in release
    assert "url: https://" not in workflow
    assert "Readiness: http" not in workflow
    assert "PATHLAB_ENVIRONMENT: production" in compose


def test_ci_contains_public_repository_security_gates() -> None:
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    security = Path(".github/workflows/security.yml").read_text(encoding="utf-8")
    deploy = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
    dependabot = Path(".github/dependabot.yml").read_text(encoding="utf-8")

    assert ci.count("persist-credentials: false") >= 3
    assert "scripts/check_public_repository.py" in security
    assert "pip-audit" in security
    assert "pnpm audit --audit-level high" in security
    assert "github/codeql-action" in security
    for workflow in (ci, security, deploy):
        uses_lines = [
            line.strip()
            for line in workflow.splitlines()
            if line.lstrip().startswith("- uses:")
        ]
        assert uses_lines
        for line in uses_lines:
            revision = line.split("@", 1)[1].split()[0]
            assert len(revision) == 40
            assert all(character in "0123456789abcdef" for character in revision)
    assert "package-ecosystem: pip" in dependabot
    assert "package-ecosystem: npm" in dependabot
    assert "package-ecosystem: github-actions" in dependabot
    assert "package-ecosystem: docker" in dependabot
