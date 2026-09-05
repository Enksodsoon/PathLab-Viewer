import hashlib
import hmac
import os
import re
import shutil
import sqlite3
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.orm import Session as OrmSession

from .admission import SharedAdmission
from .annotation_routes import register_annotation_routes
from .auth import (
    CredentialConflict,
    InvalidCurrentPassword,
    InvalidRecoveryCode,
    PasswordReuse,
    RecoveryThrottled,
    authenticate_and_create_session,
    change_password,
    recover_password,
)
from .classroom_hub import ClassroomHub
from .classroom_routes import CLASSROOM_RETRY_AFTER_SECONDS, register_classroom_routes
from .classroom_runtime import ClassroomSingletonLock
from .config import Settings
from .database import session_factory
from .delivery import deliver_file
from .desktop_routes import register_desktop_routes
from .domain import InvalidTransition, SlideState, transition
from .identity import is_default_legacy_owner
from .identity_routes import register_identity_routes
from .library_routes import register_library_routes
from .models import (
    AuditEvent,
    Job,
    PublicationGrant,
    Session,
    Slide,
    User,
)
from .ome_tiles import MemoryTileCache, OmeTileRenderer
from .publication import (
    INDIVIDUAL,
    delete_all_slide_grants,
    delivery_version,
    ensure_grant,
)
from .readiness import CachedReadiness, tile_service_is_ready
from .request_limits import AuthBodyLimitMiddleware
from .runtime_protection import read_protection_snapshot
from .security import (
    MAX_VERIFICATION_PASSWORD_LENGTH,
    InvalidToken,
    UploadGrant,
    issue_upload_token,
    random_token,
    verify_upload_token,
)
from .sharing import detach_slide_from_shares, write_share_delivery_manifest
from .storage import (
    InsufficientStorage,
    PublicationError,
    StorageLayout,
)
from .storage_accounting import reserve_new_slide, reserve_retry
from .study_pack_contract import MAX_PACK_BYTES
from .study_routes import register_study_routes
from .tile_cache import TileCache
from .tile_routes import TileRouteService, authorize_tile, private_static_target
from .time_support import as_utc, utc_now

COOKIE_NAME = "pathlab_session"
MAX_AUTH_BODY_BYTES = 4096
MAX_LIBRARY_BODY_BYTES = 64 * 1024
MAX_INTERNAL_BODY_BYTES = 64 * 1024
MAX_ANNOTATION_BODY_BYTES = 256 * 1024
MAX_ANNOTATION_IMPORT_BODY_BYTES = 8 * 1024 * 1024


def _is_sqlite_busy_or_locked(error: SQLAlchemyOperationalError) -> bool:
    original = error.orig
    if not isinstance(original, sqlite3.OperationalError):
        return False
    error_code = getattr(original, "sqlite_errorcode", None)
    if isinstance(error_code, int):
        return error_code & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
    message = str(original).casefold()
    return any(
        marker in message
        for marker in ("database is busy", "database is locked", "database table is locked")
    )


def _is_classroom_api_path(path: str) -> bool:
    return (
        path == "/api/v1/classroom"
        or path.startswith("/api/v1/classroom/")
        or path == "/api/v1/admin/classroom"
        or path.startswith("/api/v1/admin/classroom/")
    )


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=MAX_VERIFICATION_PASSWORD_LENGTH)


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    current_password: str = Field(
        alias="currentPassword", min_length=1, max_length=MAX_VERIFICATION_PASSWORD_LENGTH
    )
    new_password: str = Field(alias="newPassword", min_length=1, max_length=128)


class PasswordRecoveryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    username: str = Field(min_length=1, max_length=100)
    recovery_code: str = Field(alias="recoveryCode", min_length=1, max_length=256)
    new_password: str = Field(alias="newPassword", min_length=1, max_length=128)


class SlideRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    display_name: str = Field(alias="displayName", min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=500)
    length: int = Field(gt=0)
    folder_id: str | None = Field(default=None, alias="folderId")


class PublishRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    deidentified_confirmed: bool = Field(alias="deidentifiedConfirmed")


class UploadCompleteRequest(BaseModel):
    token: str
    path: Path
    length: int = Field(gt=0)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _public_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    allowed = ("width", "height", "physicalSizeX")
    return {key: metadata[key] for key in allowed if metadata.get(key) is not None}


def _slide_json(
    slide: Slide,
    *,
    public: bool = False,
    annotations_enabled: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": slide.id,
        "publicId": slide.public_id,
        "displayName": slide.display_name,
        "state": slide.state.value,
        "sourceBytes": slide.source_bytes,
        "errorCode": slide.error_code,
        "errorMessage": slide.error_message,
        "metadata": slide.slide_metadata,
        "createdAt": slide.created_at.isoformat(),
    }
    if public:
        result.pop("id")
        result.pop("sourceBytes")
        result.pop("errorCode")
        result.pop("errorMessage")
        result.pop("createdAt")
        result["metadata"] = _public_metadata(slide.slide_metadata)
        delivery_root = (
            f"/api/v1/public/slides/{slide.public_id}/tiles"
            if slide.render_mode == "ome_dynamic"
            else f"/tiles/{slide.public_id}/{delivery_version(slide)}"
        )
        result["tileSource"] = f"{delivery_root}/slide.dzi"
        if slide.thumbnail_filename or slide.render_mode == "ome_dynamic":
            result["thumbnailUrl"] = (
                f"{delivery_root}/{slide.thumbnail_filename or 'thumbnail.jpg'}"
            )
    else:
        result["filename"] = slide.original_filename
        result["folderId"] = slide.folder_id
        result["renderMode"] = slide.render_mode
        result["annotationsEnabled"] = annotations_enabled
        result["annotationVersion"] = slide.annotation_version
    return result


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or Settings()
    serves_general = current.service_role in {"general", "all"}
    serves_classroom = current.service_role in {"classroom", "all"}
    classroom_runtime_enabled = current.classroom_enabled and serves_classroom
    current.data_root.mkdir(parents=True, exist_ok=True)
    factory = session_factory(current)
    storage = StorageLayout(current.data_root, current.storage_cap_bytes)
    throttle = SharedAdmission(factory)
    services: dict[str, Any] = {}
    classroom_pressure: dict[str, int | float] = {
        "poolWaitP95Ms": 0.0,
        "poolTimeouts": 0,
        "sqliteLockErrors": 0,
    }
    classroom_pool_waits_ms: deque[float] = deque(maxlen=2048)
    classroom_lock = ClassroomSingletonLock(current.data_root / "runtime" / "classroom-hub.lock")
    classroom_hub = ClassroomHub()
    readiness = CachedReadiness()
    services["classroom_ready"] = not classroom_runtime_enabled

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        finalizer = services.get("desktop_finalizer")
        finalizer_started = False
        tile_route_service: TileRouteService | None = None
        if serves_general:
            if current.internal_file_redirects:
                tile_route_service = TileRouteService(
                    storage,
                    None,
                    internal_redirects=True,
                )
            else:
                cache_root = current.tile_cache_root
                if not cache_root.is_absolute():
                    cache_root = current.data_root / "cache" / "ome-tiles"
                tile_route_service = TileRouteService(
                    storage,
                    OmeTileRenderer(
                        TileCache(
                            cache_root,
                            max_bytes=current.tile_cache_max_bytes,
                            low_water_bytes=current.tile_cache_low_water_bytes,
                            max_temp_bytes=current.tile_cache_max_temp_bytes,
                        ),
                        memory_cache=MemoryTileCache(current.tile_cache_memory_bytes),
                        render_concurrency=current.tile_render_concurrency,
                    ),
                )
            services["tile_routes"] = tile_route_service
        schema_ready = readiness.validate_startup(factory)
        if serves_general and finalizer is not None and schema_ready:
            finalizer.start()
            finalizer_started = True
        study_purger = services.get("study_purger")
        if serves_general and study_purger is not None and schema_ready:
            study_purger.start()
        classroom_lock_held = False
        if classroom_runtime_enabled:
            classroom_lock_held = classroom_lock.acquire()
            services["classroom_ready"] = classroom_lock_held
            if classroom_lock_held:
                classroom_hub.start()
                classroom_presenter = services.get("classroom_presenter")
                if classroom_presenter is not None:
                    await classroom_presenter.start()
        try:
            yield
        finally:
            if finalizer is not None and finalizer_started:
                finalizer.close()
            if study_purger is not None and schema_ready:
                await study_purger.close()
            services.pop("tile_routes", None)
            if tile_route_service is not None:
                tile_route_service.close()
            if classroom_lock_held:
                classroom_presenter = services.get("classroom_presenter")
                if classroom_presenter is not None:
                    await classroom_presenter.close()
                classroom_hub.close()
                classroom_lock.release()
            services["classroom_ready"] = not classroom_runtime_enabled

    app = FastAPI(title="PathLab Viewer API", version="0.1.0", lifespan=lifespan)
    app.state.shared_admission = throttle
    app.add_middleware(
        AuthBodyLimitMiddleware,
        path_limits=(
            ("/api/v2/admin/annotations/", MAX_ANNOTATION_BODY_BYTES),
            ("/api/v2/admin/", MAX_LIBRARY_BODY_BYTES),
            ("/api/v1/internal/", MAX_INTERNAL_BODY_BYTES),
            ("/api/v1/auth/", MAX_AUTH_BODY_BYTES),
            ("/api/v1/desktop/pairings", MAX_AUTH_BODY_BYTES),
            ("/api/v1/desktop/", MAX_LIBRARY_BODY_BYTES),
            ("/api/v2/desktop/", MAX_LIBRARY_BODY_BYTES),
            ("/api/v1/admin/study/packs", MAX_PACK_BYTES),
            ("/api/v1/admin/", MAX_LIBRARY_BODY_BYTES),
            ("/api/v1/classroom/", MAX_LIBRARY_BODY_BYTES),
            ("/api/v1/study/", MAX_LIBRARY_BODY_BYTES),
        ),
        suffix_limits=(
            (
                "/api/v2/admin/annotations/",
                "/import",
                MAX_ANNOTATION_IMPORT_BODY_BYTES,
            ),
            ("/api/v1/desktop/slides/", "/annotations/batch", MAX_ANNOTATION_BODY_BYTES),
        ),
        excluded_routes=(
            ("PATCH", r"/api/v1/desktop/ingests/[^/]+/content"),
            ("PATCH", r"/api/v2/desktop/slides/[^/]+/result-deliveries/[^/]+/content"),
        ),
    )
    app.state.settings = current

    @app.middleware("http")
    async def require_classroom_singleton(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        is_classroom_path = _is_classroom_api_path(path)
        if current.service_role == "general" and is_classroom_path:
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        if current.service_role == "classroom" and not (
            is_classroom_path or path in {"/livez", "/readyz"}
        ):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        if (
            classroom_runtime_enabled
            and is_classroom_path
            and not services.get("classroom_ready", False)
        ):
            return JSONResponse(
                status_code=503,
                content={"detail": {"code": "CLASSROOM_SINGLETON_NOT_READY"}},
                headers={"Cache-Control": "no-store"},
            )
        try:
            response = await call_next(request)
        except SQLAlchemyTimeoutError:
            if not is_classroom_path:
                raise
            classroom_pressure["poolTimeouts"] = int(classroom_pressure["poolTimeouts"]) + 1
            return JSONResponse(
                status_code=503,
                content={"detail": {"code": "CLASSROOM_BUSY"}},
                headers={
                    "Cache-Control": "no-store",
                    "Retry-After": CLASSROOM_RETRY_AFTER_SECONDS,
                },
            )
        except SQLAlchemyOperationalError as error:
            if not is_classroom_path or not _is_sqlite_busy_or_locked(error):
                raise
            classroom_pressure["sqliteLockErrors"] = int(classroom_pressure["sqliteLockErrors"]) + 1
            return JSONResponse(
                status_code=503,
                content={"detail": {"code": "CLASSROOM_BUSY"}},
                headers={
                    "Cache-Control": "no-store",
                    "Retry-After": CLASSROOM_RETRY_AFTER_SECONDS,
                },
            )
        if is_classroom_path:
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def tile_routes() -> TileRouteService:
        service = services.get("tile_routes")
        if not isinstance(service, TileRouteService):
            raise HTTPException(status_code=503, detail={"code": "TILE_SERVICE_UNAVAILABLE"})
        return service

    def database() -> Iterator[OrmSession]:
        with factory() as session:
            yield session

    def classroom_database() -> Iterator[OrmSession]:
        with factory() as session:
            started = time.monotonic()
            session.connection()
            classroom_pool_waits_ms.append((time.monotonic() - started) * 1000)
            ordered = sorted(classroom_pool_waits_ms)
            index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95)))
            classroom_pressure["poolWaitP95Ms"] = round(ordered[index], 3)
            yield session

    Database = Annotated[OrmSession, Depends(database)]

    def authenticated_session(
        db: Database, pathlab_session: Annotated[str | None, Cookie()] = None
    ) -> Session:
        if not pathlab_session:
            raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED"})
        stored = db.get(Session, _token_hash(pathlab_session))
        if stored is None or as_utc(stored.expires_at) < utc_now():
            raise HTTPException(status_code=401, detail={"code": "SESSION_EXPIRED"})
        user = db.get(User, stored.user_id)
        if user is None or stored.credential_generation != user.credential_generation:
            raise HTTPException(status_code=401, detail={"code": "SESSION_EXPIRED"})
        return stored

    AuthenticatedSession = Annotated[Session, Depends(authenticated_session)]

    def csrf(
        authenticated: AuthenticatedSession,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Session:
        if not csrf_token or not hmac.compare_digest(authenticated.csrf_token, csrf_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
        return authenticated

    CsrfSession = Annotated[Session, Depends(csrf)]

    def legacy_admin_session(
        authenticated: AuthenticatedSession,
        db: Database,
    ) -> Session:
        if not is_default_legacy_owner(db, authenticated.user_id):
            raise HTTPException(status_code=403, detail={"code": "LEGACY_ADMIN_FORBIDDEN"})
        return authenticated

    LegacyAdminSession = Annotated[Session, Depends(legacy_admin_session)]

    def legacy_csrf(
        authenticated: LegacyAdminSession,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Session:
        if not csrf_token or not hmac.compare_digest(authenticated.csrf_token, csrf_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
        return authenticated

    LegacyCsrfSession = Annotated[Session, Depends(legacy_csrf)]

    async def bounded_json(request: Request) -> Any:
        body = await request.body()
        if len(body) > MAX_AUTH_BODY_BYTES:
            raise HTTPException(status_code=413, detail={"code": "REQUEST_TOO_LARGE"})
        return await request.json()

    async def password_change_payload(request: Request, _: CsrfSession) -> PasswordChangeRequest:
        try:
            return PasswordChangeRequest.model_validate(await bounded_json(request))
        except ValidationError as error:
            if error.errors() and all(
                item.get("loc", ())[-1:] == ("currentPassword",) for item in error.errors()
            ):
                raise HTTPException(
                    status_code=400, detail={"code": "CURRENT_PASSWORD_INVALID"}
                ) from error
            raise HTTPException(status_code=400, detail={"code": "INVALID_PASSWORD"}) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail={"code": "INVALID_PASSWORD"}) from error

    PasswordChangePayload = Annotated[PasswordChangeRequest, Depends(password_change_payload)]

    async def password_recovery_payload(request: Request) -> PasswordRecoveryRequest:
        try:
            return PasswordRecoveryRequest.model_validate(await bounded_json(request))
        except HTTPException:
            raise
        except ValidationError as error:
            if error.errors() and all(
                item.get("loc", ())[-1:] == ("newPassword",) for item in error.errors()
            ):
                raise HTTPException(status_code=400, detail={"code": "INVALID_PASSWORD"}) from error
            raise HTTPException(
                status_code=400, detail={"code": "INVALID_RECOVERY_CODE"}
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=400, detail={"code": "INVALID_RECOVERY_CODE"}
            ) from error

    PasswordRecoveryPayload = Annotated[PasswordRecoveryRequest, Depends(password_recovery_payload)]

    if serves_general:
        register_identity_routes(
            app,
            database_dependency=database,
            admin_dependency=authenticated_session,
            csrf_dependency=csrf,
            enabled=current.identity_governance_enabled,
        )
        register_library_routes(
            app,
            factory=factory,
            storage=storage,
            database_dependency=database,
            admin_dependency=legacy_admin_session,
            csrf_dependency=legacy_csrf,
            tile_routes=tile_routes,
        )
        register_annotation_routes(
            app,
            database_dependency=database,
            admin_dependency=legacy_admin_session,
            csrf_dependency=legacy_csrf,
        )
        services["desktop_finalizer"] = register_desktop_routes(
            app,
            database_dependency=database,
            csrf_dependency=legacy_csrf,
            storage=storage,
            tile_routes=tile_routes,
            ome_dynamic_enabled=current.desktop_ome_dynamic_enabled,
            max_upload_bytes=current.max_upload_bytes,
        )
        services["study_purger"] = register_study_routes(
            app,
            factory=factory,
            storage=storage,
            database_dependency=database,
            admin_dependency=legacy_admin_session,
            csrf_dependency=legacy_csrf,
            enabled=current.study_mode_enabled,
            ai_enabled=current.study_coach_ai_enabled,
            pilot_enabled=current.study_coach_ai_pilot_enabled,
            csrf_secret=current.secret_key,
            max_learners=current.study_max_learners,
            secure_cookies=current.secure_cookies,
            internal_file_redirects=current.internal_file_redirects,
        )
    if serves_classroom:
        services["classroom_presenter"] = register_classroom_routes(
            app,
            settings=current,
            storage=storage,
            factory=factory,
            hub=classroom_hub,
            database_dependency=classroom_database,
            admin_dependency=legacy_admin_session,
            csrf_dependency=legacy_csrf,
            pressure_metrics=classroom_pressure,
        )

    @app.get("/livez")
    def livez() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        if not readiness.database_is_ready(factory):
            raise HTTPException(status_code=503, detail={"code": "DATABASE_NOT_READY"})
        if (
            serves_general
            and current.internal_file_redirects
            and not tile_service_is_ready(current.tile_service_url)
        ):
            raise HTTPException(
                status_code=503,
                detail={"code": "TILE_SERVICE_NOT_READY"},
            )
        if classroom_runtime_enabled and not services.get("classroom_ready", False):
            raise HTTPException(
                status_code=503,
                detail={"code": "CLASSROOM_SINGLETON_NOT_READY"},
            )
        return {"status": "ready"}

    @app.post("/api/v1/auth/session", status_code=status.HTTP_201_CREATED)
    def login(
        payload: LoginRequest, request: Request, response: Response, db: Database
    ) -> dict[str, str]:
        key = request.client.host if request.client else "unknown"
        user_key = f"user:{payload.username.strip().casefold()}"
        now = datetime.now(UTC)
        throttle.check("login", key, now, user_key)
        token = random_token()
        csrf_token = random_token()
        expires = now + timedelta(hours=current.session_hours)
        authenticated = authenticate_and_create_session(
            db,
            payload.username,
            payload.password,
            _token_hash(token),
            csrf_token,
            expires,
            now,
        )
        if not authenticated:
            raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS"})
        throttle.clear("login", key, now, user_key)
        response.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            secure=current.secure_cookies,
            samesite="strict",
            max_age=current.session_hours * 3600,
            path="/",
        )
        return {"csrfToken": csrf_token}

    @app.get("/api/v1/auth/session")
    def refresh_session(authenticated: AuthenticatedSession, response: Response) -> dict[str, str]:
        response.headers["Cache-Control"] = "no-store"
        return {"csrfToken": authenticated.csrf_token}

    @app.delete("/api/v1/auth/session", status_code=status.HTTP_204_NO_CONTENT)
    def logout(authenticated: CsrfSession, response: Response, db: Database) -> None:
        db.delete(authenticated)
        db.commit()
        response.delete_cookie(COOKIE_NAME, path="/")

    @app.post(
        "/api/v1/auth/password",
        status_code=status.HTTP_204_NO_CONTENT,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": PasswordChangeRequest.model_json_schema(by_alias=True)
                    }
                },
            }
        },
    )
    def update_password(
        payload: PasswordChangePayload,
        authenticated: CsrfSession,
        request: Request,
        response: Response,
        db: Database,
    ) -> None:
        user = db.get(User, authenticated.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED"})
        key = f"password:{user.id}:{request.client.host if request.client else 'unknown'}"
        now = datetime.now(UTC)
        throttle.check("password", key, now)
        try:
            change_password(db, user, payload.current_password, payload.new_password)
        except CredentialConflict as error:
            raise HTTPException(status_code=401, detail={"code": "SESSION_EXPIRED"}) from error
        except PasswordReuse as error:
            raise HTTPException(status_code=400, detail={"code": "PASSWORD_REUSE"}) from error
        except InvalidCurrentPassword as error:
            raise HTTPException(
                status_code=400, detail={"code": "CURRENT_PASSWORD_INVALID"}
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail={"code": "INVALID_PASSWORD"}) from error
        throttle.clear("password", key, now)
        response.delete_cookie(COOKIE_NAME, path="/")

    @app.post(
        "/api/v1/auth/password/recover",
        status_code=status.HTTP_204_NO_CONTENT,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": PasswordRecoveryRequest.model_json_schema(by_alias=True)
                    }
                },
            }
        },
    )
    def recover_admin_password(
        payload: PasswordRecoveryPayload,
        request: Request,
        response: Response,
        db: Database,
    ) -> None:
        try:
            recover_password(
                db,
                payload.username,
                payload.recovery_code,
                payload.new_password,
                request.client.host if request.client else "unknown",
            )
        except RecoveryThrottled as error:
            raise HTTPException(status_code=429, detail={"code": "AUTH_THROTTLED"}) from error
        except (InvalidRecoveryCode, CredentialConflict) as error:
            raise HTTPException(
                status_code=400, detail={"code": "INVALID_RECOVERY_CODE"}
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail={"code": "INVALID_PASSWORD"}) from error
        response.delete_cookie(COOKIE_NAME, path="/")

    @app.get("/api/v1/admin/slides")
    def list_slides(_: LegacyAdminSession, db: Database) -> list[dict[str, Any]]:
        slides = db.scalars(select(Slide).order_by(Slide.created_at.desc())).all()
        return [
            _slide_json(slide, annotations_enabled=current.admin_annotations_enabled)
            for slide in slides
        ]

    @app.get("/api/v1/admin/slides/{slide_id}")
    def get_admin_slide(slide_id: str, _: LegacyAdminSession, db: Database) -> dict[str, Any]:
        slide = db.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        result = _slide_json(slide, annotations_enabled=current.admin_annotations_enabled)
        if slide.state in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}:
            result["tileSource"] = f"/api/v1/admin/slides/{slide.id}/preview/slide.dzi"
            if slide.thumbnail_filename or slide.render_mode == "ome_dynamic":
                result["thumbnailUrl"] = (
                    f"/api/v1/admin/slides/{slide.id}/preview/"
                    f"{slide.thumbnail_filename or 'thumbnail.jpg'}"
                )
        return result

    @app.get("/api/v1/admin/slides/{slide_id}/preview/{tile_path:path}")
    def private_tile(
        slide_id: str, tile_path: str, _: LegacyAdminSession, db: Database
    ) -> Response:
        slide = db.get(Slide, slide_id)
        if (
            slide is None
            or slide.trashed_at is not None
            or slide.state not in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}
        ):
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        authorized = authorize_tile(
            slide_id=slide.id,
            slide_sha256=slide.sha256,
            render_mode=slide.render_mode,
            relative_path=tile_path,
            cache_control="private, max-age=86400, immutable",
        )
        if authorized.render_mode == "ome_dynamic":
            return tile_routes().dynamic_response(authorized)
        target = private_static_target(storage, slide.id, tile_path)
        media_type = "application/xml" if target.suffix.lower() == ".dzi" else "image/jpeg"
        return deliver_file(
            target,
            data_root=current.data_root,
            internal_redirects=current.internal_file_redirects,
            media_type=media_type,
            cache_control="private, max-age=86400, immutable",
        )

    @app.post("/api/v1/admin/slides", status_code=status.HTTP_201_CREATED)
    def create_slide(payload: SlideRequest, authenticated: LegacyCsrfSession) -> dict[str, Any]:
        if payload.length > current.max_upload_bytes:
            raise HTTPException(status_code=413, detail={"code": "UPLOAD_TOO_LARGE"})
        try:
            slide = reserve_new_slide(
                factory,
                storage,
                display_name=payload.display_name,
                original_filename=Path(payload.filename).name,
                source_bytes=payload.length,
                actor_user_id=authenticated.user_id,
                folder_id=payload.folder_id,
            )
        except InsufficientStorage as error:
            raise HTTPException(status_code=507, detail={"code": "INSUFFICIENT_STORAGE"}) from error
        except LookupError as error:
            raise HTTPException(status_code=404, detail={"code": "FOLDER_NOT_FOUND"}) from error
        token = issue_upload_token(
            UploadGrant(slide.id, payload.length), current.secret_key, ttl=timedelta(hours=1)
        )
        return {
            "slide": _slide_json(slide, annotations_enabled=current.admin_annotations_enabled),
            "uploadUrl": current.tus_public_url,
            "uploadToken": token,
            "expiresIn": 3600,
        }

    def finalize_upload(
        grant: UploadGrant, upload_path: Path, reported_length: int, db: OrmSession
    ) -> dict[str, str]:
        upload_root = current.tus_internal_upload_dir.resolve()
        upload_id = upload_path.name
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", upload_id) is None:
            raise HTTPException(status_code=400, detail={"code": "INVALID_UPLOAD_PATH"})
        try:
            source = (upload_root / upload_id).resolve(strict=True)
        except OSError as error:
            raise HTTPException(status_code=400, detail={"code": "INVALID_UPLOAD_PATH"}) from error
        if source.parent != upload_root or not source.is_file():
            raise HTTPException(status_code=400, detail={"code": "INVALID_UPLOAD_PATH"})
        slide = db.get(Slide, grant.slide_id)
        if slide is None or slide.state is not SlideState.UPLOADING:
            raise HTTPException(status_code=409, detail={"code": "INVALID_STATE"})
        actual_length = source.stat().st_size
        if reported_length != grant.length or actual_length != grant.length:
            raise HTTPException(status_code=400, detail={"code": "UPLOAD_LENGTH_MISMATCH"})
        with source.open("rb") as uploaded:
            signature = uploaded.read(4)
        if signature not in {b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"}:
            raise HTTPException(status_code=400, detail={"code": "INVALID_TIFF_SIGNATURE"})
        destination = storage.for_slide(slide.id).original
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".partial")
        try:
            os.replace(source, temporary)
        except OSError:
            shutil.copy2(source, temporary)
            source.unlink()
        temporary.replace(destination)
        slide.state = transition(slide.state, SlideState.QUEUED)
        db.add(Job(slide_id=slide.id))
        db.add(AuditEvent(action="upload.complete", target_id=slide.id))
        db.commit()
        return {"slideId": slide.id, "state": slide.state.value}

    @app.post("/api/v1/internal/uploads/complete", status_code=status.HTTP_202_ACCEPTED)
    def upload_complete(payload: UploadCompleteRequest, db: Database) -> dict[str, str]:
        try:
            grant = verify_upload_token(payload.token, current.secret_key)
        except InvalidToken as error:
            raise HTTPException(status_code=401, detail={"code": "INVALID_UPLOAD_TOKEN"}) from error
        return finalize_upload(grant, payload.path, payload.length, db)

    @app.get("/api/v1/internal/uploads/admission", status_code=status.HTTP_204_NO_CONTENT)
    def upload_admission(db: Database) -> Response:
        if current.classroom_protection_enabled:
            snapshot = read_protection_snapshot(db)
            if snapshot.blocks_background_work:
                raise HTTPException(
                    status_code=423,
                    detail={"code": "CLASSROOM_PROTECTION_ACTIVE", "mode": snapshot.mode},
                    headers={"Retry-After": "120"},
                )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/v1/internal/tus/hooks")
    def tus_hook(payload: dict[str, Any], db: Database) -> dict[str, Any]:
        try:
            hook_type = str(payload["Type"])
            upload = payload["Event"]["Upload"]
            metadata = upload["MetaData"]
            token = str(metadata["uploadToken"])
            size = int(upload["Size"])
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail={"code": "INVALID_TUS_HOOK"}) from error
        if hook_type == "pre-create":
            if current.classroom_protection_enabled:
                snapshot = read_protection_snapshot(db)
                if snapshot.blocks_background_work:
                    return {
                        "RejectUpload": True,
                        "HTTPResponse": {
                            "StatusCode": 423,
                            "Body": '{"code":"CLASSROOM_PROTECTION_ACTIVE"}',
                            "Header": {
                                "Content-Type": "application/json",
                                "Retry-After": "120",
                            },
                        },
                    }
            try:
                grant = verify_upload_token(token, current.secret_key)
                slide = db.get(Slide, grant.slide_id)
                if slide is None or slide.state is not SlideState.UPLOADING or size != grant.length:
                    raise InvalidToken("Upload reservation does not match")
            except InvalidToken:
                return {
                    "RejectUpload": True,
                    "HTTPResponse": {
                        "StatusCode": 401,
                        "Body": '{"code":"INVALID_UPLOAD_TOKEN"}',
                        "Header": {"Content-Type": "application/json"},
                    },
                }
            return {"RejectUpload": False, "ChangeFileInfo": {"ID": grant.slide_id}}
        if hook_type == "post-finish":
            try:
                grant = verify_upload_token(token, current.secret_key, allow_expired=True)
                storage_path = Path(str(upload["Storage"]["Path"]))
                finalize_upload(grant, storage_path, size, db)
            except (InvalidToken, KeyError, HTTPException) as error:
                raise HTTPException(
                    status_code=500, detail={"code": "TUS_FINALIZE_FAILED"}
                ) from error
        return {}

    def mutate(slide_id: str, target: SlideState, authenticated: Session, db: OrmSession) -> Slide:
        slide = db.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        try:
            slide.state = transition(slide.state, target)
        except InvalidTransition as error:
            raise HTTPException(status_code=409, detail={"code": "INVALID_STATE"}) from error
        if target is SlideState.PUBLISHED:
            slide.published_at = datetime.now(UTC)
        elif slide.state is SlideState.READY_PRIVATE:
            slide.published_at = None
        db.add(
            AuditEvent(
                actor_user_id=authenticated.user_id,
                action=f"slide.{target.value}",
                target_id=slide.id,
            )
        )
        db.commit()
        return slide

    @app.post("/api/v1/admin/slides/{slide_id}/retry")
    def retry(slide_id: str, authenticated: LegacyCsrfSession) -> dict[str, Any]:
        try:
            slide = reserve_retry(
                factory,
                storage,
                slide_id=slide_id,
                actor_user_id=authenticated.user_id,
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"}) from error
        except InvalidTransition as error:
            raise HTTPException(status_code=409, detail={"code": "INVALID_STATE"}) from error
        except InsufficientStorage as error:
            raise HTTPException(status_code=507, detail={"code": "INSUFFICIENT_STORAGE"}) from error
        return _slide_json(slide, annotations_enabled=current.admin_annotations_enabled)

    @app.post("/api/v1/admin/slides/{slide_id}/publish")
    def publish(
        slide_id: str,
        authenticated: LegacyCsrfSession,
        db: Database,
        payload: PublishRequest | None = None,
    ) -> dict[str, Any]:
        if payload is None or not payload.deidentified_confirmed:
            raise HTTPException(
                status_code=422,
                detail={"code": "DEIDENTIFICATION_CONFIRMATION_REQUIRED"},
            )
        slide = db.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        slide.privacy_status = "passed"
        slide.privacy_scanned_at = utc_now()
        try:
            ensure_grant(db, storage, slide, INDIVIDUAL, slide.id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=409, detail={"code": "DERIVATIVE_NOT_READY"}) from error
        except PublicationError as error:
            raise HTTPException(status_code=409, detail={"code": "PUBLICATION_FAILED"}) from error
        db.add(
            AuditEvent(
                actor_user_id=authenticated.user_id,
                action="slide.published",
                target_id=slide.id,
            )
        )
        db.commit()
        return _slide_json(slide, annotations_enabled=current.admin_annotations_enabled)

    @app.post("/api/v1/admin/slides/{slide_id}/unpublish")
    def unpublish(slide_id: str, authenticated: LegacyCsrfSession, db: Database) -> dict[str, Any]:
        slide = db.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        share_updates = detach_slide_from_shares(db, storage, slide)
        delete_all_slide_grants(db, storage, slide)
        if slide.state == SlideState.PUBLISHED:
            slide.state = SlideState.READY_PRIVATE
        db.add(
            AuditEvent(
                actor_user_id=authenticated.user_id,
                action="slide.unpublished",
                target_id=slide.id,
            )
        )
        db.commit()
        for share, slides in share_updates:
            write_share_delivery_manifest(storage, share, slides)
        return _slide_json(slide, annotations_enabled=current.admin_annotations_enabled)

    @app.delete("/api/v1/admin/slides/{slide_id}", status_code=status.HTTP_202_ACCEPTED)
    def delete(slide_id: str, authenticated: LegacyCsrfSession, db: Database) -> dict[str, Any]:
        slide = db.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        delete_all_slide_grants(db, storage, slide)
        if slide.render_mode == "ome_dynamic":
            tile_routes().purge_slide(slide.sha256)
        slide = mutate(slide_id, SlideState.DELETING, authenticated, db)
        db.add(Job(slide_id=slide.id, kind="delete"))
        db.commit()
        return _slide_json(slide, annotations_enabled=current.admin_annotations_enabled)

    @app.get("/api/v1/public/slides/{public_id}")
    def public_slide(public_id: str, db: Database) -> dict[str, Any]:
        slide = db.scalar(
            select(Slide).where(
                Slide.public_id == public_id,
                Slide.state == SlideState.PUBLISHED,
                Slide.trashed_at.is_(None),
                Slide.privacy_status == "passed",
                select(PublicationGrant.id)
                .where(
                    PublicationGrant.slide_id == Slide.id,
                    PublicationGrant.source_type == INDIVIDUAL,
                    PublicationGrant.source_id == Slide.id,
                )
                .exists(),
            )
        )
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        return _slide_json(slide, public=True)

    @app.get("/api/v1/public/slides/{public_id}/tiles/{tile_path:path}")
    def public_slide_tile(public_id: str, tile_path: str, db: Database) -> Response:
        slide = db.scalar(
            select(Slide).where(
                Slide.public_id == public_id,
                Slide.state == SlideState.PUBLISHED,
                Slide.trashed_at.is_(None),
                Slide.privacy_status == "passed",
                select(PublicationGrant.id)
                .where(
                    PublicationGrant.slide_id == Slide.id,
                    PublicationGrant.source_type == INDIVIDUAL,
                    PublicationGrant.source_id == Slide.id,
                )
                .exists(),
            )
        )
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        authorized = authorize_tile(
            slide_id=slide.id,
            slide_sha256=slide.sha256,
            render_mode=slide.render_mode,
            relative_path=tile_path,
            cache_control="private, max-age=86400, immutable",
        )
        if authorized.render_mode == "ome_dynamic":
            return tile_routes().dynamic_response(authorized)
        try:
            target = storage.public_tile(slide.public_id, tile_path)
        except (FileNotFoundError, ValueError):
            raise HTTPException(status_code=404, detail={"code": "TILE_NOT_FOUND"}) from None
        media_type = "application/xml" if target.suffix.lower() == ".dzi" else "image/jpeg"
        return deliver_file(
            target,
            data_root=current.data_root,
            internal_redirects=current.internal_file_redirects,
            media_type=media_type,
            cache_control="private, max-age=86400, immutable",
        )

    if current.service_role == "classroom":
        app.router.routes[:] = [
            route
            for route in app.router.routes
            if (path := getattr(route, "path", "")) in {"/livez", "/readyz"}
            or _is_classroom_api_path(path)
        ]

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("wsi_viewer.main:app", host="0.0.0.0", port=8000)
