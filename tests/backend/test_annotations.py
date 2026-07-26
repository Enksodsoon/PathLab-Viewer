import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
        imported = client.post(
            f"/api/v2/admin/annotations/slides/{target.id}/import",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 0,
                "format": "pathlab",
                "layerName": "Imported review",
                "data": document,
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
        vertex_limited = client.post(
            f"/api/v2/admin/annotations/slides/{rejected_target.id}/import",
            headers=headers,
            json={
                "mutationId": str(uuid.uuid4()),
                "baseVersion": 0,
                "format": "pathlab",
                "data": document,
            },
        )
        assert vertex_limited.status_code == 422
        assert vertex_limited.json() == {
            "detail": {"code": "ANNOTATION_IMPORT_VERTEX_LIMIT"}
        }
