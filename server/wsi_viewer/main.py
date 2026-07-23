import hashlib
import hmac
import mimetypes
import os
import shutil
from collections import defaultdict, deque
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

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
from .config import Settings
from .database import session_factory
from .domain import InvalidTransition, SlideState, transition
from .library_routes import register_library_routes
from .models import AuditEvent, Job, Session, Slide, User
from .publication import (
    INDIVIDUAL,
    delete_all_slide_grants,
    ensure_grant,
    remove_grant,
)
from .readiness import schema_is_current
from .request_limits import AuthBodyLimitMiddleware
from .security import (
    MAX_VERIFICATION_PASSWORD_LENGTH,
    InvalidToken,
    UploadGrant,
    issue_upload_token,
    random_token,
    verify_upload_token,
)
from .storage import (
    InsufficientStorage,
    PublicationError,
    StorageLayout,
)
from .storage_accounting import reserve_new_slide, reserve_retry

COOKIE_NAME = "pathlab_session"
MAX_AUTH_BODY_BYTES = 4096
MAX_LIBRARY_BODY_BYTES = 64 * 1024


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


class LoginThrottle:
    def __init__(self) -> None:
        self.attempts: dict[str, deque[datetime]] = defaultdict(deque)

    def check(self, key: str, now: datetime) -> None:
        cutoff = now - timedelta(minutes=5)
        attempts = self.attempts[key]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if len(attempts) >= 5:
            raise HTTPException(status_code=429, detail={"code": "AUTH_THROTTLED"})
        attempts.append(now)

    def clear(self, key: str) -> None:
        self.attempts.pop(key, None)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _public_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    allowed = ("width", "height", "physicalSizeX")
    return {key: metadata[key] for key in allowed if metadata.get(key) is not None}


def _slide_json(slide: Slide, *, public: bool = False) -> dict[str, Any]:
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
        result["metadata"] = _public_metadata(slide.slide_metadata)
        result["tileSource"] = f"/tiles/{slide.public_id}/slide.dzi"
    else:
        result["filename"] = slide.original_filename
    return result


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or Settings()
    current.data_root.mkdir(parents=True, exist_ok=True)
    factory = session_factory(current)
    storage = StorageLayout(current.data_root, current.storage_cap_bytes)
    throttle = LoginThrottle()
    app = FastAPI(title="PathLab Viewer API", version="0.1.0")
    app.add_middleware(AuthBodyLimitMiddleware, max_bytes=MAX_AUTH_BODY_BYTES)
    app.add_middleware(
        AuthBodyLimitMiddleware,
        max_bytes=MAX_LIBRARY_BODY_BYTES,
        path_prefixes=("/api/v2/admin/",),
    )
    app.state.settings = current
    if current.serve_public_tiles:
        mimetypes.add_type("application/xml", ".dzi")
        public_tiles = current.data_root / "public"
        public_tiles.mkdir(parents=True, exist_ok=True)
        app.mount("/tiles", StaticFiles(directory=public_tiles), name="development-tiles")

    def database() -> Iterator[OrmSession]:
        with factory() as session:
            yield session

    Database = Annotated[OrmSession, Depends(database)]

    def admin_session(
        db: Database, pathlab_session: Annotated[str | None, Cookie()] = None
    ) -> Session:
        if not pathlab_session:
            raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED"})
        stored = db.get(Session, _token_hash(pathlab_session))
        if stored is None or stored.expires_at < datetime.now(UTC).replace(tzinfo=None):
            raise HTTPException(status_code=401, detail={"code": "SESSION_EXPIRED"})
        user = db.get(User, stored.user_id)
        if user is None or stored.credential_generation != user.credential_generation:
            raise HTTPException(status_code=401, detail={"code": "SESSION_EXPIRED"})
        return stored

    AdminSession = Annotated[Session, Depends(admin_session)]

    def csrf(
        authenticated: AdminSession,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Session:
        if not csrf_token or not hmac.compare_digest(authenticated.csrf_token, csrf_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
        return authenticated

    CsrfSession = Annotated[Session, Depends(csrf)]

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

    register_library_routes(
        app,
        factory=factory,
        storage=storage,
        database_dependency=database,
        admin_dependency=admin_session,
        csrf_dependency=csrf,
    )

    @app.get("/livez")
    def livez() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/readyz")
    def readyz(db: Database) -> dict[str, str]:
        if not schema_is_current(db):
            raise HTTPException(status_code=503, detail={"code": "DATABASE_NOT_READY"})
        return {"status": "ready"}

    @app.post("/api/v1/auth/session", status_code=status.HTTP_201_CREATED)
    def login(
        payload: LoginRequest, request: Request, response: Response, db: Database
    ) -> dict[str, str]:
        key = request.client.host if request.client else "unknown"
        now = datetime.now(UTC)
        throttle.check(key, now)
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
        throttle.clear(key)
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
        throttle.check(key, datetime.now(UTC))
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
        throttle.clear(key)
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
    def list_slides(_: AdminSession, db: Database) -> list[dict[str, Any]]:
        slides = db.scalars(select(Slide).order_by(Slide.created_at.desc())).all()
        return [_slide_json(slide) for slide in slides]

    @app.get("/api/v1/admin/slides/{slide_id}")
    def get_admin_slide(slide_id: str, _: AdminSession, db: Database) -> dict[str, Any]:
        slide = db.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        result = _slide_json(slide)
        if slide.state in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}:
            result["tileSource"] = f"/api/v1/admin/slides/{slide.id}/preview/slide.dzi"
        return result

    @app.get("/api/v1/admin/slides/{slide_id}/preview/{tile_path:path}")
    def private_tile(slide_id: str, tile_path: str, _: AdminSession, db: Database) -> FileResponse:
        slide = db.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        root = storage.for_slide(slide.id).private_derivative.resolve()
        target = (root / tile_path).resolve()
        if not target.is_relative_to(root) or target.suffix.lower() not in {
            ".dzi",
            ".jpg",
            ".jpeg",
        }:
            raise HTTPException(status_code=404, detail={"code": "TILE_NOT_FOUND"})
        if not target.is_file():
            raise HTTPException(status_code=404, detail={"code": "TILE_NOT_FOUND"})
        media_type = "application/xml" if target.suffix.lower() == ".dzi" else "image/jpeg"
        return FileResponse(target, media_type=media_type)

    @app.post("/api/v1/admin/slides", status_code=status.HTTP_201_CREATED)
    def create_slide(payload: SlideRequest, authenticated: CsrfSession) -> dict[str, Any]:
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
            "slide": _slide_json(slide),
            "uploadUrl": current.tus_public_url,
            "uploadToken": token,
            "expiresIn": 3600,
        }

    def finalize_upload(
        grant: UploadGrant, upload_path: Path, reported_length: int, db: OrmSession
    ) -> dict[str, str]:
        source = upload_path.resolve()
        upload_root = current.tus_internal_upload_dir.resolve()
        if not source.is_relative_to(upload_root) and upload_path.as_posix().startswith(
            "/data/tus/"
        ):
            source = (upload_root / upload_path.name).resolve()
        if not source.is_relative_to(upload_root) or not source.is_file():
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
    def retry(slide_id: str, authenticated: CsrfSession) -> dict[str, Any]:
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
        return _slide_json(slide)

    @app.post("/api/v1/admin/slides/{slide_id}/publish")
    def publish(
        slide_id: str,
        authenticated: CsrfSession,
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
        slide.privacy_scanned_at = datetime.now(UTC).replace(tzinfo=None)
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
        return _slide_json(slide)

    @app.post("/api/v1/admin/slides/{slide_id}/unpublish")
    def unpublish(slide_id: str, authenticated: CsrfSession, db: Database) -> dict[str, Any]:
        slide = db.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        remove_grant(db, storage, slide, INDIVIDUAL, slide.id)
        db.add(
            AuditEvent(
                actor_user_id=authenticated.user_id,
                action="slide.unpublished",
                target_id=slide.id,
            )
        )
        db.commit()
        return _slide_json(slide)

    @app.delete("/api/v1/admin/slides/{slide_id}", status_code=status.HTTP_202_ACCEPTED)
    def delete(slide_id: str, authenticated: CsrfSession, db: Database) -> dict[str, Any]:
        slide = db.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        delete_all_slide_grants(db, storage, slide)
        slide = mutate(slide_id, SlideState.DELETING, authenticated, db)
        db.add(Job(slide_id=slide.id, kind="delete"))
        db.commit()
        return _slide_json(slide)

    @app.get("/api/v1/public/slides/{public_id}")
    def public_slide(public_id: str, db: Database) -> dict[str, Any]:
        slide = db.scalar(
            select(Slide).where(
                Slide.public_id == public_id,
                Slide.state == SlideState.PUBLISHED,
                Slide.privacy_status == "passed",
            )
        )
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        return _slide_json(slide, public=True)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("wsi_viewer.main:app", host="0.0.0.0", port=8000)
