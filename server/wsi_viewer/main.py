import hashlib
import hmac
import os
import shutil
from collections import defaultdict, deque
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session as OrmSession

from .config import Settings
from .database import create_schema, session_factory
from .domain import InvalidTransition, SlideState, transition
from .models import AuditEvent, Job, Session, Slide, User
from .security import (
    InvalidToken,
    UploadGrant,
    issue_upload_token,
    random_token,
    verify_password,
    verify_upload_token,
)
from .storage import (
    InsufficientStorage,
    StorageLayout,
    publish_derivative,
    unpublish_derivative,
)

COOKIE_NAME = "pathlab_session"


class LoginRequest(BaseModel):
    username: str
    password: str


class SlideRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    display_name: str = Field(alias="displayName", min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=500)
    length: int = Field(gt=0)


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
        result["tileSource"] = f"/tiles/{slide.public_id}/slide.dzi"
    else:
        result["filename"] = slide.original_filename
    return result


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or Settings()
    current.data_root.mkdir(parents=True, exist_ok=True)
    create_schema(current)
    factory = session_factory(current)
    storage = StorageLayout(current.data_root, current.storage_cap_bytes)
    throttle = LoginThrottle()
    app = FastAPI(title="PathLab Viewer API", version="0.1.0")
    app.state.settings = current

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

    @app.get("/livez")
    def livez() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/readyz")
    def readyz(db: Database) -> dict[str, str]:
        db.execute(text("SELECT 1"))
        current.data_root.mkdir(parents=True, exist_ok=True)
        return {"status": "ready"}

    @app.post("/api/v1/auth/session", status_code=status.HTTP_201_CREATED)
    def login(
        payload: LoginRequest, request: Request, response: Response, db: Database
    ) -> dict[str, str]:
        key = request.client.host if request.client else "unknown"
        now = datetime.now(UTC)
        throttle.check(key, now)
        user = db.scalar(select(User).where(User.username == payload.username))
        if user is None or not verify_password(user.password_hash, payload.password):
            raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS"})
        throttle.clear(key)
        token = random_token()
        csrf_token = random_token()
        expires = now + timedelta(hours=current.session_hours)
        db.add(
            Session(
                id=_token_hash(token), user_id=user.id, csrf_token=csrf_token, expires_at=expires
            )
        )
        db.add(AuditEvent(actor_user_id=user.id, action="auth.login"))
        db.commit()
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

    @app.get("/api/v1/admin/slides")
    def list_slides(_: AdminSession, db: Database) -> list[dict[str, Any]]:
        slides = db.scalars(select(Slide).order_by(Slide.created_at.desc())).all()
        return [_slide_json(slide) for slide in slides]

    @app.post("/api/v1/admin/slides", status_code=status.HTTP_201_CREATED)
    def create_slide(
        payload: SlideRequest, authenticated: CsrfSession, db: Database
    ) -> dict[str, Any]:
        if payload.length > current.max_upload_bytes:
            raise HTTPException(status_code=413, detail={"code": "UPLOAD_TOO_LARGE"})
        try:
            storage.require_admission(payload.length)
        except InsufficientStorage as error:
            raise HTTPException(status_code=507, detail={"code": "INSUFFICIENT_STORAGE"}) from error
        slide = Slide(
            display_name=payload.display_name,
            original_filename=Path(payload.filename).name,
            source_bytes=payload.length,
        )
        db.add(slide)
        db.flush()
        token = issue_upload_token(
            UploadGrant(slide.id, payload.length), current.secret_key, ttl=timedelta(hours=1)
        )
        db.add(
            AuditEvent(
                actor_user_id=authenticated.user_id,
                action="slide.create",
                target_id=slide.id,
                detail={"bytes": payload.length},
            )
        )
        db.commit()
        return {
            "slide": _slide_json(slide),
            "uploadUrl": current.tus_public_url,
            "uploadToken": token,
            "expiresIn": 3600,
        }

    @app.post("/api/v1/internal/uploads/complete", status_code=status.HTTP_202_ACCEPTED)
    def upload_complete(payload: UploadCompleteRequest, db: Database) -> dict[str, str]:
        try:
            grant = verify_upload_token(payload.token, current.secret_key)
        except InvalidToken as error:
            raise HTTPException(status_code=401, detail={"code": "INVALID_UPLOAD_TOKEN"}) from error
        source = payload.path.resolve()
        upload_root = current.tus_internal_upload_dir.resolve()
        if not source.is_relative_to(upload_root) or not source.is_file():
            raise HTTPException(status_code=400, detail={"code": "INVALID_UPLOAD_PATH"})
        slide = db.get(Slide, grant.slide_id)
        if slide is None or slide.state is not SlideState.UPLOADING:
            raise HTTPException(status_code=409, detail={"code": "INVALID_STATE"})
        actual_length = source.stat().st_size
        if payload.length != grant.length or actual_length != grant.length:
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
    def retry(slide_id: str, authenticated: CsrfSession, db: Database) -> dict[str, Any]:
        slide = mutate(slide_id, SlideState.QUEUED, authenticated, db)
        slide.error_code = None
        slide.error_message = None
        db.add(Job(slide_id=slide.id))
        db.commit()
        return _slide_json(slide)

    @app.post("/api/v1/admin/slides/{slide_id}/publish")
    def publish(slide_id: str, authenticated: CsrfSession, db: Database) -> dict[str, Any]:
        slide = db.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        try:
            publish_derivative(storage, slide.id, slide.public_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=409, detail={"code": "DERIVATIVE_NOT_READY"}) from error
        return _slide_json(mutate(slide_id, SlideState.PUBLISHED, authenticated, db))

    @app.post("/api/v1/admin/slides/{slide_id}/unpublish")
    def unpublish(slide_id: str, authenticated: CsrfSession, db: Database) -> dict[str, Any]:
        slide = db.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        unpublish_derivative(storage, slide.public_id)
        return _slide_json(mutate(slide_id, SlideState.READY_PRIVATE, authenticated, db))

    @app.delete("/api/v1/admin/slides/{slide_id}", status_code=status.HTTP_202_ACCEPTED)
    def delete(slide_id: str, authenticated: CsrfSession, db: Database) -> dict[str, Any]:
        return _slide_json(mutate(slide_id, SlideState.DELETING, authenticated, db))

    @app.get("/api/v1/public/slides/{public_id}")
    def public_slide(public_id: str, db: Database) -> dict[str, Any]:
        slide = db.scalar(
            select(Slide).where(Slide.public_id == public_id, Slide.state == SlideState.PUBLISHED)
        )
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        return _slide_json(slide, public=True)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("wsi_viewer.main:app", host="0.0.0.0", port=8000)
