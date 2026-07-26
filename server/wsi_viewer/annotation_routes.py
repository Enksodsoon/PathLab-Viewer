# ruff: noqa: B008

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from .annotations import (
    MAX_ACTIVE_ANNOTATIONS,
    MAX_BATCH_OPERATIONS,
    MAX_LAYERS_PER_SLIDE,
    MAX_VERTICES_PER_IMPORT,
    MAX_VERTICES_PER_SHAPE,
    AnnotationBatchRequest,
    AnnotationBatchResult,
    AnnotationError,
    AnnotationImportRequest,
    AnnotationItemsPage,
    AnnotationManifest,
    ItemMutationRequest,
    LayerMutationRequest,
    LayerUpdateRequest,
    RestoreOperation,
    VersionedMutationRequest,
    annotation_json,
    apply_batch,
    calibration_json,
    export_csv,
    export_geojson,
    export_pathlab,
    import_annotations,
    layer_json,
    lock_annotation_mutation,
    purge_expired_tombstones,
    restore_revision,
    revision_json,
    slide_bounds,
)
from .models import (
    Annotation,
    AnnotationLayer,
    AnnotationRevision,
    AuditEvent,
    Slide,
)


def register_annotation_routes(
    app: FastAPI,
    *,
    database_dependency: Callable[[], Iterator[OrmSession]],
    admin_dependency: Callable[..., Any],
    csrf_dependency: Callable[..., Any],
) -> None:
    def require_enabled() -> None:
        if not app.state.settings.annotations_enabled:
            raise HTTPException(
                status_code=404,
                detail={"code": "ANNOTATIONS_DISABLED"},
            )

    def get_slide(database: OrmSession, slide_id: str) -> Slide:
        slide = database.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        return slide

    def annotation_error(error: AnnotationError) -> HTTPException:
        return HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, **error.detail},
        )

    def manifest(
        slide_id: str,
        _: Any = Depends(admin_dependency),
        __: None = Depends(require_enabled),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        slide = get_slide(database, slide_id)
        active_count = int(
            database.scalar(
                select(func.count(Annotation.id)).where(
                    Annotation.slide_id == slide_id,
                    Annotation.deleted_at.is_(None),
                )
            )
            or 0
        )
        trashed_count = int(
            database.scalar(
                select(func.count(Annotation.id)).where(
                    Annotation.slide_id == slide_id,
                    Annotation.deleted_at.is_not(None),
                )
            )
            or 0
        )
        try:
            width, height = slide_bounds(slide)
        except AnnotationError as error:
            raise annotation_error(error) from error
        return {
            "slideId": slide.id,
            "version": slide.annotation_version,
            "bounds": {"width": width, "height": height},
            "calibration": calibration_json(slide),
            "activeCount": active_count,
            "trashedCount": trashed_count,
            "layers": list(
                map(
                    layer_json,
                    database.scalars(
                        select(AnnotationLayer)
                        .where(AnnotationLayer.slide_id == slide_id)
                        .order_by(AnnotationLayer.sort_order, AnnotationLayer.created_at)
                    ),
                )
            ),
            "limits": {
                "activeAnnotations": MAX_ACTIVE_ANNOTATIONS,
                "layers": MAX_LAYERS_PER_SLIDE,
                "verticesPerShape": MAX_VERTICES_PER_SHAPE,
                "verticesPerImport": MAX_VERTICES_PER_IMPORT,
                "batchOperations": MAX_BATCH_OPERATIONS,
            },
        }

    app.add_api_route(
        "/api/v2/admin/annotations/slides/{slide_id}/manifest",
        manifest,
        methods=["GET"],
        response_model=AnnotationManifest,
    )

    def create_layer(
        slide_id: str,
        payload: LayerMutationRequest,
        authenticated: Any = Depends(csrf_dependency),
        _: None = Depends(require_enabled),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        started = perf_counter()
        slide = get_slide(database, slide_id)
        try:
            slide = lock_annotation_mutation(
                database,
                slide,
                payload.base_version,
            )
        except AnnotationError as error:
            raise annotation_error(error) from error
        layer_count = int(
            database.scalar(
                select(func.count(AnnotationLayer.id)).where(
                    AnnotationLayer.slide_id == slide_id
                )
            )
            or 0
        )
        if layer_count >= MAX_LAYERS_PER_SLIDE:
            database.rollback()
            raise HTTPException(
                status_code=422,
                detail={"code": "ANNOTATION_LAYER_LIMIT"},
            )
        now = datetime.now(UTC).replace(tzinfo=None)
        purged = purge_expired_tombstones(database, now)
        layer = AnnotationLayer(
            slide_id=slide_id,
            name=payload.name,
            sort_order=payload.sort_order,
            visible=payload.visible,
            locked=payload.locked,
            opacity=payload.opacity,
            created_at=now,
            updated_at=now,
        )
        slide.annotation_version += 1
        database.add(layer)
        database.add(
            AuditEvent(
                actor_user_id=authenticated.user_id,
                action="annotation.layer.create",
                target_id=slide_id,
                detail={
                    "mutationId": str(payload.mutation_id),
                    "operationCount": 1,
                    "durationMs": round((perf_counter() - started) * 1000, 3),
                    "result": "success",
                    "version": slide.annotation_version,
                    "purged": purged,
                },
            )
        )
        database.commit()
        database.refresh(layer)
        return layer_json(layer)

    app.add_api_route(
        "/api/v2/admin/annotations/slides/{slide_id}/layers",
        create_layer,
        methods=["POST"],
        status_code=201,
    )

    def list_layers(
        slide_id: str,
        _: Any = Depends(admin_dependency),
        __: None = Depends(require_enabled),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        get_slide(database, slide_id)
        layers = database.scalars(
            select(AnnotationLayer)
            .where(AnnotationLayer.slide_id == slide_id)
            .order_by(AnnotationLayer.sort_order, AnnotationLayer.created_at)
        )
        return {"items": [layer_json(layer) for layer in layers]}

    app.add_api_route(
        "/api/v2/admin/annotations/slides/{slide_id}/layers",
        list_layers,
        methods=["GET"],
    )

    def update_layer(
        slide_id: str,
        layer_id: str,
        payload: LayerUpdateRequest,
        authenticated: Any = Depends(csrf_dependency),
        _: None = Depends(require_enabled),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        started = perf_counter()
        slide = get_slide(database, slide_id)
        try:
            slide = lock_annotation_mutation(
                database,
                slide,
                payload.base_version,
            )
        except AnnotationError as error:
            raise annotation_error(error) from error
        layer = database.get(AnnotationLayer, layer_id)
        if layer is None or layer.slide_id != slide_id:
            database.rollback()
            raise HTTPException(
                status_code=404,
                detail={"code": "ANNOTATION_LAYER_NOT_FOUND"},
            )
        if payload.name is not None:
            layer.name = payload.name
        if payload.sort_order is not None:
            layer.sort_order = payload.sort_order
        if payload.visible is not None:
            layer.visible = payload.visible
        if payload.locked is not None:
            layer.locked = payload.locked
        if payload.opacity is not None:
            layer.opacity = payload.opacity
        now = datetime.now(UTC).replace(tzinfo=None)
        purged = purge_expired_tombstones(database, now)
        layer.updated_at = now
        slide.annotation_version += 1
        database.add(
            AuditEvent(
                actor_user_id=authenticated.user_id,
                action="annotation.layer.update",
                target_id=slide_id,
                detail={
                    "mutationId": str(payload.mutation_id),
                    "operationCount": 1,
                    "durationMs": round((perf_counter() - started) * 1000, 3),
                    "result": "success",
                    "version": slide.annotation_version,
                    "purged": purged,
                },
            )
        )
        database.commit()
        return {
            "version": slide.annotation_version,
            "layer": layer_json(layer),
        }

    app.add_api_route(
        "/api/v2/admin/annotations/slides/{slide_id}/layers/{layer_id}",
        update_layer,
        methods=["PATCH"],
    )

    def delete_layer(
        slide_id: str,
        layer_id: str,
        payload: VersionedMutationRequest,
        authenticated: Any = Depends(csrf_dependency),
        _: None = Depends(require_enabled),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        started = perf_counter()
        slide = get_slide(database, slide_id)
        try:
            slide = lock_annotation_mutation(
                database,
                slide,
                payload.base_version,
            )
        except AnnotationError as error:
            raise annotation_error(error) from error
        layer = database.get(AnnotationLayer, layer_id)
        if layer is None or layer.slide_id != slide_id:
            database.rollback()
            raise HTTPException(
                status_code=404,
                detail={"code": "ANNOTATION_LAYER_NOT_FOUND"},
            )
        if database.scalar(
            select(Annotation.id).where(Annotation.layer_id == layer_id).limit(1)
        ):
            database.rollback()
            raise HTTPException(
                status_code=409,
                detail={"code": "ANNOTATION_LAYER_NOT_EMPTY"},
            )
        purged = purge_expired_tombstones(
            database,
            datetime.now(UTC).replace(tzinfo=None),
        )
        database.delete(layer)
        slide.annotation_version += 1
        database.add(
            AuditEvent(
                actor_user_id=authenticated.user_id,
                action="annotation.layer.delete",
                target_id=slide_id,
                detail={
                    "mutationId": str(payload.mutation_id),
                    "operationCount": 1,
                    "durationMs": round((perf_counter() - started) * 1000, 3),
                    "result": "success",
                    "version": slide.annotation_version,
                    "purged": purged,
                },
            )
        )
        database.commit()
        return {"version": slide.annotation_version}

    app.add_api_route(
        "/api/v2/admin/annotations/slides/{slide_id}/layers/{layer_id}",
        delete_layer,
        methods=["DELETE"],
    )

    def list_items(
        slide_id: str,
        include_deleted: bool = Query(default=False, alias="includeDeleted"),
        layer_id: str | None = Query(default=None, alias="layerId"),
        min_x: float | None = Query(default=None, alias="minX"),
        min_y: float | None = Query(default=None, alias="minY"),
        max_x: float | None = Query(default=None, alias="maxX"),
        max_y: float | None = Query(default=None, alias="maxY"),
        limit: int = Query(default=1_000, ge=1, le=5_000),
        offset: int = Query(default=0, ge=0),
        _: Any = Depends(admin_dependency),
        __: None = Depends(require_enabled),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        slide = get_slide(database, slide_id)
        statement = select(Annotation).where(Annotation.slide_id == slide_id)
        count_statement = select(func.count(Annotation.id)).where(
            Annotation.slide_id == slide_id
        )
        if not include_deleted:
            statement = statement.where(Annotation.deleted_at.is_(None))
            count_statement = count_statement.where(Annotation.deleted_at.is_(None))
        if layer_id is not None:
            statement = statement.where(Annotation.layer_id == layer_id)
            count_statement = count_statement.where(Annotation.layer_id == layer_id)
        bounds = (min_x, min_y, max_x, max_y)
        if any(value is not None for value in bounds):
            if any(value is None for value in bounds):
                raise HTTPException(
                    status_code=422,
                    detail={"code": "ANNOTATION_INVALID_VIEWPORT"},
                )
            assert min_x is not None
            assert min_y is not None
            assert max_x is not None
            assert max_y is not None
            predicates = (
                Annotation.bbox_max_x >= min_x,
                Annotation.bbox_max_y >= min_y,
                Annotation.bbox_min_x <= max_x,
                Annotation.bbox_min_y <= max_y,
            )
            statement = statement.where(*predicates)
            count_statement = count_statement.where(*predicates)
        total = int(database.scalar(count_statement) or 0)
        page = list(
            database.scalars(
                statement.order_by(Annotation.created_at, Annotation.id)
                .offset(offset)
                .limit(limit)
            )
        )
        next_offset = offset + len(page) if offset + len(page) < total else None
        return {
            "items": [annotation_json(annotation, slide) for annotation in page],
            "total": total,
            "nextOffset": next_offset,
        }

    app.add_api_route(
        "/api/v2/admin/annotations/slides/{slide_id}/items",
        list_items,
        methods=["GET"],
        response_model=AnnotationItemsPage,
    )

    def batch(
        slide_id: str,
        payload: AnnotationBatchRequest,
        authenticated: Any = Depends(csrf_dependency),
        _: None = Depends(require_enabled),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        slide = get_slide(database, slide_id)
        try:
            return apply_batch(
                database,
                slide,
                payload,
                actor_user_id=authenticated.user_id,
            )
        except AnnotationError as error:
            database.rollback()
            raise annotation_error(error) from error

    app.add_api_route(
        "/api/v2/admin/annotations/slides/{slide_id}/batch",
        batch,
        methods=["POST"],
        response_model=AnnotationBatchResult,
    )

    def import_items(
        slide_id: str,
        payload: AnnotationImportRequest,
        authenticated: Any = Depends(csrf_dependency),
        _: None = Depends(require_enabled),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        slide = get_slide(database, slide_id)
        try:
            return import_annotations(
                database,
                slide,
                payload,
                actor_user_id=authenticated.user_id,
            )
        except AnnotationError as error:
            database.rollback()
            raise annotation_error(error) from error

    app.add_api_route(
        "/api/v2/admin/annotations/slides/{slide_id}/import",
        import_items,
        methods=["POST"],
    )

    def export_items(
        slide_id: str,
        format: Literal["pathlab", "geojson", "csv"] = Query(default="pathlab"),
        _: Any = Depends(admin_dependency),
        __: None = Depends(require_enabled),
        database: OrmSession = Depends(database_dependency),
    ) -> Response:
        slide = get_slide(database, slide_id)
        try:
            if format == "pathlab":
                return JSONResponse(
                    content=export_pathlab(database, slide),
                    headers={
                        "Content-Disposition": (
                            f'attachment; filename="{slide.id}-annotations.pathlab.json"'
                        )
                    },
                )
            if format == "geojson":
                return JSONResponse(
                    content=export_geojson(database, slide),
                    media_type="application/geo+json",
                    headers={
                        "Content-Disposition": (
                            f'attachment; filename="{slide.id}-annotations.geojson"'
                        )
                    },
                )
            return Response(
                content=export_csv(database, slide),
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="{slide.id}-annotation-measurements.csv"'
                    )
                },
            )
        except AnnotationError as error:
            raise annotation_error(error) from error

    app.add_api_route(
        "/api/v2/admin/annotations/slides/{slide_id}/export",
        export_items,
        methods=["GET"],
    )

    def item_revisions(
        slide_id: str,
        annotation_id: str,
        _: Any = Depends(admin_dependency),
        __: None = Depends(require_enabled),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        get_slide(database, slide_id)
        annotation = database.get(Annotation, annotation_id)
        if annotation is None or annotation.slide_id != slide_id:
            raise HTTPException(
                status_code=404,
                detail={"code": "ANNOTATION_NOT_FOUND"},
            )
        revisions = database.scalars(
            select(AnnotationRevision)
            .where(AnnotationRevision.annotation_id == annotation_id)
            .order_by(
                AnnotationRevision.version.desc(),
                AnnotationRevision.created_at.desc(),
            )
        )
        return {"items": [revision_json(revision) for revision in revisions]}

    app.add_api_route(
        "/api/v2/admin/annotations/slides/{slide_id}/items/{annotation_id}/revisions",
        item_revisions,
        methods=["GET"],
    )

    def restore_item(
        slide_id: str,
        annotation_id: str,
        payload: ItemMutationRequest,
        authenticated: Any = Depends(csrf_dependency),
        _: None = Depends(require_enabled),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        slide = get_slide(database, slide_id)
        try:
            try:
                item_id = UUID(annotation_id)
            except ValueError as error:
                raise AnnotationError(
                    "ANNOTATION_NOT_FOUND",
                    status_code=404,
                ) from error
            request = AnnotationBatchRequest(
                mutationId=payload.mutation_id,
                baseVersion=payload.base_version,
                operations=[
                    RestoreOperation(
                        type="restore",
                        id=item_id,
                        version=payload.version,
                    )
                ],
            )
            result = apply_batch(
                database,
                slide,
                request,
                actor_user_id=authenticated.user_id,
            )
            restored = database.get(Annotation, annotation_id)
            assert restored is not None
            return {
                "version": result["version"],
                "item": annotation_json(restored, slide),
                "purged": result["purged"],
            }
        except AnnotationError as error:
            database.rollback()
            raise annotation_error(error) from error

    app.add_api_route(
        "/api/v2/admin/annotations/slides/{slide_id}/items/{annotation_id}/restore",
        restore_item,
        methods=["POST"],
    )

    def restore_item_revision(
        slide_id: str,
        annotation_id: str,
        revision_id: str,
        payload: ItemMutationRequest,
        authenticated: Any = Depends(csrf_dependency),
        _: None = Depends(require_enabled),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        slide = get_slide(database, slide_id)
        annotation = database.get(Annotation, annotation_id)
        revision = database.get(AnnotationRevision, revision_id)
        if annotation is None or annotation.slide_id != slide_id:
            raise HTTPException(
                status_code=404,
                detail={"code": "ANNOTATION_NOT_FOUND"},
            )
        if revision is None or revision.annotation_id != annotation_id:
            raise HTTPException(
                status_code=404,
                detail={"code": "ANNOTATION_REVISION_NOT_FOUND"},
            )
        try:
            return restore_revision(
                database,
                slide,
                annotation,
                revision,
                payload,
                actor_user_id=authenticated.user_id,
            )
        except AnnotationError as error:
            database.rollback()
            raise annotation_error(error) from error

    app.add_api_route(
        "/api/v2/admin/annotations/slides/{slide_id}/items/{annotation_id}"
        "/revisions/{revision_id}/restore",
        restore_item_revision,
        methods=["POST"],
    )
