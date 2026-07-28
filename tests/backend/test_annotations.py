import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event
from time import sleep
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.main import create_app
from wsi_viewer.models import (
    Annotation,
    AnnotationLayer,
    AnnotationRevision,
    AuditEvent,
    Slide,
    User,
)
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password

PASSWORD = "correct horse battery"
SECRET = "annotation-tests-use-a-long-random-secret"


def _client(tmp_path: Path, *, enabled: bool) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / f'annotations-{enabled}.sqlite3'}",
        data_root=tmp_path / f"data-{enabled}",
        secret_key=SECRET,
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / f"tus-{enabled}",
        annotations_enabled=enabled,
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        database.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        database.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
            {"head": ALEMBIC_HEAD},
        )
        database.add(User(username="admin", password_hash=hash_password(PASSWORD)))
        database.commit()
    return TestClient(create_app(settings))


def _login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={"username": "admin", "password": PASSWORD},
    )
    assert response.status_code == 201
    return {"X-CSRF-Token": str(response.json()["csrfToken"])}


def _slide(
    client: TestClient,
    *,
    slide_id: str = "annotation-slide",
    state: SlideState = SlideState.READY_PRIVATE,
) -> Slide:
    with session_factory(client.app.state.settings)() as database:
        slide = Slide(
            id=slide_id,
            display_name="Annotation source",
            original_filename="annotation-source.ome.tif",
            source_bytes=10,
            state=state,
            privacy_status="passed",
            slide_metadata={
                "width": 1000,
                "height": 500,
                "physicalSizeX": 0.25,
                "physicalSizeY": 0.5,
                "physicalSizeUnit": "µm",
            },
        )
        database.add(slide)
        database.commit()
        database.refresh(slide)
        return slide


def _layer_payload(*, base_version: int = 0, name: str = "Tumor") -> dict[str, Any]:
    return {
        "mutationId": str(uuid.uuid4()),
        "baseVersion": base_version,
        "name": name,
        "sortOrder": 0,
        "visible": True,
        "locked": False,
        "opacity": 0.8,
    }


def _item_payload(layer_id: str, *, item_id: str | None = None) -> dict[str, Any]:
    return {
        "id": item_id or str(uuid.uuid4()),
        "layerId": layer_id,
        "geometry": {
            "type": "polygon",
            "points": [
                {"x": 10, "y": 20},
                {"x": 50, "y": 20},
                {"x": 50, "y": 60},
                {"x": 10, "y": 60},
            ],
        },
        "style": {
            "strokeColor": "#c43d3d",
            "fillColor": "#c43d3d",
            "strokeWidth": 2,
            "opacity": 0.35,
            "labelVisible": True,
        },
        "metadata": {
            "title": "Tumor bed",
            "classification": "Tumor",
            "tags": ["teaching"],
            "notes": "Manual region",
        },
    }


def _create_layer(client: TestClient, slide_id: str, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        f"/api/v2/admin/annotations/slides/{slide_id}/layers",
        headers=headers,
        json=_layer_payload(),
    )
    assert response.status_code == 201
    return response.json()


def _batch(
    client: TestClient,
    slide_id: str,
    headers: dict[str, str],
    *,
    base_version: int,
    operations: list[dict[str, Any]],
    mutation_id: str | None = None,
):
    return client.post(
        f"/api/v2/admin/annotations/slides/{slide_id}/batch",
        headers=headers,
        json={
            "mutationId": mutation_id or str(uuid.uuid4()),
            "baseVersion": base_version,
            "operations": operations,
        },
    )


def test_first_annotation_atomically_materializes_requested_default_layer(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client)
        layer_id = str(uuid.uuid4())
        item = _item_payload(layer_id)
        response = client.post(
            f"/api/v2/admin/annotations/slides/{slide.id}/batch",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 0,
                "ensureLayer": {
                    "id": layer_id,
                    "name": "Layer 1",
                    "sortOrder": 0,
                    "visible": True,
                    "locked": False,
                    "opacity": 1,
                },
                "operations": [{"type": "create", "item": item}],
            },
        )

        assert response.status_code == 200
        assert response.json()["version"] == 1
        manifest = client.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/manifest"
        ).json()
        assert [(layer["id"], layer["name"]) for layer in manifest["layers"]] == [
            (layer_id, "Layer 1")
        ]
        assert manifest["activeCount"] == 1


def test_concurrent_batches_with_the_same_base_version_allow_one_commit(
    tmp_path: Path,
) -> None:
    from wsi_viewer.annotations import (
        AnnotationBatchRequest,
        AnnotationError,
        apply_batch,
    )

    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client, slide_id="annotation-race")
        layer = _create_layer(client, slide.id, headers)
        first = _item_payload(layer["id"])
        second = _item_payload(layer["id"])
        created = _batch(
            client,
            slide.id,
            headers,
            base_version=1,
            operations=[
                {"type": "create", "item": first},
                {"type": "create", "item": second},
            ],
        )
        assert created.status_code == 200

        settings = client.app.state.settings
        with session_factory(settings)() as database:
            actor_user_id = str(
                database.scalar(select(User.id).where(User.username == "admin"))
            )

        ready = Barrier(2)

        def update_item(item_id: str, title: str) -> tuple[Any, ...]:
            with session_factory(settings)() as database:
                current_slide = database.get(Slide, slide.id)
                assert current_slide is not None
                ready.wait(timeout=5)
                payload = AnnotationBatchRequest.model_validate(
                    {
                        "mutationId": str(uuid.uuid4()),
                        "baseVersion": 2,
                        "operations": [
                            {
                                "type": "update",
                                "id": item_id,
                                "version": 1,
                                "metadata": {
                                    "title": title,
                                    "classification": "",
                                    "tags": [],
                                    "notes": "",
                                },
                            }
                        ],
                    }
                )
                try:
                    result = apply_batch(
                        database,
                        current_slide,
                        payload,
                        actor_user_id=actor_user_id,
                    )
                except AnnotationError as error:
                    database.rollback()
                    return (
                        "conflict",
                        error.status_code,
                        error.code,
                        error.detail.get("currentVersion"),
                    )
                except Exception as error:  # pragma: no cover - assertion reports type
                    database.rollback()
                    return ("unexpected", type(error).__name__, str(error))
                return ("success", result["version"])

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = [
                future.result(timeout=10)
                for future in (
                    executor.submit(update_item, first["id"], "First winner"),
                    executor.submit(update_item, second["id"], "Second winner"),
                )
            ]

        assert sum(outcome[0] == "success" for outcome in outcomes) == 1
        assert [
            outcome[1:]
            for outcome in outcomes
            if outcome[0] == "conflict"
        ] == [(409, "ANNOTATION_CONFLICT", 3)]
        with session_factory(settings)() as database:
            stored_slide = database.get(Slide, slide.id)
            assert stored_slide is not None
            assert stored_slide.annotation_version == 3
            titles = list(
                database.scalars(
                    select(Annotation.annotation_metadata).where(
                        Annotation.id.in_([first["id"], second["id"]])
                    )
                )
            )
        assert sum(
            title["title"] in {"First winner", "Second winner"}
            for title in titles
        ) == 1


def test_style_and_layer_mutations_reject_coercible_scalars_and_blank_names(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client, slide_id="strict-annotation-inputs")
        layer_url = f"/api/v2/admin/annotations/slides/{slide.id}/layers"

        for field, value in (
            ("sortOrder", "1"),
            ("visible", "true"),
            ("locked", "false"),
            ("opacity", "0.8"),
        ):
            payload = _layer_payload()
            payload[field] = value
            response = client.post(layer_url, headers=headers, json=payload)
            assert response.status_code == 422, field

        blank_name = client.post(
            layer_url,
            headers=headers,
            json=_layer_payload(name="   "),
        )
        assert blank_name.status_code == 422
        assert client.get(layer_url).json() == {"items": []}

        layer = _create_layer(client, slide.id, headers)
        for field, value in (
            ("strokeWidth", "2"),
            ("opacity", "0.35"),
            ("labelVisible", "true"),
        ):
            item = _item_payload(layer["id"])
            item["style"][field] = value
            response = _batch(
                client,
                slide.id,
                headers,
                base_version=1,
                operations=[{"type": "create", "item": item}],
            )
            assert response.status_code == 422, field

        manifest = client.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/manifest"
        )
        assert manifest.json()["version"] == 1
        assert manifest.json()["activeCount"] == 0


def test_historical_revision_restore_enforces_the_active_annotation_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wsi_viewer import annotations as annotation_service

    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client, slide_id="revision-restore-limit")
        layer = _create_layer(client, slide.id, headers)
        trashed = _item_payload(layer["id"])
        active = _item_payload(layer["id"])
        assert (
            _batch(
                client,
                slide.id,
                headers,
                base_version=1,
                operations=[
                    {"type": "create", "item": trashed},
                    {"type": "create", "item": active},
                ],
            ).status_code
            == 200
        )
        deleted = _batch(
            client,
            slide.id,
            headers,
            base_version=2,
            operations=[
                {
                    "type": "delete",
                    "id": trashed["id"],
                    "version": 1,
                }
            ],
        )
        assert deleted.status_code == 200
        revision_id = client.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/items/"
            f"{trashed['id']}/revisions"
        ).json()["items"][0]["id"]

        monkeypatch.setattr(annotation_service, "MAX_ACTIVE_ANNOTATIONS", 1)
        restored = client.post(
            f"/api/v2/admin/annotations/slides/{slide.id}/items/{trashed['id']}"
            f"/revisions/{revision_id}/restore",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 3,
                "version": 2,
            },
        )
        assert restored.status_code == 422
        assert restored.json() == {
            "detail": {"code": "ANNOTATION_ACTIVE_LIMIT"}
        }
        manifest = client.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/manifest"
        ).json()
        assert manifest["version"] == 3
        assert manifest["activeCount"] == 1
        assert manifest["trashedCount"] == 1


def test_geojson_import_rejects_polygon_interior_rings_before_commit(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client, slide_id="geojson-interior-ring")
        imported = client.post(
            f"/api/v2/admin/annotations/slides/{slide.id}/import",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 0,
                "format": "geojson",
                "data": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [
                                    [
                                        [10, 10],
                                        [100, 10],
                                        [100, 100],
                                        [10, 10],
                                    ],
                                    [
                                        [20, 20],
                                        [30, 20],
                                        [30, 30],
                                        [20, 20],
                                    ],
                                ],
                            },
                            "properties": {"name": "Polygon with a hole"},
                        }
                    ],
                },
            },
        )
        assert imported.status_code == 422
        assert imported.json() == {
            "detail": {"code": "ANNOTATION_IMPORT_INVALID"}
        }
        manifest = client.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/manifest"
        ).json()
        assert manifest["version"] == 0
        assert manifest["activeCount"] == 0
        assert manifest["layers"] == []


def test_feature_flag_session_csrf_and_admin_public_serialization(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=False) as disabled:
        slide = _slide(disabled, state=SlideState.PUBLISHED)
        headers = _login(disabled)

        admin = disabled.get(f"/api/v1/admin/slides/{slide.id}")
        assert admin.status_code == 200
        assert admin.json()["annotationsEnabled"] is False
        assert admin.json()["annotationVersion"] == 0

        hidden = disabled.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/manifest"
        )
        assert hidden.status_code == 404
        assert hidden.json() == {"detail": {"code": "ANNOTATIONS_DISABLED"}}

    with _client(tmp_path, enabled=True) as enabled:
        slide = _slide(enabled, slide_id="enabled-slide")
        unauthenticated = enabled.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/manifest"
        )
        assert unauthenticated.status_code == 401
        headers = _login(enabled)
        missing_csrf = enabled.post(
            f"/api/v2/admin/annotations/slides/{slide.id}/layers",
            json=_layer_payload(),
        )
        assert missing_csrf.status_code == 403
        assert (
            enabled.post(
                f"/api/v2/admin/annotations/slides/{slide.id}/layers",
                headers=headers,
                json=_layer_payload(),
            ).status_code
            == 201
        )

        admin = enabled.get(f"/api/v1/admin/slides/{slide.id}").json()
        assert admin["annotationsEnabled"] is True
        assert admin["annotationVersion"] == 1


def test_annotation_openapi_exposes_strict_manifest_and_result_contracts(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
        for name in (
            "AnnotationManifest",
            "AnnotationBatchRequest",
            "AnnotationBatchResult",
            "AnnotationItemRecord",
            "AnnotationLayerRecord",
            "AnnotationItemsPage",
        ):
            assert schemas[name]["additionalProperties"] is False

        batch = client.get("/openapi.json").json()["paths"][
            "/api/v2/admin/annotations/slides/{slide_id}/batch"
        ]["post"]
        response_schema = batch["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        assert response_schema["$ref"].endswith("/AnnotationBatchResult")


def test_annotation_mutations_do_not_coerce_versions_or_coordinates(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client)
        layer = _create_layer(client, slide.id, headers)
        item = _item_payload(layer["id"])

        string_version = client.post(
            f"/api/v2/admin/annotations/slides/{slide.id}/batch",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": "1",
                "operations": [{"type": "create", "item": item}],
            },
        )
        assert string_version.status_code == 422

        string_coordinate = client.post(
            f"/api/v2/admin/annotations/slides/{slide.id}/batch",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 1,
                "operations": [
                    {
                        "type": "create",
                        "item": {
                            **item,
                            "geometry": {
                                "type": "point",
                                "x": "10",
                                "y": 20,
                            },
                        },
                    }
                ],
            },
        )
        assert string_coordinate.status_code == 422
        assert (
            client.get(
                f"/api/v2/admin/annotations/slides/{slide.id}/manifest"
            ).json()["version"]
            == 1
        )


def test_manifest_batch_items_validation_and_atomic_conflicts(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client)
        layer = _create_layer(client, slide.id, headers)

        manifest = client.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/manifest"
        )
        assert manifest.status_code == 200
        assert manifest.json() == {
            "slideId": slide.id,
            "version": 1,
            "bounds": {"width": 1000.0, "height": 500.0},
            "calibration": {
                "x": 0.25,
                "y": 0.5,
                "unit": "µm",
            },
            "activeCount": 0,
            "trashedCount": 0,
            "layers": [layer],
            "limits": {
                "activeAnnotations": 25_000,
                "layers": 100,
                "verticesPerShape": 8_192,
                "verticesPerImport": 250_000,
                "batchOperations": 50,
            },
        }

        item = _item_payload(layer["id"], item_id="4b901447-593f-47e2-b99a-f6fcb8513119")
        created = _batch(
            client,
            slide.id,
            headers,
            base_version=1,
            operations=[{"type": "create", "item": item}],
        )
        assert created.status_code == 200
        assert created.json() == {
            "mutationId": created.json()["mutationId"],
            "version": 2,
            "results": [
                {
                    "id": item["id"],
                    "operation": "create",
                    "version": 1,
                    "deleted": False,
                }
            ],
            "purged": 0,
        }

        items = client.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/items",
            params={"limit": 100, "offset": 0},
        )
        assert items.status_code == 200
        assert items.json() == {
            "items": [
                {
                    **item,
                    "version": 1,
                    "deletedAt": None,
                    "createdAt": items.json()["items"][0]["createdAt"],
                    "updatedAt": items.json()["items"][0]["updatedAt"],
                    "bounds": {
                        "minX": 10.0,
                        "minY": 20.0,
                        "maxX": 50.0,
                        "maxY": 60.0,
                    },
                    "measurements": {
                        "area": 200.0,
                        "perimeter": 60.0,
                        "unit": "µm",
                        "areaUnit": "µm²",
                    },
                }
            ],
            "total": 1,
            "nextOffset": None,
        }

        stale_update = _batch(
            client,
            slide.id,
            headers,
            base_version=1,
            operations=[
                {
                    "type": "update",
                    "id": item["id"],
                    "version": 1,
                    "metadata": {
                        "title": "Must not commit",
                        "classification": "",
                        "tags": [],
                        "notes": "",
                    },
                }
            ],
        )
        assert stale_update.status_code == 409
        assert stale_update.json() == {
            "detail": {
                "code": "ANNOTATION_CONFLICT",
                "currentVersion": 2,
            }
        }

        atomic_rejection = _batch(
            client,
            slide.id,
            headers,
            base_version=2,
            operations=[
                {
                    "type": "update",
                    "id": item["id"],
                    "version": 1,
                    "metadata": {
                        "title": "Would be partial",
                        "classification": "",
                        "tags": [],
                        "notes": "",
                    },
                },
                {
                    "type": "create",
                    "item": {
                        **_item_payload(layer["id"]),
                        "geometry": {
                            "type": "point",
                            "x": 1001,
                            "y": 20,
                        },
                    },
                },
            ],
        )
        assert atomic_rejection.status_code == 422
        assert atomic_rejection.json() == {
            "detail": {"code": "ANNOTATION_OUT_OF_BOUNDS"}
        }
        unchanged = client.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/items"
        ).json()
        assert unchanged["items"][0]["metadata"]["title"] == "Tumor bed"
        assert unchanged["total"] == 1
        assert (
            client.get(
                f"/api/v2/admin/annotations/slides/{slide.id}/manifest"
            ).json()["version"]
            == 2
        )

        html_text = _batch(
            client,
            slide.id,
            headers,
            base_version=2,
            operations=[
                {
                    "type": "create",
                    "item": {
                        **_item_payload(layer["id"]),
                        "metadata": {
                            "title": "<script>alert(1)</script>",
                            "classification": "",
                            "tags": [],
                            "notes": "",
                        },
                    },
                }
            ],
        )
        assert html_text.status_code == 422

        unsupported = _batch(
            client,
            slide.id,
            headers,
            base_version=2,
            operations=[
                {
                    "type": "create",
                    "item": {
                        **_item_payload(layer["id"]),
                        "geometry": {"type": "sphere", "x": 10, "y": 20},
                    },
                }
            ],
        )
        assert unsupported.status_code == 422


def test_revisions_restore_trash_purge_and_private_audits(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client)
        layer = _create_layer(client, slide.id, headers)
        item = _item_payload(
            layer["id"],
            item_id="a4e89ca2-19f9-4cb8-9976-8616b8ca81ae",
        )
        assert (
            _batch(
                client,
                slide.id,
                headers,
                base_version=1,
                operations=[{"type": "create", "item": item}],
            ).status_code
            == 200
        )
        updated = _batch(
            client,
            slide.id,
            headers,
            base_version=2,
            operations=[
                {
                    "type": "update",
                    "id": item["id"],
                    "version": 1,
                    "metadata": {
                        "title": "Updated title",
                        "classification": "Tumor",
                        "tags": ["teaching"],
                        "notes": "Updated notes",
                    },
                }
            ],
        )
        assert updated.status_code == 200
        deleted = _batch(
            client,
            slide.id,
            headers,
            base_version=3,
            operations=[
                {
                    "type": "delete",
                    "id": item["id"],
                    "version": 2,
                }
            ],
        )
        assert deleted.status_code == 200
        assert deleted.json()["results"][0]["deleted"] is True
        assert (
            client.get(
                f"/api/v2/admin/annotations/slides/{slide.id}/items"
            ).json()["total"]
            == 0
        )

        revisions = client.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/items/{item['id']}/revisions"
        )
        assert revisions.status_code == 200
        assert [revision["version"] for revision in revisions.json()["items"]] == [2, 1]
        oldest_revision_id = revisions.json()["items"][1]["id"]

        restored = client.post(
            f"/api/v2/admin/annotations/slides/{slide.id}/items/{item['id']}/restore",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 4,
                "version": 3,
            },
        )
        assert restored.status_code == 200
        assert restored.json()["version"] == 5
        assert restored.json()["item"]["version"] == 4
        assert restored.json()["item"]["deletedAt"] is None

        historic = client.post(
            f"/api/v2/admin/annotations/slides/{slide.id}/items/{item['id']}"
            f"/revisions/{oldest_revision_id}/restore",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 5,
                "version": 4,
            },
        )
        assert historic.status_code == 200
        assert historic.json()["version"] == 6
        assert historic.json()["item"]["version"] == 5
        assert historic.json()["item"]["metadata"]["title"] == "Tumor bed"

        item_version = 5
        slide_version = 6
        for sequence in range(27):
            response = _batch(
                client,
                slide.id,
                headers,
                base_version=slide_version,
                operations=[
                    {
                        "type": "update",
                        "id": item["id"],
                        "version": item_version,
                        "metadata": {
                            "title": f"Revision {sequence}",
                            "classification": "",
                            "tags": [],
                            "notes": "",
                        },
                    }
                ],
            )
            assert response.status_code == 200
            slide_version += 1
            item_version += 1

        revisions = client.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/items/{item['id']}/revisions"
        ).json()["items"]
        assert len(revisions) == 25
        assert revisions[0]["version"] == item_version - 1

        settings = client.app.state.settings
        expired = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        with session_factory(settings)() as database:
            for _index in range(101):
                database.add(
                    Annotation(
                        id=str(uuid.uuid4()),
                        slide_id=slide.id,
                        layer_id=layer["id"],
                        geometry_type="point",
                        geometry={"type": "point", "x": 1.0, "y": 1.0},
                        style={
                            "strokeColor": "#c43d3d",
                            "fillColor": "#c43d3d",
                            "strokeWidth": 2,
                            "opacity": 0.35,
                            "labelVisible": True,
                        },
                        annotation_metadata={
                            "title": "",
                            "classification": "",
                            "tags": [],
                            "notes": "",
                        },
                        bbox_min_x=1,
                        bbox_min_y=1,
                        bbox_max_x=1,
                        bbox_max_y=1,
                        vertex_count=1,
                        version=1,
                        mutation_id=str(uuid.uuid4()),
                        deleted_at=expired - timedelta(days=30),
                        purge_after=expired,
                    )
                )
            database.commit()

        purge_trigger = _batch(
            client,
            slide.id,
            headers,
            base_version=slide_version,
            operations=[
                {
                    "type": "update",
                    "id": item["id"],
                    "version": item_version,
                    "metadata": {
                        "title": "Purge trigger",
                        "classification": "",
                        "tags": [],
                        "notes": "",
                    },
                }
            ],
        )
        assert purge_trigger.status_code == 200
        assert purge_trigger.json()["purged"] == 100
        with session_factory(settings)() as database:
            assert (
                database.scalar(
                    select(func.count(Annotation.id)).where(
                        Annotation.slide_id == slide.id,
                        Annotation.purge_after <= expired,
                    )
                )
                == 1
            )
            audits = list(
                database.scalars(
                    select(AuditEvent).where(
                        AuditEvent.action.like("annotation.%")
                    )
                )
            )
        assert audits
        serialized_audits = json.dumps([audit.detail for audit in audits])
        assert "Tumor bed" not in serialized_audits
        assert "Manual region" not in serialized_audits
        assert '"points"' not in serialized_audits
        for audit in audits:
            assert isinstance((audit.detail or {}).get("durationMs"), (int, float))
            assert set(audit.detail or {}) <= {
                "mutationId",
                "operationCount",
                "durationMs",
                "result",
                "version",
                "purged",
            }


def test_slide_delete_cascades_all_annotation_state(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client)
        layer = _create_layer(client, slide.id, headers)
        item = _item_payload(layer["id"])
        created = _batch(
            client,
            slide.id,
            headers,
            base_version=1,
            operations=[{"type": "create", "item": item}],
        )
        assert created.status_code == 200
        assert (
            _batch(
                client,
                slide.id,
                headers,
                base_version=2,
                operations=[
                    {
                        "type": "update",
                        "id": item["id"],
                        "version": 1,
                        "metadata": {
                            "title": "Revision",
                            "classification": "",
                            "tags": [],
                            "notes": "",
                        },
                    }
                ],
            ).status_code
            == 200
        )

        with session_factory(client.app.state.settings)() as database:
            stored = database.get(Slide, slide.id)
            assert stored is not None
            database.delete(stored)
            database.commit()
            assert database.scalar(select(func.count(AnnotationLayer.id))) == 0
            assert database.scalar(select(func.count(Annotation.id))) == 0
            assert database.scalar(select(func.count(AnnotationRevision.id))) == 0


def test_layer_crud_and_hard_limits_reject_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wsi_viewer import annotations as annotation_service

    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client)
        layer = _create_layer(client, slide.id, headers)

        listed = client.get(
            f"/api/v2/admin/annotations/slides/{slide.id}/layers"
        )
        assert listed.status_code == 200
        assert listed.json() == {"items": [layer]}

        updated = client.patch(
            f"/api/v2/admin/annotations/slides/{slide.id}/layers/{layer['id']}",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 1,
                "name": "Reviewed tumor",
                "opacity": 0.6,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["version"] == 2
        assert updated.json()["layer"]["name"] == "Reviewed tumor"
        assert updated.json()["layer"]["opacity"] == 0.6

        monkeypatch.setattr(annotation_service, "MAX_ACTIVE_ANNOTATIONS", 1)
        first = _item_payload(layer["id"])
        assert (
            _batch(
                client,
                slide.id,
                headers,
                base_version=2,
                operations=[{"type": "create", "item": first}],
            ).status_code
            == 200
        )
        overflow = _batch(
            client,
            slide.id,
            headers,
            base_version=3,
            operations=[
                {"type": "create", "item": _item_payload(layer["id"])}
            ],
        )
        assert overflow.status_code == 422
        assert overflow.json() == {
            "detail": {"code": "ANNOTATION_ACTIVE_LIMIT"}
        }
        assert (
            client.get(
                f"/api/v2/admin/annotations/slides/{slide.id}/manifest"
            ).json()["version"]
            == 3
        )

        too_many_vertices = _batch(
            client,
            slide.id,
            headers,
            base_version=3,
            operations=[
                {
                    "type": "update",
                    "id": first["id"],
                        "version": 1,
                        "geometry": {
                            "type": "polygon",
                            "points": [
                                {"x": index % 2, "y": index % 2}
                                for index in range(8_193)
                            ],
                        },
                }
            ],
        )
        assert too_many_vertices.status_code == 422

        nonempty = client.request(
            "DELETE",
            f"/api/v2/admin/annotations/slides/{slide.id}/layers/{layer['id']}",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 3,
            },
        )
        assert nonempty.status_code == 409
        assert nonempty.json() == {
            "detail": {"code": "ANNOTATION_LAYER_NOT_EMPTY"}
        }

        settings = client.app.state.settings
        with session_factory(settings)() as database:
            database.add_all(
                AnnotationLayer(
                    slide_id=slide.id,
                    name=f"Layer {index}",
                    sort_order=index,
                )
                for index in range(1, 100)
            )
            database.commit()
        layer_overflow = client.post(
            f"/api/v2/admin/annotations/slides/{slide.id}/layers",
            headers=headers,
            json=_layer_payload(base_version=3, name="Layer 101"),
        )
        assert layer_overflow.status_code == 422
        assert layer_overflow.json() == {
            "detail": {"code": "ANNOTATION_LAYER_LIMIT"}
        }


def test_layer_writes_run_the_same_bounded_tombstone_purge(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client)
        layer = _create_layer(client, slide.id, headers)
        expired = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        with session_factory(client.app.state.settings)() as database:
            database.add_all(
                Annotation(
                    id=str(uuid.uuid4()),
                    slide_id=slide.id,
                    layer_id=layer["id"],
                    geometry_type="point",
                    geometry={"type": "point", "x": 1.0, "y": 1.0},
                    style={
                        "strokeColor": "#c43d3d",
                        "fillColor": "#c43d3d",
                        "strokeWidth": 2,
                        "opacity": 0.35,
                        "labelVisible": True,
                    },
                    annotation_metadata={
                        "title": "",
                        "classification": "",
                        "tags": [],
                        "notes": "",
                    },
                    bbox_min_x=1,
                    bbox_min_y=1,
                    bbox_max_x=1,
                    bbox_max_y=1,
                    vertex_count=1,
                    version=1,
                    mutation_id=str(uuid.uuid4()),
                    deleted_at=expired - timedelta(days=30),
                    purge_after=expired,
                )
                for _index in range(101)
            )
            database.commit()

        created = client.post(
            f"/api/v2/admin/annotations/slides/{slide.id}/layers",
            headers=headers,
            json=_layer_payload(base_version=1, name="Second layer"),
        )
        assert created.status_code == 201
        with session_factory(client.app.state.settings)() as database:
            assert (
                database.scalar(
                    select(func.count(Annotation.id)).where(
                        Annotation.purge_after <= expired
                    )
                )
                == 1
            )


def test_pathlab_geojson_and_csv_interchange_is_bounded_and_lossless(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wsi_viewer import annotations as annotation_service

    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        source = _slide(client, slide_id="interchange-source")
        layer = _create_layer(client, source.id, headers)
        polygon = _item_payload(
            layer["id"],
            item_id="1b35a54b-a36a-40c1-87e8-881877b035e1",
        )
        ellipse = {
            **_item_payload(
                layer["id"],
                item_id="9cf71868-5a49-4e91-ad2f-e9e61b70f44a",
            ),
            "geometry": {
                "type": "ellipse",
                "cx": 200,
                "cy": 150,
                "rx": 20,
                "ry": 10,
            },
            "metadata": {
                "title": "Ellipse",
                "classification": "Region",
                "tags": [],
                "notes": "",
            },
        }
        created = _batch(
            client,
            source.id,
            headers,
            base_version=1,
            operations=[
                {"type": "create", "item": polygon},
                {"type": "create", "item": ellipse},
            ],
        )
        assert created.status_code == 200

        pathlab_export = client.get(
            f"/api/v2/admin/annotations/slides/{source.id}/export",
            params={"format": "pathlab"},
        )
        assert pathlab_export.status_code == 200
        assert pathlab_export.headers["content-type"].startswith("application/json")
        document = pathlab_export.json()
        assert document["schema"] == "pathlab-annotations/v1"
        assert document["slide"] == {
            "id": source.id,
            "width": 1000.0,
            "height": 500.0,
            "annotationVersion": 2,
        }
        assert len(document["layers"]) == 1
        assert len(document["annotations"]) == 2
        assert document["annotations"][0]["geometry"] == polygon["geometry"]
        assert document["annotations"][0]["style"] == polygon["style"]
        assert document["annotations"][0]["metadata"] == polygon["metadata"]

        geojson_export = client.get(
            f"/api/v2/admin/annotations/slides/{source.id}/export",
            params={"format": "geojson"},
        )
        assert geojson_export.status_code == 200
        geojson = geojson_export.json()
        assert geojson["type"] == "FeatureCollection"
        ellipse_feature = next(
            feature
            for feature in geojson["features"]
            if feature["properties"]["name"] == "Ellipse"
        )
        assert ellipse_feature["geometry"]["type"] == "Polygon"
        assert len(ellipse_feature["geometry"]["coordinates"][0]) == 65
        assert ellipse_feature["geometry"]["coordinates"][0][0] == [220.0, 150.0]

        csv_export = client.get(
            f"/api/v2/admin/annotations/slides/{source.id}/export",
            params={"format": "csv"},
        )
        assert csv_export.status_code == 200
        lines = csv_export.text.splitlines()
        assert lines[0] == (
            "id,layer,title,type,x,y,length,angle,perimeter,area,unit,areaUnit"
        )
        assert "Tumor bed" in lines[1]
        assert ",60.0,200.0,µm,µm²" in lines[1]

        target = _slide(client, slide_id="interchange-target")
        import_document = json.loads(json.dumps(document))
        imported_layer_id = str(uuid.uuid4())
        import_document["layers"][0]["id"] = imported_layer_id
        for annotation in import_document["annotations"]:
            annotation["id"] = str(uuid.uuid4())
            annotation["layerId"] = imported_layer_id
        imported = client.post(
            f"/api/v2/admin/annotations/slides/{target.id}/import",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 0,
                "format": "pathlab",
                "data": import_document,
            },
        )
        assert imported.status_code == 200
        assert imported.json()["version"] == 1
        assert imported.json()["imported"] == 2
        imported_items = client.get(
            f"/api/v2/admin/annotations/slides/{target.id}/items"
        ).json()["items"]
        imported_by_title = {
            item["metadata"]["title"]: item for item in imported_items
        }
        assert imported_by_title["Tumor bed"]["geometry"] == polygon["geometry"]
        assert imported_by_title["Tumor bed"]["style"] == polygon["style"]
        assert imported_by_title["Tumor bed"]["metadata"] == polygon["metadata"]
        assert imported_by_title["Ellipse"]["geometry"] == ellipse["geometry"]
        assert imported_by_title["Ellipse"]["style"] == ellipse["style"]
        assert imported_by_title["Ellipse"]["metadata"] == ellipse["metadata"]

        geojson_target = _slide(client, slide_id="geojson-target")
        geojson_import = client.post(
            f"/api/v2/admin/annotations/slides/{geojson_target.id}/import",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 0,
                "format": "geojson",
                "data": geojson,
            },
        )
        assert geojson_import.status_code == 200
        assert geojson_import.json()["imported"] == 2

        rejected_target = _slide(client, slide_id="rejected-import")
        outside = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "outside",
                    "geometry": {"type": "Point", "coordinates": [1001, 10]},
                    "properties": {
                        "name": "Outside",
                        "classification": None,
                        "tags": [],
                        "notes": "",
                        "layerName": "Imported",
                        "style": polygon["style"],
                    },
                }
            ],
        }
        rejected = client.post(
            f"/api/v2/admin/annotations/slides/{rejected_target.id}/import",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 0,
                "format": "geojson",
                "data": outside,
            },
        )
        assert rejected.status_code == 422
        assert rejected.json() == {
            "detail": {"code": "ANNOTATION_OUT_OF_BOUNDS"}
        }
        assert (
            client.get(
                f"/api/v2/admin/annotations/slides/{rejected_target.id}/layers"
            ).json()["items"]
            == []
        )

        monkeypatch.setattr(annotation_service, "MAX_VERTICES_PER_IMPORT", 3)
        vertex_document = json.loads(json.dumps(document))
        vertex_layer_id = str(uuid.uuid4())
        vertex_document["layers"][0]["id"] = vertex_layer_id
        for annotation in vertex_document["annotations"]:
            annotation["id"] = str(uuid.uuid4())
            annotation["layerId"] = vertex_layer_id
        vertex_limited = client.post(
            f"/api/v2/admin/annotations/slides/{rejected_target.id}/import",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 0,
                "format": "pathlab",
                "data": vertex_document,
            },
        )
        assert vertex_limited.status_code == 422
        assert vertex_limited.json() == {
            "detail": {"code": "ANNOTATION_IMPORT_VERTEX_LIMIT"}
        }


def test_pathlab_two_layer_round_trip_preserves_safe_ids_membership_and_properties(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        source = _slide(client, slide_id="two-layer-source")
        first = _create_layer(client, source.id, headers)
        second_response = client.post(
            f"/api/v2/admin/annotations/slides/{source.id}/layers",
            headers=headers,
            json={
                **_layer_payload(base_version=1, name="Review"),
                "sortOrder": 7,
                "opacity": 0.65,
            },
        )
        assert second_response.status_code == 201
        second = second_response.json()
        first_item = _item_payload(
            first["id"],
            item_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        )
        second_item = {
            **_item_payload(
                second["id"],
                item_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            ),
            "metadata": {
                "title": "Second layer",
                "classification": "Review",
                "tags": ["round-trip"],
                "notes": "Preserve me",
            },
        }
        assert _batch(
            client,
            source.id,
            headers,
            base_version=2,
            operations=[
                {"type": "create", "item": first_item},
                {"type": "create", "item": second_item},
            ],
        ).status_code == 200
        assert client.patch(
            f"/api/v2/admin/annotations/slides/{source.id}/layers/{first['id']}",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 3,
                "sortOrder": 3,
                "visible": False,
                "opacity": 0.4,
            },
        ).status_code == 200
        assert client.patch(
            f"/api/v2/admin/annotations/slides/{source.id}/layers/{second['id']}",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 4,
                "locked": True,
                "opacity": 0.65,
            },
        ).status_code == 200
        exported = client.get(
            f"/api/v2/admin/annotations/slides/{source.id}/export",
            params={"format": "pathlab"},
        ).json()
        target = _slide(client, slide_id="two-layer-target")

        collision = client.post(
            f"/api/v2/admin/annotations/slides/{target.id}/import",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 0,
                "format": "pathlab",
                "data": exported,
            },
        )
        assert collision.status_code == 409
        assert collision.json() == {
            "detail": {"code": "ANNOTATION_IMPORT_ID_CONFLICT"}
        }
        assert client.get(
            f"/api/v2/admin/annotations/slides/{target.id}/layers"
        ).json()["items"] == []

        invalid_reference = json.loads(json.dumps(exported))
        invalid_reference["annotations"][0]["layerId"] = (
            "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        )
        rejected_reference = client.post(
            f"/api/v2/admin/annotations/slides/{target.id}/import",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 0,
                "format": "pathlab",
                "data": invalid_reference,
            },
        )
        assert rejected_reference.status_code == 422
        assert rejected_reference.json() == {
            "detail": {"code": "ANNOTATION_IMPORT_INVALID"}
        }
        assert client.get(
            f"/api/v2/admin/annotations/slides/{target.id}/layers"
        ).json()["items"] == []

        with session_factory(client.app.state.settings)() as database:
            stored_source = database.get(Slide, source.id)
            assert stored_source is not None
            database.delete(stored_source)
            database.commit()

        imported = client.post(
            f"/api/v2/admin/annotations/slides/{target.id}/import",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 0,
                "format": "pathlab",
                "data": exported,
            },
        )
        assert imported.status_code == 200
        assert imported.json()["imported"] == 2
        round_trip = client.get(
            f"/api/v2/admin/annotations/slides/{target.id}/export",
            params={"format": "pathlab"},
        ).json()
        assert round_trip["layers"] == exported["layers"]
        assert round_trip["annotations"] == exported["annotations"]


def test_wal_reads_remain_available_and_atomically_visible_during_50_op_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wsi_viewer import annotations as annotation_service
    from wsi_viewer.annotations import AnnotationBatchRequest, apply_batch

    with _client(tmp_path, enabled=True) as client:
        headers = _login(client)
        slide = _slide(client, slide_id="annotation-wal-reads")
        layer = _create_layer(client, slide.id, headers)
        items = [
            _item_payload(layer["id"], item_id=str(uuid.uuid4()))
            for _ in range(50)
        ]
        created = _batch(
            client,
            slide.id,
            headers,
            base_version=1,
            operations=[{"type": "create", "item": item} for item in items],
        )
        assert created.status_code == 200

        settings = client.app.state.settings
        with session_factory(settings)() as database:
            actor_user_id = str(
                database.scalar(select(User.id).where(User.username == "admin"))
            )

        writer_started = Event()
        writer_done = Event()
        original_record_revision = annotation_service._record_revision

        def delayed_record_revision(
            database: Any,
            annotation: Annotation,
        ) -> None:
            writer_started.set()
            sleep(0.002)
            original_record_revision(database, annotation)

        monkeypatch.setattr(
            annotation_service,
            "_record_revision",
            delayed_record_revision,
        )
        payload = AnnotationBatchRequest.model_validate(
            {
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 2,
                "operations": [
                    {
                        "type": "update",
                        "id": item["id"],
                        "version": 1,
                        "metadata": {
                            "title": "Updated atomically",
                            "classification": "",
                            "tags": [],
                            "notes": "",
                        },
                    }
                    for item in items
                ],
            }
        )

        def write_batch() -> tuple[int, int]:
            try:
                with session_factory(settings)() as database:
                    current_slide = database.get(Slide, slide.id)
                    assert current_slide is not None
                    result = apply_batch(
                        database,
                        current_slide,
                        payload,
                        actor_user_id=actor_user_id,
                    )
                    return int(result["version"]), len(result["results"])
            finally:
                writer_done.set()

        def read_snapshots() -> list[tuple[int, int]]:
            assert writer_started.wait(timeout=5)
            snapshots: list[tuple[int, int]] = []
            while not writer_done.is_set():
                with session_factory(settings)() as database:
                    snapshot = database.execute(
                        text(
                            "SELECT annotation_version, "
                            "(SELECT COUNT(*) FROM annotations "
                            "WHERE slide_id = :slide_id "
                            "AND json_extract(annotation_metadata, '$.title') = "
                            "'Updated atomically') "
                            "FROM slides WHERE id = :slide_id"
                        ),
                        {"slide_id": slide.id},
                    ).one()
                snapshots.append((int(snapshot[0]), int(snapshot[1])))
            return snapshots

        with ThreadPoolExecutor(max_workers=5) as executor:
            writer = executor.submit(write_batch)
            readers = [executor.submit(read_snapshots) for _ in range(4)]
            assert writer.result(timeout=15) == (3, 50)
            observations = [
                snapshot
                for reader in readers
                for snapshot in reader.result(timeout=15)
            ]

        assert observations
        assert set(observations) <= {(2, 0), (3, 50)}
        with session_factory(settings)() as database:
            final = database.execute(
                text(
                    "SELECT annotation_version, "
                    "(SELECT COUNT(*) FROM annotations "
                    "WHERE slide_id = :slide_id "
                    "AND json_extract(annotation_metadata, '$.title') = "
                    "'Updated atomically') "
                    "FROM slides WHERE id = :slide_id"
                ),
                {"slide_id": slide.id},
            ).one()
        assert tuple(final) == (3, 50)
