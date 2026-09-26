from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from test_annotations import _client, _layer_payload, _login, _slide
from test_desktop_sync import _authorization, _pair
from wsi_viewer.database import session_factory
from wsi_viewer.models import AnnotationLayer, DesktopSyncEvent, Slide


@pytest.mark.parametrize("mutation", ["create", "update", "delete"])
def test_layer_mutation_reaches_desktop_cursor_atomically(tmp_path: Path, mutation: str) -> None:
    with _client(tmp_path, enabled=True) as client:
        desktop_headers = _authorization(_pair(client))
        admin_headers = _login(client)
        slide = _slide(client)
        settings = client.app.state.settings
        with session_factory(settings)() as database:
            layer = AnnotationLayer(slide_id=slide.id, name="Original")
            database.add(layer)
            database.add(
                DesktopSyncEvent(
                    entity_type="slide", entity_id=slide.id, operation="upsert", revision=1
                )
            )
            database.commit()
            layer_id = layer.id
            cursor = database.scalar(select(func.max(DesktopSyncEvent.sequence)))

        def mutate():
            url = f"/api/v2/admin/annotations/slides/{slide.id}/layers"
            if mutation == "create":
                return client.post(url, headers=admin_headers, json=_layer_payload())
            payload = {"mutationId": str(uuid4()), "baseVersion": 0}
            if mutation == "update":
                return client.patch(
                    f"{url}/{layer_id}",
                    headers=admin_headers,
                    json={**payload, "name": "Renamed", "visible": False},
                )
            return client.request(
                "DELETE", f"{url}/{layer_id}", headers=admin_headers, json=payload
            )

        def reject_commit(database):
            # Fail after the route stages both its mutation and its sync event.
            database.flush()
            raise RuntimeError("synthetic transaction failure")

        event.listen(Session, "before_commit", reject_commit)
        try:
            with pytest.raises(RuntimeError, match="synthetic transaction failure"):
                mutate()
        finally:
            event.remove(Session, "before_commit", reject_commit)
        with session_factory(settings)() as database:
            assert database.get(Slide, slide.id).annotation_version == 0
            assert database.scalar(select(func.count(AnnotationLayer.id))) == 1
            assert database.get(AnnotationLayer, layer_id).name == "Original"
        feed = client.get(
            f"/api/v2/desktop/library/changes?after={cursor}", headers=desktop_headers
        )
        assert feed.status_code == 200
        assert feed.json()["changes"] == []

        response = mutate()
        assert response.status_code == (201 if mutation == "create" else 200)
        feed = client.get(
            f"/api/v2/desktop/library/changes?after={cursor}", headers=desktop_headers
        )
        assert feed.status_code == 200
        changes = feed.json()["changes"]
        assert len(changes) == 1
        assert changes[0]["entityType"] == "annotation"
        assert changes[0]["entityId"] == slide.id
        assert changes[0]["operation"] == "upsert"
        assert changes[0]["revision"] == 1
        assert changes[0]["sequence"] > cursor
        with session_factory(settings)() as database:
            assert database.get(Slide, slide.id).annotation_version == 1
            assert database.scalar(select(func.count(AnnotationLayer.id))) == (
                2 if mutation == "create" else 0 if mutation == "delete" else 1
            )
