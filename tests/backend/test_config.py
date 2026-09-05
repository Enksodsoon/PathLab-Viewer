from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from wsi_viewer.config import Settings
from wsi_viewer.main import create_app

LIMIT_ENVIRONMENT = {
    "PATHLAB_LIBVIPS_CONCURRENCY": "3",
    "PATHLAB_LIBVIPS_CACHE_MAX_MEM_BYTES": "536870912",
    "PATHLAB_LIBVIPS_CACHE_MAX_FILES": "64",
    "PATHLAB_LIBVIPS_CACHE_MAX_OPERATIONS": "50",
}


def test_libvips_limits_have_conservative_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in LIMIT_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.libvips_concurrency == 1
    assert settings.libvips_cache_max_mem_bytes == 256 * 1024**2
    assert settings.libvips_cache_max_files == 128
    assert settings.libvips_cache_max_operations == 100


def test_libvips_limits_accept_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in LIMIT_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=None)

    assert settings.libvips_concurrency == 3
    assert settings.libvips_cache_max_mem_bytes == 536870912
    assert settings.libvips_cache_max_files == 64
    assert settings.libvips_cache_max_operations == 50


def test_annotations_are_disabled_by_default_and_accept_an_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PATHLAB_ANNOTATIONS_ENABLED", raising=False)

    assert Settings(_env_file=None).annotations_enabled is False

    monkeypatch.setenv("PATHLAB_ANNOTATIONS_ENABLED", "true")
    assert Settings(_env_file=None).annotations_enabled is True


def test_admin_annotation_canary_is_default_off_and_effective_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PATHLAB_ANNOTATIONS_ENABLED", raising=False)
    monkeypatch.delenv("PATHLAB_ADMIN_ANNOTATION_CANARY_ENABLED", raising=False)

    assert Settings(_env_file=None).admin_annotations_enabled is False

    monkeypatch.setenv("PATHLAB_ADMIN_ANNOTATION_CANARY_ENABLED", "true")
    settings = Settings(_env_file=None)
    assert settings.annotations_enabled is False
    assert settings.admin_annotation_canary_enabled is True
    assert settings.admin_annotations_enabled is True


def test_classroom_is_disabled_by_default_and_accepts_an_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PATHLAB_CLASSROOM_ENABLED", raising=False)

    assert Settings(_env_file=None).classroom_enabled is False

    monkeypatch.setenv("PATHLAB_CLASSROOM_ENABLED", "true")
    assert Settings(_env_file=None).classroom_enabled is True


def test_assessment_is_disabled_by_default_and_accepts_an_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PATHLAB_ASSESSMENT_ENABLED", raising=False)

    assert Settings(_env_file=None).assessment_enabled is False

    monkeypatch.setenv("PATHLAB_ASSESSMENT_ENABLED", "true")
    assert Settings(_env_file=None).assessment_enabled is True


@pytest.mark.parametrize("value", (1, 1500, 2000))
def test_classroom_participant_limit_accepts_declared_range(value: int) -> None:
    settings = Settings(_env_file=None, classroom_max_participants=value)

    assert settings.classroom_max_participants == value


@pytest.mark.parametrize("value", (0, 2001))
def test_classroom_participant_limit_rejects_values_outside_declared_range(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, classroom_max_participants=value)


def test_classroom_participant_limit_accepts_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATHLAB_CLASSROOM_MAX_PARTICIPANTS", "1500")

    assert Settings(_env_file=None).classroom_max_participants == 1500


@pytest.mark.parametrize("role", ("general", "classroom", "assessment", "worker", "tile", "all"))
def test_service_role_accepts_the_declared_process_topologies(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    monkeypatch.setenv("PATHLAB_SERVICE_ROLE", role)
    monkeypatch.delenv("PATHLAB_CLASSROOM_SERVICE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.service_role == role
    assert settings.classroom_service_url == "http://classroom:8001"


def test_production_rejects_the_combined_service_role() -> None:
    with pytest.raises(ValidationError, match="combined service role"):
        Settings(
            _env_file=None,
            environment="production",
            service_role="all",
            secret_key="unique-production-secret-that-is-long-enough",
        )


def test_production_general_role_does_not_require_the_classroom_singleton() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        service_role="general",
        secret_key="unique-production-secret-that-is-long-enough",
        classroom_enabled=True,
        classroom_singleton=False,
    )

    assert settings.service_role == "general"


def test_production_assessment_requires_postgres_and_identity_governance() -> None:
    common = {
        "_env_file": None,
        "environment": "production",
        "service_role": "assessment",
        "secret_key": "unique-production-secret-that-is-long-enough",
        "assessment_enabled": True,
    }

    with pytest.raises(ValidationError, match="Assessment requires PostgreSQL"):
        Settings(**common, identity_governance_enabled=True)

    with pytest.raises(ValidationError, match="identity governance"):
        Settings(
            **common,
            database_url="postgresql+psycopg://pathlab@postgres/pathlab",
            identity_governance_enabled=False,
        )


@pytest.mark.parametrize(
    ("role", "path", "classroom_enabled", "expected_status"),
    (
        ("general", "/api/v1/auth/session", True, 422),
        ("general", "/api/v1/classroom/join", True, 404),
        ("classroom", "/api/v1/auth/session", True, 404),
        ("classroom", "/api/v1/classroom/join", True, 422),
        ("assessment", "/api/v1/auth/session", True, 404),
        ("assessment", "/api/v2/assessment/administrations/example", True, 404),
        ("all", "/api/v1/auth/session", True, 422),
        ("all", "/api/v1/classroom/join", True, 422),
    ),
)
def test_service_roles_scope_http_route_families_and_preserve_combined_development(
    tmp_path: Path,
    role: str,
    path: str,
    classroom_enabled: bool,
    expected_status: int,
) -> None:
    settings = Settings(
        _env_file=None,
        service_role=role,
        classroom_enabled=classroom_enabled,
        database_url=f"sqlite:///{tmp_path / f'{role}.sqlite3'}",
        data_root=tmp_path / role,
        secure_cookies=False,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(path, json={})

    assert response.status_code == expected_status


def test_classroom_role_exposes_only_classroom_and_health_routes(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            service_role="classroom",
            classroom_enabled=True,
            database_url=f"sqlite:///{tmp_path / 'classroom-only.sqlite3'}",
            data_root=tmp_path / "classroom-only",
        )
    )
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/livez" in paths
    assert "/readyz" in paths
    assert "/api/v1/classroom/join" in paths
    assert "/api/v1/auth/session" not in paths
    assert "/api/v1/admin/slides" not in paths
    assert "/openapi.json" not in paths


def test_assessment_role_exposes_only_assessment_and_health_routes(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            service_role="assessment",
            assessment_enabled=True,
            database_url=f"sqlite:///{tmp_path / 'assessment-only.sqlite3'}",
            data_root=tmp_path / "assessment-only",
        )
    )
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/livez" in paths
    assert "/readyz" in paths
    assert "/api/v2/assessment/administrations/{public_id}" in paths
    assert "/api/v1/auth/session" not in paths
    assert "/api/v1/admin/slides" not in paths
    assert "/api/v1/classroom/join" not in paths
    assert "/openapi.json" not in paths


def test_production_classroom_requires_declared_singleton_topology() -> None:
    with pytest.raises(ValidationError, match="singleton topology"):
        Settings(
            _env_file=None,
            environment="production",
            service_role="classroom",
            secret_key="unique-production-secret-that-is-long-enough",
            classroom_enabled=True,
            classroom_singleton=False,
        )


def test_multi_share_is_enabled_by_default_and_accepts_the_kill_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PATHLAB_MULTI_SHARE_ENABLED", raising=False)

    assert Settings(_env_file=None).multi_share_enabled is True

    monkeypatch.setenv("PATHLAB_MULTI_SHARE_ENABLED", "false")
    assert Settings(_env_file=None).multi_share_enabled is False


def test_desktop_ome_dynamic_is_enabled_by_default_and_has_a_kill_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PATHLAB_DESKTOP_OME_DYNAMIC_ENABLED", raising=False)
    assert Settings(_env_file=None).desktop_ome_dynamic_enabled is True

    monkeypatch.setenv("PATHLAB_DESKTOP_OME_DYNAMIC_ENABLED", "false")
    assert Settings(_env_file=None).desktop_ome_dynamic_enabled is False


@pytest.mark.parametrize(
    "field",
    (
        "libvips_concurrency",
        "libvips_cache_max_mem_bytes",
        "libvips_cache_max_files",
        "libvips_cache_max_operations",
    ),
)
@pytest.mark.parametrize("value", (0, -1))
def test_libvips_limits_reject_non_positive_values(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_tile_cache_limits_are_ordered_and_bounded() -> None:
    settings = Settings(_env_file=None)
    assert settings.tile_cache_max_bytes == 2 * 1024**3
    assert settings.tile_cache_low_water_bytes == 1792 * 1024**2
    assert settings.tile_cache_memory_bytes == 256 * 1024**2

    with pytest.raises(ValueError, match="low-water"):
        Settings(
            _env_file=None,
            tile_cache_max_bytes=100,
            tile_cache_low_water_bytes=100,
        )
    with pytest.raises(ValueError, match="temporary"):
        Settings(_env_file=None, tile_cache_max_temp_bytes=8 * 1024**2 + 1)
    with pytest.raises(ValueError, match="memory"):
        Settings(_env_file=None, tile_cache_memory_bytes=512 * 1024**2 + 1)
