import asyncio
import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.pool import QueuePool
from starlette.requests import Request
from starlette.responses import StreamingResponse
from wsi_viewer.config import Settings
from wsi_viewer.database import engine_for, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.main import create_app
from wsi_viewer.models import Folder, PublicationGrant, Slide, User
from wsi_viewer.publication import delivery_version
from wsi_viewer.security import hash_password

POSTGRES_TEST_URL = os.getenv("PATHLAB_POSTGRES_TEST_URL")


@pytest.mark.skipif(
    POSTGRES_TEST_URL is None,
    reason="PATHLAB_POSTGRES_TEST_URL is required for the isolated PostgreSQL test",
)
def test_postgres_classroom_sse_yield_holds_no_database_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert POSTGRES_TEST_URL is not None
    monkeypatch.setenv("PATHLAB_DATABASE_URL", POSTGRES_TEST_URL)
    command.downgrade(Config("alembic.ini"), "base")
    command.upgrade(Config("alembic.ini"), "head")

    shared = {
        "database_url": POSTGRES_TEST_URL,
        "data_root": tmp_path / "data",
        "secret_key": "postgres-classroom-secret-that-is-long-enough",
        "secure_cookies": False,
        "classroom_enabled": True,
        "classroom_protection_enabled": True,
        "classroom_singleton": True,
    }
    general_settings = Settings(_env_file=None, service_role="general", **shared)
    classroom_settings = Settings(_env_file=None, service_role="classroom", **shared)
    with session_factory(general_settings)() as database:
        database.add(
            User(
                id="postgres-classroom-admin",
                username="postgres-classroom-admin",
                password_hash=hash_password("correct horse battery"),
            )
        )
        database.add(
            Folder(
                id="postgres-classroom-folder",
                name="PostgreSQL teaching",
                normalized_name="postgresql teaching",
            )
        )
        slide = Slide(
            id="postgres-classroom-slide",
            public_id="postgres-classroom-public",
            display_name="Synthetic PostgreSQL slide",
            original_filename="synthetic.ome.tiff",
            source_bytes=1,
            derivative_bytes=1,
            derivative_file_count=2,
            render_mode="static_dzi",
            state=SlideState.PUBLISHED,
            slide_metadata={
                "width": 100,
                "height": 100,
                "dziTileSize": 512,
                "dziFormat": "jpg",
            },
            sha256="a" * 64,
            folder_id="postgres-classroom-folder",
            published_at=datetime.now(UTC),
            privacy_status="passed",
        )
        database.add(slide)
        database.flush()
        database.add(
            PublicationGrant(
                slide_id=slide.id,
                source_type="individual",
                source_id=slide.id,
            )
        )
        database.commit()
        version = delivery_version(slide)

    derivative = (
        classroom_settings.data_root
        / "delivery"
        / "individual"
        / "postgres-classroom-public"
        / version
    )
    (derivative / "slide_files" / "0").mkdir(parents=True)
    (derivative / "slide.dzi").write_text(
        '<Image TileSize="512" Overlap="1" Format="jpg">'
        '<Size Width="100" Height="100"/></Image>',
        encoding="utf-8",
    )
    (derivative / "slide_files" / "0" / "0_0.jpg").write_bytes(b"tile")

    with (
        TestClient(create_app(general_settings)) as general,
        TestClient(create_app(classroom_settings)) as classroom,
    ):
        login = general.post(
            "/api/v1/auth/session",
            json={
                "username": "postgres-classroom-admin",
                "password": "correct horse battery",
            },
        )
        assert login.status_code == 201, login.text
        for name, value in general.cookies.items():
            classroom.cookies.set(name, value)
        created_response = classroom.post(
            "/api/v1/admin/classroom/sessions",
            headers={"X-CSRF-Token": login.json()["csrfToken"]},
            json={"slideIds": ["postgres-classroom-slide"]},
        )
        assert created_response.status_code == 201, created_response.text
        created = created_response.json()
        joined_response = classroom.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Synthetic learner"},
        )
        assert joined_response.status_code == 201, joined_response.text

        app = cast(FastAPI, classroom.app)
        route = next(
            cast(APIRoute, route)
            for route in app.routes
            if getattr(route, "path", None)
            == "/api/v1/classroom/sessions/{session_id}/events"
        )
        path = f"/api/v1/classroom/sessions/{created['id']}/events"
        cookie = "; ".join(f"{key}={value}" for key, value in classroom.cookies.items())
        request = Request(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [(b"cookie", cookie.encode())],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "root_path": "",
            }
        )

        async def inspect_open_stream() -> str:
            response = cast(StreamingResponse, route.endpoint(created["id"], request))
            body = cast(AsyncGenerator[str | bytes | memoryview, None], response.body_iterator)
            first = cast(str, await anext(body))
            pool = engine_for(classroom_settings).pool
            assert isinstance(pool, QueuePool)
            assert pool.size() == 4
            assert pool.checkedout() == 0
            await body.aclose()
            return first

        first_event = asyncio.run(inspect_open_stream())

    assert first_event.startswith("event: stream-ready")
