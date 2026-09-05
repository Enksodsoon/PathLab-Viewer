import hashlib
import io
from pathlib import Path

import numpy as np
import pytest
import tifffile
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select, text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.identity import ensure_default_owner_membership
from wsi_viewer.main import create_app
from wsi_viewer.models import Slide, User
from wsi_viewer.ome_ingest import serialize_ome_tile_index
from wsi_viewer.ome_tile_index import build_ome_tile_index
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password

STRONG_SECRET = "test-only-strong-secret-material-1234567890"


def _client(tmp_path: Path, *, internal_file_redirects: bool = False) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key=STRONG_SECRET,
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / "tus",
        internal_file_redirects=internal_file_redirects,
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        database.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        database.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
            {"head": ALEMBIC_HEAD},
        )
        admin = User(username="admin", password_hash=hash_password("correct horse battery"))
        database.add(admin)
        database.flush()
        ensure_default_owner_membership(database, admin)
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
            thumbnail_filename="thumbnail.jpg",
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
    (derivative / "thumbnail.jpg").write_bytes(b"thumbnail")
    return slide_id, public_id


def _ready_dynamic_slide(client: TestClient) -> tuple[str, str]:
    settings = client.app.state.settings
    with session_factory(settings)() as database:
        slide = Slide(
            display_name="Deidentified dynamic slide",
            original_filename="dynamic.ome.tif",
            source_bytes=1,
            state=SlideState.READY_PRIVATE,
            render_mode="ome_dynamic",
            privacy_status="private",
            slide_metadata={"width": 1024, "height": 1024, "physicalSizeX": 0.25},
        )
        database.add(slide)
        database.commit()
        slide_id, public_id = slide.id, slide.public_id
    root = settings.data_root / "originals" / slide_id
    root.mkdir(parents=True)
    source = root / "source.ome.tif"
    full = np.zeros((1024, 1024, 3), dtype=np.uint8)
    with tifffile.TiffWriter(source, ome=True, bigtiff=True) as writer:
        writer.write(
            full,
            metadata={"axes": "YXS"},
            photometric="ycbcr",
            compression="jpeg",
            tile=(512, 512),
            subifds=1,
        )
        writer.write(
            full[::2, ::2],
            photometric="ycbcr",
            compression="jpeg",
            tile=(512, 512),
            subfiletype=1,
        )
    index = build_ome_tile_index(source)
    (root / "tile-index.json").write_bytes(serialize_ome_tile_index(index))
    with session_factory(settings)() as database:
        slide = database.get(Slide, slide_id)
        assert slide is not None
        slide.source_bytes = source.stat().st_size
        slide.sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        database.commit()
    return slide_id, public_id


def test_production_settings_fail_closed() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", service_role="general")
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            service_role="general",
            secret_key="replace-with-at-least-32-random-bytes",
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            service_role="general",
            secret_key=STRONG_SECRET,
            secure_cookies=False,
        )

    settings = Settings(
        _env_file=None,
        environment="production",
        service_role="general",
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
        assert set(body) == {
            "publicId",
            "displayName",
            "state",
            "metadata",
            "thumbnailUrl",
            "tileSource",
        }
        assert body["metadata"] == {
            "width": 48,
            "height": 32,
            "physicalSizeX": 0.25,
        }
        assert body["tileSource"].startswith(f"/tiles/{public_id}/")
        assert body["tileSource"].endswith("/slide.dzi")
        assert body["thumbnailUrl"] == body["tileSource"].replace(
            "slide.dzi",
            "thumbnail.jpg",
        )
        annotation_paths = {
            getattr(route, "path", "")
            for route in client.app.routes
            if "annotations" in getattr(route, "path", "")
        }
        assert annotation_paths
        assert all(
            path.startswith(
                (
                    "/api/v2/admin/annotations/",
                    "/api/v1/desktop/slides/",
                )
            )
            for path in annotation_paths
        )
        assert not {"annotationsEnabled", "annotationVersion"} & set(body)
        version = body["tileSource"].split("/")[3]
        assert version.isdigit()
        delivery_root = (
            client.app.state.settings.data_root
            / "delivery"
            / "individual"
            / public_id
            / version
        )
        assert (delivery_root / "slide.dzi").read_text(encoding="utf-8") == "<Image />"

        tile = client.get(f"/api/v1/public/slides/{public_id}/tiles/slide.dzi")
        assert tile.status_code == 200
        assert tile.text == "<Image />"
        assert tile.headers["cache-control"] == "private, max-age=86400, immutable"
        assert client.get(
            f"/api/v1/public/slides/{public_id}/tiles/../source.ome.tif"
        ).status_code == 404

        settings = client.app.state.settings
        with session_factory(settings)() as database:
            slide = database.get(Slide, slide_id)
            assert slide is not None
            assert slide.privacy_status == "passed"
            assert slide.privacy_scanned_at is not None

        assert (
            client.post(f"/api/v1/admin/slides/{slide_id}/unpublish", headers=headers).status_code
            == 200
        )
        assert not (settings.data_root / "delivery" / "individual" / public_id).exists()


def test_dynamic_ome_publish_streams_tiles_without_public_source_or_derivatives(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        csrf = _login(client)
        slide_id, public_id = _ready_dynamic_slide(client)
        headers = {"X-CSRF-Token": csrf}

        published = client.post(
            f"/api/v1/admin/slides/{slide_id}/publish",
            headers=headers,
            json={"deidentifiedConfirmed": True},
        )
        assert published.status_code == 200
        assert not (client.app.state.settings.data_root / "public" / public_id).exists()
        assert not (
            client.app.state.settings.data_root / "delivery" / "individual" / public_id
        ).exists()

        public = client.get(f"/api/v1/public/slides/{public_id}")
        assert public.status_code == 200
        assert public.json()["tileSource"] == (
            f"/api/v1/public/slides/{public_id}/tiles/slide.dzi"
        )
        descriptor = client.get(public.json()["tileSource"])
        assert descriptor.status_code == 200
        assert b'Width="1024" Height="1024"' in descriptor.content
        tile = client.get(
            f"/api/v1/public/slides/{public_id}/tiles/slide_files/10/0_0.jpeg"
        )
        assert tile.status_code == 200
        with Image.open(io.BytesIO(tile.content)) as decoded:
            assert decoded.size == (512, 512)
        assert (
            client.get(
                f"/api/v1/public/slides/{public_id}/tiles/source.ome.tif",
                headers={"Range": "bytes=0-31"},
            ).status_code
            == 404
        )

        assert (
            client.post(
                f"/api/v1/admin/slides/{slide_id}/unpublish",
                headers=headers,
            ).status_code
            == 200
        )
        assert client.get(public.json()["tileSource"]).status_code == 404


def test_production_dynamic_route_authorizes_before_internal_tile_redirect(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, internal_file_redirects=True) as client:
        csrf = _login(client)
        slide_id, public_id = _ready_dynamic_slide(client)
        assert (
            client.post(
                f"/api/v1/admin/slides/{slide_id}/publish",
                headers={"X-CSRF-Token": csrf},
                json={"deidentifiedConfirmed": True},
            ).status_code
            == 200
        )

        redirected = client.get(
            f"/api/v1/public/slides/{public_id}/tiles/slide.dzi"
        )
        assert redirected.status_code == 200
        assert redirected.content == b""
        source = (
            client.app.state.settings.data_root
            / "originals"
            / slide_id
            / "source.ome.tif"
        )
        source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        assert redirected.headers["x-accel-redirect"] == (
            f"/_pathlab_ome/{slide_id}/{source_sha256}/slide.dzi"
        )
        denied = client.get(
            "/api/v1/public/slides/not-published/tiles/slide.dzi"
        )
        assert denied.status_code == 404
        assert "x-accel-redirect" not in denied.headers


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


def test_production_file_delivery_uses_internal_caddy_redirect(tmp_path: Path) -> None:
    with _client(tmp_path, internal_file_redirects=True) as client:
        csrf = _login(client)
        slide_id, public_id = _ready_slide(client)
        assert client.post(
            f"/api/v1/admin/slides/{slide_id}/publish",
            headers={"X-CSRF-Token": csrf},
            json={"deidentifiedConfirmed": True},
        ).status_code == 200

        tile = client.get(f"/api/v1/public/slides/{public_id}/tiles/slide.dzi")
        assert tile.status_code == 200
        assert tile.content == b""
        assert tile.headers["x-accel-redirect"] == (
            f"/pathlab-public/{public_id}/slide.dzi"
        )
        assert tile.headers["cache-control"] == "private, max-age=86400, immutable"


def test_public_proxy_and_deployment_configuration_disclose_no_live_target() -> None:
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")
    release = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")

    assert "@internal_api path /api/v1/internal/*" in caddyfile
    assert "handle @internal_api {\n\t\trespond 404\n\t}" in caddyfile
    assert caddyfile.index("handle @internal_api") < caddyfile.index("handle @backend")
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
    assert "handle_path /tiles/*" in caddyfile
    assert "root * /pathlab-individual" in caddyfile
    assert "root * /data" not in caddyfile
    assert "/pathlab-data" not in compose


def test_internal_api_bodies_are_bounded_before_json_parsing(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        oversized = b"{" + b" " * (64 * 1024)
        for path in (
            "/api/v1/internal/uploads/complete",
            "/api/v1/internal/tus/hooks",
        ):
            response = client.post(
                path,
                content=oversized,
                headers={"Content-Type": "application/json"},
            )
            assert response.status_code == 413
            assert response.json() == {"detail": {"code": "REQUEST_TOO_LARGE"}}


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
