"""Machine-local 25,000-annotation API and SQLite benchmark.

This creates a disposable database and synthetic private slide. It is a stability
diagnostic, not a production load or multi-user certification.
"""

from __future__ import annotations

import json
import tempfile
import tracemalloc
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import insert, text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, engine_for, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.main import create_app
from wsi_viewer.models import Annotation, AnnotationLayer, Slide, User
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password

ANNOTATION_COUNT = 25_000
PAGE_SIZE = 5_000
PASSWORD = "synthetic-annotation-benchmark-password"
SECRET = "synthetic-annotation-benchmark-secret"
LAYER_ID = "11111111-1111-4111-8111-111111111111"
MUTATION_ID = "22222222-2222-4222-8222-222222222222"
SLIDE_ID = "synthetic-annotation-benchmark"


def annotation_id(index: int) -> str:
    number = index + 1
    return f"{number:08x}-0000-4000-8000-{number:012x}"


def synthetic_rows() -> list[dict[str, Any]]:
    style = {
        "strokeColor": "#c43d3d",
        "fillColor": "#c43d3d",
        "strokeWidth": 2,
        "opacity": 0.35,
        "labelVisible": True,
    }
    metadata = {
        "title": "",
        "classification": "Synthetic",
        "tags": [],
        "notes": "",
    }
    return [
        {
            "id": annotation_id(index),
            "slide_id": SLIDE_ID,
            "layer_id": LAYER_ID,
            "geometry_type": "point",
            "geometry": {
                "type": "point",
                "x": float(index % 500),
                "y": float(index // 500),
            },
            "style": style,
            "annotation_metadata": metadata,
            "bbox_min_x": float(index % 500),
            "bbox_min_y": float(index // 500),
            "bbox_max_x": float(index % 500),
            "bbox_max_y": float(index // 500),
            "vertex_count": 1,
            "version": 1,
            "mutation_id": MUTATION_ID,
        }
        for index in range(ANNOTATION_COUNT)
    ]


def query_plan(database: Any, sql: str, parameters: dict[str, Any]) -> list[str]:
    return [
        str(row[3])
        for row in database.execute(
            text(f"EXPLAIN QUERY PLAN {sql}"),
            parameters,
        )
    ]


def run() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="pathlab-annotation-benchmark-") as temporary:
        root = Path(temporary)
        database_path = root / "pathlab.sqlite3"
        settings = Settings(
            database_url=f"sqlite:///{database_path}",
            data_root=root / "data",
            secret_key=SECRET,
            secure_cookies=False,
            annotations_enabled=True,
        )
        create_schema(settings)
        seed_started = perf_counter()
        with session_factory(settings)() as database:
            database.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
            )
            database.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
                {"head": ALEMBIC_HEAD},
            )
            database.add(
                User(username="admin", password_hash=hash_password(PASSWORD))
            )
            database.add(
                Slide(
                    id=SLIDE_ID,
                    display_name="Synthetic annotation benchmark",
                    original_filename="synthetic.ome.tif",
                    source_bytes=1,
                    state=SlideState.READY_PRIVATE,
                    privacy_status="passed",
                    slide_metadata={"width": 500, "height": 50},
                    annotation_version=1,
                )
            )
            database.commit()
            database.add(
                AnnotationLayer(
                    id=LAYER_ID,
                    slide_id=SLIDE_ID,
                    name="Synthetic",
                )
            )
            database.commit()
            rows = synthetic_rows()
            for start in range(0, ANNOTATION_COUNT, 1_000):
                database.execute(
                    insert(Annotation),
                    rows[start : start + 1_000],
                )
            database.commit()
        seed_ms = (perf_counter() - seed_started) * 1_000

        with session_factory(settings)() as database:
            active_plan = query_plan(
                database,
                "SELECT id FROM annotations "
                "WHERE slide_id = :slide_id AND deleted_at IS NULL "
                "ORDER BY id LIMIT 5000",
                {"slide_id": SLIDE_ID},
            )
            viewport_plan = query_plan(
                database,
                "SELECT id FROM annotations "
                "WHERE slide_id = :slide_id AND deleted_at IS NULL "
                "AND bbox_max_x >= :min_x AND bbox_max_y >= :min_y "
                "AND bbox_min_x <= :max_x AND bbox_min_y <= :max_y "
                "ORDER BY created_at, id LIMIT 5000",
                {
                    "slide_id": SLIDE_ID,
                    "min_x": 0,
                    "min_y": 0,
                    "max_x": 99,
                    "max_y": 9,
                },
            )

        with TestClient(create_app(settings)) as client:
            login = client.post(
                "/api/v1/auth/session",
                json={"username": "admin", "password": PASSWORD},
            )
            if login.status_code != 201:
                raise RuntimeError(f"Benchmark login failed: {login.status_code}")

            tracemalloc.start()
            manifest_started = perf_counter()
            manifest = client.get(
                f"/api/v2/admin/annotations/slides/{SLIDE_ID}/manifest"
            )
            manifest_ms = (perf_counter() - manifest_started) * 1_000
            page_started = perf_counter()
            page = client.get(
                f"/api/v2/admin/annotations/slides/{SLIDE_ID}/items",
                params={"limit": PAGE_SIZE},
            )
            page_ms = (perf_counter() - page_started) * 1_000
            viewport_started = perf_counter()
            viewport = client.get(
                f"/api/v2/admin/annotations/slides/{SLIDE_ID}/items",
                params={
                    "minX": 0,
                    "minY": 0,
                    "maxX": 99,
                    "maxY": 9,
                    "limit": PAGE_SIZE,
                },
            )
            viewport_ms = (perf_counter() - viewport_started) * 1_000
            _, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()

        if manifest.status_code != 200 or manifest.json()["activeCount"] != ANNOTATION_COUNT:
            raise RuntimeError("Manifest did not report the 25,000-record ceiling")
        if page.status_code != 200 or len(page.json()["items"]) != PAGE_SIZE:
            raise RuntimeError("Unfiltered endpoint did not return its bounded page")
        if viewport.status_code != 200 or viewport.json()["total"] != 1_000:
            raise RuntimeError("Viewport endpoint returned an unexpected synthetic count")
        if not any("ix_annotations_slide_active" in line for line in active_plan):
            raise RuntimeError(f"Active query missed its index: {active_plan}")
        if not any("ix_annotations_slide_bbox" in line for line in viewport_plan):
            raise RuntimeError(f"Viewport query missed its index: {viewport_plan}")

        result = {
            "scope": "machine-local synthetic; not live or multi-user acceptance",
            "annotations": ANNOTATION_COUNT,
            "pageSize": PAGE_SIZE,
            "databaseBytes": database_path.stat().st_size,
            "seedMs": round(seed_ms, 3),
            "manifestMs": round(manifest_ms, 3),
            "pageMs": round(page_ms, 3),
            "viewportMs": round(viewport_ms, 3),
            "endpointPeakAllocatedBytes": peak_bytes,
            "activeQueryPlan": active_plan,
            "viewportQueryPlan": viewport_plan,
            "manifestActiveCount": manifest.json()["activeCount"],
            "pageItems": len(page.json()["items"]),
            "viewportItems": len(viewport.json()["items"]),
            "viewportTotal": viewport.json()["total"],
        }
        engine_for(settings).dispose()
        return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
