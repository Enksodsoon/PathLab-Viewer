import os
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from wsi_viewer.annotations import utcnow as annotation_now
from wsi_viewer.config import Settings
from wsi_viewer.desktop_sync import decode_library_cursor, encode_library_cursor
from wsi_viewer.domain import SlideState
from wsi_viewer.library import apply_sort_and_cursor, encode_cursor
from wsi_viewer.library import utcnow as library_now
from wsi_viewer.main import create_app
from wsi_viewer.models import Base, DesktopCredential, Slide, StudyCourse, StudyPack, User
from wsi_viewer.publication import delivery_version, ensure_grant
from wsi_viewer.storage import StorageLayout
from wsi_viewer.time_support import as_utc

POSTGRES_TEST_URL = os.getenv("PATHLAB_POSTGRES_TEST_URL")
BANGKOK = timezone(timedelta(hours=7))
INSTANT = datetime(2026, 9, 7, 3, 12, 45, 123456, tzinfo=UTC)


@pytest.mark.skipif(POSTGRES_TEST_URL is None, reason="isolated PostgreSQL URL required")
@pytest.mark.parametrize("zone", ["UTC", "Asia/Bangkok"])
@pytest.mark.parametrize("cursor_kind", ["desktop", "library"])
@pytest.mark.parametrize("aware", [False, True])
def test_cursor_keeps_the_same_page_boundary(zone: str, cursor_kind: str, aware: bool) -> None:
    assert POSTGRES_TEST_URL is not None
    engine = create_engine(POSTGRES_TEST_URL)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT set_config('TimeZone', :zone, false)"), {"zone": zone})
            connection.execute(text("CREATE SCHEMA time_cursors"))
            connection.execute(text("SET search_path TO time_cursors"))
            Base.metadata.create_all(connection)
            with Session(connection) as database:
                slide = _slide()
                slide.updated_at = INSTANT
                database.add(slide)
                database.flush()
                cursor_slide = _slide()
                cursor_slide.updated_at = (
                    INSTANT.astimezone(BANGKOK) if aware else INSTANT.replace(tzinfo=None)
                )
                if cursor_kind == "desktop":
                    boundary, _ = decode_library_cursor(encode_library_cursor(cursor_slide))
                    statement = select(Slide).where(Slide.updated_at > boundary)
                else:
                    statement = apply_sort_and_cursor(
                        select(Slide), sort="updated_asc",
                        cursor=encode_cursor(cursor_slide.updated_at.isoformat(), slide.id),
                    )
                assert database.scalars(statement).all() == []
            connection.rollback()
    finally:
        engine.dispose()


def _slide() -> Slide:
    return Slide(
        id="time-slide", public_id="time-public", display_name="Time test",
        original_filename="synthetic.ome.tif", source_bytes=1,
        state=SlideState.READY_PRIVATE, published_at=INSTANT,
    )


def test_delivery_version_preserves_instant_across_offsets() -> None:
    slide = _slide()
    expected = delivery_version(slide)
    slide.published_at = INSTANT.astimezone(BANGKOK)
    assert delivery_version(slide) == expected
    slide.published_at = INSTANT.replace(tzinfo=None)
    assert delivery_version(slide) == expected


@pytest.mark.parametrize("clock", [annotation_now, library_now])
def test_database_write_clocks_are_aware(clock: Callable[[], datetime]) -> None:
    assert clock().utcoffset() == timedelta(0)


@pytest.mark.parametrize("scenario", ["bound", "canonical", "copied", "ambiguous", "stale"])
def test_existing_delivery_requires_unique_historical_binding(
    tmp_path: Path, scenario: str,
) -> None:
    slide = _slide()
    storage = StorageLayout(tmp_path)
    canonical = delivery_version(slide)
    descriptor = storage.public_for(slide.public_id) / "slide.dzi"
    descriptor.parent.mkdir(parents=True)
    descriptor.write_text("current descriptor", encoding="utf-8")
    legacy = INSTANT.astimezone(BANGKOK).strftime("%Y%m%d%H%M%S%f")
    target = storage.individual_delivery_for(slide.public_id, legacy)
    target.mkdir(parents=True)
    if scenario == "copied":
        shutil.copyfile(descriptor, target / "slide.dzi")
    else:
        os.link(descriptor, target / "slide.dzi")
    if scenario == "ambiguous":
        other = storage.individual_delivery_for(
            slide.public_id, (INSTANT + timedelta(hours=8)).strftime("%Y%m%d%H%M%S%f")
        )
        other.mkdir()
        os.link(descriptor, other / "slide.dzi")
    if scenario == "canonical":
        storage.individual_delivery_for(slide.public_id, canonical).mkdir()
    if scenario == "stale":
        slide.published_at = INSTANT + timedelta(days=2)
        canonical = delivery_version(slide)
    assert delivery_version(slide, storage) == (legacy if scenario == "bound" else canonical)
    # The choice remains stable after a PostgreSQL session changes timezone.
    assert slide.published_at is not None
    slide.published_at = as_utc(slide.published_at).astimezone(BANGKOK)
    assert delivery_version(slide, storage) == (legacy if scenario == "bound" else canonical)


@pytest.mark.skipif(POSTGRES_TEST_URL is None, reason="isolated PostgreSQL URL required")
@pytest.mark.parametrize("zone", ["UTC", "Asia/Bangkok"])
def test_publication_write_and_reload_preserve_time_and_path(tmp_path: Path, zone: str) -> None:
    assert POSTGRES_TEST_URL is not None
    engine = create_engine(POSTGRES_TEST_URL)
    storage = StorageLayout(tmp_path)
    slide = _slide()
    slide.published_at = None
    private = storage.for_slide(slide.id).private_derivative
    private.mkdir(parents=True)
    (private / "slide.dzi").write_text("<Image />", encoding="utf-8")
    with engine.connect() as connection:
        connection.execute(text("SELECT set_config('TimeZone', :zone, false)"), {"zone": zone})
        # A temporary schema isolates this regression from migration/Classroom fixtures.
        connection.execute(text("CREATE SCHEMA time_regression"))
        connection.execute(text("SET search_path TO time_regression"))
        Base.metadata.create_all(connection)
        with Session(connection) as database:
            database.add(slide)
            before = datetime.now(UTC)
            ensure_grant(database, storage, slide, "individual", slide.id)
            database.flush()
            version = delivery_version(slide)
            database.expire(slide)
            assert slide.published_at is not None
            assert before <= as_utc(slide.published_at) <= datetime.now(UTC)
            assert delivery_version(slide) == version
            assert storage.individual_delivery_for(slide.public_id, version).is_dir()
        connection.rollback()
    engine.dispose()


@pytest.mark.skipif(POSTGRES_TEST_URL is None, reason="isolated PostgreSQL URL required")
@pytest.mark.parametrize("zone", ["UTC", "Asia/Bangkok"])
def test_study_and_desktop_serializers_preserve_loaded_instants(tmp_path: Path, zone: str) -> None:
    assert POSTGRES_TEST_URL is not None
    settings = Settings(
        _env_file=None, database_url=POSTGRES_TEST_URL, data_root=tmp_path,
        study_mode_enabled=True, secret_key="synthetic-time-regression-secret-long-enough",
    )
    app = create_app(settings)
    endpoints = {
        route.path: route.endpoint for route in app.routes
        if isinstance(route, APIRoute) and "GET" in route.methods
    }
    engine = create_engine(POSTGRES_TEST_URL)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT set_config('TimeZone', :zone, false)"), {"zone": zone})
            connection.execute(text("CREATE SCHEMA time_serializers"))
            connection.execute(text("SET search_path TO time_serializers"))
            Base.metadata.create_all(connection)
            with Session(connection) as database:
                user = User(id="time-user", username="synthetic", password_hash="unused")
                database.add(user)
                database.flush()
                pack = StudyPack(
                    id="time-pack", pack_key="time", version=1, title="Time",
                    checksum="a" * 64, definition={}, created_by_user_id=user.id,
                    created_at=INSTANT.astimezone(BANGKOK),
                )
                database.add(pack)
                database.flush()
                database.add(StudyCourse(
                    pack_id=pack.id, title="Time", created_by_user_id=user.id,
                    ends_at=INSTANT, purge_after=INSTANT,
                    pilot_acknowledged_at=INSTANT.astimezone(BANGKOK),
                ))
                credential = DesktopCredential(
                    id="time-credential", user_id=user.id, device_name="Time",
                    expires_at=INSTANT.astimezone(BANGKOK),
                )
                database.add(credential)
                database.flush()
                database.expire_all()
                # Exercise the registered serializers with real loaded values;
                # authentication is covered by the existing API suites.
                courses = endpoints["/api/v1/admin/study/courses"](database=database)
                for field in ("endsAt", "purgeAfter", "pilotAcknowledgedAt"):
                    assert datetime.fromisoformat(courses[0][field]) == INSTANT
                packs = endpoints["/api/v1/admin/study/packs"](database=database)
                assert datetime.fromisoformat(packs[0]["createdAt"]) == INSTANT
                result = endpoints["/api/v1/desktop/credential"](authenticated=credential)
                assert datetime.fromisoformat(result["expiresAt"]) == INSTANT
            connection.rollback()
    finally:
        engine.dispose()
