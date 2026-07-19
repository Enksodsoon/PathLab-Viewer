from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from wsi_viewer.auth import issue_recovery_code
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.main import create_app
from wsi_viewer.models import Job, Slide, User
from wsi_viewer.security import hash_password


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="test-secret-that-is-long-enough",
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / "tus",
    )
    create_schema(settings)
    with session_factory(settings)() as database:
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


def _has_error(response: Response, status_code: int, code: str) -> bool:
    return response.status_code == status_code and response.json() == {
        "detail": {"code": code}
    }


def test_health_and_readiness(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.get("/livez").json() == {"status": "live"}
        assert client.get("/readyz").status_code == 200


def test_admin_session_requires_valid_password(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/auth/session", json={"username": "admin", "password": "incorrect"}
        )
        assert response.status_code == 401


def test_password_change_requires_csrf_and_revokes_sessions(tmp_path: Path) -> None:
    with _client(tmp_path) as client, TestClient(client.app) as other_session:
        unauthenticated = client.post(
            "/api/v1/auth/password",
            json={
                "currentPassword": "correct horse battery",
                "newPassword": "new correct horse battery",
            },
        )
        assert unauthenticated.status_code == 401

        csrf = _login(client)
        _login(other_session)
        denied = client.post(
            "/api/v1/auth/password",
            json={
                "currentPassword": "correct horse battery",
                "newPassword": "new correct horse battery",
            },
        )
        assert denied.status_code == 403

        changed = client.post(
            "/api/v1/auth/password",
            headers={"X-CSRF-Token": csrf},
            json={
                "currentPassword": "correct horse battery",
                "newPassword": "new correct horse battery",
            },
        )
        assert changed.status_code == 204
        changed_cookie = changed.headers["set-cookie"]
        if "pathlab_session=" not in changed_cookie or "Max-Age=0" not in changed_cookie:
            pytest.fail("Password change did not expire the session cookie")
        assert client.get("/api/v1/admin/slides").status_code == 401
        assert other_session.get("/api/v1/admin/slides").status_code == 401
        old_login = client.post(
            "/api/v1/auth/session",
            json={"username": "admin", "password": "correct horse battery"},
        )
        assert old_login.status_code == 401
        new_login = client.post(
            "/api/v1/auth/session",
            json={"username": "admin", "password": "new correct horse battery"},
        )
        assert new_login.status_code == 201


def test_password_change_returns_exact_errors_for_invalid_inputs(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        csrf = _login(client)
        headers = {"X-CSRF-Token": csrf}
        wrong_current = client.post(
            "/api/v1/auth/password",
            headers=headers,
            json={
                "currentPassword": "incorrect password",
                "newPassword": "new correct horse battery",
            },
        )
        reused_password = client.post(
            "/api/v1/auth/password",
            headers=headers,
            json={
                "currentPassword": "correct horse battery",
                "newPassword": "correct horse battery",
            },
        )
        weak_password = client.post(
            "/api/v1/auth/password",
            headers=headers,
            json={"currentPassword": "correct horse battery", "newPassword": "short"},
        )
        oversized_password = client.post(
            "/api/v1/auth/password",
            headers=headers,
            json={"currentPassword": "correct horse battery", "newPassword": "x" * 129},
        )

        if not _has_error(wrong_current, 400, "INVALID_PASSWORD"):
            pytest.fail("Wrong current password did not use the stable password error")
        if not _has_error(reused_password, 400, "PASSWORD_REUSE"):
            pytest.fail("Reused password did not use the stable reuse error")
        if not _has_error(weak_password, 400, "INVALID_PASSWORD"):
            pytest.fail("Weak password change did not use the stable password error")
        if not _has_error(oversized_password, 400, "INVALID_PASSWORD"):
            pytest.fail("Oversized password change did not use the stable password error")


def test_password_change_checks_session_and_csrf_before_parsing_json(tmp_path: Path) -> None:
    invalid_json = b'{"currentPassword":'
    headers = {"Content-Type": "application/json"}
    with _client(tmp_path) as client:
        unauthenticated = client.post(
            "/api/v1/auth/password", headers=headers, content=invalid_json
        )
        if not _has_error(unauthenticated, 401, "AUTH_REQUIRED"):
            pytest.fail("Malformed password change did not require authentication first")

        csrf = _login(client)
        missing_csrf = client.post(
            "/api/v1/auth/password", headers=headers, content=invalid_json
        )
        if not _has_error(missing_csrf, 403, "CSRF_INVALID"):
            pytest.fail("Malformed password change did not require CSRF first")

        authenticated_headers = {**headers, "X-CSRF-Token": csrf}
        malformed = client.post(
            "/api/v1/auth/password", headers=authenticated_headers, content=invalid_json
        )
        if not _has_error(malformed, 400, "INVALID_PASSWORD"):
            pytest.fail("Malformed password change did not use the stable password error")


def test_password_change_invalid_shapes_use_stable_error(tmp_path: Path) -> None:
    invalid_payloads = [
        {},
        {"currentPassword": None, "newPassword": None},
        {"currentPassword": [], "newPassword": {}},
    ]
    with _client(tmp_path) as client:
        csrf = _login(client)
        headers = {"X-CSRF-Token": csrf}
        for payload in invalid_payloads:
            response = client.post("/api/v1/auth/password", headers=headers, json=payload)
            if not _has_error(response, 400, "INVALID_PASSWORD"):
                pytest.fail("Invalid password-change shape did not use the stable password error")


def test_password_change_accepts_unicode_policy_boundaries(tmp_path: Path) -> None:
    minimum_password = "pässwörd安全12"
    maximum_password = "密" * 128
    if len(minimum_password) != 12 or len(maximum_password) != 128:
        pytest.fail("Password boundary fixture has the wrong character length")

    with _client(tmp_path / "minimum") as minimum_client:
        csrf = _login(minimum_client)
        changed = minimum_client.post(
            "/api/v1/auth/password",
            headers={"X-CSRF-Token": csrf},
            json={
                "currentPassword": "correct horse battery",
                "newPassword": minimum_password,
            },
        )
        assert changed.status_code == 204
        accepted = minimum_client.post(
            "/api/v1/auth/session",
            json={"username": "admin", "password": minimum_password},
        )
        assert accepted.status_code == 201

    with _client(tmp_path / "maximum") as maximum_client:
        csrf = _login(maximum_client)
        changed = maximum_client.post(
            "/api/v1/auth/password",
            headers={"X-CSRF-Token": csrf},
            json={
                "currentPassword": "correct horse battery",
                "newPassword": maximum_password,
            },
        )
        assert changed.status_code == 204
        accepted = maximum_client.post(
            "/api/v1/auth/session",
            json={"username": "admin", "password": maximum_password},
        )
        assert accepted.status_code == 201


def test_password_recovery_malformed_json_uses_generic_error(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/auth/password/recover",
            headers={"Content-Type": "application/json"},
            content=b'{"username":',
        )
        if not _has_error(response, 400, "INVALID_RECOVERY_CODE"):
            pytest.fail("Malformed recovery JSON did not use the generic recovery error")


def test_password_recovery_invalid_shapes_use_generic_error(tmp_path: Path) -> None:
    invalid_payloads = [
        {},
        {"username": None, "recoveryCode": None, "newPassword": None},
        {"username": [], "recoveryCode": {}, "newPassword": 1},
    ]
    with _client(tmp_path) as client:
        for payload in invalid_payloads:
            response = client.post("/api/v1/auth/password/recover", json=payload)
            if not _has_error(response, 400, "INVALID_RECOVERY_CODE"):
                pytest.fail("Invalid recovery shape did not use the generic recovery error")


def test_forgot_password_uses_generic_single_use_error_and_expires_cookie(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        _login(client)
        settings = client.app.state.settings
        with session_factory(settings)() as database:
            user = database.scalar(select(User).where(User.username == "admin"))
            assert user is not None
            code = issue_recovery_code(database, user)
            database.commit()

        reset = client.post(
            "/api/v1/auth/password/recover",
            json={
                "username": "admin",
                "recoveryCode": code,
                "newPassword": "new correct horse battery",
            },
        )
        assert reset.status_code == 204
        reset_cookie = reset.headers["set-cookie"]
        if "pathlab_session=" not in reset_cookie or "Max-Age=0" not in reset_cookie:
            pytest.fail("Password recovery did not expire the session cookie")
        assert client.get("/api/v1/admin/slides").status_code == 401

        reused = client.post(
            "/api/v1/auth/password/recover",
            json={
                "username": "admin",
                "recoveryCode": code,
                "newPassword": "another correct password",
            },
        )
        unknown = client.post(
            "/api/v1/auth/password/recover",
            json={
                "username": "missing",
                "recoveryCode": code,
                "newPassword": "another correct password",
            },
        )
        if not _has_error(reused, 400, "INVALID_RECOVERY_CODE"):
            pytest.fail("Reused recovery code did not use the generic recovery error")
        if not _has_error(unknown, 400, "INVALID_RECOVERY_CODE"):
            pytest.fail("Unknown recovery user did not use the generic recovery error")


def test_recovery_rejects_invalid_password_without_consuming_code(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        settings = client.app.state.settings
        with session_factory(settings)() as database:
            user = database.scalar(select(User).where(User.username == "admin"))
            assert user is not None
            code = issue_recovery_code(database, user)
            database.commit()

        weak_password = client.post(
            "/api/v1/auth/password/recover",
            json={"username": "admin", "recoveryCode": code, "newPassword": "short"},
        )
        oversized_password = client.post(
            "/api/v1/auth/password/recover",
            json={"username": "admin", "recoveryCode": code, "newPassword": "x" * 129},
        )
        if not _has_error(weak_password, 400, "INVALID_PASSWORD"):
            pytest.fail("Weak recovery password did not use the stable password error")
        if not _has_error(oversized_password, 400, "INVALID_PASSWORD"):
            pytest.fail("Oversized recovery password did not use the stable password error")

        recovered = client.post(
            "/api/v1/auth/password/recover",
            json={
                "username": "admin",
                "recoveryCode": code,
                "newPassword": "new correct horse battery",
            },
        )
        assert recovered.status_code == 204


def test_recovery_throttle_is_shared_across_api_workers(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'shared.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="test-secret-that-is-long-enough",
        secure_cookies=False,
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        database.add(User(username="admin", password_hash=hash_password("correct horse battery")))
        database.commit()

    with TestClient(create_app(settings)) as worker_one, TestClient(
        create_app(settings)
    ) as worker_two:
        payload = {
            "username": "admin",
            "recoveryCode": "wrong",
            "newPassword": "new correct horse battery",
        }
        for index in range(5):
            worker = worker_one if index % 2 == 0 else worker_two
            response = worker.post("/api/v1/auth/password/recover", json=payload)
            if not _has_error(response, 400, "INVALID_RECOVERY_CODE"):
                pytest.fail("Invalid recovery attempt did not use the generic recovery error")
        throttled = worker_two.post("/api/v1/auth/password/recover", json=payload)
        if not _has_error(throttled, 429, "AUTH_THROTTLED"):
            pytest.fail("Recovery throttle did not use the stable throttle error")


def test_slide_lifecycle_and_public_metadata(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        csrf = _login(client)
        created = client.post(
            "/api/v1/admin/slides",
            headers={"X-CSRF-Token": csrf},
            json={
                "displayName": "HER2 control",
                "filename": "private-name.ome.tif",
                "length": 4096,
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["slide"]["state"] == "uploading"
        assert "private-name" not in body["uploadUrl"]
        assert body["uploadToken"]

        slide_id = body["slide"]["id"]
        assert client.get("/api/v1/admin/slides").json()[0]["id"] == slide_id
        assert client.get(f"/api/v1/public/slides/{body['slide']['publicId']}").status_code == 404


def test_completed_tus_upload_is_signature_checked_and_queued(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        csrf = _login(client)
        settings = client.app.state.settings
        upload = settings.tus_internal_upload_dir / "tus-upload"
        upload.parent.mkdir(parents=True, exist_ok=True)
        upload.write_bytes(b"II*\x00" + b"payload")
        created = client.post(
            "/api/v1/admin/slides",
            headers={"X-CSRF-Token": csrf},
            json={"displayName": "Test", "filename": "x.ome.tif", "length": upload.stat().st_size},
        ).json()
        completed = client.post(
            "/api/v1/internal/uploads/complete",
            json={
                "token": created["uploadToken"],
                "path": str(upload),
                "length": upload.stat().st_size,
            },
        )
        assert completed.status_code == 202
        slides = client.get("/api/v1/admin/slides").json()
        assert slides[0]["state"] == "queued"


def test_tusd_hooks_authorize_and_finalize_reserved_upload(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        csrf = _login(client)
        settings = client.app.state.settings
        upload = settings.tus_internal_upload_dir / "hook-upload"
        upload.parent.mkdir(parents=True, exist_ok=True)
        upload.write_bytes(b"MM\x00*" + b"payload")
        created = client.post(
            "/api/v1/admin/slides",
            headers={"X-CSRF-Token": csrf},
            json={"displayName": "Hook", "filename": "x.ome.tif", "length": upload.stat().st_size},
        ).json()
        upload_info = {
            "Size": upload.stat().st_size,
            "Offset": upload.stat().st_size,
            "MetaData": {"uploadToken": created["uploadToken"]},
            "Storage": {"Path": str(upload)},
        }
        authorized = client.post(
            "/api/v1/internal/tus/hooks",
            json={"Type": "pre-create", "Event": {"Upload": upload_info}},
        )
        assert authorized.json()["RejectUpload"] is False
        finished = client.post(
            "/api/v1/internal/tus/hooks",
            json={"Type": "post-finish", "Event": {"Upload": upload_info}},
        )
        assert finished.status_code == 200
        assert client.get("/api/v1/admin/slides").json()[0]["state"] == "queued"


def test_completed_upload_rejects_non_tiff_without_moving_it(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        csrf = _login(client)
        settings = client.app.state.settings
        upload = settings.tus_internal_upload_dir / "not-tiff"
        upload.parent.mkdir(parents=True, exist_ok=True)
        upload.write_bytes(b"not a tiff")
        created = client.post(
            "/api/v1/admin/slides",
            headers={"X-CSRF-Token": csrf},
            json={"displayName": "Test", "filename": "x.ome.tif", "length": upload.stat().st_size},
        ).json()
        response = client.post(
            "/api/v1/internal/uploads/complete",
            json={
                "token": created["uploadToken"],
                "path": str(upload),
                "length": upload.stat().st_size,
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "INVALID_TIFF_SIGNATURE"


def test_private_preview_publish_and_delete_lifecycle(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        csrf = _login(client)
        settings = client.app.state.settings
        with session_factory(settings)() as database:
            slide = Slide(
                display_name="Preview slide",
                original_filename="private.ome.tif",
                source_bytes=100,
                state=SlideState.READY_PRIVATE,
                slide_metadata={"width": 48, "height": 32},
            )
            database.add(slide)
            database.commit()
            slide_id, public_id = slide.id, slide.public_id
        derivative = settings.data_root / "private" / slide_id
        (derivative / "slide_files" / "0").mkdir(parents=True)
        (derivative / "slide.dzi").write_text("<Image />", encoding="utf-8")
        (derivative / "slide_files" / "0" / "0_0.jpeg").write_bytes(b"jpeg")

        preview = client.get(f"/api/v1/admin/slides/{slide_id}")
        assert preview.status_code == 200
        assert preview.json()["tileSource"].endswith("/slide.dzi")
        tile = client.get(f"/api/v1/admin/slides/{slide_id}/preview/slide_files/0/0_0.jpeg")
        assert tile.content == b"jpeg"

        published = client.post(
            f"/api/v1/admin/slides/{slide_id}/publish", headers={"X-CSRF-Token": csrf}
        )
        assert published.status_code == 200
        assert client.get(f"/api/v1/public/slides/{public_id}").status_code == 200

        deleted = client.delete(f"/api/v1/admin/slides/{slide_id}", headers={"X-CSRF-Token": csrf})
        assert deleted.status_code == 202
        with session_factory(settings)() as database:
            assert database.query(Job).filter(Job.slide_id == slide_id, Job.kind == "delete").one()
